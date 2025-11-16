from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional, Union

import pandas as pd
import numpy as np
import plotly.graph_objects as go


def _normalize_datetime(dt: Any) -> Optional[datetime]:
    """
    Convert various datetime types to Python datetime for Plotly compatibility.
    
    Handles:
    - None -> None
    - pandas Timestamp -> datetime
    - numpy datetime64 -> datetime
    - datetime -> datetime (passthrough)
    - str -> datetime (parsed)
    
    Args:
        dt: Datetime value in various formats
        
    Returns:
        Python datetime or None
    """
    if dt is None:
        return None
    
    if isinstance(dt, pd.Timestamp):
        return dt.to_pydatetime()
    
    if isinstance(dt, np.datetime64):
        return pd.Timestamp(dt).to_pydatetime()
    
    if isinstance(dt, datetime):
        return dt
    
    if isinstance(dt, str):
        try:
            # Try parsing common formats
            return pd.to_datetime(dt).to_pydatetime()
        except Exception:
            return None
    
    # Fallback: try to convert via pandas
    try:
        return pd.Timestamp(dt).to_pydatetime()
    except Exception:
        return None


def _series_to_trace(name: str, s: pd.Series, yaxis: str = "y") -> go.Scatter:
    """
    Convert pandas Series to Plotly Scatter trace, handling NaN values and empty series.
    """
    if s.empty or len(s) == 0:
        # Return empty trace if series is empty
        return go.Scatter(name=name, x=[], y=[], mode="lines", yaxis=yaxis)
    
    # Drop NaN values to avoid Plotly errors
    s_clean = s.dropna()
    if s_clean.empty or len(s_clean) == 0:
        # Return empty trace if all values are NaN
        return go.Scatter(name=name, x=[], y=[], mode="lines", yaxis=yaxis)
    
    x = s_clean.index
    if isinstance(x, pd.DatetimeIndex):
        x = x.to_pydatetime()
    
    # Ensure values are finite (not inf or NaN)
    y_values = s_clean.values
    if isinstance(y_values, np.ndarray):
        # Filter out inf and NaN
        finite_mask = np.isfinite(y_values)
        if not np.any(finite_mask):
            # All values are inf or NaN
            return go.Scatter(name=name, x=[], y=[], mode="lines", yaxis=yaxis)
        y_values = y_values[finite_mask]
        if isinstance(x, np.ndarray):
            x = x[finite_mask]
        elif hasattr(x, '__getitem__'):
            # For DatetimeIndex or Index, use boolean indexing
            x = x[finite_mask]
    
    return go.Scatter(name=name, x=x, y=y_values, mode="lines", yaxis=yaxis)


def time_series_figure(
    series_map: Dict[str, pd.Series],
    change_point: Optional[Any] = None,
) -> go.Figure:
    fig = go.Figure()
    
    # Map series keys to readable names and descriptions
    series_labels = {
        "raw_series": ("Raw values", "Исходные значения метрики"),
        "signal": ("Signal", "После лог-трансформации и десезонализации (STL)"),
        "short": ("Short-term trend", "Краткосрочный тренд (EWMA с коротким окном)"),
        "long": ("Long-term trend", "Долгосрочный тренд (EWMA с длинным окном)")
    }
    
    # Color mapping for better visual distinction
    colors = {
        "raw_series": "#888888",
        "signal": "#2563eb",
        "short": "#16a34a",
        "long": "#dc2626"
    }
    
    # Add traces, filtering out empty/invalid series
    for key in ["raw_series", "signal", "short", "long"]:
        if key in series_map:
            s = series_map[key]
            # Only add trace if series is valid and not empty
            if s is not None and not s.empty and len(s.dropna()) > 0:
                label, description = series_labels.get(key, (key, ""))
                trace = _series_to_trace(label, s)
                trace.line.color = colors.get(key, "#000000")
                trace.hovertemplate = f"<b>{label}</b><br>%{{x}}<br>%{{y}}<extra></extra>"
                # Only add if trace has data
                if len(trace.x) > 0 and len(trace.y) > 0:
                    fig.add_trace(trace)

    if change_point is not None:
        # Normalize datetime to Python datetime for Plotly compatibility
        change_point_normalized = _normalize_datetime(change_point)
        if change_point_normalized is not None:
            # Use add_shape instead of add_vline for datetime compatibility
            # add_vline tries to compute mean of datetime values, which fails
            fig.add_shape(
                type="line",
                x0=change_point_normalized,
                x1=change_point_normalized,
                y0=0,
                y1=1,
                yref="paper",
                line=dict(color="red", width=1, dash="dot"),
            )
            # Add annotation text separately
            fig.add_annotation(
                x=change_point_normalized,
                y=1,
                yref="paper",
                text="change_point",
                showarrow=False,
                xanchor="left",
                font=dict(color="red", size=10),
            )

    fig.update_layout(
        title=dict(
            text="Time Series: Raw Values and Trends",
            font=dict(size=16),
            x=0.5,
            xanchor="center"
        ),
        xaxis=dict(title="Time"),
        yaxis=dict(title="Metric Value"),
        margin=dict(l=60, r=10, t=60, b=50),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(size=11)
        ),
        hovermode="x unified",
        height=450,
    )
    return fig


def diagnostics_figure(series_map: Dict[str, pd.Series]) -> go.Figure:
    fig = go.Figure()
    
    # Map series keys to readable names
    series_labels = {
        "z": "Z-score (robust)",
        "rel": "Relative change",
        "cusum_pos": "CUSUM positive",
        "cusum_neg": "CUSUM negative"
    }
    
    colors = {
        "z": "#2563eb",
        "rel": "#7c3aed",
        "cusum_pos": "#16a34a",
        "cusum_neg": "#dc2626"
    }
    
    # rel and z on secondary/primary axes
    if "z" in series_map:
        s = series_map["z"]
        if s is not None and not s.empty and len(s.dropna()) > 0:
            tr = _series_to_trace(series_labels["z"], s)
            tr.line.color = colors["z"]
            tr.hovertemplate = f"<b>{series_labels['z']}</b><br>%{{x}}<br>%{{y}}<extra></extra>"
            if len(tr.x) > 0 and len(tr.y) > 0:
                fig.add_trace(tr)
    if "rel" in series_map:
        s = series_map["rel"]
        if s is not None and not s.empty and len(s.dropna()) > 0:
            tr = _series_to_trace(series_labels["rel"], s)
            tr.line.color = colors["rel"]
            tr.hovertemplate = f"<b>{series_labels['rel']}</b><br>%{{x}}<br>%{{y}}<extra></extra>"
            if len(tr.x) > 0 and len(tr.y) > 0:
                tr.yaxis = "y2"
                fig.add_trace(tr)
    if "cusum_pos" in series_map:
        s = series_map["cusum_pos"]
        if s is not None and not s.empty and len(s.dropna()) > 0:
            tr = _series_to_trace(series_labels["cusum_pos"], s)
            tr.line.color = colors["cusum_pos"]
            tr.hovertemplate = f"<b>{series_labels['cusum_pos']}</b><br>%{{x}}<br>%{{y}}<extra></extra>"
            if len(tr.x) > 0 and len(tr.y) > 0:
                fig.add_trace(tr)
    if "cusum_neg" in series_map:
        s = series_map["cusum_neg"]
        if s is not None and not s.empty and len(s.dropna()) > 0:
            tr = _series_to_trace(series_labels["cusum_neg"], s)
            tr.line.color = colors["cusum_neg"]
            tr.hovertemplate = f"<b>{series_labels['cusum_neg']}</b><br>%{{x}}<br>%{{y}}<extra></extra>"
            if len(tr.x) > 0 and len(tr.y) > 0:
                fig.add_trace(tr)

    fig.update_layout(
        title=dict(
            text="Diagnostics: Z-score, Relative Change, and CUSUM",
            font=dict(size=16),
            x=0.5,
            xanchor="center"
        ),
        xaxis=dict(title="Time"),
        yaxis=dict(
            title="Z-score / CUSUM",
            side="left",
            showgrid=True,
            zeroline=True,
            zerolinecolor="gray",
            zerolinewidth=1
        ),
        yaxis2=dict(
            title="Relative change (%)",
            overlaying="y",
            side="right",
            showgrid=False,
            zeroline=False
        ),
        margin=dict(l=70, r=70, t=60, b=50),
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            font=dict(size=11)
        ),
        hovermode="x unified",
        height=450,
    )
    return fig


