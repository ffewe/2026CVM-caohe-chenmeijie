#!/usr/bin/env bash
set -euo pipefail

CONTAINER_NAME="${CONTAINER_NAME:-cpu-profiler}"
DATA_DIR="${DATA_DIR:-/data/perf}"
OUTPUT_PATH="${OUTPUT_PATH:-/data/output/stress-ng-matrixprod.svg}"
STRESS_SECONDS="${STRESS_SECONDS:-60}"
STRESS_CPUS="${STRESS_CPUS:-2}"

if ! command -v docker >/dev/null 2>&1; then
  echo "docker command not found" >&2
  exit 1
fi

if ! command -v stress-ng >/dev/null 2>&1; then
  echo "stress-ng command not found; install it on the host before running this test" >&2
  exit 1
fi

if ! docker inspect "$CONTAINER_NAME" >/dev/null 2>&1; then
  echo "container $CONTAINER_NAME not found; start cpu-profiler before running this test" >&2
  exit 1
fi

echo "== CPU spike validation =="
echo "container: $CONTAINER_NAME"
echo "workload: stress-ng --cpu $STRESS_CPUS --cpu-method matrixprod -t ${STRESS_SECONDS}s"

START_UTC="$(date -u '+%Y-%m-%dT%H:%M:%S+00:00')"
echo "start_utc: $START_UTC"

stress-ng --cpu "$STRESS_CPUS" --cpu-method matrixprod -t "${STRESS_SECONDS}s"

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
