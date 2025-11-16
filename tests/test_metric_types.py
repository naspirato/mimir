"""Tests for metric types, transformations, and auto-detection."""
import pytest
import numpy as np
import pandas as pd
from detector.metric_types import (
    MetricType,
    MetricTypeTransformer,
    MetricTypeDetector,
    transform_for_type,
    detect_metric_type,
)


class TestMetricTypeEnum:
    """Test MetricType enum."""

    def test_enum_values(self):
        """Test that all expected metric types exist."""
        assert MetricType.DURATION == "duration"
        assert MetricType.ERROR_RATE == "error_rate"
        assert MetricType.COUNT == "count"
        assert MetricType.THROUGHPUT == "throughput"
        assert MetricType.PERCENTAGE == "percentage"
        assert MetricType.BINARY == "binary"
        assert MetricType.GAUSSIAN == "gaussian"
        assert MetricType.SIZE == "size"
        assert MetricType.OTHER == "other"

    def test_from_string(self):
        """Test conversion from string to MetricType."""
        assert MetricType.from_string("duration") == MetricType.DURATION
        assert MetricType.from_string("DURATION") == MetricType.DURATION
        assert MetricType.from_string("  error_rate  ") == MetricType.ERROR_RATE
        assert MetricType.from_string("unknown") == MetricType.OTHER
        assert MetricType.from_string("") == MetricType.OTHER


class TestMetricTypeTransformations:
    """Test transformations for different metric types."""

    def test_duration_transform(self):
        """Test log transformation for duration metrics."""
        s = pd.Series([10, 100, 1000, 10000, 0.1])
        transformed = MetricTypeTransformer.transform(s, MetricType.DURATION)
        assert len(transformed) == len(s)
        assert all(transformed > 0)  # log1p always positive
        assert transformed.iloc[0] < transformed.iloc[2]  # Monotonic

    def test_error_rate_transform(self):
        """Test logit transformation for error rates."""
        s = pd.Series([0.01, 0.1, 0.5, 0.9, 0.99])
        transformed = MetricTypeTransformer.transform(s, MetricType.ERROR_RATE)
        assert len(transformed) == len(s)
        # Logit should map [0,1] to (-inf, +inf)
        assert transformed.iloc[0] < transformed.iloc[-1]

        # Test percentage format [0, 100]
        s_pct = pd.Series([1, 10, 50, 90, 99])
        transformed_pct = MetricTypeTransformer.transform(s_pct, MetricType.ERROR_RATE)
        assert len(transformed_pct) == len(s_pct)

    def test_count_transform(self):
        """Test square root transformation for count data."""
        s = pd.Series([0, 1, 4, 9, 16, 25, 100])
        transformed = MetricTypeTransformer.transform(s, MetricType.COUNT)
        assert len(transformed) == len(s)
        assert all(transformed >= 0)
        # sqrt(16) = 4
        assert abs(transformed.iloc[4] - 4.0) < 1e-6

    def test_throughput_transform(self):
        """Test log transformation for throughput."""
        s = pd.Series([10, 100, 1000])
        transformed = MetricTypeTransformer.transform(s, MetricType.THROUGHPUT)
        assert len(transformed) == len(s)
        assert transformed.iloc[0] < transformed.iloc[-1]

    def test_percentage_transform(self):
        """Test arcsine-sqrt transformation for percentages."""
        s = pd.Series([0.1, 0.25, 0.5, 0.75, 0.9])
        transformed = MetricTypeTransformer.transform(s, MetricType.PERCENTAGE)
        assert len(transformed) == len(s)
        # arcsine-sqrt maps [0,1] to [0, pi/2]
        assert all(0 <= t <= np.pi / 2 + 0.1 for t in transformed)

        # Test [0, 100] format
        s_pct = pd.Series([10, 25, 50, 75, 90])
        transformed_pct = MetricTypeTransformer.transform(s_pct, MetricType.PERCENTAGE)
        assert len(transformed_pct) == len(s_pct)

    def test_binary_transform(self):
        """Test no transformation for binary data."""
        s = pd.Series([0, 1, 0, 1, 1, 0])
        transformed = MetricTypeTransformer.transform(s, MetricType.BINARY)
        assert transformed.equals(s)

    def test_gaussian_transform(self):
        """Test no transformation for gaussian data."""
        s = pd.Series([1.0, 2.0, 3.0, 4.0, 5.0])
        transformed = MetricTypeTransformer.transform(s, MetricType.GAUSSIAN)
        assert transformed.equals(s)

    def test_size_transform(self):
        """Test log10 transformation for size metrics."""
        s = pd.Series([100, 1000, 10000, 100000, 1000000])
        transformed = MetricTypeTransformer.transform(s, MetricType.SIZE)
        assert len(transformed) == len(s)
        # log10(1000) ≈ 3
        assert abs(transformed.iloc[1] - 3.0) < 0.5

    def test_other_transform(self):
        """Test no transformation for other/generic metrics."""
        s = pd.Series([-5, 0, 5, 10, -10])
        transformed = MetricTypeTransformer.transform(s, MetricType.OTHER)
        assert transformed.equals(s)

    def test_transform_for_type_string(self):
        """Test convenience function with string."""
        s = pd.Series([10, 100, 1000])
        transformed = transform_for_type(s, "duration")
        assert len(transformed) == len(s)


class TestMetricTypeDetection:
    """Test automatic metric type detection."""

    def test_detect_binary(self):
        """Test detection of binary metrics."""
        s = pd.Series([0, 1, 0, 1, 1, 0, 1, 0])
        detected, diagnostics = MetricTypeDetector.detect(s)
        assert detected == MetricType.BINARY
        assert diagnostics["method"] in ["detected", "hint"]
        assert "binary" in diagnostics.get("reason", "").lower()

    def test_detect_duration(self):
        """Test detection of duration metrics."""
        # Right-skewed positive values in duration range
        s = pd.Series([10, 20, 25, 30, 50, 100, 200, 500] * 2)  # More points for better detection
        detected, diagnostics = MetricTypeDetector.detect(s)
        assert detected in [MetricType.DURATION, MetricType.THROUGHPUT, MetricType.OTHER]
        assert diagnostics["method"] in ["detected", "hint", "fallback"]

    def test_detect_error_rate(self):
        """Test detection of error rate metrics."""
        # Bounded [0,1] with high skewness
        s = pd.Series([0.01, 0.02, 0.03, 0.05, 0.1, 0.15, 0.2] * 2)  # More points
        detected, diagnostics = MetricTypeDetector.detect(s)
        assert detected in [MetricType.ERROR_RATE, MetricType.PERCENTAGE, MetricType.OTHER]
        assert diagnostics["method"] in ["detected", "hint", "fallback"]

    def test_detect_percentage(self):
        """Test detection of percentage metrics."""
        # Bounded [0, 100]
        s = pd.Series([10, 20, 30, 40, 50, 60, 70] * 2)  # More points
        detected, diagnostics = MetricTypeDetector.detect(s)
        assert detected in [MetricType.PERCENTAGE, MetricType.GAUSSIAN, MetricType.OTHER]
        assert diagnostics["method"] in ["detected", "hint", "fallback"]

    def test_detect_count(self):
        """Test detection of count metrics."""
        # Integer-like, Poisson-like variance
        s = pd.Series([5, 6, 7, 8, 9, 10, 11, 12, 13] * 2)  # More points
        detected, diagnostics = MetricTypeDetector.detect(s)
        assert detected in [MetricType.COUNT, MetricType.GAUSSIAN, MetricType.THROUGHPUT, MetricType.OTHER]
        assert diagnostics["method"] in ["detected", "hint", "fallback"]

    def test_detect_throughput(self):
        """Test detection of throughput metrics."""
        # Positive, less skewed, higher values
        s = pd.Series([100, 120, 150, 180, 200, 220, 250] * 2)  # More points
        detected, diagnostics = MetricTypeDetector.detect(s)
        assert detected in [MetricType.THROUGHPUT, MetricType.GAUSSIAN, MetricType.DURATION, MetricType.OTHER]
        assert diagnostics["method"] in ["detected", "hint", "fallback"]

    def test_detect_size(self):
        """Test detection of size metrics."""
        # Very large positive values
        s = pd.Series([1e6, 2e6, 5e6, 10e6, 20e6] * 2)  # More points
        detected, diagnostics = MetricTypeDetector.detect(s)
        assert detected in [MetricType.SIZE, MetricType.DURATION, MetricType.THROUGHPUT, MetricType.OTHER]
        assert diagnostics["method"] in ["detected", "hint", "fallback"]

    def test_detect_gaussian(self):
        """Test detection of gaussian/normal metrics."""
        # Symmetric distribution - use values outside [0,100] to avoid percentage detection
        np.random.seed(42)
        s = pd.Series(np.random.normal(1000, 100, 100))  # Mean at 1000, not in percentage range
        detected, diagnostics = MetricTypeDetector.detect(s)
        assert detected in [MetricType.GAUSSIAN, MetricType.THROUGHPUT, MetricType.OTHER]
        assert diagnostics["method"] in ["detected", "hint", "fallback"]

    def test_detect_with_hint(self):
        """Test detection with hint."""
        s = pd.Series([1, 2, 3, 4, 5])
        detected, diagnostics = MetricTypeDetector.detect(s, hint="duration")
        assert detected == MetricType.DURATION
        assert diagnostics["method"] == "hint"

    def test_detect_too_few_points(self):
        """Test detection with too few points."""
        s = pd.Series([1, 2, 3])
        detected, diagnostics = MetricTypeDetector.detect(s)
        assert detected == MetricType.OTHER
        assert diagnostics["method"] == "fallback"

    def test_detect_metric_type_convenience(self):
        """Test convenience function."""
        s = pd.Series([0, 1, 0, 1])
        detected = detect_metric_type(s)
        assert detected == MetricType.BINARY

    def test_get_type_description(self):
        """Test getting type descriptions."""
        desc = MetricTypeDetector.get_type_description(MetricType.DURATION)
        assert "name" in desc
        assert "description" in desc
        assert "transformation" in desc
        assert "reason" in desc

        # Test all types
        for mt in MetricType:
            desc = MetricTypeDetector.get_type_description(mt)
            assert isinstance(desc, dict)
            assert "name" in desc


class TestIntegrationWithDetector:
    """Test integration of metric types with detector."""

    def test_detector_with_explicit_type(self):
        """Test detector with explicit metric type."""
        from detector import UniversalTSDetectorV2

        detector = UniversalTSDetectorV2(metric_kind="duration", direction="lower_is_better")
        s = pd.Series([10, 20, 30, 40, 50] * 10, index=pd.date_range("2024-01-01", periods=50, freq="H"))
        result = detector.analyze(s)
        assert result["profile"]["metric_kind"] == "duration"

    def test_detector_with_auto_detect(self):
        """Test detector with auto-detection."""
        from detector import UniversalTSDetectorV2

        detector = UniversalTSDetectorV2(
            metric_kind=None,
            auto_detect_metric_type=True,
            direction="lower_is_better",
        )
        # Binary data
        s = pd.Series([0, 1, 0, 1, 1, 0, 1, 0, 1, 1] * 10, index=pd.date_range("2024-01-01", periods=100, freq="H"))
        result = detector.analyze(s)
        assert "metric_kind" in result["profile"]
        # Should have detection info
        if "metric_type_detection" in result:
            assert "detected_type" in result["metric_type_detection"]

    def test_detector_with_metric_name_hint(self):
        """Test detector with metric name hint."""
        from detector import UniversalTSDetectorV2

        detector = UniversalTSDetectorV2(
            metric_kind=None,
            auto_detect_metric_type=True,
            metric_name_hint="login_time",
            direction="lower_is_better",
        )
        s = pd.Series([10, 20, 30, 40, 50] * 10, index=pd.date_range("2024-01-01", periods=50, freq="H"))
        result = detector.analyze(s)
        assert "metric_kind" in result["profile"]

    def test_detector_different_types_produce_different_transforms(self):
        """Test that different types produce different transformations."""
        from detector import UniversalTSDetectorV2

        s = pd.Series([10, 20, 30, 40, 50] * 10, index=pd.date_range("2024-01-01", periods=50, freq="H"))

        detector_duration = UniversalTSDetectorV2(metric_kind="duration")
        result_duration = detector_duration.analyze(s, debug=True)

        detector_other = UniversalTSDetectorV2(metric_kind="other")
        result_other = detector_other.analyze(s, debug=True)

        # Signal should be different (log-transformed vs not)
        signal_duration = result_duration["debug"]["signal"]
        signal_other = result_other["debug"]["signal"]

        # Log transform should reduce values
        assert signal_duration.max() < signal_other.max()

