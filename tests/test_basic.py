import pandas as pd
from detector import UniversalTSDetectorV2, AlertEngineV2


def make_df():
    data = {
        "timestamp": [
            "2024-10-05T10:00:00Z",
            "2024-10-05T11:00:00Z",
            "2024-10-05T12:00:00Z",
            "2024-10-05T13:00:00Z",
            "2024-10-05T14:00:00Z",
            "2024-10-05T15:00:00Z",
            "2024-10-05T16:00:00Z",
            "2024-10-05T17:00:00Z",
            "2024-10-05T18:00:00Z",
            "2024-10-05T19:00:00Z",
            "2024-10-05T20:00:00Z",
            "2024-10-05T21:00:00Z",
        ],
        "branch": ["main"] * 12,
        "build_type": ["release"] * 12,
        "testname": ["login"] * 12,
        "commit": ["a111"] * 6 + ["b222"] * 6,
        "value": [100, 105, 102, 103, 101, 104, 140, 150, 145, 148, 142, 147],
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
