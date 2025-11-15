from dataclasses import dataclass, asdict, fields
from typing import Optional, Dict, Any, List, Tuple
import numpy as np
import pandas as pd

try:
    from statsmodels.tsa.seasonal import STL
except ImportError:
    STL = None

try:
    import ruptures as rpt
except ImportError:
    rpt = None


@dataclass
class DetectorProfileV2:
    metric_kind: str
    direction: str
    regularity: str
    has_seasonality: bool
    noise_level: str
    window_short: int
    window_long: int
    smoothing_span: int
    use_stl: bool
    use_ruptures: bool
    z_stable_threshold: float
    z_strong_threshold: float


def profile_v2_from_dict(d: Dict[str, Any]) -> DetectorProfileV2:
    field_names = {f.name for f in fields(DetectorProfileV2)}
    clean = {k: v for k, v in d.items() if k in field_names}
    return DetectorProfileV2(**clean)


class UniversalTSDetectorV2:
    """
    Prod-grade universal time-series detector.

    - лог-трансформ для duration;
    - опциональное STL-десезонализирование;
    - относительное изменение short vs long;
    - robust z-score;
    - simple CUSUM;
    - опциональный ruptures для change points;
    - risk score.
    """

    def __init__(
        self,
        metric_kind: str = "duration",
        direction: str = "lower_is_better",
        use_stl: bool = True,
        use_ruptures: bool = True,
    ) -> None:
        self.metric_kind = metric_kind
        self.direction = direction
        self._use_stl = use_stl and (STL is not None)
        self._use_ruptures = use_ruptures and (rpt is not None)

    # ---------- utils ----------

    def _to_series(self, data) -> pd.Series:
        if isinstance(data, pd.Series):
            s = data.astype(float)
        elif isinstance(data, pd.DataFrame):
            if "value" not in data.columns:
                raise ValueError("DataFrame must contain 'value' column")
            s = data["value"].astype(float)
            if isinstance(data.index, pd.DatetimeIndex):
                s.index = data.index
        else:
            s = pd.Series(data, dtype=float)
        return s.dropna()

    def _diagnose_regularity(self, s: pd.Series) -> str:
        if isinstance(s.index, pd.DatetimeIndex):
            diffs = s.index.to_series().diff().dropna().dt.total_seconds()
        else:
            diffs = s.index.to_series().diff().dropna()
        if len(diffs) < 2:
            return "regular"
        ratio = diffs.std() / (diffs.mean() + 1e-9)
        return "regular" if ratio < 0.1 else "irregular"

    def _diagnose_noise_level(self, s: pd.Series) -> str:
        med = s.median()
        mad = (s - med).abs().median() + 1e-9
        z = (s - med).abs() / mad
        high = (z > 6).mean()
        med_frac = (z > 3).mean()
        if high > 0.05:
            return "high"
        elif med_frac > 0.05:
            return "medium"
        return "low"

    def _diagnose_seasonality(self, s: pd.Series) -> bool:
        N = len(s)
        if N < 200:
            return False
        max_lag = min(48, N // 2)
        s_norm = (s - s.mean()) / (s.std() + 1e-9)
        acfs = []
        for lag in [24, 12, 7]:
            if lag < max_lag:
                acfs.append(s_norm.autocorr(lag=lag))
        return bool(acfs) and max(acfs) > 0.5

    def _choose_windows(self, N: int) -> Tuple[int, int]:
        if N < 30:
            ws = max(5, N // 4)
            wl = max(10, N // 2)
        elif N < 200:
            ws = max(10, N // 10)
            wl = max(20, N // 4)
        else:
            ws = max(20, N // 20)
            wl = max(40, N // 8)
        return ws, wl

    def _log_transform_if_needed(self, s: pd.Series) -> pd.Series:
        if self.metric_kind == "duration":
            return np.log1p(s.clip(lower=1e-9))
        return s

    def _stl_deseasonalize(self, s: pd.Series) -> pd.Series:
        if not self._use_stl or STL is None:
            return s
        N = len(s)
        if N < 50:
            return s
        period = min(48, max(7, N // 10))
        try:
            res = STL(s, period=period, robust=True).fit()
            return res.trend + res.resid
        except Exception:
            return s

    def _build_profile_auto(self, s: pd.Series) -> DetectorProfileV2:
        s = self._log_transform_if_needed(s)
        regularity = self._diagnose_regularity(s)
        noise_level = self._diagnose_noise_level(s)
        has_seasonality = self._diagnose_seasonality(s)
        ws, wl = self._choose_windows(len(s))
        smoothing_span = max(2, ws // 2)
        return DetectorProfileV2(
            metric_kind=self.metric_kind,
            direction=self.direction,
            regularity=regularity,
            has_seasonality=has_seasonality,
            noise_level=noise_level,
            window_short=ws,
            window_long=wl,
            smoothing_span=smoothing_span,
            use_stl=self._use_stl and has_seasonality,
            use_ruptures=self._use_ruptures,
            z_stable_threshold=0.8,
            z_strong_threshold=2.5,
        )

    def _prepare_signal(self, s: pd.Series, profile: DetectorProfileV2) -> pd.Series:
        s_tr = self._log_transform_if_needed(s)
        if profile.use_stl:
            s_tr = self._stl_deseasonalize(s_tr)
        return s_tr

    def _rolling_stats(self, x: pd.Series, ws: int, wl: int):
        short = x.ewm(span=ws, adjust=False).mean()
        long = x.ewm(span=wl, adjust=False).mean()
        return short, long

    def _relative_diff_and_z(
        self,
        short: pd.Series,
        long: pd.Series,
        profile: DetectorProfileV2,
    ):
        eps = 1e-9
        rel = (short - long) / (long.abs() + eps)
        med = rel.median()
        mad = (rel - med).abs().median() + eps
        z = (rel - med) / mad
        return rel, z

    def _simple_cusum(self, z: pd.Series, k: float = 0.5):
        cpos = []
        cneg = []
        last_pos = 0.0
        last_neg = 0.0
        for zi in z:
            last_pos = max(0.0, last_pos + zi - k)
            last_neg = min(0.0, last_neg + zi + k)
            cpos.append(last_pos)
            cneg.append(last_neg)
        return pd.Series(cpos, index=z.index), pd.Series(cneg, index=z.index)

    def _ruptures_change_point(self, x: pd.Series):
        if not self._use_ruptures or rpt is None:
            return None
        if len(x) < 50:
            return None
        try:
            algo = rpt.Binseg(model="l2").fit(x.values)
            res = algo.predict(n_bkps=3)
            if len(res) <= 1:
                return None
            last_cp_idx = res[-2]
            return x.index[last_cp_idx]
        except Exception:
            return None

    def _state_from_z_and_sign(
        self,
        z_last: float,
        rel_last: float,
        profile: DetectorProfileV2,
    ) -> str:
        if profile.direction == "higher_is_better":
            physical_sign = np.sign(rel_last)
        else:
            physical_sign = -np.sign(rel_last)
        if abs(z_last) < profile.z_stable_threshold:
            return "stable"
        return "improvement" if physical_sign > 0 else "regression"

    def analyze(
        self,
        data,
        profile: Optional[DetectorProfileV2] = None,
        debug: bool = False,
    ) -> Dict[str, Any]:
        s_raw = self._to_series(data)
        if len(s_raw) < 10:
            raise ValueError("Too few points for prod analysis (N < 10).")
        if profile is None:
            profile = self._build_profile_auto(s_raw)
        x = self._prepare_signal(s_raw, profile)
        short, long = self._rolling_stats(x, profile.window_short, profile.window_long)
        rel, z = self._relative_diff_and_z(short, long, profile)
        z_last = float(z.iloc[-1])
        rel_last = float(rel.iloc[-1])
        state = self._state_from_z_and_sign(z_last, rel_last, profile)
        cpos, cneg = self._simple_cusum(z)
        change_point = self._ruptures_change_point(x)
        severity = float(min(1.0, abs(z_last) / profile.z_strong_threshold))
        confidence = float(0.5 + 0.5 * severity)
        risk = float(severity * confidence)
        detector_result: Dict[str, Any] = {
            "detector": "zscore_rel_cusum_v2",
            "state": state,
            "z_score": z_last,
            "rel_change": rel_last,
            "severity": severity,
            "confidence": confidence,
            "risk": risk,
            "change_point": change_point,
            "short_last": float(short.iloc[-1]),
            "long_last": float(long.iloc[-1]),
        }
        result: Dict[str, Any] = {
            "meta": {
                "metric_kind": profile.metric_kind,
                "direction": profile.direction,
                "n_points": len(s_raw),
            },
            "profile": asdict(profile),
            "detector_result": detector_result,
            "current_state": state,
            "current_point": s_raw.index[-1],
            "current_value": float(s_raw.iloc[-1]),
        }
        if debug:
            result["debug"] = {
                "raw_series": s_raw,
                "signal": x,
                "short": short,
                "long": long,
                "rel": rel,
                "z": z,
                "cusum_pos": cpos,
                "cusum_neg": cneg,
            }
        return result

    def analyze_many(
        self,
        df: pd.DataFrame,
        context_fields: List[str],
        value_field: str = "value",
        timestamp_field: str = "timestamp",
        meta_fields: Optional[List[str]] = None,
        profile: Optional[DetectorProfileV2] = None,
        debug: bool = False,
    ) -> Dict[Any, Dict[str, Any]]:
        df = df.copy()
        df[timestamp_field] = pd.to_datetime(df[timestamp_field])
        df = df.sort_values(timestamp_field)
        results: Dict[Any, Dict[str, Any]] = {}
        for ctx_vals, group in df.groupby(context_fields):
            if not isinstance(ctx_vals, tuple):
                ctx_vals = (ctx_vals,)
            s = pd.Series(
                group[value_field].astype(float).values,
                index=group[timestamp_field].values,
            )
            res = self.analyze(s, profile=profile, debug=debug)
            ctx_dict = dict(zip(context_fields, ctx_vals))
            res["context"] = ctx_dict
            if meta_fields:
                meta_df = group[meta_fields]
                res["meta_last"] = meta_df.iloc[-1].to_dict()
                if debug:
                    res.setdefault("debug", {})["meta"] = meta_df
            results[ctx_vals] = res
        return results
