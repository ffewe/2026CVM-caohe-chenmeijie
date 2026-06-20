from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path


@dataclass(frozen=True)
class QueryWindow:
    start_time: datetime
    end_time: datetime
    path: Path
    size_bytes: int
    status: str
    exit_code: int
    raw: dict


def parse_time(value: str) -> datetime:
    normalized = value.strip()
    if " " in normalized and "T" not in normalized:
        normalized = normalized.replace(" ", "T", 1)
    parsed = datetime.fromisoformat(normalized)
    if parsed.tzinfo is None:
        return parsed.astimezone()
    return parsed.astimezone()


def resolve_record_path(index_path: Path, raw_path: object) -> Path:
    path = Path(raw_path)
    if path.is_absolute():
        return path
    return index_path.parent / path


def record_status(record: dict, size_bytes: int, exit_code: int) -> str:
    explicit = record.get("status")
    if explicit in {"ok", "failed"}:
        return explicit
    return "ok" if exit_code == 0 and size_bytes > 0 else "failed"


def load_valid_windows(index_path: Path) -> list[QueryWindow]:
    if not index_path.exists():
        return []

    windows: list[QueryWindow] = []
    for line in index_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            record = json.loads(line)
            path = resolve_record_path(index_path, record["path"])
            start_time = parse_time(record["start_time"])
            end_time = parse_time(record["end_time"])
            size_bytes = int(record.get("size_bytes", 0))
            exit_code = int(record.get("exit_code", 1))
            status = record_status(record, size_bytes, exit_code)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue

        if status != "ok" or size_bytes <= 0 or not path.exists():
            continue

        windows.append(
            QueryWindow(
                start_time=start_time,
                end_time=end_time,
                path=path,
                size_bytes=size_bytes,
                status=status,
                exit_code=exit_code,
                raw=record,
            )
        )

    return sorted(windows, key=lambda item: item.start_time)


def windows_overlapping(index_path: Path, query_from: datetime, query_to: datetime) -> list[QueryWindow]:
    if query_from >= query_to:
        raise ValueError("--from must be earlier than --to")
    return [
        window
        for window in load_valid_windows(index_path)
        if window.start_time < query_to and window.end_time > query_from
    ]


def human_size(size_bytes: int) -> str:
    units = ["B", "K", "M", "G", "T"]
    value = float(size_bytes)
    for unit in units:
        if value < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(value)}{unit}"
            return f"{value:.1f}{unit}"
        value /= 1024


def window_to_json(window: QueryWindow) -> dict:
    return {
        "start_time": window.start_time.isoformat(timespec="seconds"),
        "end_time": window.end_time.isoformat(timespec="seconds"),
        "path": str(window.path),
        "size_bytes": window.size_bytes,
        "status": window.status,
        "exit_code": window.exit_code,
    }

