import pandas as pd
from detector import UniversalTSDetectorV2, AlertEngineV2


def make_df():
    data = {
        "timestamp": [
            "2024-10-05T10:00:00Z",
            "2024-10-05T11:00:00Z",
            "2024-10-05T12:00:00Z",
            "2024-10-05T13:00:00Z",
        ],
        "branch": ["main"] * 4,
        "build_type": ["release"] * 4,
        "testname": ["login"] * 4,
        "commit": ["a111", "a111", "b222", "b222"],
        "value": [100, 105, 140, 150],
    }
    return pd.DataFrame(data)


def test_detector_runs():
    df = make_df()
    detector = UniversalTSDetectorV2(metric_kind="duration", direction="lower_is_better")
    res = detector.analyze_many(
        df,
        context_fields=["branch", "build_type", "testname"],
        meta_fields=["commit"],
        value_field="value",
        timestamp_field="timestamp",
        profile=None,
        debug=True,
    )
    assert len(res) == 1
    ctx, r = list(res.items())[0]
    assert "current_state" in r
    assert "detector_result" in r
    assert "risk" in r["detector_result"]


def test_alert_engine_v2():
    df = make_df()
    detector = UniversalTSDetectorV2(metric_kind="duration", direction="lower_is_better")
    results = detector.analyze_many(
        df,
        context_fields=["branch", "build_type", "testname"],
        meta_fields=["commit"],
        value_field="value",
        timestamp_field="timestamp",
        profile=None,
        debug=False,
    )
    state_store = {}
    engine = AlertEngineV2(state_store)
    alerts = []
    for ctx, r in results.items():
        alerts.extend(engine.process(ctx, r))
    assert isinstance(alerts, list)
    assert isinstance(state_store, dict)
