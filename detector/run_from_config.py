from __future__ import annotations

from typing import Any, Dict, List, Optional
import yaml
import pandas as pd
import os

from .config_schema import DataConfig
from .adapters import AdapterRegistry
from .detector_v2 import UniversalTSDetectorV2


def load_config(path: str) -> DataConfig:
    with open(path, "r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    return DataConfig.model_validate(data)


def load_dataset(cfg: DataConfig) -> pd.DataFrame:
    # Merge dataset-level field names into adapter config so adapters can validate/parse correctly
    adapter_config: Dict[str, Any] = dict(cfg.dataset.adapter_config)
    adapter_config.setdefault("timestamp_field", cfg.dataset.timestamp_field)
    
    # Support both single and multiple metric fields
    if cfg.dataset.value_fields and len(cfg.dataset.value_fields) > 1:
        # Multiple metrics: pass the first one to adapter, we'll handle the rest after
        adapter_config.setdefault("value_field", cfg.dataset.value_fields[0])
    else:
        # Single metric (legacy or single value_fields)
        value_field = cfg.dataset.value_field or (cfg.dataset.value_fields[0] if cfg.dataset.value_fields else "value")
        adapter_config.setdefault("value_field", value_field)
    
    adapter = AdapterRegistry.create(cfg.dataset.adapter, adapter_config)
    df = adapter.load()
    
    # If multiple metrics specified, transform to long format with metric_name
    if cfg.dataset.value_fields and len(cfg.dataset.value_fields) > 1:
        df = _melt_metric_fields(df, cfg.dataset.value_fields, cfg.dataset.timestamp_field)
    
    return df


def _melt_metric_fields(df: pd.DataFrame, metric_fields: List[str], timestamp_field: str) -> pd.DataFrame:
    """
    Transform wide format (multiple metric columns) to long format (metric_value + metric_name).
    
    Example:
        Input:  timestamp | tpmC | newOrderLatency90 | cluster | ...
        Output: timestamp | metric_value | metric_name | cluster | ...
    """
    # Get all non-metric, non-timestamp columns (context fields)
    id_vars = [col for col in df.columns if col not in metric_fields and col != timestamp_field]
    
    # Melt metric columns into metric_value and metric_name
    df_melted = df.melt(
        id_vars=[timestamp_field] + id_vars,
        value_vars=metric_fields,
        var_name="metric_name",
        value_name="metric_value"
    )
    
    # Remove rows where metric_value is NaN
    df_melted = df_melted.dropna(subset=["metric_value"])
    
    # Sort by timestamp
    df_melted = df_melted.sort_values(timestamp_field).reset_index(drop=True)
    
    return df_melted


def analyze_from_config(cfg: DataConfig, df: Optional[pd.DataFrame] = None) -> Dict[str, Any]:
    if df is None:
        df = load_dataset(cfg)
    # Ensure timestamp is datetime
    ts_field = cfg.dataset.timestamp_field
    if ts_field in df.columns and not isinstance(df[ts_field].dtype, pd.DatetimeTZDtype):
        df[ts_field] = pd.to_datetime(df[ts_field])

    metrics = cfg.analysis.metrics
    detector = UniversalTSDetectorV2(
        metric_kind=metrics.metric_kind,
        direction=metrics.direction,
        auto_detect_metric_type=metrics.auto_detect_metric_type,
        # name hint optional; we can pass metric name as hint
        metric_name_hint=metrics.name,
    )

    # Determine value_field to use for analyze_many
    # If we used value_fields (multiple metrics), they've been melted to metric_value
    if cfg.dataset.value_fields and len(cfg.dataset.value_fields) > 1:
        value_field = "metric_value"  # From melted format
    else:
        value_field = cfg.dataset.value_field or (cfg.dataset.value_fields[0] if cfg.dataset.value_fields else "value")
    
    results = detector.analyze_many(
        df,
        context_fields=cfg.analysis.context_fields,
        value_field=value_field,
        timestamp_field=cfg.dataset.timestamp_field,
        meta_fields=cfg.analysis.meta_fields,
        profile=None,
        debug=cfg.analysis.output.debug,
    )
    return results


def run_from_file(path: str) -> Dict[str, Any]:
    cfg = load_config(path)
    return analyze_from_config(cfg)


# ---------- two-phase workflow: fetch → save → analyze ----------

def _infer_format_from_path(file_path: str) -> str:
    _, ext = os.path.splitext(file_path.lower())
    # Support .jsonl, .ndjson, .jsonlines
    if ext in [".jsonl", ".ndjson", ".jsonlines"]:
        return "jsonl"
    # Default to csv for anything else
    return "csv"

def fetch_dataset_to_file(cfg: DataConfig, output_path: str, fmt: Optional[str] = None) -> str:
    """
    Fetch dataset using adapter and save to file.
    fmt: 'csv' or 'jsonl'
    Returns output_path.
    """
    from pathlib import Path
    # Ensure parent directory exists
    output_path_obj = Path(output_path)
    output_path_obj.parent.mkdir(parents=True, exist_ok=True)
    
    df = load_dataset(cfg)
    if fmt is None:
        fmt = _infer_format_from_path(output_path)
    if fmt == "csv":
        df.to_csv(output_path, index=False)
    elif fmt in ("jsonl", "jsonlines", "ndjson"):
        df.to_json(output_path, orient="records", lines=True, date_format="iso")
    else:
        raise ValueError("Unsupported format: use 'csv' or 'jsonl'")
    return output_path


def analyze_from_saved(cfg: DataConfig, input_path: str, fmt: Optional[str] = None) -> Dict[str, Any]:
    """
    Load previously saved dataset and run analysis using config settings.
    """
    if fmt is None:
        fmt = _infer_format_from_path(input_path)
    if fmt == "csv":
        df = pd.read_csv(input_path)
    elif fmt in ("jsonl", "jsonlines", "ndjson"):
        df = pd.read_json(input_path, orient="records", lines=True)
    else:
        raise ValueError("Unsupported format: use 'csv' or 'jsonl'")
    return analyze_from_config(cfg, df=df)


