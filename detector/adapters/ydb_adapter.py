"""
YDB adapter that conforms to DataAdapter interface.
Relies on an external helper 'ydb_wrapper.YDBWrapper' if available.
"""
from typing import Any, Dict, List, Optional

import pandas as pd

from .base import DataAdapter


def _fix_ydb_timestamp(series: pd.Series) -> pd.Series:
    """
    Fix YDB timestamp conversion issue where microseconds are interpreted as nanoseconds.
    
    YDB returns timestamps in microseconds since epoch, but pandas may interpret
    them as nanoseconds, resulting in dates in 1970. This function detects and fixes that.
    """
    if len(series) == 0:
        return series
    
    # If already datetime, check if incorrectly converted (year < 2000)
    if pd.api.types.is_datetime64_any_dtype(series):
        sample = series.iloc[0]
        if isinstance(sample, pd.Timestamp) and sample.year < 2000:
            # Incorrectly converted: pandas interpreted microseconds as nanoseconds
            # Fix: use int64 value as microseconds
            ns_values = series.astype('int64')
            return pd.to_datetime(ns_values, unit='us')
        return series
    
    # If numeric, determine unit by value range
    if pd.api.types.is_numeric_dtype(series):
        non_null = series.dropna()
        if len(non_null) == 0:
            return pd.to_datetime(series, unit='us', errors='coerce')
        
        min_val = non_null.min()
        max_val = non_null.max()
        
        # YDB timestamps are typically in microseconds
        # Range for 2000-2100: ~946684800000000 to ~4102444800000000 microseconds
        min_reasonable_us = 946684800000000  # 2000-01-01
        max_reasonable_us = 4102444800000000  # 2100-01-01
        
        if min_reasonable_us <= min_val <= max_reasonable_us:
            # Definitely microseconds
            result = pd.to_datetime(series, unit='us', errors='coerce')
            # Double-check: if still wrong, fix it
            if len(result.dropna()) > 0 and result.dropna().iloc[0].year < 2000:
                ns_values = series.astype('int64')
                return pd.to_datetime(ns_values, unit='us', errors='coerce')
            return result
        elif 946684800000 <= min_val <= 4102444800000:
            # Milliseconds range
            return pd.to_datetime(series, unit='ms', errors='coerce')
        elif 946684800 <= min_val <= 4102444800:
            # Seconds range
            return pd.to_datetime(series, unit='s', errors='coerce')
        else:
            # Try microseconds first (YDB default), fallback to auto
            try:
                result = pd.to_datetime(series, unit='us', errors='coerce')
                if len(result.dropna()) > 0 and result.dropna().iloc[0].year < 2000:
                    ns_values = series.astype('int64')
                    return pd.to_datetime(ns_values, unit='us', errors='coerce')
                return result
            except Exception:
                return pd.to_datetime(series, errors='coerce')
    
    # String or other: use default conversion
    result = pd.to_datetime(series, errors='coerce')
    # Check if conversion resulted in 1970 dates (wrong interpretation)
    if len(result.dropna()) > 0 and result.dropna().iloc[0].year < 2000:
        # Try to extract numeric values and interpret as microseconds
        try:
            numeric = pd.to_numeric(series, errors='coerce')
            return pd.to_datetime(numeric, unit='us', errors='coerce')
        except Exception:
            pass
    return result

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
            # Try to extract column names from query for empty DataFrame
            # This ensures empty DataFrame has correct structure
            import re
            # Simple regex to extract column names from SELECT ... FROM
            # More robust would be SQL parsing, but this covers common cases
            select_match = re.search(r'SELECT\s+(.*?)\s+FROM', query, re.IGNORECASE | re.DOTALL)
            if select_match:
                columns_str = select_match.group(1).strip()
                # Split by comma, handle newlines and whitespace
                columns = [col.strip().split()[-1].strip('`"\'') for col in columns_str.split(',')]
                # Filter out empty strings and handle aliases
                columns = [col for col in columns if col]
                if columns:
                    return pd.DataFrame(columns=columns)
            # Fallback: return minimal columns
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
        # Fix YDB timestamp conversion (microseconds vs nanoseconds issue)
        if self.timestamp_field in df.columns and len(df) > 0:
            df[self.timestamp_field] = _fix_ydb_timestamp(df[self.timestamp_field])
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
