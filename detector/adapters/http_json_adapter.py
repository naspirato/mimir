from __future__ import annotations

from typing import Any, Dict, Optional, List

import pandas as pd
import requests

from .base import DataAdapter


class HTTPJSONAdapter(DataAdapter):
    """
    HTTP JSON adapter.

    Expects the endpoint to return either:
      - a JSON list of objects [{"timestamp": "...", "value": ...}, ...]
      - or a dict with key configured by 'data_key' that holds such a list

    Config:
      - url: str (required)
      - method: str = "GET"
      - headers: Dict[str, str] = {}
      - params: Dict[str, Any] = {}
      - data_key: Optional[str] = None
      - timestamp_field: str = "timestamp"
      - value_field: str = "value"
      - timeout: float = 10.0
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(config)
        url = self.config.get("url")
        if not url:
            raise ValueError("HTTPJSONAdapter requires 'url' in config")
        self.method = (self.config.get("method") or "GET").upper()
        self.headers = dict(self.config.get("headers", {}))
        self.params = dict(self.config.get("params", {}))
        self.data_key = self.config.get("data_key")
        self.timestamp_field = self.config.get("timestamp_field", "timestamp")
        self.value_field = self.config.get("value_field", "value")
        self.timeout = float(self.config.get("timeout", 10.0))

    def load(self) -> pd.DataFrame:
        url: str = self.config["url"]
        resp = requests.request(
            self.method,
            url,
            headers=self.headers,
            params=self.params,
            timeout=self.timeout,
        )
        resp.raise_for_status()
        payload = resp.json()
        if self.data_key is not None:
            payload = payload[self.data_key]
        if not isinstance(payload, list):
            raise ValueError("HTTPJSONAdapter expects a list of objects in response")
        df = pd.DataFrame(payload)
        if self.timestamp_field in df.columns:
            df[self.timestamp_field] = pd.to_datetime(df[self.timestamp_field])
        if self.value_field not in df.columns:
            raise ValueError(f"HTTPJSONAdapter: value_field '{self.value_field}' not found")
        return df


