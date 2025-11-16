from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict

from .run_from_config import (
    load_config,
    run_from_file,
    fetch_dataset_to_file,
    analyze_from_saved,
)


def cmd_save_dataset(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    out = fetch_dataset_to_file(cfg, args.path, fmt=args.fmt)
    print(f"Saved dataset to {out}")
    return 0


def cmd_analyze_many(args: argparse.Namespace) -> int:
    cfg = load_config(args.config)
    if args.dataset_path:
        results: Dict[str, Any] = analyze_from_saved(cfg, args.dataset_path, fmt=args.fmt)
    else:
        # If dataset_path is not provided, fetch and analyze live
        results = run_from_file(args.config)
    # Convert non-JSON-serializable keys (e.g., tuples) to strings
    def stringify_keys(obj):
        if isinstance(obj, dict):
            return {str(k): stringify_keys(v) for k, v in obj.items()}
        if isinstance(obj, list):
            return [stringify_keys(v) for v in obj]
        return obj

    serializable = stringify_keys(results)

    def default(o):
        try:
            return str(o)
        except Exception:
            return "<unserializable>"
    print(json.dumps(serializable, indent=2, default=default))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="mimir",
        description="MiMiR CLI: fetch datasets and run analysis from config",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    p_save = sub.add_parser("save_dataset", help="Fetch dataset and save to file")
    p_save.add_argument("--config", required=True, help="Path to YAML config")
    p_save.add_argument("--path", required=True, help="Output dataset path (csv/jsonl)")
    p_save.add_argument("--fmt", required=False, help="Output format: csv or jsonl. If omitted, inferred from file extension.")
    p_save.set_defaults(func=cmd_save_dataset)

    p_an = sub.add_parser("analyze_many", help="Run analysis")
    p_an.add_argument("--config", required=True, help="Path to YAML config")
    p_an.add_argument(
        "--dataset_path",
        required=False,
        help="Optional path to previously saved dataset (csv/jsonl). If omitted, data will be fetched live.",
    )
    p_an.add_argument("--fmt", required=False, help="Dataset format: csv or jsonl. If omitted, inferred from file extension.")
    p_an.set_defaults(func=cmd_analyze_many)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    sys.exit(main())


