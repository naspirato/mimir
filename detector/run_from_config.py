from __future__ import annotations

from typing import Any, Dict, Optional
import yaml
import pandas as pd

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


