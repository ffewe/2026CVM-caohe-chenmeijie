# Cache Line 微基准测试

本目录用于完成题目 1 第三小题：**AI 辅助编写自定义微基准测试**。

实验目标是编写一个 C 语言程序，通过不同步长遍历大数组，观察 **CPU Cache Line 大小对数组遍历性能的影响**。程序会测试不同 stride 下的平均访问延迟和有效读取吞吐量，并使用 `perf stat` 采集 `L1-dcache-load-misses` 和 `LLC-load-misses` 等硬件性能事件。

---

## 1. 目录结构

```bash
task1/3-cache-line-test/
├── README.md
├── src/
│   └── cache_line_test.c
├── results/
│   ├── perf_summary.csv
│   ├── perf_stride_1.txt
│   ├── perf_stride_2.txt
│   ├── perf_stride_4.txt
│   ├── perf_stride_8.txt
│   ├── perf_stride_16.txt
│   ├── perf_stride_32.txt
│   ├── perf_stride_64.txt
│   ├── perf_stride_128.txt
│   └── perf_stride_256.txt
├── flamegraphs/
│   ├── stride_1_flame.svg
│   └── stride_64_flame.svg
├── report.pdf
└── ai-chat-log/
```

---

## 2. 测试环境准备

建议在 Linux x86_64 环境下运行。

需要安装：

```bash
sudo apt update
sudo apt install -y build-essential linux-tools-common linux-tools-generic git
```

如果使用 CentOS / RHEL 系统：

```bash
sudo yum groupinstall -y "Development Tools"
sudo yum install -y perf git
```

检查 `perf` 是否可用：

```bash
perf --version
```

如果 `perf` 权限受限，可以临时降低限制：

```bash
sudo sh -c 'echo -1 > /proc/sys/kernel/perf_event_paranoid'
sudo sh -c 'echo 0 > /proc/sys/kernel/kptr_restrict'
```

也可以在命令前加 `sudo` 运行。

---

## 3. 编译方法

进入本目录：

```bash
cd task1/3-cache-line-test
```

创建输出目录：

```bash
mkdir -p results flamegraphs
```

编译 C 程序：

```bash
gcc -O2 -g -fno-omit-frame-pointer -fno-tree-vectorize \
  -o cache_line_test src/cache_line_test.c
```

参数说明：

```text
-O2                    启用常规优化，使程序性能接近真实运行场景
-g                     保留调试符号，方便 perf / 火焰图显示函数名
-fno-omit-frame-pointer 保留栈帧，便于 perf record -g 采集调用栈
-fno-tree-vectorize     关闭自动向量化，避免编译器将循环改写成 SIMD 宽访存模式
```

---

## 4. 程序运行方式

程序参数格式：

```bash
./cache_line_test <array_size_mb> <stride_bytes> <repeat>
```

参数含义：

```text
array_size_mb  测试数组大小，单位 MB，要求 >= 16MB
stride_bytes   遍历数组时的步长，单位字节
repeat         重复遍历次数，用于增加测试时间、降低计时误差
```

示例：

```bash
./cache_line_test 256 64 20
```

含义：

```text
使用 256MB 数组
按 64 字节步长遍历
重复遍历 20 轮
```

程序输出 CSV 格式结果：

```text
array_size_mb,stride_bytes,repeat,accesses,elapsed_ns,ns_per_access,effective_MBps,sum
256,64,20,83886080,xxxx,xxxx,xxxx,xxxx
```

其中：

```text
ns_per_access    平均每次访问延迟，单位 ns/access
effective_MBps   程序视角下的有效读取吞吐量，单位 MB/s
```

---

## 5. 批量运行所有 stride

本实验测试以下步长：

```text
1, 2, 4, 8, 16, 32, 64, 128, 256 字节
```

批量运行命令：

```bash
mkdir -p results

echo "array_size_mb,stride_bytes,repeat,accesses,elapsed_ns,ns_per_access,effective_MBps,sum" \
  > results/perf_summary.csv

for s in 1 2 4 8 16 32 64 128 256; do
    echo "Running stride=$s"
    ./cache_line_test 256 $s 20 | tail -n 1 >> results/perf_summary.csv
done
```

运行完成后，性能数据保存在：

```bash
results/perf_summary.csv
```

---

## 6. perf stat 采集命令

题目要求采集不同 stride 下的 `L1-dcache-load-misses` 和 `LLC-load-misses`。

推荐同时采集以下事件：

```text
cycles
instructions
cache-references
cache-misses
L1-dcache-load-misses
LLC-load-misses
```

单个 stride 采集示例：

```bash
perf stat \
  -e cycles,instructions,cache-references,cache-misses,L1-dcache-load-misses,LLC-load-misses \
  -o results/perf_stride_64.txt \
  -- ./cache_line_test 256 64 20
```

批量采集所有 stride：

```bash
mkdir -p results

for s in 1 2 4 8 16 32 64 128 256; do
    echo "perf stat stride=$s"
    perf stat \
      -e cycles,instructions,cache-references,cache-misses,L1-dcache-load-misses,LLC-load-misses \
      -o results/perf_stride_${s}.txt \
      -- ./cache_line_test 256 $s 20
done
```

如果权限不足，可以使用：

```bash
sudo perf stat \
  -e cycles,instructions,cache-references,cache-misses,L1-dcache-load-misses,LLC-load-misses \
  -o results/perf_stride_64.txt \
  -- ./cache_line_test 256 64 20
```

---

## 7. 衍生指标计算方式

后续报告中可以根据 `perf stat` 结果计算：

```text
IPC = instructions / cycles

L1 DCache Miss Rate = L1-dcache-load-misses / cache-references

LLC Miss Rate = LLC-load-misses / cache-references
```

程序自身输出的性能指标：

```text
平均访问延迟 ns/access = elapsed_ns / accesses

有效读取吞吐量 MB/s = accesses × 8B / elapsed_time
```

说明：

```text
程序每次显式读取 uint64_t，即 8 字节。
effective_MBps 是程序视角下的有效读取吞吐量，不等价于内存总线真实带宽。
```

---

## 8. perf record 火焰图采集

题目要求至少选择两个 stride 生成火焰图。这里选择：

```text
stride = 1
stride = 64
```

选择原因：

```text
stride=1 代表 cache line 内连续访问，空间局部性最好；
stride=64 接近主流 x86 CPU 的 cache line 大小，能够体现 cache line 边界对性能的影响。
```

---

### 8.1 下载 FlameGraph 工具

在 `task1/3-cache-line-test` 目录下执行：

```bash
git clone https://github.com/brendangregg/FlameGraph.git
```

---

### 8.2 采集 stride=1

```bash
perf record -F 99 -g \
  -o results/perf_stride_1.data \
  -- ./cache_line_test 256 1 50
```

导出 perf script：

```bash
perf script -i results/perf_stride_1.data > results/perf_stride_1.script
```

生成火焰图：

```bash
./FlameGraph/stackcollapse-perf.pl results/perf_stride_1.script | \
./FlameGraph/flamegraph.pl > flamegraphs/stride_1_flame.svg
```

---

### 8.3 采集 stride=64

```bash
perf record -F 99 -g \
  -o results/perf_stride_64.data \
  -- ./cache_line_test 256 64 50
```

导出 perf script：

```bash
perf script -i results/perf_stride_64.data > results/perf_stride_64.script
```

生成火焰图：

```bash
./FlameGraph/stackcollapse-perf.pl results/perf_stride_64.script | \
./FlameGraph/flamegraph.pl > flamegraphs/stride_64_flame.svg
```

如果权限不足，可以将上述 `perf record` 和 `perf script` 命令前加 `sudo`。

---

## 9. 预期实验现象

预期性能趋势：

```text
stride 较小时，例如 1B、2B、4B、8B：
多个访问会落在同一条 cache line 内，空间局部性较好，平均访问延迟较低。

stride 增大到 16B、32B：
一条 cache line 内可复用的数据次数减少，平均访问延迟可能开始上升。

stride 达到 64B：
每次访问基本落到新的 cache line 上，cache line 内部剩余数据难以被充分利用，L1-dcache-load-misses 可能明显增加，性能曲线可能出现拐点。

stride 达到 128B、256B：
访问间隔继续增大，空间局部性更差，可能进一步增加 LLC miss 和 TLB 压力。
```

报告中重点标注：

```text
stride = 64B
```

该位置通常对应主流 x86 CPU 的 Cache Line 边界。

---

## 10. 结果文件说明

运行完成后，应得到以下文件：

```bash
results/perf_summary.csv
```

保存程序自身输出的性能数据，包括：

```text
stride_bytes
ns_per_access
effective_MBps
```

每个 stride 对应的 perf stat 原始输出：

```bash
results/perf_stride_1.txt
results/perf_stride_2.txt
results/perf_stride_4.txt
results/perf_stride_8.txt
results/perf_stride_16.txt
results/perf_stride_32.txt
results/perf_stride_64.txt
results/perf_stride_128.txt
results/perf_stride_256.txt
```

火焰图文件：

```bash
flamegraphs/stride_1_flame.svg
flamegraphs/stride_64_flame.svg
```

---

## 11. 一键运行示例

可以将下面内容保存为 `run_all.sh`：

```bash
#!/bin/bash
set -e

mkdir -p results flamegraphs

gcc -O2 -g -fno-omit-frame-pointer -fno-tree-vectorize \
  -o cache_line_test src/cache_line_test.c

echo "array_size_mb,stride_bytes,repeat,accesses,elapsed_ns,ns_per_access,effective_MBps,sum" \
  > results/perf_summary.csv

for s in 1 2 4 8 16 32 64 128 256; do
    echo "[RUN] stride=$s"
    ./cache_line_test 256 $s 20 | tail -n 1 >> results/perf_summary.csv

    echo "[PERF STAT] stride=$s"
    perf stat \
      -e cycles,instructions,cache-references,cache-misses,L1-dcache-load-misses,LLC-load-misses \
      -o results/perf_stride_${s}.txt \
      -- ./cache_line_test 256 $s 20
done

if [ ! -d FlameGraph ]; then
    git clone https://github.com/brendangregg/FlameGraph.git
fi

echo "[PERF RECORD] stride=1"
perf record -F 99 -g \
  -o results/perf_stride_1.data \
  -- ./cache_line_test 256 1 50

perf script -i results/perf_stride_1.data > results/perf_stride_1.script

./FlameGraph/stackcollapse-perf.pl results/perf_stride_1.script | \
./FlameGraph/flamegraph.pl > flamegraphs/stride_1_flame.svg

echo "[PERF RECORD] stride=64"
perf record -F 99 -g \
  -o results/perf_stride_64.data \
  -- ./cache_line_test 256 64 50

perf script -i results/perf_stride_64.data > results/perf_stride_64.script

./FlameGraph/stackcollapse-perf.pl results/perf_stride_64.script | \
./FlameGraph/flamegraph.pl > flamegraphs/stride_64_flame.svg

echo "All tests finished."
```

赋予执行权限：

```bash
chmod +x run_all.sh
```

运行：

```bash
./run_all.sh
```

如果 perf 权限不足，使用：

```bash
sudo ./run_all.sh
```

---

## 12. 报告撰写建议

报告中建议包含：

```text
1. 测试环境
   - CPU 型号
   - cache line size
   - L1/L2/L3 cache 大小
   - 内核版本
   - 编译器版本

2. 实验方法
   - 数组大小
   - stride 取值
   - repeat 次数
   - 编译参数
   - perf stat 事件

3. 性能结果
   - stride vs ns/access 曲线
   - stride vs effective_MBps 曲线

4. perf 指标分析
   - L1-dcache-load-misses 对比
   - LLC-load-misses 对比
   - IPC 对比

5. 火焰图分析
   - stride=1 热点函数
   - stride=64 热点函数
   - 两者差异

6. Cache Line 拐点解释
   - 64B cache line
   - 空间局部性
   - cache line 利用率
   - L1/LLC miss 增加原因

7. AI 辅助说明
   - 使用 AI 生成初版 C 程序
   - 使用 AI 解释 perf 指标
   - 使用 AI 排查编译、运行、火焰图生成问题
```

---

## 13. 常见问题

### 13.1 perf 提示无权限

临时解决：

```bash
sudo sh -c 'echo -1 > /proc/sys/kernel/perf_event_paranoid'
sudo sh -c 'echo 0 > /proc/sys/kernel/kptr_restrict'
```

或者使用：

```bash
sudo perf stat ...
sudo perf record ...
```

---

### 13.2 火焰图没有函数名

确认编译时加入：

```bash
-g -fno-omit-frame-pointer
```

并使用：

```bash
perf record -g
```

---

### 13.3 结果波动较大

建议：

```text
1. 增加 repeat 次数
2. 固定 CPU 核心运行
3. 关闭其他后台负载
4. 多次运行取平均值
```

例如固定到 CPU 0：

```bash
taskset -c 0 ./cache_line_test 256 64 20
```

perf 采集时也可以固定核心：

```bash
taskset -c 0 perf stat \
  -e cycles,instructions,cache-references,cache-misses,L1-dcache-load-misses,LLC-load-misses \
  -o results/perf_stride_64.txt \
  -- ./cache_line_test 256 64 20
```
