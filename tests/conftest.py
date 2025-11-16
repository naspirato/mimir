import json
from pathlib import Path
from typing import Any, Dict, Tuple

import pandas as pd
import pytest
import yaml


@pytest.fixture
def tmp_dataset_df() -> pd.DataFrame:
    timestamps = pd.date_range("2024-01-01", periods=12, freq="h")
    return pd.DataFrame(
        {
            "timestamp": timestamps,
            "branch": ["main"] * 12,
            "build_type": ["release"] * 12,
            "testname": ["login"] * 12,
            "commit": ["a"] * 6 + ["b"] * 6,
            "value": [100, 101, 102, 103, 104, 105, 140, 150, 145, 148, 142, 147],
        }
    )


@pytest.fixture
def tmp_dataset_csv(tmp_path: Path, tmp_dataset_df: pd.DataFrame) -> Path:
    csv_path = tmp_path / "data.csv"
    tmp_dataset_df.to_csv(csv_path, index=False)
    return csv_path


def _make_cfg_dict(src_path: Path) -> Dict[str, Any]:
    return {
        "version": 1,
        "dataset": {
            "adapter": "csv",
            "adapter_config": {"path": str(src_path), "parse_dates": True},
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


@pytest.fixture
def tmp_config_path(tmp_path: Path, tmp_dataset_csv: Path) -> Path:
    cfg_dict = _make_cfg_dict(tmp_dataset_csv)
    cfg_path = tmp_path / "cfg.yaml"
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg_dict, f)
    return cfg_path


