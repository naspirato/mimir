from typing import Dict, Any, List


class AlertEngineV2:
    """Stateful alert engine with hysteresis on risk and persistence.

    state_store: dict-like mapping context_key_str -> {
      "last_state": str,
      "same_state_count": int,
      "last_change_point": any,
      "last_commit": str or None,
    }
    """

    def __init__(
        self,
        state_store: Dict[str, Any],
        min_risk_start: float = 0.6,
        min_risk_end: float = 0.2,
        min_persist_start: int = 2,
        min_persist_end: int = 2,
    ) -> None:
        self.state = state_store
        self.min_risk_start = min_risk_start
        self.min_risk_end = min_risk_end
        self.min_persist_start = min_persist_start
        self.min_persist_end = min_persist_end

    @staticmethod
    def _ctx_to_key(context) -> str:
        if isinstance(context, dict):
            items = sorted(context.items())
            return "|".join(f"{k}={v}" for k, v in items)
        return str(context)

    def process(self, context, result: Dict[str, Any]) -> List[Dict[str, Any]]:
        ctx_key = self._ctx_to_key(context)
        prev = self.state.get(ctx_key, {
            "last_state": "stable",
            "same_state_count": 0,
            "last_change_point": None,
            "last_commit": None,
        })
        prev_state = prev.get("last_state", "stable")
        prev_count = int(prev.get("same_state_count", 0))
        now_state = result.get("current_state", "stable")
        risk = float(result.get("detector_result", {}).get("risk", 0.0))
        commit = result.get("meta_last", {}).get("commit")
        change_point = result.get("detector_result", {}).get("change_point")
        current_point = result.get("current_point")

        if now_state == prev_state:
            same_state_count = prev_count + 1
        else:
            same_state_count = 1

        alerts: List[Dict[str, Any]] = []

        def emit_start_event():
            alerts.append({
                "type": "start",
                "state": now_state,
                "context": result.get("context", context),
                "started_at": change_point or current_point,
                "current_point": current_point,
                "current_commit": commit,
                "risk": risk,
            })

        def emit_end_event(end_state: str):
            alerts.append({
                "type": "end",
                "prev_state": end_state,
                "context": result.get("context", context),
                "ended_at": current_point,
                "current_commit": commit,
                "risk": risk,
            })

        if prev_state == "stable":
            if now_state in ("regression", "improvement"):
                if same_state_count >= self.min_persist_start and risk >= self.min_risk_start:
                    emit_start_event()
        elif prev_state in ("regression", "improvement"):
            if now_state == prev_state:
                # продолжающееся событие
                pass
            elif now_state == "stable":
                if same_state_count >= self.min_persist_end and risk <= self.min_risk_end:
                    emit_end_event(prev_state)
            else:
                # смена типа события (regression -> improvement или наоборот)
                if same_state_count >= self.min_persist_start and risk >= self.min_risk_start:
                    emit_end_event(prev_state)
                    emit_start_event()

        self.state[ctx_key] = {
            "last_state": now_state,
            "same_state_count": same_state_count,
            "last_change_point": change_point,
            "last_commit": commit,
        }
        return alerts
