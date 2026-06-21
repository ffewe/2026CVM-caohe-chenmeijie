#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="${CONTAINER_NAME:-cpu-profiler}"
DATA_DIR="${DATA_DIR:-/data/perf}"
OUTPUT_PATH="${OUTPUT_PATH:-/data/output/symbolic-hotspot.svg}"
SECONDS_TO_RUN="${SECONDS_TO_RUN:-60}"
THREADS="${THREADS:-16}"
BIN_PATH="${BIN_PATH:-/tmp/cpu-hotspot}"
SOURCE_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/cpu_hotspot.c"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker command not found" >&2
  exit 1
fi

if ! command -v gcc >/dev/null 2>&1; then
  echo "gcc command not found; install build-essential before running this test" >&2
  exit 1
fi

if ! docker inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
  echo "container $CONTAINER_NAME not found; start cpu-profiler before running this test" >&2
  exit 1
fi

echo "== symbolic hotspot validation =="
echo "source: $SOURCE_PATH"
echo "binary: $BIN_PATH"
echo "duration: ${SECONDS_TO_RUN}s"
echo "threads: ${THREADS}"

gcc -O0 -g -fno-omit-frame-pointer -pthread -o "$BIN_PATH" "$SOURCE_PATH" -lm

START_UTC="$(date -u '+%Y-%m-%dT%H:%M:%S+00:00')"
echo "start_utc: $START_UTC"

"$BIN_PATH" "$SECONDS_TO_RUN" "$THREADS"

END_UTC="$(date -u '+%Y-%m-%dT%H:%M:%S+00:00')"
echo "end_utc:   $END_UTC"

echo "== Matching perf windows =="
docker exec "$CONTAINER_NAME" perfbox query \
  --from "$START_UTC" \
  --to "$END_UTC" \
  --data-dir "$DATA_DIR"

echo "== Generating flame graph =="
docker exec "$CONTAINER_NAME" perfbox flame \
  --from "$START_UTC" \
  --to "$END_UTC" \
  --data-dir "$DATA_DIR" \
  --output "$OUTPUT_PATH"

echo "== Output =="
echo "svg: $OUTPUT_PATH"
echo "host path when using -v \"\$(pwd)/data:/data\": data/output/$(basename "$OUTPUT_PATH")"
echo "expected hotspots: matrix_hotspot / synthetic_hot_loop"
echo "expected machine-wide CPU increase: roughly ${THREADS} fully busy logical CPUs"
