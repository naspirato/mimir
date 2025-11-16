import os
from typing import Any, Dict
import pandas as pd
import yaml

from detector.config_schema import DataConfig
from detector.run_from_config import load_config, analyze_from_config
from detector.adapters import AdapterRegistry


def test_schema_parses_csv_example():
    cfg = load_config("configs/example_csv.yaml")
    assert isinstance(cfg, DataConfig)
    assert cfg.dataset.adapter == "csv"
    assert cfg.analysis.metrics.direction in ("lower_is_better", "higher_is_better")


def test_adapter_registry_mapping():
    cfg = load_config("configs/example_csv.yaml")
    inst = AdapterRegistry.create(cfg.dataset.adapter, cfg.dataset.adapter_config)
    # csv adapter should be creatable without errors
    assert inst is not None


def test_end_to_end_csv_tmp(tmp_path):
    # Create temp CSV with >= 12 rows to satisfy detector
    timestamps = pd.date_range("2024-01-01", periods=12, freq="h")
    df = pd.DataFrame(
        {
            "timestamp": timestamps,
            "branch": ["main"] * 12,
            "build_type": ["release"] * 12,
            "testname": ["login"] * 12,
            "commit": ["a"] * 6 + ["b"] * 6,
            "value": [100, 101, 102, 103, 104, 105, 140, 150, 145, 148, 142, 147],
        }
    )
    csv_path = tmp_path / "data.csv"
    df.to_csv(csv_path, index=False)

    cfg_dict: Dict[str, Any] = {
        "version": 1,
        "dataset": {
            "adapter": "csv",
            "adapter_config": {"path": str(csv_path), "parse_dates": True},
            "timestamp_field": "timestamp",
            "value_field": "value",
        },
        "analysis": {
            "context_fields": ["branch", "build_type", "testname"],
            "meta_fields": ["commit"],
            "metrics": {
                "name": "api_latency",
                "direction": "lower_is_better",
                "metric_kind": "duration",
                "auto_detect_metric_type": True,
            },
            "event_types": ["regression", "improvement"],
            "output": {"debug": False},
        },
    }
    cfg_path = tmp_path / "config.yaml"
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg_dict, f)

    cfg = load_config(str(cfg_path))
    results = analyze_from_config(cfg)
    # Single context key expected
    assert len(results) == 1
    ctx_key, res = list(results.items())[0]
    assert "current_state" in res
    assert "detector_result" in res

