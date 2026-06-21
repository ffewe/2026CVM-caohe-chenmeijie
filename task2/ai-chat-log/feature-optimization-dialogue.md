# task2 功能优化对话记录

说明：

- 本文件整理了本次 `task2` 功能优化过程中与 AI 编程助手的主要往返对话。
- 内容按真实开发顺序归纳，重点保留需求、判断、修改方向、验证问题和解决方案。
- 由于平台环境限制，这里保存的是可提交的文本整理稿，用于说明 AI 参与开发与调试的过程。

---

## 1. Web 是否算完成

**用户：**

现在的 web 还没完成吗，他不是可以用了吗

**AI：**

从当前仓库状态看，`web.py` 已经实现了 Web 后端逻辑，但 CLI 还没有注册 `web` 子命令，`Dockerfile` 默认也还是 `perfbox start`，而且页面文件 `ui-preview.html` 当时缺失，所以不能算最终交付完成。

---

## 2. 打通 docker load + docker run 后自动启动 Web

**用户：**

那你先完成这个功能吧，实现的效果是当评审 docker load + docker run 之后，数据采集和 web 都会同时启动是吗

**AI：**

是，目标就是让评审执行 `docker load + docker run` 后，容器默认启动 `perfbox web`，Web 再自动拉起 collector 子进程，同时提供 `http://localhost:8080` 页面。

**实现内容：**

- 在 `task2/src/perfbox/cli.py` 中新增 `perfbox web`
- 新增 `task2/ui-preview.html`
- 修改 `task2/Dockerfile`，默认命令改为：

```bash
perfbox web --host 0.0.0.0 --port 8080
```

- 重写 `task2/README.md`，对齐新的交付方式

对应提交：

- `cba4e22 Enable web UI as default task2 container entrypoint`

---

## 3. Web 打不开的排查

**用户：**

我打不开 web

**AI：**

先查容器状态和日志。排查结果显示容器实际启动命令仍然是：

```text
Entrypoint: ["perfbox"]
Cmd: ["start"]
```

说明运行的还是旧镜像，只启动了采集器，没有启动 Web。

**建议命令：**

```bash
docker stop cpu-profiler
docker rm cpu-profiler
cd /home/mkom/2026CVM-kaohe-chenmeijie/task2
docker build -t cpu-profiler:latest .
```

然后重新 `docker run`。

---

## 4. 页面布局恢复为原版风格

**用户：**

布局可以和原来一样吗，通过按键切换不同的视图

**AI：**

先尝试找原页面文件。后续用户提供了原始 `ui-preview.html`，于是将当前页面恢复为：

- 原来的暖色系风格
- 顶部 tab 切换
- 分为 `概览 / 时间线 / 火焰图 / 诊断`

并保留当前后端 API 的真实数据接入：

- `/api/overview`
- `/api/windows`
- `/api/flame`
- `/api/diagnostics`

---

## 5. 下载 SVG 按钮修复

**用户：**

你下载 svg 的按键没有成功下载火焰图

**AI：**

原因是按钮只是调用了 `window.open(...)`，更像“新开页面”而不是真正下载。后续修改为：

- `独立打开`：继续走 `window.open`
- `下载 SVG`：创建带 `download` 属性的 `<a>` 触发文件下载

---

## 6. 时间窗口选择精度问题

**用户：**

怎么你这个窗口只可以两个两个地选取

**AI：**

问题原因是时间输入框最初只保留到“分钟”，没有保留“秒”，导致 60 秒窗口容易把相邻窗口一起命中。修复方式：

- `datetime-local` 输入框加 `step="1"`
- 自动填充窗口时间时保留秒级精度

---

## 7. stress-ng 只显示进程名

**用户：**

最后成功生成了火焰图，多少热点函数最后是 `[stress-ng]`，而不是具体的某个函数

**AI：**

排查后发现宿主机上的 `stress-ng` 是被 strip 的二进制：

```text
/usr/bin/stress-ng: stripped
nm: /usr/bin/stress-ng: no symbols
```

因此火焰图只能稳定定位到 `stress-ng` 进程，而难以还原 `matrixprod` 这类更细粒度函数。

---

## 8. 新增带符号的自定义压测程序

**用户：**

那要不写一个新的 CPU 测压的程序吧，比如写一个死循环

**AI：**

新增：

- `task2/test/cpu_hotspot.c`
- `task2/test/test_symbolic_hotspot.sh`

初版使用单线程计算热点函数：

- `matrix_hotspot`
- `synthetic_hot_loop`

这样更适合在火焰图中稳定看到明确函数名。

---

## 9. 适配 32 核机器的多线程压测

**用户：**

我的机器是 32 核

**AI：**

单线程压测只能打满 1 个核，整机 CPU 只会增加约 `3%` 左右，不够明显。因此将程序升级为多线程版：

- 使用 `pthread`
- `test_symbolic_hotspot.sh` 新增：

```bash
THREADS=16
SECONDS_TO_RUN=180
```

这样更适合在 32 核机器上制造明显 CPU 飙升，同时保留函数级热点。

对应提交中包含：

- `task2/test/cpu_hotspot.c`
- `task2/test/test_symbolic_hotspot.sh`

---

## 10. 压测结束后 no matching perf.data windows

**用户：**

运行脚本后出现：

```text
no matching perf.data windows
```

**AI：**

原因不是压测失败，而是采样窗口还没结束，`.perf.data` 尚未落盘并写入索引。建议：

1. 观察：

```bash
docker logs -f cpu-profiler
```

2. 等看到：

```text
window finished status=ok
```

3. 再执行 `perfbox query` / `perfbox flame`

之后 README 中也补充了这段说明。

---

## 11. README 测试验证补全

**用户：**

测试验证的代码将创建容器等指令也加到 README 里

**AI：**

对 `task2/README.md` 的第 7 节进行了补全，内容包括：

- 如何停止并删除旧容器
- 如何重新创建 profiling 容器
- 如何确认 Web 和 collector 已启动
- 如何运行 `stress-ng` 脚本和符号化压测脚本
- 为什么有时需要等待窗口落盘
- 32 核机器的推荐压测命令

---

## 12. 将功能优化整理成 git commit

**用户：**

整理一下，将做出的优化 git commit

**AI：**

本轮优化对应提交：

- `aa0b2fe Refine task2 UI and add symbolic hotspot validation`

这次提交包含：

- 恢复原页面布局并接入真实数据
- 修复前端交互问题
- 新增多线程符号化压测程序
- 完善 README 的测试验证流程

---

## 13. 导出 Docker 镜像

**用户：**

生成 `task2/profiler.tar`

**AI：**

执行：

```bash
docker save -o task2/profiler.tar cpu-profiler:latest
```

生成结果：

- `task2/profiler.tar`
- 大小约 `68M`

---

## 14. 当前建议的最终交付重点

AI 在整理后建议：

1. 保留 `task2/profiler.tar`
2. 在 `task2/test/screenshots/` 放测试截图
3. 保留本目录 `task2/ai-chat-log/` 说明 AI 参与过程
4. 确保 `task2/README.md` 足以独立指导评审复现

---

## 15. 本次优化涉及的主要文件

- `task2/src/perfbox/cli.py`
- `task2/src/perfbox/web.py`
- `task2/ui-preview.html`
- `task2/Dockerfile`
- `task2/README.md`
- `task2/test/cpu_hotspot.c`
- `task2/test/test_symbolic_hotspot.sh`

---

## 16. 相关提交记录

```text
cba4e22 Enable web UI as default task2 container entrypoint
aa0b2fe Refine task2 UI and add symbolic hotspot validation
```
