from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any, Dict, Optional

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
    extract_debug_series,
)
from webapp.viz import time_series_figure, diagnostics_figure


app = Flask(__name__)
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
    results = analyze_live(config_path)
    table = results_to_table(results)
    table_records = table.to_dict(orient="records")
    return render_template(
        "results.html",
        config_path=config_path,
        results=results,
        table_records=table_records,
        saved_path=None,
    )


@app.route("/analyze_saved", methods=["POST"])
def analyze_saved_route():
    config_path = request.form.get("config_path")
    dataset_path = request.form.get("dataset_path")
    if not config_path or not dataset_path:
        flash("Config and dataset path are required", "error")
        return redirect(url_for("index"))
    results = analyze_from_file(config_path, dataset_path)
    table = results_to_table(results)
    table_records = table.to_dict(orient="records")
    return render_template(
        "results.html",
        config_path=config_path,
        results=results,
        table_records=table_records,
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
    if saved_path:
        results = analyze_from_file(config_path, saved_path)
    else:
        results = analyze_live(config_path)
    # Parse context dict from JSON and find matching entry by 'context' equality
    try:
        ctx_dict = json.loads(ctx_raw)
    except Exception:
        ctx_dict = None
    res = None
    if isinstance(ctx_dict, dict):
        for _, v in results.items():
            if v.get("context") == ctx_dict:
                res = v
                break
    if res is None:
        return {"error": "Context not found"}, 404
    if not res:
        return {"error": "Context not found"}, 404
    series_map = extract_debug_series(res)
    det = res.get("detector_result", {})
    cp = det.get("change_point")
    fig_main = time_series_figure(series_map, change_point=cp)
    fig_diag = diagnostics_figure(series_map)
    return {
        "main": json.loads(plotly_to_json(fig_main)),
        "diag": json.loads(plotly_to_json(fig_diag)),
        "state": res.get("current_state"),
        "detector_result": det,
        "meta_last": res.get("meta_last"),
        "context": res.get("context"),
    }


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=True)


