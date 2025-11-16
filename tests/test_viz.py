"""Tests for webapp/viz.py"""
from datetime import datetime
from typing import Dict, Any

import pandas as pd
import pytest
import numpy as np

from webapp.viz import time_series_figure, diagnostics_figure, _normalize_datetime


def test_normalize_datetime_none():
    """Test that None is returned as None"""
    assert _normalize_datetime(None) is None


def test_normalize_datetime_pandas_timestamp():
    """Test pandas Timestamp conversion"""
    ts = pd.Timestamp('2024-01-15 10:30:00')
    result = _normalize_datetime(ts)
    assert isinstance(result, datetime)
    assert result.year == 2024
    assert result.month == 1
    assert result.day == 15


def test_normalize_datetime_python_datetime():
    """Test Python datetime passthrough"""
    dt = datetime(2024, 1, 15, 10, 30, 0)
    result = _normalize_datetime(dt)
    assert result is dt


def test_normalize_datetime_numpy_datetime64():
    """Test numpy datetime64 conversion"""
    dt64 = np.datetime64('2024-01-15T10:30:00')
    result = _normalize_datetime(dt64)
    assert isinstance(result, datetime)


def test_normalize_datetime_string():
    """Test string datetime conversion"""
    dt_str = "2024-01-15 10:30:00"
    result = _normalize_datetime(dt_str)
    assert isinstance(result, datetime)


def test_normalize_datetime_iso_string():
    """Test ISO format string conversion"""
    dt_str = "2024-01-15T10:30:00"
    result = _normalize_datetime(dt_str)
    assert isinstance(result, datetime)


def test_time_series_figure_with_timestamp_change_point():
    """Test that time_series_figure handles pandas Timestamp change_point"""
    series_map = {
        "raw_series": pd.Series([1, 2, 3], index=pd.date_range('2024-01-01', periods=3))
    }
    change_point = pd.Timestamp('2024-01-02')
    fig = time_series_figure(series_map, change_point=change_point)
    # Should not raise exception
    assert fig is not None
    # Verify figure has traces
    assert len(fig.data) > 0


def test_time_series_figure_with_datetime_change_point():
    """Test that time_series_figure handles Python datetime change_point"""
    series_map = {
        "raw_series": pd.Series([1, 2, 3], index=pd.date_range('2024-01-01', periods=3))
    }
    change_point = datetime(2024, 1, 2)
    fig = time_series_figure(series_map, change_point=change_point)
    assert fig is not None


def test_time_series_figure_with_none_change_point():
    """Test that time_series_figure handles None change_point"""
    series_map = {
        "raw_series": pd.Series([1, 2, 3], index=pd.date_range('2024-01-01', periods=3))
    }
    fig = time_series_figure(series_map, change_point=None)
    assert fig is not None


def test_time_series_figure_with_all_series():
    """Test time_series_figure with all debug series"""
    dates = pd.date_range('2024-01-01', periods=10)
    series_map = {
        "raw_series": pd.Series(range(10), index=dates),
        "signal": pd.Series(range(10), index=dates),
        "short": pd.Series(range(10), index=dates),
        "long": pd.Series(range(10), index=dates),
    }
    change_point = pd.Timestamp('2024-01-05')
    fig = time_series_figure(series_map, change_point=change_point)
    assert fig is not None
    assert len(fig.data) == 4  # raw, signal, short, long


def test_diagnostics_figure():
    """Test diagnostics_figure"""
    dates = pd.date_range('2024-01-01', periods=10)
    series_map = {
        "z": pd.Series(range(10), index=dates),
        "rel": pd.Series(range(10), index=dates),
        "cusum_pos": pd.Series(range(10), index=dates),
        "cusum_neg": pd.Series(range(10), index=dates),
    }
    fig = diagnostics_figure(series_map)
    assert fig is not None
    assert len(fig.data) == 4


def test_series_with_nan_values():
    """Test that series with NaN values are handled correctly"""
    dates = pd.date_range('2024-01-01', periods=10)
    series_map = {
        "raw_series": pd.Series([1, 2, np.nan, 4, 5, np.nan, 7, 8, 9, 10], index=dates),
    }
    fig = time_series_figure(series_map, change_point=None)
    assert fig is not None
    # Should have one trace with valid data (NaN filtered out)
    assert len(fig.data) == 1
    # Check that NaN values were filtered
    assert len(fig.data[0].x) == 8  # 10 total - 2 NaN = 8 valid points


def test_series_with_all_nan():
    """Test that series with all NaN values are handled gracefully"""
    dates = pd.date_range('2024-01-01', periods=10)
    series_map = {
        "raw_series": pd.Series([np.nan] * 10, index=dates),
    }
    fig = time_series_figure(series_map, change_point=None)
    assert fig is not None
    # Should have no traces since all values are NaN
    assert len(fig.data) == 0


def test_series_with_inf_values():
    """Test that series with inf values are handled correctly"""
    dates = pd.date_range('2024-01-01', periods=10)
    series_map = {
        "raw_series": pd.Series([1, 2, np.inf, 4, 5, -np.inf, 7, 8, 9, 10], index=dates),
    }
    fig = time_series_figure(series_map, change_point=None)
    assert fig is not None
    # Should have one trace with valid data (inf filtered out)
    assert len(fig.data) == 1
    # Check that inf values were filtered
    assert len(fig.data[0].x) == 8  # 10 total - 2 inf = 8 valid points


