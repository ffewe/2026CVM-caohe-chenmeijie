# 多场景微架构指标采集

本目录对应题目一的第一小题：使用 `perf stat` 对五类典型负载采集微架构指标，并在题目必做指标基础上额外加入前端停顿和后端停顿相关的 Topdown 指标。

## 目录说明

```text
task1/1-perf-stat/
├── README.md
├── results/
│   ├── int64.txt
│   ├── matrixprod.txt
│   ├── read64.txt
│   ├── rand-set.txt
│   ├── queens.txt
│   ├── env-info.md
│   └── env/
│       ├── lscpu.txt
│       ├── uname.txt
│       ├── virt.txt
│       ├── numa.txt
│       ├── cpupower.txt
│       └── cpuinfo.txt
└── report.pdf
```

## 环境准备

安装依赖：

```bash
sudo apt update
sudo apt install -y linux-tools-common linux-tools-generic linux-tools-$(uname -r) stress-ng numactl cpufrequtils
```

如果 `cpupower` 不存在，可额外安装：

```bash
sudo apt install -y linux-cpupower
```

检查工具是否可用：

```bash
perf --version
stress-ng --version
numactl --hardware
cpupower frequency-info
```

如果某个 `stress-ng` 方法不可用，先查看候选项：

```bash
stress-ng --cpu-method list
stress-ng --vm-method list
```

## 环境记录落盘

提交时保留环境原始输出，并整理一份 `results/env-info.md`。

```bash
mkdir -p results/env
lscpu > results/env/lscpu.txt
uname -a > results/env/uname.txt
systemd-detect-virt > results/env/virt.txt
numactl --hardware > results/env/numa.txt
cpupower frequency-info > results/env/cpupower.txt
cat /proc/cpuinfo > results/env/cpuinfo.txt
```

`results/env-info.md` 建议包含：

```md
# 测试环境记录

## 1. CPU 信息

- CPU 型号：从 `lscpu` 的 `Model name` 提取
- 微架构代号：根据 CPU 型号填写，例如 Raptor Lake-HX / Cascade Lake / Zen 4 / Neoverse V2

## 2. 内核与虚拟化

- 内核版本：从 `uname -a` 提取
- 虚拟化类型：从 `systemd-detect-virt` 提取

## 3. NUMA 拓扑

- 摘要记录 `numactl --hardware` 的关键结果

## 4. CPU 频率策略

- 摘要记录 `cpupower frequency-info` 的关键结果

## 5. 原始文件位置

- `results/env/lscpu.txt`
- `results/env/uname.txt`
- `results/env/virt.txt`
- `results/env/numa.txt`
- `results/env/cpupower.txt`
- `results/env/cpuinfo.txt`
```

## 采集指标

题目要求的必做 `perf stat` 事件如下：

```text
cycles,instructions,cache-references,cache-misses,L1-dcache-load-misses,L1-icache-load-misses,LLC-load-misses,branch-instructions,branch-misses,dTLB-load-misses,context-switches,cpu-migrations
```

为了计算更严格的 L1D/LLC/dTLB miss rate，本 README 在题目必做事件基础上额外加入三个成对分母事件：

```text
L1-dcache-loads,LLC-loads,dTLB-loads
```

含义如下：

| 指标 | 用途 |
|---|---|
| `L1-dcache-loads` | 作为 `L1-dcache-load-misses` 的对应分母，计算更严格的 L1D load miss rate |
| `LLC-loads` | 作为 `LLC-load-misses` 的对应分母，计算更严格的 LLC load miss rate |
| `dTLB-loads` | 作为 `dTLB-load-misses` 的对应分母，计算更严格的 dTLB load miss rate |

为了观察前端停顿和后端停顿，本 README 还额外加入两个 Intel Topdown/TMA 指标：

```text
tma_frontend_bound,tma_backend_bound
```

含义如下：

| 指标 | 含义 | 用途 |
|---|---|---|
| `tma_frontend_bound` | 前端无法充分向后端供给微操作的比例 | 判断取指、解码、I-cache、ITLB、分支重定向等前端问题是否明显 |
| `tma_backend_bound` | 后端成为瓶颈的比例 | 判断执行单元、load/store、cache/memory、资源队列等后端问题是否明显 |

采集命令统一采用：

```bash
perf stat -e <题目必做事件 + L1-dcache-loads,LLC-loads,dTLB-loads> -M tma_frontend_bound,tma_backend_bound -- <测试命令>
```

由于同一次 `perf stat` 中事件较多，输出中可能出现事件复用比例，例如 `(81.82%)`。这不影响保留完整原始输出；如果希望更稳定地观察前端/后端瓶颈比例，可以额外单独执行 `perf stat -M tma_frontend_bound,tma_backend_bound -- <测试命令>` 作为补充校验。

补充说明：题目给出的 `L1-dcache-load-misses / cache-references`、`LLC-load-misses / cache-references`、`dTLB-load-misses / cache-references` 可以按题目口径保留；但在当前 Intel 平台上，`cache-references` 并不等价于 L1D/LLC/dTLB 的访问总次数。因此建议同时采集上述成对分母事件，在报告中补充更严格的 miss rate。

## 混合架构 CPU 的测试口径

当前机器为 Intel 混合架构 CPU。为了降低 P-core / E-core 调度差异对结果的影响，五类单线程负载统一固定到同一个逻辑 CPU：

```bash
taskset -c 2
```

报告中建议说明：

- 本次正式对比使用固定核心运行结果。
- 对 Intel 混合架构平台，优先使用 `cpu_core/...` 域的有效计数。
- `cpu_atom/...` 若出现 `<not counted>` 或 `<not supported>`，说明该事件没有在当前固定核心上计数，不能混入正式表格计算。
- Topdown 指标是百分比性质的瓶颈分类，用于辅助解释 IPC、cache miss、branch miss、TLB miss 等基础指标。

## 五类负载采集命令

先进入本目录并创建结果目录：

```bash
cd task1/1-perf-stat
mkdir -p results
```

### 1. 纯计算（整数 int64）

```bash
taskset -c 2 perf stat -e cycles,instructions,cache-references,cache-misses,L1-dcache-loads,L1-dcache-load-misses,L1-icache-load-misses,LLC-loads,LLC-load-misses,branch-instructions,branch-misses,dTLB-loads,dTLB-load-misses,context-switches,cpu-migrations -M tma_frontend_bound,tma_backend_bound -- \
stress-ng --cpu 1 --cpu-method int64 -t 30s \
2>&1 | tee results/int64.txt
```

### 2. 纯计算（浮点/矩阵 matrixprod）

```bash
taskset -c 2 perf stat -e cycles,instructions,cache-references,cache-misses,L1-dcache-loads,L1-dcache-load-misses,L1-icache-load-misses,LLC-loads,LLC-load-misses,branch-instructions,branch-misses,dTLB-loads,dTLB-load-misses,context-switches,cpu-migrations -M tma_frontend_bound,tma_backend_bound -- \
stress-ng --cpu 1 --cpu-method matrixprod -t 30s \
2>&1 | tee results/matrixprod.txt
```

### 3. 访存密集型（read64）

```bash
taskset -c 2 perf stat -e cycles,instructions,cache-references,cache-misses,L1-dcache-loads,L1-dcache-load-misses,L1-icache-load-misses,LLC-loads,LLC-load-misses,branch-instructions,branch-misses,dTLB-loads,dTLB-load-misses,context-switches,cpu-migrations -M tma_frontend_bound,tma_backend_bound -- \
stress-ng --vm 1 --vm-bytes 1G --vm-method read64 --vm-keep -t 30s \
2>&1 | tee results/read64.txt
```

### 4. 随机访存型（rand-set）

```bash
taskset -c 2 perf stat -e cycles,instructions,cache-references,cache-misses,L1-dcache-loads,L1-dcache-load-misses,L1-icache-load-misses,LLC-loads,LLC-load-misses,branch-instructions,branch-misses,dTLB-loads,dTLB-load-misses,context-switches,cpu-migrations -M tma_frontend_bound,tma_backend_bound -- \
stress-ng --vm 1 --vm-bytes 512M --vm-method rand-set --vm-keep -t 30s \
2>&1 | tee results/rand-set.txt
```

### 5. 分支密集型（queens）

```bash
taskset -c 2 perf stat -e cycles,instructions,cache-references,cache-misses,L1-dcache-loads,L1-dcache-load-misses,L1-icache-load-misses,LLC-loads,LLC-load-misses,branch-instructions,branch-misses,dTLB-loads,dTLB-load-misses,context-switches,cpu-migrations -M tma_frontend_bound,tma_backend_bound -- \
stress-ng --cpu 1 --cpu-method queens -t 30s \
2>&1 | tee results/queens.txt
```

## 结果文件要求

`results/` 目录中保留每类负载的完整 `perf stat` 原始输出：

- `results/int64.txt`
- `results/matrixprod.txt`
- `results/read64.txt`
- `results/rand-set.txt`
- `results/queens.txt`

环境记录文件：

- `results/env-info.md`
- `results/env/lscpu.txt`
- `results/env/uname.txt`
- `results/env/virt.txt`
- `results/env/numa.txt`
- `results/env/cpupower.txt`
- `results/env/cpuinfo.txt`

## 汇总表建议

报告中的横向对比表至少保留题目要求的衍生指标：

| 衍生指标 | 计算方式 |
|---|---|
| IPC | `instructions / cycles` |
| L1 DCache Miss Rate | `L1-dcache-load-misses / cache-references` |
| LLC Miss Rate | `LLC-load-misses / cache-references` |
| 分支预测失败率 | `branch-misses / branch-instructions` |
| TLB Miss Rate | `dTLB-load-misses / cache-references` |

建议额外补充更严格的成对 miss rate：

| 补充衍生指标 | 计算方式 |
|---|---|
| L1D Load Miss Rate | `L1-dcache-load-misses / L1-dcache-loads` |
| LLC Load Miss Rate | `LLC-load-misses / LLC-loads` |
| dTLB Load Miss Rate | `dTLB-load-misses / dTLB-loads` |
| Generic Cache Miss Rate | `cache-misses / cache-references` |

在此基础上增加两列 Topdown 指标：

| 补充指标 | 来源 | 报告含义 |
|---|---|---|
| Frontend Bound | `perf stat -M tma_frontend_bound` 输出的百分比 | 前端取指/解码/指令供给瓶颈程度 |
| Backend Bound | `perf stat -M tma_backend_bound` 输出的百分比 | 后端执行/访存/资源瓶颈程度 |

## 分析写法建议

差异分析可以按题目要求从前端取指/解码、后端执行单元、访存子系统三个角度组织：

1. 先用 `IPC` 判断整体流水线效率。
2. 用 `branch-misses / branch-instructions` 判断分支预测压力。
3. 用 `L1-dcache-load-misses`、`LLC-load-misses`、`dTLB-load-misses` 判断 cache、内存层级和地址翻译压力。
4. 用 `tma_frontend_bound` 判断是否存在明显前端供给不足。
5. 用 `tma_backend_bound` 判断是否存在明显后端执行或访存瓶颈。

示例描述：

```text
若某负载的 Backend Bound 明显高于其他负载，同时 cache miss 或 TLB miss 也较高，则说明性能更可能受访存子系统或后端资源限制。
若某负载的 Frontend Bound 明显高，同时分支预测失败率或 L1 ICache miss 较高，则说明前端取指、解码或分支重定向可能是主要瓶颈。
```

## 复现顺序

评审可按以下顺序复现：

```bash
cd task1/1-perf-stat
cat README.md
ls results
```

如果需要完整复测，按“五类负载采集命令”依次运行五条 `perf stat` 命令即可。
