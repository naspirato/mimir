"""
Metric types and transformations for time-series analysis.

Each metric type defines how the raw values should be transformed
before statistical analysis. This ensures proper handling of different
data distributions and ranges.
"""
from enum import Enum
from typing import Tuple, Optional, Dict, Any
import numpy as np
import pandas as pd


class MetricType(str, Enum):
    """Supported metric types with their transformation strategies."""

    DURATION = "duration"
    ERROR_RATE = "error_rate"
    COUNT = "count"
    THROUGHPUT = "throughput"
    PERCENTAGE = "percentage"
    BINARY = "binary"
    GAUSSIAN = "gaussian"
    SIZE = "size"
    OTHER = "other"

    @classmethod
    def from_string(cls, value: str) -> "MetricType":
        """Convert string to MetricType, case-insensitive."""
        value_lower = value.lower().strip()
        for mt in cls:
            if mt.value == value_lower:
                return mt
        # Default to OTHER if not found
        return cls.OTHER


class MetricTypeTransformer:
    """Handles transformations for different metric types."""

    @staticmethod
    def transform(series: pd.Series, metric_type: MetricType) -> pd.Series:
        """
        Transform series according to metric type.

        Args:
            series: Raw input series
            metric_type: Type of metric determining transformation

        Returns:
            Transformed series ready for analysis
        """
        if metric_type == MetricType.DURATION:
            return MetricTypeTransformer._log_transform(series)
        elif metric_type == MetricType.ERROR_RATE:
            return MetricTypeTransformer._logit_transform(series)
        elif metric_type == MetricType.COUNT:
            return MetricTypeTransformer._sqrt_transform(series)
        elif metric_type == MetricType.THROUGHPUT:
            return MetricTypeTransformer._log_transform(series)
        elif metric_type == MetricType.PERCENTAGE:
            return MetricTypeTransformer._asin_sqrt_transform(series)
        elif metric_type == MetricType.BINARY:
            return MetricTypeTransformer._no_transform(series)
        elif metric_type == MetricType.GAUSSIAN:
            return MetricTypeTransformer._no_transform(series)
        elif metric_type == MetricType.SIZE:
            return MetricTypeTransformer._log_transform(series, base=10)
        elif metric_type == MetricType.OTHER:
            return MetricTypeTransformer._no_transform(series)
        else:
            return MetricTypeTransformer._no_transform(series)

    @staticmethod
    def _log_transform(series: pd.Series, base: Optional[float] = None) -> pd.Series:
        """Log transformation: log1p for natural log, log10/log2 for others."""
        s_clipped = series.clip(lower=1e-9)
        if base is None:
            return np.log1p(s_clipped)
        elif base == 10:
            return np.log10(s_clipped + 1)
        elif base == 2:
            return np.log2(s_clipped + 1)
        else:
            return np.log(s_clipped + 1) / np.log(base)

    @staticmethod
    def _logit_transform(series: pd.Series) -> pd.Series:
        """Logit transformation for rates/percentages in [0,1]."""
        # Normalize to [0, 1] if needed (assume [0, 100] if max > 1.1)
        s_norm = series.copy()
        if s_norm.max() > 1.1:
            s_norm = s_norm / 100.0
        s_norm = s_norm.clip(lower=1e-6, upper=1 - 1e-6)
        return np.log(s_norm / (1 - s_norm))

    @staticmethod
    def _sqrt_transform(series: pd.Series) -> pd.Series:
        """Square root transformation for count data (stabilizes variance for Poisson)."""
        s_clipped = series.clip(lower=0)
        return np.sqrt(s_clipped)

    @staticmethod
    def _asin_sqrt_transform(series: pd.Series) -> pd.Series:
        """Arcsine square root transformation for percentages."""
        # Normalize to [0, 1] if needed
        s_norm = series.copy()
        if s_norm.max() > 1.1:
            s_norm = s_norm / 100.0
        s_norm = s_norm.clip(lower=0, upper=1)
        return np.arcsin(np.sqrt(s_norm))

    @staticmethod
    def _no_transform(series: pd.Series) -> pd.Series:
        """No transformation, return as-is."""
        return series


class MetricTypeDetector:
    """Automatically detects metric type from data characteristics."""

    @staticmethod
    def detect(series: pd.Series, hint: Optional[str] = None) -> Tuple[MetricType, Dict[str, Any]]:
        """
        Detect metric type from series characteristics.

        Args:
            series: Input series to analyze
            hint: Optional hint (metric name or explicit type)

        Returns:
            Tuple of (detected_type, diagnostics_dict)
        """
        if hint:
            try:
                hint_type = MetricType.from_string(hint)
                if hint_type != MetricType.OTHER:
                    return hint_type, {"method": "hint", "hint": hint}
            except Exception:
                pass

        s_clean = series.dropna()
        
        # Check for binary FIRST (most specific) - can work with fewer points
        unique_vals = s_clean.unique()
        # Check if only 0 and 1 values (allowing for float representation)
        if len(unique_vals) <= 2:
            unique_set = set(float(v) for v in unique_vals)
            if unique_set.issubset({0.0, 1.0}) and len(s_clean) >= 4:
                return MetricType.BINARY, {"method": "detected", "reason": "binary_values"}
        
        # Need at least 10 points for other detections
        if len(s_clean) < 10:
            return MetricType.OTHER, {"method": "fallback", "reason": "too_few_points"}

        # Check range and distribution
        min_val = float(s_clean.min())
        max_val = float(s_clean.max())
        median_val = float(s_clean.median())
        mean_val = float(s_clean.mean())
        skew = float(s_clean.skew())
        std_val = float(s_clean.std())

        # Skip gaussian check here - will check after bounded ranges

        # Check for bounded ranges [0, 1] (error_rate, percentage)
        if min_val >= 0 and max_val <= 1.1:
            # Could be error_rate or percentage - check skewness
            if skew > 1.5:  # Highly skewed -> error_rate
                return MetricType.ERROR_RATE, {
                    "method": "detected",
                    "reason": "bounded_range_high_skew",
                }
            else:
                return MetricType.PERCENTAGE, {
                    "method": "detected",
                    "reason": "bounded_range_low_skew",
                }

        # Check for bounded ranges [0, 100] - percentages
        if min_val >= 0 and max_val <= 101 and median_val <= 100:
            # Check if symmetric (then gaussian) or skewed (then percentage)
            if abs(skew) < 0.5 and std_val > 0:
                # Symmetric distribution in [0, 100] - could be gaussian
                return MetricType.GAUSSIAN, {"method": "detected", "reason": "symmetric_bounded"}
            else:
                return MetricType.PERCENTAGE, {"method": "detected", "reason": "percent_range"}

        # Check for size-like (VERY large positive values)
        if min_val >= 0 and max_val > 1e6:
            if skew > 1.0:
                return MetricType.SIZE, {"method": "detected", "reason": "very_large_values"}

        # Check for duration/latency (positive, right-skewed, medium range)
        if min_val >= 0 and skew > 0.8:
            # Typical duration range: milliseconds to seconds (0.1ms to 10000ms/10s)
            if 0.1 <= median_val <= 10000 and max_val < 1e5:
                return MetricType.DURATION, {"method": "detected", "reason": "duration_range"}

        # Check for count-like (non-negative integers, smaller values)
        is_integer_like = (s_clean % 1 == 0).mean() > 0.8
        if min_val >= 0 and is_integer_like and max_val < 10000:
            # Check variance-to-mean ratio (Poisson-like)
            if mean_val > 0:
                var_to_mean = s_clean.var() / mean_val
                if 0.3 < var_to_mean < 3.0:  # Relaxed for Poisson
                    return MetricType.COUNT, {"method": "detected", "reason": "poisson_like"}
            # Highly skewed integer values
            if skew > 1.5:
                return MetricType.COUNT, {"method": "detected", "reason": "integer_high_skew"}

        # Check for throughput (positive, less skewed, moderate-high values)
        if min_val >= 0 and -0.3 < skew < 1.3 and mean_val > 20 and max_val < 1e6:
            return MetricType.THROUGHPUT, {"method": "detected", "reason": "throughput_like"}

        # Check for gaussian (symmetric distribution) - fallback
        if abs(skew) < 0.5 and std_val > 0:
            return MetricType.GAUSSIAN, {"method": "detected", "reason": "symmetric_distribution"}

        # Default fallback
        return MetricType.OTHER, {"method": "fallback", "reason": "unknown_characteristics"}

    @staticmethod
    def get_type_description(metric_type: MetricType) -> Dict[str, str]:
        """Get human-readable description of metric type."""
        descriptions = {
            MetricType.DURATION: {
                "name": "Duration/Latency",
                "description": "Time-based metrics (execution time, latency, delays)",
                "transformation": "log-transform",
                "reason": "Right-skewed distribution with long tail",
                "typical_range": "milliseconds to seconds",
            },
            MetricType.ERROR_RATE: {
                "name": "Error Rate",
                "description": "Percentage of errors or failures (0-1 or 0-100%)",
                "transformation": "logit-transform",
                "reason": "Bounded range, binomial-like distribution",
                "typical_range": "0-1 or 0-100%",
            },
            MetricType.COUNT: {
                "name": "Count/Rate",
                "description": "Event counts or frequency per time unit",
                "transformation": "square-root",
                "reason": "Count data with Poisson-like distribution",
                "typical_range": "non-negative integers",
            },
            MetricType.THROUGHPUT: {
                "name": "Throughput/Capacity",
                "description": "Throughput, capacity, or performance metrics",
                "transformation": "log-transform",
                "reason": "Right-skewed, variance stabilization needed",
                "typical_range": "positive values, often large",
            },
            MetricType.PERCENTAGE: {
                "name": "Percentage/Ratio",
                "description": "Percentages, ratios, or proportions (0-1 or 0-100%)",
                "transformation": "arcsine-sqrt",
                "reason": "Bounded range, stabilizes variance",
                "typical_range": "0-1 or 0-100%",
            },
            MetricType.BINARY: {
                "name": "Binary/Boolean",
                "description": "Binary metrics (0/1, pass/fail, on/off)",
                "transformation": "none (requires aggregation)",
                "reason": "Discrete values, needs window aggregation",
                "typical_range": "0 or 1",
            },
            MetricType.GAUSSIAN: {
                "name": "Gaussian/Normal",
                "description": "Metrics with approximately normal distribution",
                "transformation": "none",
                "reason": "Symmetric distribution, no transformation needed",
                "typical_range": "any range",
            },
            MetricType.SIZE: {
                "name": "Size/Bytes",
                "description": "Size metrics (file size, memory usage, data size)",
                "transformation": "log10-transform",
                "reason": "Large values with right-skewed distribution",
                "typical_range": "bytes, kilobytes, megabytes",
            },
            MetricType.OTHER: {
                "name": "Other/Generic",
                "description": "Generic metrics without specific transformation",
                "transformation": "none",
                "reason": "Unknown characteristics, minimal processing",
                "typical_range": "any range",
            },
        }
        return descriptions.get(metric_type, descriptions[MetricType.OTHER])


# Convenience functions
def transform_for_type(series: pd.Series, metric_type: str) -> pd.Series:
    """Transform series using metric type string."""
    mt = MetricType.from_string(metric_type)
    return MetricTypeTransformer.transform(series, mt)


def detect_metric_type(series: pd.Series, hint: Optional[str] = None) -> MetricType:
    """Detect metric type from series, returns type only."""
    return MetricTypeDetector.detect(series, hint)[0]

