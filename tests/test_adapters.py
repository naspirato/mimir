import json
from typing import Any, Dict

import pandas as pd
import pytest

from detector.adapters import AdapterRegistry, CSVAdapter, HTTPJSONAdapter, DataFrameAdapter


def test_ydb_registry_optional():
    # ydb may or may not be registered depending on environment
    try:
        inst = AdapterRegistry.create("ydb", {"query": "SELECT 1"})
        # If we got here, environment has YDB wrapper; we won't actually .load()
        assert inst is not None
    except ValueError as e:
        # Unknown adapter 'ydb' -> it's optional; acceptable
        assert "Unknown adapter" in str(e)
    except ImportError:
        # YDB wrapper not available; acceptable
        assert True
    except RuntimeError as e:
        # YDB wrapper present but no local config file available; acceptable in CI
        assert "Config file not found" in str(e)


def test_csv_adapter_loads_examples(tmp_path):
    # Use existing example CSV
    adapter = CSVAdapter({"path": "examples/metrics_example.csv"})
    df = adapter.load()
    assert isinstance(df, pd.DataFrame)
    assert "timestamp" in df.columns
    assert "value" in df.columns
    assert pd.api.types.is_datetime64_any_dtype(df["timestamp"])


def test_dataframe_adapter_passthrough():
    df = pd.DataFrame({"timestamp": pd.date_range("2024-01-01", periods=3, freq="h"), "value": [1.0, 2.0, 3.0]})
    adapter = DataFrameAdapter(df)
    loaded = adapter.load()
    assert loaded.equals(df)


def test_http_json_adapter(monkeypatch):
    # Mock requests.request
    records = [
        {"timestamp": "2024-01-01T00:00:00Z", "value": 10},
        {"timestamp": "2024-01-01T01:00:00Z", "value": 12},
    ]

    class DummyResp:
        def raise_for_status(self) -> None:
            return None

        def json(self):
            return records

    def dummy_request(method: str, url: str, headers: Dict[str, Any], params: Dict[str, Any], timeout: float):
        assert method == "GET"
        assert url == "https://example.com/data"
        return DummyResp()

    import detector.adapters.http_json_adapter as http_mod

    monkeypatch.setattr(http_mod.requests, "request", dummy_request)
    adapter = HTTPJSONAdapter({"url": "https://example.com/data"})
    df = adapter.load()
    assert len(df) == 2
    assert "timestamp" in df.columns and "value" in df.columns
    assert pd.api.types.is_datetime64_any_dtype(df["timestamp"])


def test_adapter_registry_creates_instances():
    cfg = {"path": "examples/metrics_example.csv"}
    inst = AdapterRegistry.create("csv", cfg)
    assert isinstance(inst, CSVAdapter)


