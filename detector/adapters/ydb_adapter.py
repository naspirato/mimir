"""
YDB adapter that conforms to DataAdapter interface.
Relies on an external helper 'ydb_wrapper.YDBWrapper' if available.
"""
from typing import Any, Dict, List, Optional

import pandas as pd

from .base import DataAdapter

try:
    # Expect a module utils/ydb_wrapper.py in project (provided by user env)
    from ..utils.ydb_wrapper import YDBWrapper  # type: ignore
except Exception:
    YDBWrapper = None  # type: ignore


class YDBAdapter(DataAdapter):
    """
    Adapter for YDB using YDBWrapper if available.

    Config:
      - query: str (required for load)
      - query_name: Optional[str]
      - wrapper_kwargs: Dict[str, Any] passed to YDBWrapper(...)
      - timestamp_field: str = "timestamp"
      - value_field: str = "value"
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        super().__init__(config)
        self.timestamp_field = self.config.get("timestamp_field", "timestamp")
        self.value_field = self.config.get("value_field", "value")
        wrapper_kwargs = dict(self.config.get("wrapper_kwargs", {}))
        if YDBWrapper is None:
            raise ImportError(
                "YDBAdapter requires utils.ydb_wrapper.YDBWrapper to be available in project."
            )
        self._wrapper = YDBWrapper(**wrapper_kwargs)

    def load(self) -> pd.DataFrame:
        query = self.config.get("query")
        query_name = self.config.get("query_name")
        if not query:
            raise ValueError("YDBAdapter requires 'query' in config for load()")
        results = self._wrapper.execute_scan_query(query, query_name=query_name)
        if not results:
            return pd.DataFrame(columns=[self.timestamp_field, self.value_field])
        # Convert rows to dicts with bytes decoding
        dict_results: List[Dict[str, Any]] = []
        for row in results:
            row_dict = dict(row)
            for k, v in row_dict.items():
                if isinstance(v, (bytes, bytearray)):
                    row_dict[k] = bytes(v).decode("utf-8")
            dict_results.append(row_dict)
        df = pd.DataFrame(dict_results)
        # Best-effort timestamp parsing
        if self.timestamp_field in df.columns:
            df[self.timestamp_field] = pd.to_datetime(df[self.timestamp_field], errors="coerce")
        if self.value_field not in df.columns:
            raise ValueError(f"YDBAdapter: value_field '{self.value_field}' not found in query result")
        return df

    # Extra helper methods (optional)
    def execute_query(self, query: str, query_name: Optional[str] = None, **kwargs) -> Any:
        return self._wrapper.execute_scan_query(query, query_name=query_name)

    def bulk_upsert(
        self,
        table_path: str,
        data: List[Dict[str, Any]],
        column_types: Any,
        batch_size: int = 1000,
        query_name: Optional[str] = None,
    ) -> bool:
        if not data:
            return True
        if len(data) > batch_size:
            self._wrapper.bulk_upsert_batches(table_path, data, column_types, batch_size=batch_size, query_name=query_name)
        else:
            self._wrapper.bulk_upsert(table_path, data, column_types)
        return True
