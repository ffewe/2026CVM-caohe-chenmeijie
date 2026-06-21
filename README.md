# 2026 CVM 考核仓库
https://github.com/ffewe/2026CVM-caohe-chenmeijie/blob/main/task1/2-flamegraph/README.md
本仓库用于提交《CVM 竞品微架构深度分析考题》的完成结果，覆盖题目 1 的三项必做内容，以及题目 2 的选做加分项代码实现。

## 个人信息

- 姓名：陈美洁
- 仓库名：`2026CVM-kaohe-caohe-chenmeijie`
- 考核主题：CPU 微架构性能分析、火焰图定位、Cache Line 微基准、持续 CPU Profiling 工具

## 完成情况概览
| 题目 | 内容 | 当前状态 | 说明 |
|---|---|---|---|
| 题目 1-1 | 多场景微架构指标采集 | 已完成 | 已提供 `perf stat` 运行说明、环境采集方案、结果文件与分析文档骨架 |
| 题目 1-2 | 火焰图生成与热点分析 | 已完成 | 已提供 FlameGraph 工具链、五类负载火焰图文件与运行说明 |
| 题目 1-3 | Cache Line 微基准测试 | 已完成 | 已提供 C 语言微基准程序、批量实验结果、火焰图与说明文档 |
| 题目 2 | 持续 CPU Profiling 工具 | 已完成代码实现 | 已提供容器化工具源码、Web 界面、测试脚本与使用说明 |

说明：

- 当前仓库以“代码、结果文件、运行说明”为主。
- `resume/`、各子题 `report.pdf`、`task2/profiler.tar`、`ai-chat-log/` 等最终提交材料，当前仓库中尚未补齐。

## 仓库结构

```text
2026CVM-kaohe-caohe-chenmeijie/
├── README.md
├── task1/
│   ├── 1-perf-stat/
│   │   ├── README.md
│   │   └── results/
│   ├── 2-flamegraph/
│   │   ├── README.md
│   │   └── flamegraphs/
│   └── 3-cache-line-test/
│       ├── README.md
│       ├── src/
│       ├── results/
│       └── flamegraphs/
└── task2/
    ├── README.md
    ├── Dockerfile
    ├── src/
    ├── test/
    ├── third_party/
    └── ui-preview.html
```

## 题目 1：CPU 微架构性能分析

### 1. `task1/1-perf-stat`

对应考题“多场景微架构指标采集”。

已包含内容：

- 五类典型负载的 `perf stat` 采集方案
- 环境记录要求与原始输出保存方式
- IPC、Cache Miss Rate、Branch Miss Rate、TLB Miss Rate 等衍生指标口径
- `results/` 中的原始结果文件

建议评审入口：

- [task1/1-perf-stat/README.md](/home/mkom/2026CVM-kaohe-chenmeijie/2026CVM-caohe-chenmeijie/task1/1-perf-stat/README.md)
- `task1/1-perf-stat/results/`

### 2. `task1/2-flamegraph`

对应考题“火焰图生成与热点分析”。

已包含内容：

- `perf record`、`perf script`、FlameGraph 的完整出图流程
- 五类负载的火焰图输出文件
- 针对热点函数、内核态符号、不同负载形态差异的分析说明框架

建议评审入口：

- [task1/2-flamegraph/README.md](/home/mkom/2026CVM-kaohe-chenmeijie/2026CVM-caohe-chenmeijie/task1/2-flamegraph/README.md)
- `task1/2-flamegraph/flamegraphs/`

### 3. `task1/3-cache-line-test`

对应考题“AI 辅助编写 Cache Line 微基准测试”。

已包含内容：

- C 语言微基准源码 `src/cache_line_test.c`
- 不同 stride 下的性能结果与 `perf stat` 原始输出
- `stride=1`、`stride=16`、`stride=64` 的火焰图
- 面向复现实验的编译、运行、采样说明

建议评审入口：

- [task1/3-cache-line-test/README.md](/home/mkom/2026CVM-kaohe-chenmeijie/2026CVM-caohe-chenmeijie/task1/3-cache-line-test/README.md)
- [task1/3-cache-line-test/src/cache_line_test.c](/home/mkom/2026CVM-kaohe-chenmeijie/2026CVM-caohe-chenmeijie/task1/3-cache-line-test/src/cache_line_test.c)
- `task1/3-cache-line-test/results/`

## 题目 2：持续 CPU Profiling 工具

`task2/` 对应选做加分题，实现了一个面向 Linux 场景的持续 CPU Profiling 工具。

当前实现能力包括：

- 后台持续采集 `perf record` 数据并按时间窗口轮转
- 自动清理超出保留时长的历史采样文件
- 按时间区间回查采样窗口
- 一键生成火焰图
- 提供命令行接口和 Web 界面
- 提供 Dockerfile 与测试脚本

建议评审入口：

- [task2/README.md](/home/mkom/2026CVM-kaohe-chenmeijie/2026CVM-caohe-chenmeijie/task2/README.md)
- [task2/src/perfbox/cli.py](/home/mkom/2026CVM-kaohe-chenmeijie/2026CVM-caohe-chenmeijie/task2/src/perfbox/cli.py)
- [task2/src/perfbox/web.py](/home/mkom/2026CVM-kaohe-chenmeijie/2026CVM-caohe-chenmeijie/task2/src/perfbox/web.py)
- [task2/test/test_scenario.sh](/home/mkom/2026CVM-kaohe-chenmeijie/2026CVM-caohe-chenmeijie/task2/test/test_scenario.sh)

## 与考题要求的对应关系

本仓库当前已经覆盖考题中的主要工程内容：

- 题目 1：三项必做题均已有对应目录、说明文档、结果文件或源码
- 题目 2：核心功能、Docker 工程结构、测试脚本和前端界面代码均已具备

当前仍建议在最终提交前补齐以下材料：

- `resume/resume.pdf`
- `task1/*/report.pdf`
- `task1/3-cache-line-test/ai-chat-log/`
- `task2/profiler.tar`
- `task2` 的测试截图、录屏或产物归档

## 使用建议

若从总入口开始阅读，推荐顺序如下：

1. 先阅读 [task1/1-perf-stat/README.md](/home/mkom/2026CVM-kaohe-chenmeijie/2026CVM-caohe-chenmeijie/task1/1-perf-stat/README.md)，了解测试环境和指标采集口径。
2. 再阅读 [task1/2-flamegraph/README.md](/home/mkom/2026CVM-kaohe-chenmeijie/2026CVM-caohe-chenmeijie/task1/2-flamegraph/README.md) 与火焰图产物，查看热点分析思路。
3. 接着查看 [task1/3-cache-line-test/README.md](/home/mkom/2026CVM-kaohe-chenmeijie/2026CVM-caohe-chenmeijie/task1/3-cache-line-test/README.md) 和源码，了解自定义微基准实验。
4. 最后阅读 [task2/README.md](/home/mkom/2026CVM-kaohe-chenmeijie/2026CVM-caohe-chenmeijie/task2/README.md)，评估持续 CPU Profiling 工具的设计与实现。
