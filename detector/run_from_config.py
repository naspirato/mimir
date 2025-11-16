from __future__ import annotations

from typing import Any, Dict, Optional
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
    adapter = AdapterRegistry.create(cfg.dataset.adapter, cfg.dataset.adapter_config)
    df = adapter.load()
    return df


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

    results = detector.analyze_many(
        df,
        context_fields=cfg.analysis.context_fields,
        value_field=cfg.dataset.value_field,
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


