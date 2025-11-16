from __future__ import annotations

import os
from dataclasses import dataclass
from glob import glob
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import numpy as np

from detector.run_from_config import (
    load_config,
    fetch_dataset_to_file,
    analyze_from_config,
    analyze_from_saved,
)


@dataclass
class ConfigSummary:
    path: str
    name: str
    adapter: str
    timestamp_field: str
    value_field: str
    context_fields: List[str]
    meta_fields: List[str]
    debug: bool


def list_config_paths(configs_dir: str = "configs") -> List[str]:
    paths = sorted(glob(os.path.join(configs_dir, "*.yaml"))) + sorted(
        glob(os.path.join(configs_dir, "*.yml"))
    )
    return paths


def get_config_summary(path: str) -> ConfigSummary:
    cfg = load_config(path)
    return ConfigSummary(
        path=path,
        name=Path(path).stem,
        adapter=cfg.dataset.adapter,
        timestamp_field=cfg.dataset.timestamp_field,
        value_field=cfg.dataset.value_field,
        context_fields=list(cfg.analysis.context_fields or []),
        meta_fields=list(cfg.analysis.meta_fields or []),
        debug=bool(getattr(cfg.analysis.output, "debug", False)),
    )


def ensure_data_dirs(base_dir: str, cfg_stem: str) -> Dict[str, str]:
    root = Path(base_dir) / cfg_stem
    raw = root / "raw"
    processed = root / "processed"
    reports = root / "reports"
    for p in [raw, processed, reports]:
        p.mkdir(parents=True, exist_ok=True)
    return {"root": str(root), "raw": str(raw), "processed": str(processed), "reports": str(reports)}


def default_saved_dataset_path(dir_map: Dict[str, str], fmt: str = "csv") -> str:
    ext = "csv" if fmt == "csv" else "jsonl"
    return str(Path(dir_map["raw"]) / f"dataset.{ext}")


def fetch_dataset(config_path: str, output_path: str, fmt: Optional[str] = None) -> Tuple[str, int]:
    cfg = load_config(config_path)
    out = fetch_dataset_to_file(cfg, output_path, fmt=fmt)
    # Preview row count
    if out.lower().endswith(".csv"):
        df = pd.read_csv(out)
    else:
        df = pd.read_json(out, orient="records", lines=True)
    return out, int(len(df))


def analyze_live(config_path: str) -> Dict[str, Any]:
    cfg = load_config(config_path)
    return analyze_from_config(cfg)


def analyze_from_file(config_path: str, dataset_path: str) -> Dict[str, Any]:
    cfg = load_config(config_path)
    return analyze_from_saved(cfg, dataset_path)


def results_to_table(results: Dict[Any, Dict[str, Any]]) -> pd.DataFrame:
    rows: List[Dict[str, Any]] = []
    for ctx_key, res in results.items():
        det = res.get("detector_result", {})
        ctx = res.get("context", {})
        ctx_clean = json_sanitize(ctx)
        row = {
            "context": ctx_clean,
            "context_json": json.dumps(ctx_clean, ensure_ascii=False),
            "state": res.get("current_state"),
            "risk": det.get("risk"),
            "z_score": det.get("z_score"),
            "rel_change": det.get("rel_change"),
            "change_point": det.get("change_point"),
        }
        rows.append(row)
    if not rows:
        return pd.DataFrame(columns=["context", "context_json", "state", "risk", "z_score", "rel_change", "change_point"])
    df = pd.DataFrame(rows)
    df = df.sort_values(["risk"], ascending=[False], na_position="last").reset_index(drop=True)
    return df


def extract_debug_series(res: Dict[str, Any]) -> Dict[str, pd.Series]:
    debug = res.get("debug", {})
    series_map: Dict[str, pd.Series] = {}
    for key in ["raw_series", "signal", "short", "long", "rel", "z", "cusum_pos", "cusum_neg"]:
        val = debug.get(key)
        if isinstance(val, pd.Series):
            series_map[key] = val
    return series_map


def json_sanitize(obj: Any) -> Any:
    """
    Convert numpy/pandas scalars to native Python types so JSON serialization works.
    """
    # numpy scalar
    if isinstance(obj, np.generic):
        return obj.item()
    # pandas Timestamp
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    # dict
    if isinstance(obj, dict):
        return {k: json_sanitize(v) for k, v in obj.items()}
    # list/tuple
    if isinstance(obj, (list, tuple)):
        return [json_sanitize(v) for v in obj]
    return obj


