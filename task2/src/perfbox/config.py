from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


TASK2_DIR = Path(__file__).resolve().parents[2]


def _int_from_env(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or raw == "":
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc
    if value <= 0:
        raise ValueError(f"{name} must be greater than 0, got {value}")
    return value


@dataclass(frozen=True)
class PerfboxConfig:
    window_seconds: int
    perf_freq: int
    retention_hours: int
    data_dir: Path
    perf_bin: str

    @property
    def index_path(self) -> Path:
        return self.data_dir / "index.jsonl"


def load_config(
    *,
    window_seconds: int | None = None,
    perf_freq: int | None = None,
    retention_hours: int | None = None,
    data_dir: str | None = None,
    perf_bin: str | None = None,
) -> PerfboxConfig:
    resolved_window = window_seconds or _int_from_env("WINDOW_SECONDS", 60)
    resolved_freq = perf_freq or _int_from_env("PERF_FREQ", 99)
    resolved_retention = retention_hours or _int_from_env("RETENTION_HOURS", 24)
    resolved_data_dir = Path(data_dir or os.environ.get("DATA_DIR", TASK2_DIR / "data" / "perf"))
    resolved_perf_bin = perf_bin or os.environ.get("PERF_BIN", "perf")

    return PerfboxConfig(
        window_seconds=resolved_window,
        perf_freq=resolved_freq,
        retention_hours=resolved_retention,
        data_dir=resolved_data_dir.expanduser().resolve(),
        perf_bin=resolved_perf_bin,
    )

