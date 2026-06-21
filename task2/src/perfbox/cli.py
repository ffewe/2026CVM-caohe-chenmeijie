from __future__ import annotations

import argparse
import json
from pathlib import Path

from .collector import cleanup_old_samples, start_collection
from .config import load_config
from .flame import DEFAULT_FLAMEGRAPH_DIR, build_flamegraph, default_flamegraph_dir
from .query import human_size, load_valid_windows, parse_time, window_to_json, windows_overlapping
from .web import start_web_server


def positive_int(value: str) -> int:
    parsed = int(value)
    if parsed <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return parsed


def add_common_config(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--window-seconds", type=positive_int, help="seconds per perf record window")
    parser.add_argument("--freq", type=positive_int, help="perf sampling frequency in Hz")
    parser.add_argument("--retention-hours", type=positive_int, help="hours of perf.data history to keep")
    parser.add_argument("--data-dir", help="directory for perf.data windows and index.jsonl")
    parser.add_argument("--perf-bin", help="perf executable path")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="perfbox",
        description="Local continuous CPU profiling collector for task2.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    start = subparsers.add_parser("start", help="continuously collect perf.data windows")
    add_common_config(start)

    clean = subparsers.add_parser("clean", help="delete perf.data files older than the retention window")
    clean.add_argument("--retention-hours", type=positive_int, help="hours of perf.data history to keep")
    clean.add_argument("--data-dir", help="directory for perf.data windows and index.jsonl")

    list_cmd = subparsers.add_parser("list", help="list valid perf.data windows from index.jsonl")
    list_cmd.add_argument("--data-dir", help="directory for perf.data windows and index.jsonl")
    list_cmd.add_argument("--json", action="store_true", help="print machine-readable JSON")

    query = subparsers.add_parser("query", help="find perf.data windows overlapping a time range")
    query.add_argument("--from", dest="query_from", required=True, help="range start, e.g. '2026-06-18 23:36:00'")
    query.add_argument("--to", dest="query_to", required=True, help="range end, e.g. '2026-06-18 23:40:00'")
    query.add_argument("--data-dir", help="directory for perf.data windows and index.jsonl")
    query.add_argument("--json", action="store_true", help="print machine-readable JSON")

    flame = subparsers.add_parser("flame", help="generate a flame graph SVG for a time range")
    flame.add_argument("--from", dest="query_from", required=True, help="range start, e.g. '2026-06-18 23:36:00'")
    flame.add_argument("--to", dest="query_to", required=True, help="range end, e.g. '2026-06-18 23:40:00'")
    flame.add_argument("--data-dir", help="directory for perf.data windows and index.jsonl")
    flame.add_argument("--output", help="output SVG path; .perfscript and .folded are written beside it")
    flame.add_argument(
        "--flamegraph-dir",
        help=f"FlameGraph directory; defaults to FLAMEGRAPH_DIR or {DEFAULT_FLAMEGRAPH_DIR}",
    )
    flame.add_argument("--perf-bin", help="perf executable path")

    web = subparsers.add_parser("web", help="start the web UI and collector")
    add_common_config(web)
    web.add_argument("--host", default="127.0.0.1", help="bind address for the web server")
    web.add_argument("--port", type=positive_int, default=8080, help="port for the web server")
    web.add_argument(
        "--no-collector",
        action="store_true",
        help="serve the UI without starting the collector subprocess",
    )

    return parser


def print_windows(windows, *, as_json: bool) -> None:
    if as_json:
        print(json.dumps([window_to_json(window) for window in windows], ensure_ascii=False, indent=2))
        return

    if not windows:
        print("no matching perf.data windows")
        return

    print(f"{'START':25} {'END':25} {'SIZE':>8} PATH")
    for window in windows:
        print(
            f"{window.start_time.isoformat(timespec='seconds'):25} "
            f"{window.end_time.isoformat(timespec='seconds'):25} "
            f"{human_size(window.size_bytes):>8} "
            f"{window.path}"
        )


def print_symbol_quality(result) -> None:
    stats = result.folded_stats
    print("")
    print("symbol quality:")
    print(f"  total samples:   {stats.total_samples}")
    print(f"  unknown samples: {stats.unknown_samples}")
    print(f"  unknown ratio:   {stats.unknown_percent:.2f}%")
    print(f"  assessment:      {stats.assessment}")
    if stats.top_unknown_lines:
        print("  top unknown stacks:")
        for line in stats.top_unknown_lines[:3]:
            print(f"    {line.samples} {line.stack}")


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.command == "start":
        config = load_config(
            window_seconds=args.window_seconds,
            perf_freq=args.freq,
            retention_hours=args.retention_hours,
            data_dir=args.data_dir,
            perf_bin=args.perf_bin,
        )
        return start_collection(config)

    if args.command == "clean":
        config = load_config(retention_hours=args.retention_hours, data_dir=args.data_dir)
        cleanup = cleanup_old_samples(config)
        for path in cleanup.removed_paths:
            print(path)
        print(
            f"removed {len(cleanup.removed_paths)} perf.data files older than {config.retention_hours}h "
            f"from {Path(config.data_dir)}; "
            f"removed {cleanup.removed_index_records} stale index records; "
            f"kept {cleanup.kept_index_records} index records"
        )
        return 0

    if args.command == "list":
        config = load_config(data_dir=args.data_dir)
        print_windows(load_valid_windows(config.index_path), as_json=args.json)
        return 0

    if args.command == "query":
        config = load_config(data_dir=args.data_dir)
        try:
            query_from = parse_time(args.query_from)
            query_to = parse_time(args.query_to)
            windows = windows_overlapping(config.index_path, query_from, query_to)
        except ValueError as exc:
            parser.error(str(exc))
        print_windows(windows, as_json=args.json)
        return 0

    if args.command == "flame":
        config = load_config(data_dir=args.data_dir, perf_bin=args.perf_bin)
        try:
            query_from = parse_time(args.query_from)
            query_to = parse_time(args.query_to)
            result = build_flamegraph(
                index_path=config.index_path,
                data_dir=config.data_dir,
                query_from=query_from,
                query_to=query_to,
                output_path=Path(args.output) if args.output else None,
                flamegraph_dir=Path(args.flamegraph_dir).expanduser().resolve()
                if args.flamegraph_dir
                else default_flamegraph_dir(),
                perf_bin=config.perf_bin,
            )
        except (FileNotFoundError, RuntimeError, ValueError) as exc:
            parser.error(str(exc))
        print(f"matched {len(result.windows)} perf.data window(s)")
        print(f"perfscript: {result.perfscript_path}")
        print(f"folded:     {result.folded_path}")
        print(f"svg:        {result.svg_path}")
        print_symbol_quality(result)
        return 0

    if args.command == "web":
        config = load_config(
            window_seconds=args.window_seconds,
            perf_freq=args.freq,
            retention_hours=args.retention_hours,
            data_dir=args.data_dir,
            perf_bin=args.perf_bin,
        )
        return start_web_server(
            config,
            host=args.host,
            port=args.port,
            with_collector=not args.no_collector,
        )

    parser.error(f"unknown command: {args.command}")
    return 2
