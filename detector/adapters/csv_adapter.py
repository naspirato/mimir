from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd

from .base import DataAdapter


class CSVAdapter(DataAdapter):
    """
    CSV file adapter.

    Config:
      - path: str (required) - path to CSV file
      - timestamp_field: str = "timestamp"
      - value_field: str = "value"
      - parse_dates: bool = True
      - kwargs: Dict[str, Any] - extra kwargs forwarded to pandas.read_csv
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(config)
        if "path" not in self.config or not self.config["path"]:
            raise ValueError("CSVAdapter requires 'path' in config")
        self.timestamp_field = self.config.get("timestamp_field", "timestamp")
        self.value_field = self.config.get("value_field", "value")
        self.parse_dates = bool(self.config.get("parse_dates", True))
        self.kwargs = dict(self.config.get("kwargs", {}))

    def load(self) -> pd.DataFrame:
        df = pd.read_csv(
            self.config["path"],
            **self.kwargs,
        )
        if self.parse_dates and self.timestamp_field in df.columns:
            df[self.timestamp_field] = pd.to_datetime(df[self.timestamp_field])
        if self.value_field not in df.columns:
            raise ValueError(f"CSVAdapter: value_field '{self.value_field}' not found")
        return df


