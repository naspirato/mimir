from __future__ import annotations

from typing import Any, Dict, Optional

import pandas as pd
import plotly.graph_objects as go


def _series_to_trace(name: str, s: pd.Series, yaxis: str = "y") -> go.Scatter:
    x = s.index
    if isinstance(x, pd.DatetimeIndex):
        x = x.to_pydatetime()
    return go.Scatter(name=name, x=x, y=s.values, mode="lines", yaxis=yaxis)


def time_series_figure(
    series_map: Dict[str, pd.Series],
    change_point: Optional[Any] = None,
) -> go.Figure:
    fig = go.Figure()
    if "raw_series" in series_map:
        fig.add_trace(_series_to_trace("raw", series_map["raw_series"]))
    if "signal" in series_map:
        fig.add_trace(_series_to_trace("signal", series_map["signal"]))
    if "short" in series_map:
        fig.add_trace(_series_to_trace("short", series_map["short"]))
    if "long" in series_map:
        fig.add_trace(_series_to_trace("long", series_map["long"]))

    if change_point is not None:
        fig.add_vline(x=change_point, line_color="red", line_dash="dot", annotation_text="change_point")

    fig.update_layout(
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified",
    )
    return fig


def diagnostics_figure(series_map: Dict[str, pd.Series]) -> go.Figure:
    fig = go.Figure()
    # rel and z on secondary/primary axes
    if "z" in series_map:
        tr = _series_to_trace("z", series_map["z"])
        fig.add_trace(tr)
    if "rel" in series_map:
        tr = _series_to_trace("rel", series_map["rel"])
        tr.yaxis = "y2"
        fig.add_trace(tr)
    if "cusum_pos" in series_map:
        fig.add_trace(_series_to_trace("cusum_pos", series_map["cusum_pos"]))
    if "cusum_neg" in series_map:
        fig.add_trace(_series_to_trace("cusum_neg", series_map["cusum_neg"]))

    fig.update_layout(
        margin=dict(l=10, r=10, t=30, b=10),
        legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1),
        hovermode="x unified",
        yaxis2=dict(overlaying="y", side="right", showgrid=False, zeroline=False),
    )
    return fig


