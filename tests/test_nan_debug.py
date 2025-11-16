"""Debug test to find NaN sources in the analysis pipeline"""
import json
import pandas as pd
import numpy as np
from pathlib import Path

from detector.run_from_config import load_config, load_dataset, analyze_from_saved
from webapp.viz import time_series_figure, diagnostics_figure
from webapp.service import extract_debug_series
from plotly.io import to_json as plotly_to_json


def test_nan_in_pipeline():
    """Test the full pipeline for NaN values"""
    config_path = "configs/tpcc_performance_explicit.yaml"
    dataset_path = "data/tpcc_performance_explicit/raw/dataset.csv"
    
    print("=" * 80)
    print("Testing NaN in pipeline")
    print("=" * 80)
    
    # 1. Load config and data
    print("\n1. Loading config and data...")
    cfg = load_config(config_path)
    df = pd.read_csv(dataset_path)
    print(f"   Dataset shape: {df.shape}")
    print(f"   Columns: {df.columns.tolist()}")
    
    # 2. Filter by context
    context = {
        'cluster': 'perf2',
        'warehouses': 12000,
        'git_branch': 'origin/main',
        'run_type': 'latency',
        'metric_name': 'newOrderLatency90'
    }
    print(f"\n2. Filtering by context: {context}")
    
    context_fields = cfg.analysis.context_fields
    filter_mask = pd.Series([True] * len(df))
    for field in context_fields:
        if field in df.columns:
            if field == 'warehouses':
                filter_mask &= (df[field] == context[field])
            else:
                filter_mask &= (df[field] == str(context[field]))
    
    df_filtered = df[filter_mask].copy()
    print(f"   Filtered rows: {len(df_filtered)}")
    print(f"   First few rows:")
    print(df_filtered.head())
    
    # 3. Check for NaN in input data
    print(f"\n3. Checking for NaN in input data:")
    print(f"   NaN counts: {df_filtered.isna().sum().to_dict()}")
    
    # 4. Run analysis
    print(f"\n4. Running analysis...")
    results = analyze_from_saved(cfg, dataset_path)
    print(f"   Number of result contexts: {len(results)}")
    
    # 5. Find our specific context result
    print(f"\n5. Finding result for context: {context}")
    target_res = None
    for ctx_key, res in results.items():
        res_ctx = res.get("context", {})
        if all(res_ctx.get(k) == v for k, v in context.items()):
            target_res = res
            print(f"   Found matching result!")
            break
    
    if target_res is None:
        print("   ERROR: No matching result found!")
        print(f"   Available contexts:")
        for ctx_key, res in list(results.items())[:5]:
            print(f"     {res.get('context', {})}")
        return
    
    # 6. Check debug series for NaN
    print(f"\n6. Checking debug series for NaN:")
    debug = target_res.get("debug", {})
    print(f"   Debug dict keys: {list(debug.keys()) if debug else 'None'}")
    print(f"   Config debug setting: {cfg.analysis.output.debug}")
    
    series_map = extract_debug_series(target_res)
    print(f"   Series map keys: {list(series_map.keys())}")
    
    for name, series in series_map.items():
        nan_count = series.isna().sum()
        inf_count = np.isinf(series).sum() if hasattr(series, 'values') else 0
        print(f"   {name}: shape={series.shape}, NaN={nan_count}, inf={inf_count}")
        if nan_count > 0 or inf_count > 0:
            print(f"      First few values: {series.head(10).tolist()}")
            print(f"      NaN positions: {series[series.isna()].index[:10].tolist()}")
        if len(series) > 0:
            print(f"      Sample values (first 5): {series.head(5).tolist()}")
            print(f"      Sample values (last 5): {series.tail(5).tolist()}")
    
    # 7. Create figures
    print(f"\n7. Creating figures...")
    det = target_res.get("detector_result", {})
    cp = det.get("change_point")
    print(f"   Change point: {cp} (type: {type(cp)})")
    
    fig_main = time_series_figure(series_map, change_point=cp)
    fig_diag = diagnostics_figure(series_map)
    
    # 8. Check traces for NaN
    print(f"\n8. Checking Plotly traces for NaN:")
    for i, trace in enumerate(fig_main.data):
        x_has_nan = any(pd.isna(x) if isinstance(x, (int, float)) or hasattr(x, '__iter__') else False for x in trace.x)
        y_has_nan = any(pd.isna(y) if isinstance(y, (int, float)) or hasattr(y, '__iter__') else False for y in trace.y)
        print(f"   Main trace {i} ({trace.name}): x_has_nan={x_has_nan}, y_has_nan={y_has_nan}")
        if x_has_nan or y_has_nan:
            x_list = list(trace.x) if hasattr(trace.x, '__iter__') else [trace.x]
            y_list = list(trace.y) if hasattr(trace.y, '__iter__') else [trace.y]
            x_nan_indices = [i for i, x in enumerate(x_list) if isinstance(x, float) and (np.isnan(x) or np.isinf(x))]
            y_nan_indices = [i for i, y in enumerate(y_list) if isinstance(y, float) and (np.isnan(y) or np.isinf(y))]
            print(f"      x NaN indices: {x_nan_indices[:10]}")
            print(f"      y NaN indices: {y_nan_indices[:10]}")
    
    for i, trace in enumerate(fig_diag.data):
        x_has_nan = any(pd.isna(x) if isinstance(x, (int, float)) or hasattr(x, '__iter__') else False for x in trace.x)
        y_has_nan = any(pd.isna(y) if isinstance(y, (int, float)) or hasattr(y, '__iter__') else False for y in trace.y)
        print(f"   Diag trace {i} ({trace.name}): x_has_nan={x_has_nan}, y_has_nan={y_has_nan}")
    
    # 9. Convert to JSON and check for NaN
    print(f"\n9. Converting to JSON and checking for NaN...")
    main_json = json.loads(plotly_to_json(fig_main))
    diag_json = json.loads(plotly_to_json(fig_diag))
    
    def find_nan_in_json(obj, path="", max_depth=10):
        """Recursively find NaN values in JSON structure"""
        if max_depth <= 0:
            return []
        nan_paths = []
        if isinstance(obj, dict):
            for k, v in obj.items():
                nan_paths.extend(find_nan_in_json(v, f"{path}.{k}" if path else k, max_depth - 1))
        elif isinstance(obj, list):
            for i, item in enumerate(obj):
                nan_paths.extend(find_nan_in_json(item, f"{path}[{i}]", max_depth - 1))
        elif isinstance(obj, float):
            if np.isnan(obj) or np.isinf(obj):
                nan_paths.append((path, obj))
        return nan_paths
    
    main_nans = find_nan_in_json(main_json)
    diag_nans = find_nan_in_json(diag_json)
    
    print(f"   Main JSON NaN paths: {len(main_nans)}")
    for path, val in main_nans[:10]:
        print(f"      {path}: {val}")
    
    print(f"   Diag JSON NaN paths: {len(diag_nans)}")
    for path, val in diag_nans[:10]:
        print(f"      {path}: {val}")
    
    # 10. Test cleaning function (copy from app.py)
    print(f"\n10. Testing with cleaning function...")
    
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
                if isinstance(cleaned_item, float):
                    if not (np.isnan(cleaned_item) or np.isinf(cleaned_item)):
                        cleaned.append(cleaned_item)
                elif cleaned_item is not None:
                    cleaned.append(cleaned_item)
            return cleaned
        elif isinstance(obj, float):
            if np.isnan(obj) or np.isinf(obj):
                return None
            return obj
        return obj
    
    main_json_cleaned = clean_plotly_json(main_json)
    diag_json_cleaned = clean_plotly_json(diag_json)
    
    main_nans_after = find_nan_in_json(main_json_cleaned)
    diag_nans_after = find_nan_in_json(diag_json_cleaned)
    
    print(f"   Main JSON NaN paths after cleaning: {len(main_nans_after)}")
    print(f"   Diag JSON NaN paths after cleaning: {len(diag_nans_after)}")
    
    print("\n" + "=" * 80)
    print("Test completed!")
    print("=" * 80)


if __name__ == "__main__":
    test_nan_in_pipeline()

