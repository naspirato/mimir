from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Dict, Optional

import pandas as pd
import streamlit as st

from .service import (
    list_config_paths,
    get_config_summary,
    ensure_data_dirs,
    default_saved_dataset_path,
    fetch_dataset,
    analyze_live,
    analyze_from_file,
    results_to_table,
    extract_debug_series,
)
from .viz import time_series_figure, diagnostics_figure


st.set_page_config(page_title="MiMiR – Config → Fetch → Analyze → Visualize", layout="wide")


@st.cache_data
def cached_config_summary(path: str) -> Dict[str, Any]:
    s = get_config_summary(path)
    return s.__dict__


@st.cache_data
def cached_fetch(config_path: str, out_path: str, fmt: Optional[str]) -> Dict[str, Any]:
    saved_path, n_rows = fetch_dataset(config_path, out_path, fmt=fmt)
    return {"saved_path": saved_path, "n_rows": n_rows}


@st.cache_data(show_spinner=False)
def cached_analyze_live(config_path: str) -> Dict[str, Any]:
    return analyze_live(config_path)


@st.cache_data(show_spinner=False)
def cached_analyze_from_file(config_path: str, dataset_path: str) -> Dict[str, Any]:
    return analyze_from_file(config_path, dataset_path)


def main() -> None:
    st.title("MiMiR – Config → Fetch → Analyze → Visualize")
    st.caption("MVP Streamlit UI over detector.run_from_config")

    # Sidebar: config picker
    st.sidebar.header("Configuration")
    cfg_paths = list_config_paths("configs")
    if not cfg_paths:
        st.sidebar.error("No configs found in `configs/`")
        return
    cfg_path = st.sidebar.selectbox("Select config", options=cfg_paths, index=0)
    summary = cached_config_summary(cfg_path)
    st.sidebar.json(
        {
            "adapter": summary["adapter"],
            "timestamp_field": summary["timestamp_field"],
            "value_field": summary["value_field"],
            "context_fields": summary["context_fields"],
            "meta_fields": summary["meta_fields"],
            "debug": summary["debug"],
        },
        expanded=False,
    )

    cfg_stem = Path(cfg_path).stem
    dir_map = ensure_data_dirs("data", cfg_stem)

    with st.expander("Directories", expanded=False):
        st.write(dir_map)

    tab_fetch, tab_analyze, tab_results = st.tabs(["1) Fetch", "2) Analyze", "3) Results"])

    # 1) Fetch
    with tab_fetch:
        st.subheader("Fetch dataset to file")
        fmt = st.selectbox("Format", options=["csv", "jsonl"], index=0)
        default_path = default_saved_dataset_path(dir_map, fmt=fmt)
        out_path = st.text_input("Output path", value=default_path)
        if st.button("Fetch dataset", type="primary"):
            with st.spinner("Fetching..."):
                res = cached_fetch(cfg_path, out_path, fmt)
            st.success(f"Saved to {res['saved_path']}, rows={res['n_rows']}")
            # Preview a few rows
            df_preview: Optional[pd.DataFrame] = None
            try:
                if res["saved_path"].lower().endswith(".csv"):
                    df_preview = pd.read_csv(res["saved_path"]).head(50)
                else:
                    df_preview = pd.read_json(res["saved_path"], orient="records", lines=True).head(50)
            except Exception as e:
                st.warning(f"Could not read preview: {e}")
            if df_preview is not None:
                st.dataframe(df_preview, use_container_width=True, hide_index=True)

    # 2) Analyze
    with tab_analyze:
        st.subheader("Analyze")
        col1, col2 = st.columns(2)
        with col1:
            if st.button("Analyze live (load via adapter)"):
                with st.spinner("Analyzing (live)..."):
                    results_live = cached_analyze_live(cfg_path)
                st.session_state["last_results"] = results_live
                st.success("Live analysis complete")
        with col2:
            saved_path_guess = default_saved_dataset_path(dir_map, fmt="csv")
            dataset_path = st.text_input("Analyze from saved dataset", value=saved_path_guess)
            if st.button("Analyze from saved file"):
                with st.spinner("Analyzing (from saved)..."):
                    results_saved = cached_analyze_from_file(cfg_path, dataset_path)
                st.session_state["last_results"] = results_saved
                st.success("Analysis from saved file complete")

        # Quick glance at the raw JSON size
        if "last_results" in st.session_state:
            res = st.session_state["last_results"]
            st.caption(f"Results contexts: {len(res)}")

    # 3) Results
    with tab_results:
        st.subheader("Results browser")
        if "last_results" not in st.session_state:
            st.info("Run analysis in tab 2 to see results here.")
        else:
            results = st.session_state["last_results"]
            table = results_to_table(results)
            st.dataframe(table, use_container_width=True, hide_index=True)

            # Select a row by context
            # Build a simple selector based on stringified context for uniqueness
            context_options = []
            ctx_to_key: Dict[str, Any] = {}
            for key, res in results.items():
                ctx = res.get("context", {})
                label = json.dumps(ctx, ensure_ascii=False, sort_keys=True)
                context_options.append(label)
                ctx_to_key[label] = key
            if context_options:
                selected = st.selectbox("Select context", options=context_options, index=0)
                sel_key = ctx_to_key[selected]
                res = results[sel_key]

                det = res.get("detector_result", {})
                with st.container():
                    st.markdown("**Current state**")
                    st.json(
                        {
                            "state": res.get("current_state"),
                            "z_score": det.get("z_score"),
                            "rel_change": det.get("rel_change"),
                            "severity": det.get("severity"),
                            "confidence": det.get("confidence"),
                            "risk": det.get("risk"),
                            "change_point": det.get("change_point"),
                        },
                        expanded=False,
                    )
                    if "meta_last" in res:
                        st.markdown("**Meta (last)**")
                        st.json(res.get("meta_last"), expanded=False)

                # Plots
                series_map = extract_debug_series(res)
                if not series_map:
                    st.info("Debug series are not available. Enable debug in the config to see charts.")
                else:
                    cp = det.get("change_point")
                    fig_main = time_series_figure(series_map, change_point=cp)
                    st.plotly_chart(fig_main, use_container_width=True)

                    fig_diag = diagnostics_figure(series_map)
                    st.plotly_chart(fig_diag, use_container_width=True)


if __name__ == "__main__":
    main()


