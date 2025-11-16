from __future__ import annotations

from typing import Any, Dict, List, Literal, Optional
from pydantic import BaseModel, Field, field_validator


class DatasetConfig(BaseModel):
    adapter: Literal["csv", "http_json", "ydb"]
    adapter_config: Dict[str, Any] = Field(default_factory=dict)
    timestamp_field: str = "timestamp"
    value_field: str = "value"


class MetricsConfig(BaseModel):
    name: str
    direction: Literal["higher_is_better", "lower_is_better"]
    metric_kind: Optional[str] = None  # duration, error_rate, etc. or None for auto
    auto_detect_metric_type: bool = True


class OutputConfig(BaseModel):
    debug: bool = False


class AnalysisConfig(BaseModel):
    context_fields: List[str]
    meta_fields: Optional[List[str]] = None
    metrics: MetricsConfig
    event_types: List[Literal["regression", "improvement", "stable"]] = Field(
        default_factory=lambda: ["regression", "improvement"]
    )
    output: OutputConfig = Field(default_factory=OutputConfig)

    @field_validator("context_fields")
    @classmethod
    def non_empty_context(cls, v: List[str]) -> List[str]:
        if not v:
            raise ValueError("context_fields must not be empty")
        return v


class DataConfig(BaseModel):
    version: int = 1
    dataset: DatasetConfig
    analysis: AnalysisConfig


