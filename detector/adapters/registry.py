from __future__ import annotations

from typing import Any, Dict, Type

from .base import DataAdapter
from .csv_adapter import CSVAdapter
from .http_json_adapter import HTTPJSONAdapter


class AdapterRegistry:
    """
    Simple registry/factory for data adapters.
    """

    _registry: Dict[str, Type[DataAdapter]] = {
        "csv": CSVAdapter,
        "http_json": HTTPJSONAdapter,
    }

    # Optional adapters (registered if import succeeds)
    try:
        from .ydb_adapter import YDBAdapter  # type: ignore

        _registry["ydb"] = YDBAdapter
    except Exception:
        # YDB is optional; ignore if unavailable
        pass
    @classmethod
    def register(cls, name: str, adapter_cls: Type[DataAdapter]) -> None:
        cls._registry[name] = adapter_cls

    @classmethod
    def create(cls, name: str, config: Dict[str, Any]) -> DataAdapter:
        name_lower = name.lower()
        if name_lower not in cls._registry:
            raise ValueError(f"Unknown adapter '{name}'. Registered: {list(cls._registry.keys())}")
        return cls._registry[name_lower](config)


