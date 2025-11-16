from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Optional
from urllib.parse import unquote

import numpy as np
import pandas as pd
from flask import Flask, render_template, request, redirect, url_for, flash
from plotly.io import to_json as plotly_to_json

from webapp.service import (
    list_config_paths,
    get_config_summary,
    ensure_data_dirs,
    default_saved_dataset_path,
    fetch_dataset,
    analyze_live,
    analyze_from_file,
    results_to_table,
    group_results_by_context,
    extract_debug_series,
    json_sanitize,
)
from webapp.viz import time_series_figure, diagnostics_figure


app = Flask(__name__, static_folder='resources', static_url_path='/static')
app.secret_key = "mimir-secret-key"  # for flash messages (replace in prod)


def _get_configs() -> Dict[str, Dict[str, Any]]:
    configs = {}
    for p in list_config_paths("configs"):
        s = get_config_summary(p)
        configs[p] = asdict(s)
    return configs


@app.route("/", methods=["GET"])
def index():
    configs = _get_configs()
    selected = request.args.get("config") or next(iter(configs.keys()), None)
    fmt = request.args.get("fmt") or "csv"
    saved_path: Optional[str] = request.args.get("saved_path")
    cfg_stem = Path(selected).stem if selected else "dataset"
    dir_map = ensure_data_dirs("data", cfg_stem) if selected else {"raw": "data/raw"}
    default_out = default_saved_dataset_path(dir_map, fmt=fmt) if selected else ""
    return render_template(
        "index.html",
        configs=configs,
        selected=selected,
        fmt=fmt,
        default_out=default_out,
        saved_path=saved_path,
    )


@app.route("/fetch", methods=["POST"])
def fetch():
    config_path = request.form.get("config_path")
    fmt = request.form.get("fmt") or "csv"
    out_path = request.form.get("out_path")
    if not config_path or not out_path:
        flash("Config and output path are required", "error")
        return redirect(url_for("index"))
    # Ensure absolute path and parent directory exists
    from pathlib import Path
    out_path_obj = Path(out_path)
    if not out_path_obj.is_absolute():
        # If relative, make it relative to current working directory
        out_path = str(out_path_obj.resolve())
    # Parent directory will be created in fetch_dataset_to_file, but double-check here
    Path(out_path).parent.mkdir(parents=True, exist_ok=True)
    saved_path, n_rows = fetch_dataset(config_path, out_path, fmt=fmt)
    # Try to preview
    preview: Optional[pd.DataFrame] = None
    try:
        if saved_path.lower().endswith(".csv"):
            preview = pd.read_csv(saved_path).head(50)
        else:
            preview = pd.read_json(saved_path, orient="records", lines=True).head(50)
    except Exception as e:
        flash(f"Could not read preview: {e}", "warning")
    preview_records = preview.to_dict(orient="records") if isinstance(preview, pd.DataFrame) else []
    flash(f"Saved {n_rows} rows to {saved_path}", "success")
    return render_template(
        "fetch.html",
        config_path=config_path,
        fmt=fmt,
        saved_path=saved_path,
        preview_records=preview_records,
    )


@app.route("/analyze_live", methods=["POST"])
def analyze_live_route():
    config_path = request.form.get("config_path")
    if not config_path:
        flash("Config is required", "error")
        return redirect(url_for("index"))
    from detector.run_from_config import load_config
    cfg = load_config(config_path)
    results = analyze_live(config_path)
    # Group by context without metric_name
    context_fields = cfg.analysis.context_fields
    context_fields_without_metric = [f for f in context_fields if f != "metric_name"]
    if context_fields_without_metric:
        grouped_results = group_results_by_context(results, context_fields_without_metric)
    else:
        # Fallback to flat structure if no grouping possible
        table = results_to_table(results)
        grouped_results = [{"group_key": "", "group_context": {}, "metrics": table.to_dict(orient="records"), "max_risk": 0}]
    return render_template(
        "results.html",
        config_path=config_path,
        results=results,
        grouped_results=grouped_results,
        table_records=None,
        saved_path=None,
    )


@app.route("/analyze_saved", methods=["POST"])
def analyze_saved_route():
    config_path = request.form.get("config_path")
    dataset_path = request.form.get("dataset_path")
    if not config_path or not dataset_path:
        flash("Config and dataset path are required", "error")
        return redirect(url_for("index"))
    from detector.run_from_config import load_config
    cfg = load_config(config_path)
    results = analyze_from_file(config_path, dataset_path)
    # Group by context without metric_name
    context_fields = cfg.analysis.context_fields
    context_fields_without_metric = [f for f in context_fields if f != "metric_name"]
    if context_fields_without_metric:
        grouped_results = group_results_by_context(results, context_fields_without_metric)
    else:
        # Fallback to flat structure if no grouping possible
        table = results_to_table(results)
        grouped_results = [{"group_key": "", "group_context": {}, "metrics": table.to_dict(orient="records"), "max_risk": 0}]
    return render_template(
        "results.html",
        config_path=config_path,
        results=results,
        grouped_results=grouped_results,
        table_records=None,
        saved_path=dataset_path,
    )


@app.route("/context_plot", methods=["GET"])
def context_plot():
    # Query params: config_path, saved_path (optional), ctx (json-encoded context dict)
    config_path = request.args.get("config_path")
    saved_path = request.args.get("saved_path")
    ctx_raw = request.args.get("ctx")
    if not (config_path and ctx_raw):
        return {"error": "Missing params"}, 400
    # Re-run analysis to get the same result dict; for MVP simplicity
    # Force debug=True for visualization, even if config has debug=False
    if saved_path:
        results = analyze_from_file(config_path, saved_path, force_debug=True)
    else:
        results = analyze_live(config_path, force_debug=True)
    # Parse context dict from JSON and find matching entry by 'context' equality
    # Flask auto-decodes URL params, but sometimes we get double-encoded strings
    try:
        # Try to decode if still URL-encoded (contains %)
        if '%' in ctx_raw:
            ctx_raw = unquote(ctx_raw)
        ctx_dict = json.loads(ctx_raw)
    except (json.JSONDecodeError, UnicodeDecodeError) as e:
        app.logger.error(f"Failed to parse context JSON: {e}, raw: {ctx_raw[:200]}")
        return {"error": f"Invalid context JSON: {e}"}, 400
    
    if not isinstance(ctx_dict, dict):
        return {"error": "Context must be a dict"}, 400
    
    # Normalize the incoming context for comparison
    ctx_dict_normalized = json_sanitize(ctx_dict)
    
    res = None
    for ctx_key, v in results.items():
        result_ctx = v.get("context", {})
        # Normalize result context for comparison
        result_ctx_normalized = json_sanitize(result_ctx)
        if result_ctx_normalized == ctx_dict_normalized:
            res = v
            break
    
    if res is None:
        # Log available contexts for debugging
        available_contexts = [json_sanitize(v.get("context", {})) for v in results.values()]
        app.logger.warning(
            f"Context not found. Looking for: {ctx_dict_normalized}, "
            f"Available contexts: {available_contexts[:5]}..."
        )
        return {"error": "Context not found"}, 404
    series_map = extract_debug_series(res)
    det = res.get("detector_result", {})
    cp = det.get("change_point")
    fig_main = time_series_figure(series_map, change_point=cp)
    fig_diag = diagnostics_figure(series_map)
    
    # Convert to JSON and clean NaN values
    main_json = json.loads(plotly_to_json(fig_main))
    diag_json = json.loads(plotly_to_json(fig_diag))
    
    # Recursively clean NaN values from Plotly JSON
    def clean_plotly_json(obj):
        """Remove NaN and inf values from Plotly JSON structure"""
        if isinstance(obj, dict):
            # Special handling for Plotly trace data - preserve x/y pairs
            if 'x' in obj and 'y' in obj and isinstance(obj['x'], list) and isinstance(obj['y'], list):
                x_list = obj['x']
                y_list = obj['y']
                # Filter out NaN pairs while keeping x/y synchronized
                cleaned_x = []
                cleaned_y = []
                for i in range(min(len(x_list), len(y_list))):
                    x_val = x_list[i]
                    y_val = y_list[i]
                    # Check if either is NaN/inf
                    x_is_bad = isinstance(x_val, float) and (np.isnan(x_val) or np.isinf(x_val))
                    y_is_bad = isinstance(y_val, float) and (np.isnan(y_val) or np.isinf(y_val))
                    if not (x_is_bad or y_is_bad):
                        cleaned_x.append(clean_plotly_json(x_val))
                        cleaned_y.append(clean_plotly_json(y_val))
                result = {k: clean_plotly_json(v) for k, v in obj.items()}
                result['x'] = cleaned_x
                result['y'] = cleaned_y
                return result
            return {k: clean_plotly_json(v) for k, v in obj.items()}
        elif isinstance(obj, list):
            cleaned = []
            for item in obj:
                cleaned_item = clean_plotly_json(item)
                # Skip NaN and inf values in lists (but preserve structure for x/y arrays)
                if isinstance(cleaned_item, float):
                    if not (np.isnan(cleaned_item) or np.isinf(cleaned_item)):
                        cleaned.append(cleaned_item)
                elif cleaned_item is not None:
                    cleaned.append(cleaned_item)
            return cleaned
        elif isinstance(obj, float):
            if np.isnan(obj) or np.isinf(obj):
                return None  # Replace NaN/inf with None, which JSON can handle
            return obj
        return obj
    
    main_json = clean_plotly_json(main_json)
    diag_json = clean_plotly_json(diag_json)
    
    # Sanitize all data for JSON serialization
    result = {
        "main": main_json,
        "diag": diag_json,
        "state": json_sanitize(res.get("current_state")),
        "detector_result": json_sanitize(det),
        "meta_last": json_sanitize(res.get("meta_last")),
        "context": json_sanitize(res.get("context")),
    }
    return result


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)


