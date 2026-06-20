from __future__ import annotations

import json
import fcntl
import os
import signal
import subprocess
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from pathlib import Path
from typing import TextIO

from .config import PerfboxConfig


@dataclass(frozen=True)
class SampleWindow:
    start_time: str
    end_time: str
    path: str
    exit_code: int
    size_bytes: int
    status: str
    perf_command: list[str]


@dataclass(frozen=True)
class CleanupResult:
    removed_paths: list[str]
    kept_index_records: int
    removed_index_records: int


class StopRequested:
    value = False


class CollectorAlreadyRunning(RuntimeError):
    pass


def request_stop(signum: int, _frame: object) -> None:
    StopRequested.value = True
    print(f"\nreceived signal {signum}; stopping after the current window", flush=True)


def install_signal_handlers() -> None:
    signal.signal(signal.SIGINT, request_stop)
    signal.signal(signal.SIGTERM, request_stop)


def format_dt(value: datetime) -> str:
    return value.astimezone().isoformat(timespec="seconds")


def window_output_path(data_dir: Path, started_at: datetime) -> Path:
    date_dir = data_dir / started_at.strftime("%Y-%m-%d")
    filename = f"{started_at.strftime('%Y%m%d-%H%M%S')}.perf.data"
    return date_dir / filename


def perf_record_command(config: PerfboxConfig, output_path: Path) -> list[str]:
    return [
        config.perf_bin,
        "record",
        "-F",
        str(config.perf_freq),
        "-a",
        "--call-graph",
        "dwarf",
        "-o",
        str(output_path),
        "--",
        "sleep",
        str(config.window_seconds),
    ]


def append_index(index_path: Path, window: SampleWindow) -> None:
    index_path.parent.mkdir(parents=True, exist_ok=True)
    with index_path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(asdict(window), ensure_ascii=False) + "\n")


def window_status(exit_code: int, size_bytes: int) -> str:
    return "ok" if exit_code == 0 and size_bytes > 0 else "failed"


def acquire_collector_lock(data_dir: Path) -> TextIO:
    data_dir.mkdir(parents=True, exist_ok=True)
    lock_fp = (data_dir / "perfbox.lock").open("w", encoding="utf-8")
    try:
        fcntl.flock(lock_fp.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError as exc:
        lock_fp.close()
        raise CollectorAlreadyRunning("another perfbox collector is already running") from exc

    lock_fp.seek(0)
    lock_fp.truncate()
    lock_fp.write(str(os.getpid()))
    lock_fp.flush()
    return lock_fp


def parse_index_time(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone()


def rewrite_index(index_path: Path, cutoff: datetime) -> tuple[int, int]:
    if not index_path.exists():
        return 0, 0

    kept: list[str] = []
    removed = 0
    for line in index_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            path = Path(record["path"])
            if not path.is_absolute():
                path = index_path.parent / path
            end_time = parse_index_time(record["end_time"])
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            removed += 1
            continue
        if path.exists() and end_time >= cutoff:
            kept.append(json.dumps(record, ensure_ascii=False))
        else:
            removed += 1

    index_path.write_text("\n".join(kept) + ("\n" if kept else ""), encoding="utf-8")
    return len(kept), removed


def cleanup_old_samples(config: PerfboxConfig, *, now: datetime | None = None) -> CleanupResult:
    config.data_dir.mkdir(parents=True, exist_ok=True)
    cutoff = (now or datetime.now().astimezone()) - timedelta(hours=config.retention_hours)
    removed: list[str] = []

    for perf_data in config.data_dir.glob("*/*.perf.data"):
        try:
            mtime = datetime.fromtimestamp(perf_data.stat().st_mtime).astimezone()
        except FileNotFoundError:
            continue
        if mtime < cutoff:
            try:
                perf_data.unlink()
                removed.append(str(perf_data))
            except FileNotFoundError:
                pass

    for child in config.data_dir.iterdir():
        if child.is_dir():
            try:
                child.rmdir()
            except OSError:
                pass

    kept_index_records, removed_index_records = rewrite_index(config.index_path, cutoff)

    return CleanupResult(
        removed_paths=removed,
        kept_index_records=kept_index_records,
        removed_index_records=removed_index_records,
    )


def run_one_window(config: PerfboxConfig, *, stdout: TextIO | None = None) -> SampleWindow:
    out = stdout
    started_at = datetime.now().astimezone()
    output_path = window_output_path(config.data_dir, started_at)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    command = perf_record_command(config, output_path)

    print(f"[{format_dt(started_at)}] recording {config.window_seconds}s -> {output_path}", file=out, flush=True)
    completed = subprocess.run(command, check=False)
    ended_at = datetime.now().astimezone()

    size_bytes = output_path.stat().st_size if output_path.exists() else 0
    status = window_status(completed.returncode, size_bytes)
    window = SampleWindow(
        start_time=format_dt(started_at),
        end_time=format_dt(ended_at),
        path=str(output_path),
        exit_code=completed.returncode,
        size_bytes=size_bytes,
        status=status,
        perf_command=command,
    )
    append_index(config.index_path, window)
    print(
        f"[{format_dt(ended_at)}] window finished status={status} exit={completed.returncode} size={size_bytes}",
        file=out,
        flush=True,
    )
    return window


def start_collection(config: PerfboxConfig) -> int:
    install_signal_handlers()
    try:
        lock_fp = acquire_collector_lock(config.data_dir)
    except CollectorAlreadyRunning as exc:
        print(str(exc), flush=True)
        return 1

    print(
        "perfbox start: "
        f"window={config.window_seconds}s freq={config.perf_freq}Hz "
        f"retention={config.retention_hours}h data_dir={config.data_dir}",
        flush=True,
    )

    try:
        while not StopRequested.value:
            run_one_window(config)
            cleanup = cleanup_old_samples(config)
            if cleanup.removed_paths or cleanup.removed_index_records:
                print(
                    "retention cleanup "
                    f"removed_files={len(cleanup.removed_paths)} "
                    f"removed_index_records={cleanup.removed_index_records} "
                    f"kept_index_records={cleanup.kept_index_records}",
                    flush=True,
                )
    finally:
        print("perfbox stopped", flush=True)
        lock_fp.close()
    return 0
