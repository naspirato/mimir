import json
import os
import sys
import subprocess
from pathlib import Path

import pandas as pd
import yaml
import pytest


def write_tmp_csv(tmp_path: Path) -> Path:
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
    p = tmp_path / "src.csv"
    df.to_csv(p, index=False)
    return p


def write_cfg(tmp_path: Path, src_csv: Path) -> Path:
    cfg = {
        "version": 1,
        "dataset": {
            "adapter": "csv",
            "adapter_config": {"path": str(src_csv), "parse_dates": True},
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
    cfg_path = tmp_path / "cfg.yaml"
    with open(cfg_path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f)
    return cfg_path


def run_cli(*args: str, cwd: Path) -> subprocess.CompletedProcess:
    cmd = [sys.executable, "-m", "detector.cli", *args]
    return subprocess.run(cmd, cwd=str(cwd), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, check=True)


def test_cli_save_and_analyze(tmp_path: Path):
    # Arrange
    src = write_tmp_csv(tmp_path)
    cfg_path = write_cfg(tmp_path, src)
    out_csv = tmp_path / "dataset.csv"

    # Act: save_dataset
    cp1 = run_cli("save_dataset", "--config", str(cfg_path), "--path", str(out_csv), "--fmt", "csv", cwd=Path.cwd())
    assert out_csv.exists(), f"stdout={cp1.stdout}\nstderr={cp1.stderr}"

    # Act: analyze_many from saved
    cp2 = run_cli("analyze_many", "--config", str(cfg_path), "--dataset_path", str(out_csv), "--fmt", "csv", cwd=Path.cwd())
    assert "current_state" in cp2.stdout, f"stdout={cp2.stdout}\nstderr={cp2.stderr}"

    # Act: analyze_many live (no dataset_path)
    cp3 = run_cli("analyze_many", "--config", str(cfg_path), cwd=Path.cwd())
    assert "current_state" in cp3.stdout, f"stdout={cp3.stdout}\nstderr={cp3.stderr}"

def test_cli_save_jsonl_and_analyze_from_saved(tmp_path: Path, tmp_config_path: Path):
    out_jsonl = tmp_path / "dataset.jsonl"
    cp1 = run_cli(
        "save_dataset",
        "--config",
        str(tmp_config_path),
        "--path",
        str(out_jsonl),
        cwd=Path.cwd(),
    )
    assert out_jsonl.exists(), f"stdout={cp1.stdout}\nstderr={cp1.stderr}"

    cp2 = run_cli(
        "analyze_many",
        "--config",
        str(tmp_config_path),
        "--dataset_path",
        str(out_jsonl),
        cwd=Path.cwd(),
    )
    # stdout should be JSON
    data = json.loads(cp2.stdout)
    assert isinstance(data, dict)
    # At least one context result with required fields
    assert any("current_state" in v for v in data.values())

def test_cli_analyze_live_outputs_json(tmp_config_path: Path):
    cp = run_cli("analyze_many", "--config", str(tmp_config_path), cwd=Path.cwd())
    data = json.loads(cp.stdout)
    assert isinstance(data, dict)
    assert any("current_state" in v for v in data.values())

def test_cli_infers_format_by_extension(tmp_path: Path, tmp_config_path: Path):
    # Save as .jsonl without passing --fmt; CLI should infer jsonl
    out_jsonl = tmp_path / "auto.jsonl"
    cp1 = run_cli(
        "save_dataset",
        "--config",
        str(tmp_config_path),
        "--path",
        str(out_jsonl),
        cwd=Path.cwd(),
    )
    assert out_jsonl.exists(), f"stdout={cp1.stdout}\nstderr={cp1.stderr}"

    # Analyze without --fmt; should infer jsonl from extension
    cp2 = run_cli(
        "analyze_many",
        "--config",
        str(tmp_config_path),
        "--dataset_path",
        str(out_jsonl),
        cwd=Path.cwd(),
    )
    data = json.loads(cp2.stdout)
    assert isinstance(data, dict)
    assert any("current_state" in v for v in data.values())


