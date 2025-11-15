import json
import pandas as pd
from detector import UniversalTSDetectorV2, AlertEngineV2


def main():
    df = pd.read_csv("metrics_example.csv")

    # В реальном CI можно загрузить state_store из файла JSON
    state_store = {}

    detector = UniversalTSDetectorV2(
        metric_kind="duration",
        direction="lower_is_better",
    )

    results = detector.analyze_many(
        df,
        context_fields=["branch", "build_type", "testname"],
        meta_fields=["commit"],
        value_field="value",
        timestamp_field="timestamp",
        profile=None,
        debug=False,
    )

    engine = AlertEngineV2(state_store)
    all_alerts = []

    for ctx, res in results.items():
        alerts = engine.process(ctx, res)
        all_alerts.extend(alerts)

    print("Results:")
    for ctx, res in results.items():
        print(
            ctx,
            "->",
            res["current_state"],
            "value=",
            res["current_value"],
            "risk=",
            res["detector_result"]["risk"],
        )

    print("\nAlerts:")
    for a in all_alerts:
        print(a)

    print("\nUpdated state_store:")
    print(json.dumps(state_store, indent=2, default=str))


if __name__ == "__main__":
    main()
