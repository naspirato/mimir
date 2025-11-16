from __future__ import annotations

import json
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
    value_field: Optional[str]  # Single metric (legacy)
    value_fields: Optional[List[str]]  # Multiple metrics (preferred)
    context_fields: List[str]
    meta_fields: List[str]
    metric_name: Optional[str]
    metric_direction: Optional[str]
    metric_kind: Optional[str]
    auto_detect_metric_type: bool
    debug: bool


def list_config_paths(configs_dir: str = "configs") -> List[str]:
    paths = sorted(glob(os.path.join(configs_dir, "*.yaml"))) + sorted(
        glob(os.path.join(configs_dir, "*.yml"))
    )
    return paths


def get_config_summary(path: str) -> ConfigSummary:
    cfg = load_config(path)
    metrics = cfg.analysis.metrics
    return ConfigSummary(
        path=path,
        name=Path(path).stem,
        adapter=cfg.dataset.adapter,
        timestamp_field=cfg.dataset.timestamp_field,
        value_field=cfg.dataset.value_field,
        value_fields=cfg.dataset.value_fields,
        context_fields=list(cfg.analysis.context_fields or []),
        meta_fields=list(cfg.analysis.meta_fields or []),
        metric_name=metrics.name if metrics.name else None,
        metric_direction=metrics.direction if metrics.direction else None,
        metric_kind=metrics.metric_kind if metrics.metric_kind else None,
        auto_detect_metric_type=bool(getattr(metrics, "auto_detect_metric_type", False)),
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


def analyze_live(config_path: str, force_debug: bool = False) -> Dict[str, Any]:
    cfg = load_config(config_path)
    if force_debug:
        original_debug = cfg.analysis.output.debug
        cfg.analysis.output.debug = True
        try:
            result = analyze_from_config(cfg)
        finally:
            cfg.analysis.output.debug = original_debug
        return result
    return analyze_from_config(cfg)


def analyze_from_file(config_path: str, dataset_path: str, force_debug: bool = False) -> Dict[str, Any]:
    cfg = load_config(config_path)
    if force_debug:
        original_debug = cfg.analysis.output.debug
        cfg.analysis.output.debug = True
        try:
            result = analyze_from_saved(cfg, dataset_path)
        finally:
            cfg.analysis.output.debug = original_debug
        return result
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
            "metric_name": ctx_clean.get("metric_name", ""),
        }
        rows.append(row)
    if not rows:
        return pd.DataFrame(columns=["context", "context_json", "state", "risk", "z_score", "rel_change", "change_point", "metric_name"])
    df = pd.DataFrame(rows)
    df = df.sort_values(["risk"], ascending=[False], na_position="last").reset_index(drop=True)
    return df


def group_results_by_context(results: Dict[Any, Dict[str, Any]], context_fields_without_metric: List[str]) -> List[Dict[str, Any]]:
    """Group results by context without metric_name, returning grouped structure."""
    from collections import defaultdict
    
    # Group results by context (excluding metric_name)
    groups: Dict[str, List[Dict[str, Any]]] = defaultdict(list)
    
    for ctx_key, res in results.items():
        ctx = res.get("context", {})
        # Create group key from context without metric_name
        group_key_parts = []
        for field in context_fields_without_metric:
            if field in ctx:
                group_key_parts.append(str(ctx[field]))
        group_key = "|".join(group_key_parts)
        
        det = res.get("detector_result", {})
        ctx_clean = json_sanitize(ctx)
        
        metric_row = {
            "context": ctx_clean,
            "context_json": json.dumps(ctx_clean, ensure_ascii=False),
            "state": res.get("current_state"),
            "risk": det.get("risk"),
            "z_score": det.get("z_score"),
            "rel_change": det.get("rel_change"),
            "change_point": det.get("change_point"),
            "metric_name": ctx_clean.get("metric_name", ""),
        }
        groups[group_key].append(metric_row)
    
    # Convert to list of groups, sorted by max risk
    grouped_list = []
    for group_key, metrics in groups.items():
        # Get context for the group (same for all metrics, just without metric_name)
        first_ctx = metrics[0]["context"]
        group_ctx = {k: v for k, v in first_ctx.items() if k != "metric_name"}
        
        # Sort metrics by risk
        metrics_sorted = sorted(metrics, key=lambda x: x["risk"] or 0, reverse=True)
        
        # Format group context as string for display
        group_ctx_items = sorted([f"{k}: {v}" for k, v in group_ctx.items()])
        group_ctx_str = ", ".join(group_ctx_items)
        
        grouped_list.append({
            "group_key": group_key,
            "group_context": group_ctx,
            "group_context_str": group_ctx_str,
            "metrics": metrics_sorted,
            "max_risk": max((m["risk"] or 0 for m in metrics), default=0),
        })
    
    # Sort groups by max risk
    grouped_list.sort(key=lambda x: x["max_risk"], reverse=True)
    return grouped_list


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


