from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional

import pandas as pd


class DataAdapter(ABC):
    """
    Base adapter interface for loading time-series data into a pandas DataFrame.

    Contract:
    - load() MUST return a DataFrame with at least:
        - 'timestamp' column (parseable to pandas datetime)
        - 'value' column (numeric)
      Additional context/meta columns are allowed.
    """

    def __init__(self, config: Optional[Dict[str, Any]] = None) -> None:
        self.config: Dict[str, Any] = config or {}

    @abstractmethod
    def load(self) -> pd.DataFrame:
        raise NotImplementedError


class DataFrameAdapter(DataAdapter):
    """
    Pass-through adapter for an existing DataFrame.
    Useful for unified usage with the registry/factory.
    """

    def __init__(self, df: pd.DataFrame) -> None:
        super().__init__({})
        self._df = df

    def load(self) -> pd.DataFrame:
        return self._df


