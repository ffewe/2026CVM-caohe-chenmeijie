from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import threading
import time
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlparse

from .collector import parse_index_time
from .config import PerfboxConfig, TASK2_DIR
from .flame import build_flamegraph, default_flamegraph_dir
from .query import parse_time


UI_PREVIEW_CANDIDATES = (
    TASK2_DIR / "ui-preview.html",
    Path("/opt/perf-blackbox/ui-preview.html"),
)


def resolve_ui_preview_path() -> Path:
    for candidate in UI_PREVIEW_CANDIDATES:
        if candidate.exists():
            return candidate
    raise FileNotFoundError(
        "ui-preview.html not found; checked: "
        + ", ".join(str(candidate) for candidate in UI_PREVIEW_CANDIDATES)
    )


@dataclass(frozen=True)
class IndexRecord:
    start_time: datetime
    end_time: datetime
    path: Path
    size_bytes: int
    status: str
    exit_code: int
    path_exists: bool
    queryable: bool
    raw: dict[str, Any]


@dataclass
class WebState:
    config: PerfboxConfig
    collector_process: subprocess.Popen[str] | None
    collector_started_by_web: bool
    collector_log: deque[str]


def default_output_dir(config: PerfboxConfig) -> Path:
    return config.data_dir.parent / "output"


def data_root(config: PerfboxConfig) -> Path:
    return config.data_dir.parent


def detect_collector_status(config: PerfboxConfig) -> dict[str, Any]:
    lock_path = config.data_dir / "perfbox.lock"
    if not lock_path.exists():
        return {"status": "stopped", "pid": None, "message": "collector not running"}

    try:
        pid_text = lock_path.read_text(encoding="utf-8").strip()
        pid = int(pid_text)
    except (OSError, ValueError):
        return {"status": "failed", "pid": None, "message": "invalid perfbox.lock contents"}

    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return {"status": "failed", "pid": pid, "message": "stale perfbox.lock; process not found"}
    except PermissionError:
        return {"status": "running", "pid": pid, "message": "collector running"}

    return {"status": "running", "pid": pid, "message": "collector running"}


def sample_cpu_percent(interval: float = 0.15) -> float:
    def read_cpu_times() -> tuple[int, int]:
        with Path("/proc/stat").open("r", encoding="utf-8") as fp:
            parts = fp.readline().split()
        values = [int(value) for value in parts[1:]]
        idle = values[3] + (values[4] if len(values) > 4 else 0)
        total = sum(values)
        return idle, total

    idle1, total1 = read_cpu_times()
    time.sleep(interval)
    idle2, total2 = read_cpu_times()
    total_delta = max(total2 - total1, 1)
    idle_delta = max(idle2 - idle1, 0)
    return round((1.0 - idle_delta / total_delta) * 100.0, 1)


def directory_size(path: Path) -> int:
    if not path.exists():
        return 0
    total = 0
    for child in path.rglob("*"):
        if child.is_file():
            try:
                total += child.stat().st_size
            except FileNotFoundError:
                continue
    return total


def disk_usage(path: Path) -> dict[str, int]:
    target = path if path.exists() else path.parent
    stats = os.statvfs(target)
    total = stats.f_frsize * stats.f_blocks
    free = stats.f_frsize * stats.f_bavail
    used = total - free
    return {"total_bytes": total, "used_bytes": used, "free_bytes": free}


def record_status(record: dict[str, Any], size_bytes: int, exit_code: int, path_exists: bool) -> tuple[str, bool]:
    explicit = record.get("status")
    status = explicit if explicit in {"ok", "failed"} else ("ok" if exit_code == 0 and size_bytes > 0 else "failed")
    queryable = status == "ok" and size_bytes > 0 and path_exists
    return status, queryable


def load_index_records(index_path: Path) -> list[IndexRecord]:
    if not index_path.exists():
        return []

    records: list[IndexRecord] = []
    for line in index_path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
            raw_path = Path(raw["path"])
            path = raw_path if raw_path.is_absolute() else index_path.parent / raw_path
            start_time = parse_index_time(raw["start_time"])
            end_time = parse_index_time(raw["end_time"])
            size_bytes = int(raw.get("size_bytes", 0))
            exit_code = int(raw.get("exit_code", 1))
            path_exists = path.exists()
            status, queryable = record_status(raw, size_bytes, exit_code, path_exists)
        except (KeyError, TypeError, ValueError, json.JSONDecodeError):
            continue
        records.append(
            IndexRecord(
                start_time=start_time,
                end_time=end_time,
                path=path,
                size_bytes=size_bytes,
                status=status,
                exit_code=exit_code,
                path_exists=path_exists,
                queryable=queryable,
                raw=raw,
            )
        )

    return sorted(records, key=lambda item: item.start_time)


def index_record_to_json(record: IndexRecord) -> dict[str, Any]:
    return {
        "start_time": record.start_time.isoformat(timespec="seconds"),
        "end_time": record.end_time.isoformat(timespec="seconds"),
        "path": str(record.path),
        "basename": record.path.name,
        "size_bytes": record.size_bytes,
        "status": record.status,
        "exit_code": record.exit_code,
        "path_exists": record.path_exists,
        "queryable": record.queryable,
    }


def records_in_range(records: list[IndexRecord], query_from: datetime, query_to: datetime) -> list[IndexRecord]:
    return [record for record in records if record.start_time < query_to and record.end_time > query_from]


def recent_records(records: list[IndexRecord], hours: int) -> list[IndexRecord]:
    cutoff = datetime.now().astimezone() - timedelta(hours=hours)
    return [record for record in records if record.end_time >= cutoff]


def perfbox_bin() -> Path:
    return TASK2_DIR / "src" / "bin" / "perfbox"


def start_collector_subprocess(config: PerfboxConfig, log_buffer: deque[str]) -> subprocess.Popen[str] | None:
    status = detect_collector_status(config)
    if status["status"] == "running":
        log_buffer.append("collector already running; web server will attach in read-only mode")
        return None

    command = [
        str(perfbox_bin()),
        "start",
        "--window-seconds",
        str(config.window_seconds),
        "--freq",
        str(config.perf_freq),
        "--retention-hours",
        str(config.retention_hours),
        "--data-dir",
        str(config.data_dir),
        "--perf-bin",
        config.perf_bin,
    ]
    process = subprocess.Popen(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
    )

    def consume_output() -> None:
        assert process.stdout is not None
        for line in process.stdout:
            log_buffer.append(line.rstrip())

    threading.Thread(target=consume_output, daemon=True).start()
    return process


def build_overview(state: WebState) -> dict[str, Any]:
    records = load_index_records(state.config.index_path)
    collector = detect_collector_status(state.config)
    latest = records[-1] if records else None
    last_failed = next((record for record in reversed(records) if record.status == "failed"), None)
    perf_dir_size = directory_size(state.config.data_dir)
    output_dir = default_output_dir(state.config)
    output_size = directory_size(output_dir)
    latest_svg = next((item for item in sorted(output_dir.glob("*.svg"), reverse=True)), None)
    return {
        "collector": collector,
        "cpu_percent": sample_cpu_percent(),
        "valid_window_count": sum(1 for record in records if record.queryable),
        "total_window_count": len(records),
        "perf_size_bytes": perf_dir_size,
        "output_size_bytes": output_size,
        "disk": disk_usage(data_root(state.config)),
        "latest_window": index_record_to_json(latest) if latest else None,
        "last_failed_window": index_record_to_json(last_failed) if last_failed else None,
        "latest_svg": latest_svg.name if latest_svg else None,
        "log_tail": list(state.collector_log)[-6:],
    }


def build_diagnostics(state: WebState) -> dict[str, Any]:
    records = load_index_records(state.config.index_path)
    failures = [index_record_to_json(record) for record in records if record.status == "failed"][-10:]
    return {
        "collector": detect_collector_status(state.config),
        "runtime": {
            "data_dir": str(state.config.data_dir),
            "output_dir": str(default_output_dir(state.config)),
            "perf_bin": state.config.perf_bin,
            "flamegraph_dir": str(default_flamegraph_dir()),
            "retention_hours": state.config.retention_hours,
            "window_seconds": state.config.window_seconds,
            "perf_freq": state.config.perf_freq,
        },
        "recent_failures": failures,
        "log_tail": list(state.collector_log)[-20:],
    }


def make_handler(state: WebState) -> type[BaseHTTPRequestHandler]:
    class Handler(BaseHTTPRequestHandler):
        server_version = "PerfboxHTTP/0.1"

        def do_GET(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path == "/":
                try:
                    return self._serve_file(resolve_ui_preview_path(), "text/html; charset=utf-8")
                except FileNotFoundError as exc:
                    return self._error(HTTPStatus.INTERNAL_SERVER_ERROR, str(exc))
            if parsed.path == "/api/overview":
                return self._json(build_overview(state))
            if parsed.path == "/api/windows":
                query = parse_qs(parsed.query)
                hours = int(query.get("hours", ["1"])[0])
                include_failed = query.get("include_failed", ["1"])[0] != "0"
                records = recent_records(load_index_records(state.config.index_path), hours)
                if not include_failed:
                    records = [record for record in records if record.queryable]
                return self._json({"windows": [index_record_to_json(record) for record in records]})
            if parsed.path == "/api/query":
                query = parse_qs(parsed.query)
                try:
                    query_from = parse_time(query["from"][0])
                    query_to = parse_time(query["to"][0])
                except (KeyError, IndexError, ValueError) as exc:
                    return self._error(HTTPStatus.BAD_REQUEST, f"invalid query range: {exc}")
                records = records_in_range(load_index_records(state.config.index_path), query_from, query_to)
                return self._json({"windows": [index_record_to_json(record) for record in records]})
            if parsed.path == "/api/diagnostics":
                return self._json(build_diagnostics(state))
            if parsed.path == "/api/logs":
                return self._json({"lines": list(state.collector_log)})
            if parsed.path.startswith("/artifacts/"):
                relative = parsed.path.removeprefix("/artifacts/")
                return self._serve_artifact(relative)
            return self._error(HTTPStatus.NOT_FOUND, "not found")

        def do_POST(self) -> None:  # noqa: N802
            parsed = urlparse(self.path)
            if parsed.path != "/api/flame":
                return self._error(HTTPStatus.NOT_FOUND, "not found")
            try:
                body = self._read_json()
                query_from = parse_time(str(body["from"]))
                query_to = parse_time(str(body["to"]))
            except (KeyError, ValueError, json.JSONDecodeError) as exc:
                return self._error(HTTPStatus.BAD_REQUEST, f"invalid flame request: {exc}")

            output_dir = default_output_dir(state.config)
            output_dir.mkdir(parents=True, exist_ok=True)
            output_name = str(body.get("output_name") or "")
            output_path = output_dir / output_name if output_name else None

            try:
                result = build_flamegraph(
                    index_path=state.config.index_path,
                    data_dir=state.config.data_dir,
                    query_from=query_from,
                    query_to=query_to,
                    output_path=output_path,
                    flamegraph_dir=default_flamegraph_dir(),
                    perf_bin=state.config.perf_bin,
                )
            except (FileNotFoundError, RuntimeError, ValueError) as exc:
                return self._error(HTTPStatus.BAD_REQUEST, str(exc))

            self._json(
                {
                    "windows": len(result.windows),
                    "svg": result.svg_path.name,
                    "perfscript": result.perfscript_path.name,
                    "folded": result.folded_path.name,
                    "folded_stats": asdict(result.folded_stats),
                    "artifact_urls": {
                        "svg": f"/artifacts/output/{result.svg_path.name}",
                        "perfscript": f"/artifacts/output/{result.perfscript_path.name}",
                        "folded": f"/artifacts/output/{result.folded_path.name}",
                    },
                }
            )

        def log_message(self, format: str, *args: Any) -> None:
            return

        def _json(self, payload: dict[str, Any], status: HTTPStatus = HTTPStatus.OK) -> None:
            body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def _error(self, status: HTTPStatus, message: str) -> None:
            self._json({"error": message}, status=status)

        def _read_json(self) -> dict[str, Any]:
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length)
            return json.loads(body or b"{}")

        def _serve_file(self, path: Path, content_type: str) -> None:
            content = path.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(content)))
            self.end_headers()
            self.wfile.write(content)

        def _serve_artifact(self, relative: str) -> None:
            root = data_root(state.config).resolve()
            candidate = (root / relative).resolve()
            if root not in candidate.parents and candidate != root:
                return self._error(HTTPStatus.FORBIDDEN, "artifact path not allowed")
            if not candidate.exists() or not candidate.is_file():
                return self._error(HTTPStatus.NOT_FOUND, "artifact not found")
            if candidate.suffix == ".svg":
                content_type = "image/svg+xml"
            elif candidate.suffix == ".json":
                content_type = "application/json; charset=utf-8"
            else:
                content_type = "text/plain; charset=utf-8"
            return self._serve_file(candidate, content_type)

    return Handler


def start_web_server(
    config: PerfboxConfig,
    *,
    host: str = "127.0.0.1",
    port: int = 8080,
    with_collector: bool = True,
) -> int:
    collector_log: deque[str] = deque(maxlen=200)
    process = start_collector_subprocess(config, collector_log) if with_collector else None
    state = WebState(
        config=config,
        collector_process=process,
        collector_started_by_web=process is not None,
        collector_log=collector_log,
    )
    server = ThreadingHTTPServer((host, port), make_handler(state))

    def shutdown(*_args: Any) -> None:
        server.shutdown()

    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print(f"perfbox web listening on http://{host}:{port}", flush=True)
    try:
        server.serve_forever()
    finally:
        if state.collector_started_by_web and state.collector_process is not None and state.collector_process.poll() is None:
            state.collector_process.terminate()
            try:
                state.collector_process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                state.collector_process.kill()
    return 0
