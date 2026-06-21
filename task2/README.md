# task2 持续 CPU Profiling 工具

## 1. 项目简介

本项目实现了一个面向 Linux 主机的持续 CPU Profiling 工具，满足题目要求的主链路：

- 容器后台持续执行 `perf record`
- 按固定时间窗口轮转保存 `.perf.data`
- 自动清理超过保留期的历史采样
- 根据输入时间段回查对应窗口
- 一键生成 `perfscript`、`.folded` 和 SVG 火焰图
- 提供 Web 页面查看概览、窗口列表和火焰图

默认交付形态：

- Docker 镜像：`cpu-profiler:latest`
- 导出文件：`task2/profiler.tar`
- 默认访问地址：`http://localhost:8080`
- 默认数据根目录：`/data`

## 2. 架构设计

整体结构由一个 collector 和一个轻量 Web 服务组成：

```text
宿主机
├── Docker 容器 cpu-profiler
│   ├── perfbox web
│   │   ├── 启动 Web UI
│   │   ├── 自动拉起 collector 子进程
│   │   └── 提供 /api/overview /api/windows /api/query /api/flame
│   └── perfbox start
│       ├── 调用 perf record -a --call-graph dwarf
│       ├── 每 60s 生成一个 perf.data 窗口
│       ├── 写入 /data/perf/index.jsonl
│       └── 执行 retention clean
├── 宿主机 perf 二进制
│   └── 可通过 PERF_BIN=/host-perf 挂载到容器
└── 挂载目录 ./data
    ├── perf/    保存 perf.data 和索引
    ├── output/  保存 perfscript / folded / svg
    └── logs/    预留日志目录
```

## 3. 目录结构

```text
task2/
├── Dockerfile
├── README.md
├── profiler.tar
├── ui-preview.html
├── src/
│   ├── bin/
│   │   └── perfbox
│   └── perfbox/
│       ├── __init__.py
│       ├── __main__.py
│       ├── cli.py
│       ├── collector.py
│       ├── config.py
│       ├── flame.py
│       ├── query.py
│       └── web.py
├── test/
│   ├── cpu_hotspot.c
│   ├── test_scenario.sh
│   └── test_symbolic_hotspot.sh
├── third_party/
│   └── FlameGraph/
└── data/
    ├── perf/
    └── output/
```

## 4. 快速启动

### 4.1 题目要求的一键启动

评审方执行下面两条命令后，容器会同时启动数据采集和 Web：

```bash
cd task2
docker load -i profiler.tar
docker run --privileged -d -p 8080:8080 --name cpu-profiler cpu-profiler:latest
```

启动完成后访问：

```text
http://localhost:8080
```

当前镜像默认入口等价于：

```bash
perfbox web --host 0.0.0.0 --port 8080
```

Web 服务会自动尝试拉起 collector 子进程，因此评审不需要再额外执行采集命令。

### 4.2 推荐的可验证启动方式

为了同时满足宿主机采样、数据持久化和内核版本兼容，推荐使用：

```bash
cd task2
mkdir -p data

PERF_HOST="$(readlink -f /usr/lib/linux-tools/$(uname -r)/perf)"

docker run --privileged --pid=host -d \
  -p 8080:8080 \
  --name cpu-profiler \
  -e PERF_BIN=/host-perf \
  -v "$PERF_HOST:/host-perf:ro" \
  -v "$(pwd)/data:/data" \
  cpu-profiler:latest
```

推荐原因：

- `--privileged`：允许 `perf` 访问宿主机 PMU 和 `perf_event_open`
- `--pid=host`：采集宿主机进程，而不是只看容器内部进程
- `PERF_BIN=/host-perf`：避免容器内 `perf` 与宿主机内核版本不匹配
- `-v "$(pwd)/data:/data"`：将采样结果和火焰图持久化到宿主机

## 5. Web 界面说明

默认打开 `http://localhost:8080` 后可直接使用 Web 页面，当前页面提供：

- 系统概览：CPU 使用率、有效窗口数、采样目录占用、火焰图产物占用
- 采样状态：显示 collector 运行状态和最近日志
- 时间范围查询：输入开始和结束时间后回查对应窗口
- 窗口列表：展示最近 N 小时采样窗口，点击即可填充查询时间
- 火焰图展示：直接生成并加载 SVG 火焰图

主要 API：

- `GET /api/overview`
- `GET /api/windows?hours=24`
- `GET /api/query?from=...&to=...`
- `POST /api/flame`
- `GET /api/diagnostics`
- `GET /artifacts/output/<name>.svg`

## 6. CLI 使用示例

查看当前有效采样窗口：

```bash
docker exec cpu-profiler perfbox list --data-dir /data/perf
```

按时间段回查：

```bash
docker exec cpu-profiler perfbox query \
  --from "2026-06-21T03:16:00+08:00" \
  --to "2026-06-21T03:19:30+08:00" \
  --data-dir /data/perf
```

生成火焰图：

```bash
docker exec cpu-profiler perfbox flame \
  --from "2026-06-21T03:16:00+08:00" \
  --to "2026-06-21T03:19:30+08:00" \
  --data-dir /data/perf \
  --output /data/output/example.svg
```

生成后会得到：

```text
/data/output/example.perfscript
/data/output/example.folded
/data/output/example.svg
```

## 7. 测试验证

建议按下面的顺序完成一次完整测试验证。

### 7.1 启动测试容器

如果 `cpu-profiler` 已经存在，先清理旧容器：

```bash
docker stop cpu-profiler
docker rm cpu-profiler
```

然后在 `task2` 目录启动新的 profiling 容器：

```bash
cd task2
mkdir -p data

PERF_HOST="$(readlink -f /usr/lib/linux-tools/$(uname -r)/perf)"

docker run --privileged --pid=host -d \
  -p 8080:8080 \
  --name cpu-profiler \
  -e PERF_BIN=/host-perf \
  -v "$PERF_HOST:/host-perf:ro" \
  -v "$(pwd)/data:/data" \
  cpu-profiler:latest
```

确认容器和 Web 都已启动：

```bash
docker logs -f cpu-profiler
```

日志中应能看到类似：

```text
perfbox web listening on http://0.0.0.0:8080
perfbox start: window=60s freq=99Hz retention=24h data_dir=/data/perf
```

页面访问地址：

```text
http://localhost:8080
```

### 7.2 运行测试脚本

项目提供两个端到端验证脚本：

```bash
cd task2
bash test/test_scenario.sh
THREADS=16 bash test/test_symbolic_hotspot.sh
```

其中：

- `test/test_scenario.sh` 使用 `stress-ng` 构造 CPU 飙升
- `test/test_symbolic_hotspot.sh` 编译并运行一个带调试符号的本地 C 压测程序

`test_symbolic_hotspot.sh` 会自动：

1. 使用 `gcc -O0 -g -fno-omit-frame-pointer -pthread` 编译 `test/cpu_hotspot.c`
2. 记录压测开始时间
3. 运行 60 秒多线程热点循环
4. 调用 `perfbox query` 回查对应窗口
5. 调用 `perfbox flame` 生成火焰图

相比 `stress-ng`，这个自定义压测程序没有被 strip，更适合演示具体函数热点。预期在火焰图中能看到：

- `matrix_hotspot`
- `synthetic_hot_loop`

脚本支持通过环境变量控制线程数，适合多核机器。例如在 32 核机器上运行 16 线程压测：

```bash
THREADS=16 bash test/test_symbolic_hotspot.sh
```

如果希望 CPU 飙升持续更久，可以把压测时间拉长。例如：

```bash
SECONDS_TO_RUN=180 THREADS=16 bash test/test_symbolic_hotspot.sh
```

这类压测更适合制造“整机 CPU 明显上升”的场景，同时仍然保留可读的函数热点。

### 7.3 等待窗口落盘并回查

采样窗口只有在当前 `perf record` 窗口结束后，才会写入 `index.jsonl`。因此压测脚本运行完后，如果立刻查询，可能出现：

```text
no matching perf.data windows
```

这是因为对应窗口尚未写盘，不代表压测失败。此时建议：

1. 继续观察容器日志
2. 等待当前采样窗口结束
3. 再执行 `query` 和 `flame`

例如：

```bash
docker logs -f cpu-profiler
```

等看到类似：

```text
window finished status=ok
```

再执行时间回查。

### 7.4 手动测试命令

手动测试也可以使用：

```bash
START_UTC="$(date -u '+%Y-%m-%dT%H:%M:%S+00:00')"
stress-ng --cpu 2 --cpu-method matrixprod -t 60s
END_UTC="$(date -u '+%Y-%m-%dT%H:%M:%S+00:00')"

docker exec cpu-profiler perfbox query \
  --from "$START_UTC" \
  --to "$END_UTC" \
  --data-dir /data/perf

docker exec cpu-profiler perfbox flame \
  --from "$START_UTC" \
  --to "$END_UTC" \
  --data-dir /data/perf \
  --output /data/output/stress-ng-matrixprod.svg
```

对于自定义多线程压测，推荐：

```bash
cd task2
THREADS=16 SECONDS_TO_RUN=180 bash test/test_symbolic_hotspot.sh
```

### 7.5 验收关注点

如果希望稳定看到具体函数名，推荐运行：

```bash
cd task2
THREADS=16 bash test/test_symbolic_hotspot.sh
```

验收时重点检查：

- 回查结果是否命中压测时间段
- 是否成功生成 SVG 火焰图
- 火焰图中是否能看到 `stress-ng` 或自定义压测程序对应的热点
- 对于自定义压测程序，是否能看到 `matrix_hotspot` / `synthetic_hot_loop`

## 8. 特权模式说明

本工具必须使用 `--privileged` 启动。原因是 `perf record -a` 需要访问宿主机 PMU、硬件性能事件、内核符号和进程信息。普通容器权限下可能出现：

- `Operation not permitted`
- `perf_event_open` 权限不足
- 硬件事件不可用
- 调用栈缺失，火焰图中 `[unknown]` 比例显著升高

推荐额外加上 `--pid=host`，否则容器只能看到自己的 PID namespace，采样结果会更偏向容器内部进程。

## 9. 设计权衡

- 默认采样频率设为 `99Hz`，优先平衡采样开销与可读性
- 默认窗口大小为 `60s`，既方便按分钟回查，也能限制单文件体积
- 采用 `index.jsonl` 维护窗口索引，简单直接，便于 CLI 和 Web 共用
- Web 服务直接内嵌在 Python 标准库 HTTP server 中，减少依赖，便于镜像交付
- 默认保留 `24h` 历史数据，控制磁盘占用，避免长期运行时数据无限增长

## 10. 常用运维命令

```bash
docker logs -f cpu-profiler
docker exec cpu-profiler perfbox list --data-dir /data/perf
docker exec cpu-profiler perfbox query --from "2026-06-21T03:16:00+08:00" --to "2026-06-21T03:19:30+08:00" --data-dir /data/perf
docker stop cpu-profiler
docker rm cpu-profiler
```
