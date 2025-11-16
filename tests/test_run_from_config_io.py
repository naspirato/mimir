import os
from detector.run_from_config import load_config, fetch_dataset_to_file, analyze_from_saved
from pathlib import Path
from typing import Dict, Any
import pytest


def test_fetch_then_analyze_csv(tmp_path: Path, tmp_config_path: Path):
    cfg = load_config(str(tmp_config_path))

    saved_csv = tmp_path / "fetched.csv"
    out_path = fetch_dataset_to_file(cfg, str(saved_csv), fmt="csv")
    assert os.path.exists(out_path)

    results = analyze_from_saved(cfg, out_path, fmt="csv")
    assert isinstance(results, dict)
    assert len(results) == 1
    _, res = list(results.items())[0]
    assert "current_state" in res

