from __future__ import annotations

import os
import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .query import QueryWindow, windows_overlapping


TASK_DIR = Path(__file__).resolve().parents[3]
DEFAULT_FLAMEGRAPH_DIR = TASK_DIR / "task1" / "2-flamegraph" / "FlameGraph"


def default_flamegraph_dir() -> Path:
    configured = os.environ.get("FLAMEGRAPH_DIR")
    if configured:
        return Path(configured).expanduser().resolve()
    return DEFAULT_FLAMEGRAPH_DIR


@dataclass(frozen=True)
class FlamegraphResult:
    windows: list[QueryWindow]
    perfscript_path: Path
    folded_path: Path
    svg_path: Path
    folded_stats: FoldedStats


@dataclass(frozen=True)
class StackLine:
    stack: str
    samples: int


@dataclass(frozen=True)
class FoldedStats:
    total_samples: int
    unknown_samples: int
    unknown_percent: float
    assessment: str
    top_lines: list[StackLine]
    top_unknown_lines: list[StackLine]


def safe_time_label(value: datetime) -> str:
    return value.strftime("%Y%m%d-%H%M%S")


def default_output_path(data_dir: Path, query_from: datetime, query_to: datetime) -> Path:
    return data_dir.parent / "output" / f"cpu-{safe_time_label(query_from)}-{safe_time_label(query_to)}.svg"


def sibling_output_paths(svg_path: Path) -> tuple[Path, Path]:
    if svg_path.suffix == ".svg":
        stem = svg_path.with_suffix("")
    else:
        stem = svg_path
    return stem.with_suffix(".perfscript"), stem.with_suffix(".folded")


def require_flamegraph_tools(flamegraph_dir: Path) -> tuple[Path, Path]:
    stackcollapse = flamegraph_dir / "stackcollapse-perf.pl"
    flamegraph = flamegraph_dir / "flamegraph.pl"
    missing = [str(path) for path in (stackcollapse, flamegraph) if not path.exists()]
    if missing:
        raise FileNotFoundError("missing FlameGraph tool(s): " + ", ".join(missing))
    return stackcollapse, flamegraph


def run_checked(command: list[str], *, stdin=None, stdout=None) -> None:
    completed = subprocess.run(command, stdin=stdin, stdout=stdout, check=False)
    if completed.returncode != 0:
        raise RuntimeError(f"command failed with exit code {completed.returncode}: {' '.join(command)}")


def write_perfscript(windows: list[QueryWindow], perfscript_path: Path, perf_bin: str) -> None:
    perfscript_path.parent.mkdir(parents=True, exist_ok=True)
    with perfscript_path.open("wb") as out:
        for window in windows:
            command = [perf_bin, "script", "-i", str(window.path)]
            run_checked(command, stdout=out)


def collapse_perfscript(stackcollapse: Path, perfscript_path: Path, folded_path: Path) -> None:
    folded_path.parent.mkdir(parents=True, exist_ok=True)
    with perfscript_path.open("rb") as src, folded_path.open("wb") as dst:
        run_checked([str(stackcollapse)], stdin=src, stdout=dst)


def render_flamegraph(flamegraph: Path, folded_path: Path, svg_path: Path) -> None:
    svg_path.parent.mkdir(parents=True, exist_ok=True)
    with folded_path.open("rb") as src, svg_path.open("wb") as dst:
        run_checked([str(flamegraph)], stdin=src, stdout=dst)


def is_unknown_stack(stack: str) -> bool:
    lowered = stack.lower()
    return "unknown" in lowered or "??" in stack


def assess_unknown_percent(percent: float) -> str:
    if percent < 5.0:
        return "acceptable"
    if percent <= 20.0:
        return "warning"
    return "poor"


def parse_folded_line(line: str) -> StackLine | None:
    stripped = line.strip()
    if not stripped:
        return None
    try:
        stack, samples_text = stripped.rsplit(" ", 1)
        samples = int(samples_text)
    except ValueError:
        return None
    return StackLine(stack=stack, samples=samples)


def analyze_folded(folded_path: Path) -> FoldedStats:
    total_samples = 0
    unknown_samples = 0
    all_lines: list[StackLine] = []
    unknown_lines: list[StackLine] = []

    for raw_line in folded_path.read_text(encoding="utf-8", errors="replace").splitlines():
        parsed = parse_folded_line(raw_line)
        if parsed is None:
            continue
        total_samples += parsed.samples
        all_lines.append(parsed)
        if is_unknown_stack(parsed.stack):
            unknown_samples += parsed.samples
            unknown_lines.append(parsed)

    unknown_percent = (unknown_samples * 100.0 / total_samples) if total_samples else 0.0
    return FoldedStats(
        total_samples=total_samples,
        unknown_samples=unknown_samples,
        unknown_percent=unknown_percent,
        assessment=assess_unknown_percent(unknown_percent),
        top_lines=sorted(all_lines, key=lambda item: item.samples, reverse=True)[:5],
        top_unknown_lines=sorted(unknown_lines, key=lambda item: item.samples, reverse=True)[:5],
    )


def build_flamegraph(
    *,
    index_path: Path,
    data_dir: Path,
    query_from: datetime,
    query_to: datetime,
    output_path: Path | None,
    flamegraph_dir: Path,
    perf_bin: str,
) -> FlamegraphResult:
    windows = windows_overlapping(index_path, query_from, query_to)
    if not windows:
        raise ValueError("no matching perf.data windows")

    stackcollapse, flamegraph = require_flamegraph_tools(flamegraph_dir)
    svg_path = (output_path or default_output_path(data_dir, query_from, query_to)).expanduser().resolve()
    perfscript_path, folded_path = sibling_output_paths(svg_path)

    write_perfscript(windows, perfscript_path, perf_bin)
    collapse_perfscript(stackcollapse, perfscript_path, folded_path)
    folded_stats = analyze_folded(folded_path)
    render_flamegraph(flamegraph, folded_path, svg_path)

    return FlamegraphResult(
        windows=windows,
        perfscript_path=perfscript_path,
        folded_path=folded_path,
        svg_path=svg_path,
        folded_stats=folded_stats,
    )
