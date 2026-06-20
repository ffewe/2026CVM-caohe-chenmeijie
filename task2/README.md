# task2 持续 CPU Profiling 工具

## 1. 当前阶段

本目录对应考核题目 2（选做加分）。当前已实现本地 CLI 版本的四个核心能力，并补充 Docker 容器化交付：

- 后台持续采集：循环执行 `perf record` 采集 CPU 调用栈。
- 历史数据保留：按固定时间窗口保存采样文件，并自动删除超过保留期的 `.perf.data`。
- 按时间回查：输入时间范围，自动定位与该范围有交集的有效采样文件。
- 一键生成火焰图：对指定时间段自动生成 `perfscript`、`folded` 和 SVG 火焰图。
- Docker 容器化：镜像名为 `cpu-profiler:latest`，导出文件为 `profiler.tar`，容器默认启动持续采集。

容器运行 `perf` 必须使用 `--privileged`，推荐同时使用 `--pid=host` 采集宿主机进程。

## 2. 当前目录结构

```text
task2/
├── Dockerfile
├── README.md
├── profiler.tar
├── src/
│   ├── bin/
│   │   └── perfbox
│   └── perfbox/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── collector.py
│       └── config.py
├── third_party/
│   └── FlameGraph/
│       ├── flamegraph.pl
│       └── stackcollapse-perf.pl
└── data/
    ├── perf/
    └── output/
```

## 3. Docker 一键启动

评审方加载镜像并按题目要求启动：

```bash
cd task2
docker load -i profiler.tar
docker run --privileged -d -p 8080:8080 --name cpu-profiler cpu-profiler:latest
```

当前版本已内置 Web 界面，容器启动后可直接访问：

```bash
http://localhost:8080
```

容器默认执行：

```bash
perfbox web --host 0.0.0.0 --port 8080
```

如果需要把采样数据、索引和火焰图持久化到宿主机，推荐使用：

```bash
cd task2
mkdir -p data
docker run --privileged --pid=host -d \
  -p 8080:8080 \
  --name cpu-profiler \
  -v "$(pwd)/data:/data" \
  cpu-profiler:latest
```

容器内默认路径：

| 路径 | 说明 |
|------|------|
| `/opt/perf-blackbox` | 程序目录 |
| `/opt/perf-blackbox/FlameGraph` | FlameGraph 工具链 |
| `/data/perf` | `.perf.data` 和 `index.jsonl` |
| `/data/output` | 火焰图和中间文件输出目录 |
| `/data/logs` | 预留日志目录 |

镜像构建和导出命令：

```bash
cd task2
docker build -t cpu-profiler:latest .
docker save -o profiler.tar cpu-profiler:latest
```

常用验证命令：

```bash
docker logs -f cpu-profiler
docker exec cpu-profiler perfbox list --data-dir /data/perf
docker exec cpu-profiler perfbox query --from "2026-06-18T23:36:00+08:00" --to "2026-06-18T23:40:00+08:00" --data-dir /data/perf
docker stop cpu-profiler
docker rm cpu-profiler
```

## 4. 特权模式运行说明

`--privileged` 是本工具的必需运行参数。`perf record -a` 需要访问宿主机 PMU、`perf_event_open`、硬件性能事件、内核符号和进程信息；普通容器权限下可能出现：

- `perf_event_open` 权限不足。
- 硬件事件不可用。
- `Operation not permitted`。
- 调用栈缺失，或火焰图中 `[unknown]` 比例明显升高。

推荐加上 `--pid=host`，否则容器只能看到自己的 PID namespace，采样结果可能偏向容器内部进程，不能完整反映宿主机 CPU 热点。

当前 MVP 不实现最小权限模式，最小权限运行只作为后续优化方向。如果容器内 `perf` 与宿主机内核版本不匹配，可以挂载宿主机真实的 `perf` 二进制作为 fallback：

```bash
PERF_HOST="$(readlink -f /usr/lib/linux-tools/$(uname -r)/perf)"

docker run --privileged --pid=host -d \
  -p 8080:8080 \
  --name cpu-profiler \
  -e PERF_BIN=/host-perf \
  -v "$PERF_HOST:/host-perf:ro" \
  -v "$(pwd)/data:/data" \
  cpu-profiler:latest
```

## 5. 本地启动持续采集

在仓库根目录执行：

```bash
cd /home/mkom/task
task2/src/bin/perfbox start
```

默认配置：

| 配置 | 默认值 | 说明 |
|------|--------|------|
| `WINDOW_SECONDS` | `60` | 每个 `perf record` 采样窗口的秒数 |
| `PERF_FREQ` | `99` | perf 采样频率，单位 Hz |
| `RETENTION_HOURS` | `24` | 保留最近多少小时的 `.perf.data` |
| `DATA_DIR` | `task2/data/perf` | 采样文件和索引保存目录 |

每个窗口实际执行的命令形态为：

```bash
perf record -F 99 -a --call-graph dwarf -o <output.perf.data> -- sleep 60
```

输出文件按窗口开始时间命名：

```text
task2/data/perf/YYYY-MM-DD/YYYYMMDD-HHMMSS.perf.data
```

每个窗口结束后会追加一条索引记录：

```text
task2/data/perf/index.jsonl
```

索引字段包括：

- `start_time`
- `end_time`
- `path`
- `exit_code`
- `size_bytes`
- `status`
- `perf_command`

其中 `status` 的取值为：

- `ok`：`exit_code == 0` 且 `size_bytes > 0`
- `failed`：采样命令失败、被中断，或输出文件为空

后续做时间回查和火焰图生成时，只应选择 `status == "ok"`、`size_bytes > 0` 且 `path` 仍存在的窗口。

## 6. 快速验证命令

为了快速看到轮转效果，可以把窗口调短：

```bash
cd /home/mkom/task
task2/src/bin/perfbox start --window-seconds 5 --data-dir task2/data/perf
```

运行 2 到 3 个窗口后按 `Ctrl+C` 停止。检查输出：

```bash
find task2/data/perf -name "*.perf.data" -type f -ls
cat task2/data/perf/index.jsonl
```

检查某个采样文件是否能被 `perf script` 读取：

```bash
perf script -i task2/data/perf/<日期>/<文件名>.perf.data | head
```

## 7. 按时间回查

列出当前所有有效采样窗口：

```bash
task2/src/bin/perfbox list --data-dir task2/data/perf
```

查询指定时间段内对应的采样文件：

```bash
task2/src/bin/perfbox query \
  --from "2026-06-18 23:36:00" \
  --to "2026-06-18 23:40:00" \
  --data-dir task2/data/perf
```

回查逻辑会选择与输入时间段有交集的窗口，并且只返回满足以下条件的采样文件：

- `status == "ok"`
- `size_bytes > 0`
- `path` 仍然存在

如果需要脚本处理，可以输出 JSON：

```bash
task2/src/bin/perfbox query \
  --from "2026-06-18T23:36:00+08:00" \
  --to "2026-06-18T23:40:00+08:00" \
  --data-dir task2/data/perf \
  --json
```

## 8. 一键生成火焰图

对指定时间段生成火焰图：

```bash
task2/src/bin/perfbox flame \
  --from "2026-06-18 23:36:00" \
  --to "2026-06-18 23:40:00" \
  --data-dir task2/data/perf \
  --output task2/data/output/cpu-2336-2340.svg
```

该命令会复用时间回查逻辑，自动找到时间段内的有效 `.perf.data` 文件，然后依次执行：

```text
perf script -i <perf.data>
stackcollapse-perf.pl
flamegraph.pl
```

如果指定 `--output xxx.svg`，中间文件会保存在同一目录：

```text
xxx.perfscript
xxx.folded
xxx.svg
```

当前默认复用题目一中已有的 FlameGraph 工具目录：

```text
task1/2-flamegraph/FlameGraph
```

也可以手动指定：

```bash
task2/src/bin/perfbox flame \
  --from "2026-06-18T23:36:00+08:00" \
  --to "2026-06-18T23:40:00+08:00" \
  --data-dir task2/data/perf \
  --flamegraph-dir task1/2-flamegraph/FlameGraph
```

## 9. 历史数据保留

持续采集模式下，每个窗口结束后会自动执行一次过期清理。默认只保留最近 24 小时的数据。

清理时会同时处理两类数据：

- 删除超过保留期的 `.perf.data` 文件。
- 重写 `index.jsonl`，只保留 `path` 仍存在、且 `end_time` 不早于保留期 cutoff 的记录。

也可以手动执行清理：

```bash
task2/src/bin/perfbox clean --retention-hours 24 --data-dir task2/data/perf
```

如果要快速验证清理逻辑，可以临时设置很小的保留窗口：

```bash
task2/src/bin/perfbox clean --retention-hours 1 --data-dir task2/data/perf
```

## 10. 参数和环境变量

CLI 参数示例：

```bash
task2/src/bin/perfbox start \
  --window-seconds 10 \
  --freq 99 \
  --retention-hours 24 \
  --data-dir task2/data/perf
```

环境变量示例：

```bash
WINDOW_SECONDS=10 \
PERF_FREQ=99 \
RETENTION_HOURS=24 \
DATA_DIR=task2/data/perf \
task2/src/bin/perfbox start
```

CLI 参数优先级高于环境变量。

Docker 环境默认设置：

```bash
DATA_DIR=/data/perf
FLAMEGRAPH_DIR=/opt/perf-blackbox/FlameGraph
```

本地打开 Web 预览：

```bash
cd /home/mkom/task
task2/src/bin/perfbox web --host 127.0.0.1 --port 8080 --no-collector
```

## 11. 设计说明

- 使用固定时间窗口轮转，而不是写入单个巨大 `perf.data`，便于后续按时间段回查，也能降低单文件损坏影响。
- 默认使用 `-a` 做全系统采样，因为题目目标是 7x24 黑匣子，故障发生前不一定知道热点进程是谁。
- 默认使用显式 `--call-graph dwarf` 采集调用栈，比隐式 `-g` 更有利于减少后续火焰图中的调用栈缺失。
- 默认 99Hz 是为了控制采样开销，同时保留定位 CPU 热点所需的信息。
- 启动采集时会持有 `task2/data/perf/perfbox.lock`，避免误启动多个 collector 同时写入 `index.jsonl` 或竞争 PMU。

## 12. 测试验证记录

Docker 特权模式已在 Ubuntu 22.04 / Linux 6.8.0-124-generic 环境验证通过。由于容器内 `linux-tools-generic` 的 `perf` 版本可能与宿主机内核不一致，本次验证使用宿主机真实 `perf` 二进制挂载到容器内：

```bash
PERF_HOST="$(readlink -f /usr/lib/linux-tools/$(uname -r)/perf)"

docker run --privileged --pid=host -d \
  -p 8080:8080 \
  --name cpu-profiler \
  -e PERF_BIN=/host-perf \
  -v "$PERF_HOST:/host-perf:ro" \
  -v "$(pwd)/data:/data" \
  cpu-profiler:latest
```

持续采集验证结果：

```text
perfbox start: window=60s freq=99Hz retention=24h data_dir=/data/perf
[2026-06-19T07:40:06+00:00] recording 60s -> /data/perf/2026-06-19/20260619-074006.perf.data
[2026-06-19T07:41:08+00:00] window finished status=ok exit=0 size=89151186
[2026-06-19T07:41:08+00:00] recording 60s -> /data/perf/2026-06-19/20260619-074108.perf.data
[2026-06-19T07:42:10+00:00] window finished status=ok exit=0 size=79985210
```

按时间回查并生成火焰图验证结果：

```bash
docker exec cpu-profiler perfbox flame \
  --from "2026-06-19T07:40:06+00:00" \
  --to "2026-06-19T07:42:10+00:00" \
  --data-dir /data/perf \
  --output /data/output/docker-verify.svg
```

```text
matched 2 perf.data window(s)
perfscript: /data/output/docker-verify.perfscript
folded:     /data/output/docker-verify.folded
svg:        /data/output/docker-verify.svg
unknown ratio:   9.79%
assessment:      warning
```

宿主机挂载目录中已生成：

```text
data/output/docker-verify.perfscript
data/output/docker-verify.folded
data/output/docker-verify.svg
```

CPU 飙升复现实验脚本位于：

```text
task2/test/test_scenario.sh
```

运行方式：

```bash
cd task2
sudo ./test/test_scenario.sh
```

脚本会记录 `stress-ng --cpu 2 --cpu-method matrixprod -t 60s` 的开始和结束时间，调用容器内 `perfbox query` 回查对应窗口，并生成 `/data/output/stress-ng-matrixprod.svg`。
