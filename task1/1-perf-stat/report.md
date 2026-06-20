# 五场景对比表格与差异分析报告

本报告基于五类负载的锁核 `perf stat` 结果整理，正式计算采用 `cpu_core/...` 行的有效计数。当前测试平台为 Intel 混合架构 CPU，`cpu_atom/...` 在本次锁核结果中多为 `<not counted>` 或 `<not supported>`，因此未纳入计算。

## 1. 五场景对比表格

### 1.1 指标说明

| 指标 | 计算方式 | 说明 |
|---|---|---|
| IPC | `instructions / cycles` | 每周期退休指令数，反映流水线整体利用率 |
| L1 DCache Miss Rate（题目口径） | `L1-dcache-load-misses / cache-references` | 题目要求的公式，保留用于提交对齐 |
| LLC Miss Rate（题目口径） | `LLC-load-misses / cache-references` | 题目要求的公式，保留用于提交对齐 |
| 分支预测失败率 | `branch-misses / branch-instructions` | 分支预测失败占全部分支指令比例 |
| TLB Miss Rate（题目口径） | `dTLB-load-misses / cache-references` | 题目要求的公式，保留用于提交对齐 |
| Generic Cache Miss Rate | `cache-misses / cache-references` | perf 通用 cache 事件的 miss 比例 |
| L1D Load Miss Rate | `L1-dcache-load-misses / L1-dcache-loads` | 更严格的 L1D load miss rate |
| LLC Load Miss Rate | `LLC-load-misses / LLC-loads` | 更严格的 LLC load miss rate |
| dTLB Load Miss Rate | `dTLB-load-misses / dTLB-loads` | 更严格的 dTLB load miss rate |
| Frontend Bound | `perf stat -M tma_frontend_bound` | 前端取指、解码、指令供给瓶颈比例 |
| Backend Bound | `perf stat -M tma_backend_bound` | 后端执行、访存、资源等待瓶颈比例 |

说明：题目口径中的 `cache-references` 是 perf 的通用 cache 事件，在本机并不等价于 L1D/LLC/dTLB 的访问总次数。因此题目口径指标用于满足题目表格要求；分析时主要结合成对 miss rate、Generic Cache Miss Rate 和 Topdown 指标。

### 1.2 cache-references 事件口径排查

在初次整理表格时，`L1-dcache-load-misses / cache-references` 出现了远大于 100% 的结果。为了确认原因，额外检查了本机 `cache-references` 的事件映射和实际计数行为。

首先使用 `perf list --details cache-references` 和 `/sys` 中的 PMU 事件定义检查本机映射：

```bash
perf list --details cache-references
cat /sys/bus/event_source/devices/cpu_core/events/cache-references
cat /sys/bus/event_source/devices/cpu_core/events/cache-misses
```

本机输出显示：

```text
cpu_core/cache-references/: event=0x2e,umask=0x4f
cpu_core/cache-misses/:     event=0x2e,umask=0x41
```

这说明在当前 Raptor Lake-HX 平台上，`cache-references` 会被内核映射成 `cpu_core` PMU 的具体硬件事件，而不是一个抽象的“所有缓存层级访问总数”。同时，`perf list` 中存在独立的 L1D 成对事件：

```text
cpu_core/L1-dcache-loads/
cpu_core/L1-dcache-load-misses/
```

随后使用短时间测试交叉验证：

```bash
taskset -c 2 perf stat \
  -e cpu_core/cache-references/,cpu_core/cache-misses/,cpu_core/L1-dcache-loads/,cpu_core/L1-dcache-load-misses/ \
  -- stress-ng --cpu 1 --cpu-method int64 -t 3s
```

该测试中观察到：

```text
cache-references         = 363,397
cache-misses             = 182,952
L1-dcache-loads          = 19,597,293
L1-dcache-load-misses    = 197,579
```

如果 `cache-references` 是所有缓存访问总数，它不应明显小于 `L1-dcache-loads`。但实测中 `cache-references` 比 `L1-dcache-loads` 小了几十倍，说明它不能作为 L1D load 总次数，也不能作为所有缓存访问总次数。

因此，本报告保留题目要求的 `L1-dcache-load-misses / cache-references`、`LLC-load-misses / cache-references`、`dTLB-load-misses / cache-references` 作为“题目口径”指标；同时补充 `L1-dcache-loads`、`LLC-loads`、`dTLB-loads` 作为对应分母，计算更严格的成对 miss rate，并以这些成对指标作为主要分析依据。

### 1.3 题目要求衍生指标

| 负载场景 | IPC | L1 DCache Miss Rate（题目口径） | LLC Miss Rate（题目口径） | 分支预测失败率 | TLB Miss Rate（题目口径） |
|---|---:|---:|---:|---:|---:|
| 纯计算（整数 int64） | 3.054 | 103.466% | 0.448% | 0.103% | 0.146% |
| 纯计算（浮点/矩阵 matrixprod） | 2.319 | 959021.307% | 2.862% | 0.145% | 0.073% |
| 访存密集型（read64） | 4.234 | 158.449% | 0.370% | 0.000% | 10.696% |
| 随机访存型（rand-set） | 4.881 | 1.075% | 0.161% | 0.001% | 0.006% |
| 分支密集型（queens） | 1.950 | 113.553% | 0.860% | 11.625% | 0.107% |

### 1.4 补充成对 miss rate 与 Topdown 指标

| 负载场景 | Generic Cache Miss Rate | L1D Load Miss Rate | LLC Load Miss Rate | dTLB Load Miss Rate | Frontend Bound | Backend Bound |
|---|---:|---:|---:|---:|---:|---:|
| 纯计算（整数 int64） | 13.061% | 1.473% | 1.118% | 0.00224% | 0.8% | 46.3% |
| 纯计算（浮点/矩阵 matrixprod） | 19.652% | 49.372% | 10.210% | 0.00000% | 26.3% | 10.2% |
| 访存密集型（read64） | 10.418% | 0.039% | 9.752% | 0.00261% | 7.9% | 23.2% |
| 随机访存型（rand-set） | 47.014% | 0.015% | 35.602% | 0.00009% | 13.8% | 29.4% |
| 分支密集型（queens） | 14.161% | 0.006% | 2.195% | 0.00001% | 10.3% | 7.7% |

### 1.5 主导瓶颈概览

| 负载 | 执行内容 | 主导微架构压力 | 指标体现 |
|---|---|---|---|
| int64 | 64 位整数运算 | 整数 ALU、后端执行吞吐 | IPC 较高，Frontend Bound 最低，Backend Bound 最高 |
| matrixprod | 矩阵乘法 | 浮点/SIMD、L1D 数据供给、前端指令供给 | IPC 低于 int64，L1D Load Miss Rate 最高，Frontend Bound 最高 |
| read64 | 1G 大块内存连续读取 | 顺序访存、硬件预取、LLC/内存层级、TLB | IPC 较高，分支失败率近 0，Backend Bound 中等 |
| rand-set | 512M 内存区域随机设置/访问 | 随机访存、cache 局部性差、预取失效 | Generic Cache Miss Rate 和 LLC Load Miss Rate 最高，Backend Bound 较高 |
| queens | N 皇后搜索、递归回溯 | 分支预测、bad speculation、流水线清空 | IPC 最低，分支预测失败率最高 |

## 2. 差异分析报告

### 2.1 整数计算负载：int64

`int64` 主要执行 64 位整数运算，核心压力集中在后端整数 ALU、整数流水线吞吐和指令依赖链上。它的 IPC 为 3.054，说明每个周期能够退休较多指令，流水线整体利用率较好。

从前端看，`int64` 的分支预测失败率只有 0.103%，Frontend Bound 也只有 0.8%，说明取指、解码和分支预测基本能够稳定供给后端。从后端看，Backend Bound 达到 46.3%，是五类负载中最高的，说明性能主要受后端执行资源、端口占用、整数运算吞吐或指令依赖限制。

从访存看，严格的 L1D Load Miss Rate 为 1.473%，LLC Load Miss Rate 为 1.118%，dTLB Load Miss Rate 为 0.00224%，均不高。因此，`int64` 不是典型访存瓶颈，也不是前端瓶颈，而是偏后端整数执行吞吐型负载。

### 2.2 浮点/矩阵负载：matrixprod

`matrixprod` 执行矩阵乘法，包含矩阵元素加载、乘法、加法或乘加运算。相比整数计算，它更依赖浮点/SIMD 执行单元，也更依赖 load/store 端口持续供给数据。

它的 IPC 为 2.319，低于 `int64`，说明浮点/矩阵类指令对执行资源和数据供给的要求更高。分支预测失败率为 0.145%，仍然很低，说明控制流并不是主要问题。

成对指标显示，`matrixprod` 的 L1D Load Miss Rate 达到 49.372%，是五类负载中最高的；LLC Load Miss Rate 为 10.210%，也高于整数和分支负载。这说明矩阵计算对 L1D 数据供给压力非常明显，部分数据访问还会继续下探到 LLC 或更低层级。Frontend Bound 达到 26.3%，也是五类负载中最高的，说明该负载除了数据供给外，还可能受到循环体指令供给、解码、I-cache 或前端队列影响。

综合来看，`matrixprod` 不是单一瓶颈，而是浮点/SIMD 执行、L1/L2 数据供给和前端指令供给共同影响的混合型负载。

### 2.3 连续访存负载：read64

`read64` 对 1G 大块内存进行连续读取。连续访问具有较好的空间局部性，硬件预取器可以根据顺序访问模式提前加载后续 cache line，因此该负载的分支预测失败率几乎为 0，IPC 达到 4.234。

从成对指标看，`read64` 的 L1D Load Miss Rate 只有 0.039%，说明顺序访问对 L1D/预取机制较友好；LLC Load Miss Rate 为 9.752%，说明仍有一定比例访问会到达更低层级。dTLB Load Miss Rate 为 0.00261%，数值不高，但由于总 `dTLB-loads` 很大，原始 dTLB miss 次数仍达到 7,672,991，说明大工作集连续扫描会带来可观的地址翻译事件。

Topdown 指标中，Backend Bound 为 23.2%，Frontend Bound 为 7.9%，说明前端不是主要瓶颈，后端压力更多来自 load/store、cache/memory 子系统、TLB 和内存带宽。`read64` 因此主要反映连续大块访存下的预取效率、LLC/内存层级访问和地址翻译压力。

### 2.4 随机访存负载：rand-set

`rand-set` 在 512M 内存区域中随机设置或访问数据。随机地址序列缺少稳定步长，硬件预取器难以预测下一次访问位置，cache line 的空间局部性也较差。

该负载的 IPC 为 4.881，是五类中最高的，但这不表示访存压力最低。它的 Generic Cache Miss Rate 达到 47.014%，LLC Load Miss Rate 达到 35.602%，均为五类负载中最高，说明 cache 子系统承受了最明显的随机访问和替换压力。

从 Topdown 看，Backend Bound 为 29.4%，明显高于 `matrixprod`、`read64` 和 `queens`。这说明随机访存会让后端成为主要限制因素，可能表现为 load/store 队列等待、LLC 访问延迟、乱序窗口被长延迟 load 占满等。由于分支预测失败率只有 0.001%，dTLB Load Miss Rate 也只有 0.00009%，它的主导问题不是控制流或 TLB，而是 cache 局部性差和预取失效。

### 2.5 分支密集负载：queens

`queens` 执行 N 皇后搜索，包含大量递归、条件判断和回溯。搜索路径依赖中间状态，分支走向难以稳定预测，因此它是典型的分支密集型负载。

该负载 IPC 为 1.950，是五类中最低的；分支预测失败率为 11.625%，远高于其他负载。这说明性能主要被错误分支预测拖慢。分支预测失败时，CPU 会丢弃错误路径上已经取指、解码甚至进入流水线的指令，并从正确路径重新取指，导致前端重定向和流水线清空，后端执行单元也会出现空泡。

访存相关成对指标并不突出：L1D Load Miss Rate 为 0.006%，LLC Load Miss Rate 为 2.195%，dTLB Load Miss Rate 为 0.00001%。因此，`queens` 的瓶颈不是 cache/memory 后端等待，而是分支预测失败、bad speculation 和控制流恢复成本。

## 3. 总结

从前端角度看，`matrixprod` 的 Frontend Bound 最高，为 26.3%，说明其指令供给或前端队列存在一定压力；`queens` 的关键问题则是分支预测失败率高达 11.625%，属于控制流和 bad speculation 主导。

从后端执行角度看，`int64` 的 Backend Bound 最高，为 46.3%，主要受整数执行吞吐、端口资源和依赖链影响；`rand-set` 的 Backend Bound 为 29.4%，主要由随机访存和 cache 层级访问延迟造成。

从访存子系统角度看，`matrixprod` 的 L1D Load Miss Rate 最高，说明矩阵计算对 L1D 数据供给最敏感；`rand-set` 的 Generic Cache Miss Rate 和 LLC Load Miss Rate 最高，说明随机访存对 LLC/内存层级压力最大；`read64` 的顺序访问对 L1D 较友好，但由于工作集大，仍会产生大量地址翻译和更低层 cache 访问事件。

整体来看，五类负载分别覆盖了后端整数吞吐、浮点/矩阵计算、连续访存、随机访存和分支预测五类典型微架构压力点。补充成对 miss rate 后，L1D、LLC 和 dTLB 的分析口径更清晰，也避免了单纯使用 `cache-references` 作为统一分母带来的误读。
