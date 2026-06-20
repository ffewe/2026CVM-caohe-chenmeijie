# 火焰图实验结果与热点分析

本文对应题目一第二小题，基于 `task1/2-flamegraph/flamegraphs/` 中已经生成的五张 SVG 火焰图进行分析。火焰图横向宽度表示采样占比，因此本文将每张图中占比最大的函数栈作为题目要求的“热点函数”。

## a. 火焰图嵌入与热点函数（占比最大函数栈）

### 1. 纯整数计算 `int64`

![int64 flame graph](./flamegraphs/int64_flame.svg)

热点函数（占比最大函数栈）为：

```text
stress-ng-cpu -> main -> stress_parallel_run -> stress_run -> stress_child_run -> stress_cpu -> stress_call_cpu_method -> stress_cpu_int64 -> stress_mwc32
```

该栈约占 41.53%。主负载热点是 `stress_cpu_int64` / `stress_mwc32`，说明采样主要落在整数计算和伪随机数生成路径上。图中也出现了 `open64`、`read`、`kernfs_fop_open`、`kernfs_seq_start` 等系统路径，它们来自 `stress-ng` 启动和 CPU/cache 信息探测阶段。

### 2. 矩阵计算 `matrixprod`

![matrixprod flame graph](./flamegraphs/matrixprod_flame.svg)

热点函数（占比最大函数栈）为：

```text
stress-ng-cpu -> main -> stress_parallel_run -> stress_run -> stress_child_run -> stress_cpu -> stress_call_cpu_method -> stress_cpu_matrix_prod
```

该栈约占 96.32%，末端热点函数是 `stress_cpu_matrix_prod`。这是五张图中热点最集中的负载，CPU 时间几乎全部落在用户态矩阵乘法计算路径上，火焰图呈现明显的“尖塔”形态。

### 3. 连续访存 `read64`

![read64 flame graph](./flamegraphs/read64_flame.svg)

热点函数（占比最大函数栈）为：

```text
stress-ng -> [unknown] -> stress_cpu_cache_details_get -> stress_cpu_cache_get_details -> stress_cpu_cache_get_index -> __scandir64 -> __opendir -> __GI___open64_nocancel -> entry_SYSCALL_64_after_hwframe -> do_syscall_64 -> x64_sys_call -> __x64_sys_openat -> do_sys_openat2 -> getname -> getname_flags.part.0 -> __memset
```

该栈约占 19.50%，主要对应 `stress-ng` 启动/探测 CPU cache 信息时产生的目录扫描和 `openat` 系统调用路径。主负载相关的较宽函数栈包括：

```text
stress-ng-vm -> main -> stress_parallel_run -> stress_run -> stress_child_run -> stress_vm -> stress_oomable_child -> stress_vm_child -> stress_vm_read64 -> asm_exc_page_fault -> exc_page_fault -> do_user_addr_fault -> handle_mm_fault -> __handle_mm_fault
```

其中 `pte_offset_map_nolock` 约占 18.66%，`down_read_trylock` 约占 14.54%，`__handle_mm_fault` 约占 12.85%。热点函数可以概括为 `stress_vm_read64` 触发的缺页处理路径，说明连续访存负载在采样期间包含了大量首次触页、页表查询和内存管理开销。

### 4. 随机访存 `rand-set`

![rand-set flame graph](./flamegraphs/rand_set_flame.svg)

热点函数（占比最大函数栈）为：

```text
stress-ng -> [unknown] -> stress_cpu_cache_details_get -> stress_cpu_cache_get_details -> stress_cpu_cache_get_index -> stress_add_cpu_cache_detail -> stress_get_string_from_file -> stress_fs_file_read -> __GI___close -> entry_SYSCALL_64_after_hwframe -> do_syscall_64 -> x64_sys_call -> __x64_sys_close -> __fput_sync -> __fput -> __fsnotify_parent
```

该栈约占 24.18%，主要对应 `stress-ng` 启动/探测阶段读取系统信息并关闭文件描述符的内核路径。主负载相关的热点函数栈为：

```text
stress-ng-vm -> main -> stress_parallel_run -> stress_run -> stress_child_run -> stress_vm -> stress_oomable_child -> stress_vm_child -> stress_vm_rand_set -> stress_mwc8
```

`stress_mwc8` 约占 22.37%，是随机写入路径中的主要用户态热点。图中还出现：

```text
stress_vm_rand_set -> asm_exc_page_fault -> exc_page_fault -> do_user_addr_fault -> handle_mm_fault -> __handle_mm_fault -> handle_pte_fault -> do_anonymous_page -> folio_add_lru_vma -> folio_add_lru
```

其中 `folio_add_lru` 约占 11.98%。这说明随机访存不仅消耗在用户态随机写入逻辑，也消耗在匿名页分配、缺页处理和页回收链表维护等内核路径上。

### 5. 分支密集型 `queens`

![queens flame graph](./flamegraphs/queens_flame.svg)

热点函数（占比最大函数栈）为：

```text
stress-ng -> [unknown] -> stress_cpu_cache_details_get -> stress_get_string_from_file -> stress_fs_file_read -> open64 -> __libc_open64 -> entry_SYSCALL_64_after_hwframe -> do_syscall_64 -> x64_sys_call -> __x64_sys_openat -> do_sys_openat2 -> do_filp_open -> path_openat -> link_path_walk.part.0.constprop.0 -> walk_component -> step_into -> __lookup_mnt
```

该栈约占 32.78%，主要对应 `stress-ng` 启动/探测阶段的文件打开和路径/挂载点查找。主负载相关的热点函数栈为：

```text
stress-ng-cpu -> main -> stress_parallel_run -> stress_run -> stress_child_run -> stress_cpu -> stress_call_cpu_method -> stress_cpu_queens -> queens_try -> queens_try -> ...
```

`queens_try` 合计约占 19.41%，是 N 皇后递归搜索和回溯的主要负载热点。当前图里的热点函数（占比最大函数栈）不是 `queens_try`，而是以 `__lookup_mnt` 结尾的系统路径，说明采样窗口包含了 `stress-ng` 启动、目录扫描或 CPU/cache 探测开销。因此分析 `queens` 时应把 `__lookup_mnt` 栈作为题目要求的“热点函数（占比最大函数栈）”如实报告，把 `queens_try` 作为主负载热点单独说明。

## b. 两种不同负载火焰图对比：`matrixprod` 与 `rand-set`

这里选择 `matrixprod` 和 `rand-set` 两种负载进行对比。`matrixprod` 代表计算密集型负载，`rand-set` 代表随机访存密集型负载，二者的火焰图形态差异最明显。

`matrixprod` 的火焰图宽度高度集中，热点函数（占比最大函数栈）为：

```text
stress-ng-cpu -> main -> stress_parallel_run -> stress_run -> stress_child_run -> stress_cpu -> stress_call_cpu_method -> stress_cpu_matrix_prod
```

该栈约占 96.32%。这说明 `matrixprod` 的 CPU 时间几乎全部集中在矩阵乘法主循环中，火焰图呈现典型的“尖塔”形态。它的主要瓶颈更偏向用户态计算，包括算术执行单元吞吐、流水线执行效率以及循环代码的执行效率。

`rand-set` 的火焰图更分散。它的热点函数（占比最大函数栈）为：

```text
stress-ng -> [unknown] -> stress_cpu_cache_details_get -> stress_cpu_cache_get_details -> stress_cpu_cache_get_index -> stress_add_cpu_cache_detail -> stress_get_string_from_file -> stress_fs_file_read -> __GI___close -> entry_SYSCALL_64_after_hwframe -> do_syscall_64 -> x64_sys_call -> __x64_sys_close -> __fput_sync -> __fput -> __fsnotify_parent
```

该栈约占 24.18%，主要来自 `stress-ng` 启动/探测阶段的系统信息读取和文件关闭路径。与此同时，`rand-set` 的主负载相关热点还包括：

```text
stress-ng-vm -> main -> stress_parallel_run -> stress_run -> stress_child_run -> stress_vm -> stress_oomable_child -> stress_vm_child -> stress_vm_rand_set -> stress_mwc8
```

以及：

```text
stress_vm_rand_set -> asm_exc_page_fault -> exc_page_fault -> do_user_addr_fault -> handle_mm_fault -> __handle_mm_fault -> handle_pte_fault -> do_anonymous_page -> folio_add_lru_vma -> folio_add_lru
```

相比 `matrixprod`，`rand-set` 不呈现单一极宽的用户态计算栈，而是分布在随机写入、伪随机数生成、缺页处理、匿名页分配和 LRU 维护等多个路径上。因此它的火焰图更“扁平”，热点更分散。根本原因是随机访存破坏了空间局部性和时间局部性，CPU 更容易遇到 cache miss、TLB miss、首次触页和内存分配开销，流水线后端可能等待数据返回；而 `matrixprod` 的循环结构和访问模式更稳定，CPU 可以长时间执行同一段计算代码，所以热点集中。

## c. 内核态函数出现原因及性能影响

程序运行时，凡是涉及到IO读写、内存分配等硬件资源的操作时，往往不能直接操作，而是通过一种叫系统调用的过程，让程序陷入到内核态运行，然后内核态的CPU执行有关硬件资源操作指令，得到相关的硬件资源后在返回到用户态继续执行，之间还要进行一系列的数据传输，在这一内核态和用户态的切换过程中，会触发内核态函数的运行。
此外，下面这两种情况也会出现内核态函数的调用
异常： （当CPU正在执行运行在用户态的程序时，突然发生某些预先不可知的异常事件，如缺页异常，触发从当前用户态执行的进程转向内核态执行相关的异常事件；
外设中断（硬中断）：当外围设备完成用户的请求操作后，会像CPU发出中断信号，此时，CPU就会暂停执行下一条即将要执行的指令，转而去执行中断信号对应的处理程序，如果先前执行的指令是在用户态下，则自然就发生从用户态到内核态的转换。


### 1. `int64`

`int64` 是纯整数计算负载，图中出现了少量内核态函数和系统调用路径，例如：

```text
open64 -> __libc_open64 -> entry_SYSCALL_64_after_hwframe -> do_syscall_64
-> x64_sys_call -> __x64_sys_openat -> do_sys_openat2 -> do_filp_open
-> path_openat -> do_open -> vfs_open -> do_dentry_open -> kernfs_fop_open
```

以及：

```text
read -> __GI___libc_read -> entry_SYSCALL_64_after_hwframe -> do_syscall_64
-> x64_sys_call -> __x64_sys_read -> ksys_read -> vfs_read
-> kernfs_fop_read_iter -> kernfs_seq_start
```

对应原因和影响如下：

- 负载操作对应关系：`int64` 主循环本身只做整数运算和伪随机数生成，正常情况下不需要频繁进入内核；图中的内核函数主要对应 `stress-ng` 在真正开始压测前读取 CPU/cache 拓扑、CPU idle 状态等环境信息。
- `__x64_sys_openat`、`do_sys_openat2`、`do_filp_open`、`path_openat`、`vfs_open`、`kernfs_fop_open`：由 `stress-ng` 启动阶段读取 `/sys`、`/proc` 中的 CPU/cache 信息引起，属于文件系统和 kernfs 访问开销。
- `__x64_sys_read`、`ksys_read`、`vfs_read`、`kernfs_fop_read_iter`、`kernfs_seq_start`：由读取 sysfs/procfs 文件内容引起，用于获得 CPU/cache 拓扑、空闲状态等环境信息。
- `inode_permission`：由打开文件时的 VFS 权限检查引起。
- 若图中出现 `usb_*`、`hid_*`、`input_*`、`handle_softirqs` 等路径，则通常不是 `int64` 主循环造成，而是采样期间系统处理外设输入或 USB/HID 设备中断，属于设备管理/中断处理噪声。

性能影响上，这些路径属于启动和环境探测开销，会带来一次性的系统调用、路径查找、权限检查和 kernfs 读取成本；对长时间运行的 `int64` 主循环影响较小，但在 30s 采样中仍可能形成可见的窄栈。设备管理或中断路径若出现，通常表示采样窗口内系统有异步外设事件，会轻微扰动 CPU 样本分布，但不是该负载的主要瓶颈。

### 2. `matrixprod`

`matrixprod` 的火焰图中内核态路径很少。当前图中可见的内核路径主要出现在动态链接或启动阶段，例如：

```text
_dl_start -> dl_main -> _dl_map_object -> open_verify
-> __GI___open64_nocancel -> entry_SYSCALL_64_after_hwframe
-> do_syscall_64 -> x64_sys_call -> __x64_sys_openat
-> do_sys_openat2 -> getname -> getname_flags.part.0 -> __memset
```

对应原因和影响如下：

- 负载操作对应关系：`matrixprod` 主循环是在用户态反复做矩阵乘法，绝大多数时间不需要系统调用；图中的内核函数主要对应程序装载共享库、解析动态链接依赖和初始化运行环境。
- `_dl_start`、`dl_main`、`_dl_map_object`、`open_verify`：由动态链接器启动、加载共享库和解析依赖引起。
- `__GI___open64_nocancel`、`__x64_sys_openat`、`do_sys_openat2`、`getname`、`getname_flags.part.0`：由动态链接器打开共享库文件或检查库路径引起。
- `__memset`：由内核或运行时在路径名/结构体初始化、用户态缓冲处理过程中进行内存清零引起。
- 若图中出现 `sysvec_thermal`、`intel_thermal_interrupt`、`native_read_msr` 等路径，则通常来自 CPU 热管理/硬件中断采样，不是矩阵乘法算法本身，属于设备/硬件管理事件。

性能影响上，它们主要影响程序启动阶段，对矩阵乘法主循环的持续计算性能影响很小。由于 `matrixprod` 的计算循环稳定且热点集中，这类内核路径在火焰图中占比很低，说明该负载主要瓶颈仍是用户态计算吞吐，而不是系统调用、设备管理或内存管理。

### 3. `read64`

`read64` 是连续访存负载，内核态函数明显增多。图中主负载相关的内核路径包括：

```text
stress_vm_read64 -> asm_exc_page_fault -> exc_page_fault
-> do_user_addr_fault -> handle_mm_fault -> __handle_mm_fault
-> pte_offset_map_nolock
```

以及：

```text
stress_vm_read64 -> asm_exc_page_fault -> exc_page_fault
-> do_user_addr_fault -> down_read_trylock
```

对应原因和影响如下：

- 负载操作对应关系：`read64` 会申请一段较大的虚拟内存区域并连续读取其中的数据。用户态的连续读操作本身是普通 load 指令，但第一次访问尚未建立物理页映射的地址时，会触发缺页异常，内核需要分配/确认物理页、建立页表项并更新进程的虚拟内存映射。
- `asm_exc_page_fault`、`exc_page_fault`、`do_user_addr_fault`：由用户态访问尚未建立映射的虚拟页触发，属于缺页异常入口。
- `handle_mm_fault`、`__handle_mm_fault`、`pte_offset_map_nolock`：由内核处理页表、查找 PTE、建立或确认虚拟地址到物理页的映射引起。
- `down_read_trylock`：由缺页处理时尝试获取进程内存映射读锁引起，反映 VMA/page fault 路径中的同步开销。
- `__x64_sys_openat`、`do_filp_open`、`lookup_fast`、`d_same_name`、`kernfs_fop_open`：由启动阶段扫描和读取 CPU/cache/sysfs 信息引起，属于文件系统/kernfs 路径，不是 `read64` 主循环本身。
- `kmem_cache_alloc`、`__memcg_slab_post_alloc_hook`：由打开文件、分配内核对象或内存 cgroup 计费引起，属于内核对象分配和资源统计开销。

性能影响上，page fault 会导致 CPU 从用户态陷入内核态，执行页表检查、VMA 查找和映射建立；这会增加延迟并扰动 TLB/cache。文件系统和 kernfs 路径主要是启动探测成本，而 `handle_mm_fault`、`pte_offset_map_nolock` 等路径才更能反映 `read64` 访存过程中的内存管理开销。相比纯计算负载，`read64` 的 CPU 时间更容易分散到内存管理路径上。

### 4. `rand-set`

`rand-set` 是随机写内存负载，内核态路径比连续读更复杂。图中一类内核函数来自启动和系统信息探测，例如：

```text
stress_cpu_cache_details_get -> stress_fs_file_read -> __GI___close
-> entry_SYSCALL_64_after_hwframe -> do_syscall_64 -> x64_sys_call
-> __x64_sys_close -> __fput_sync -> __fput -> __fsnotify_parent
```

另一类更能反映主负载特征，来自随机写入触发的缺页和匿名页管理：

```text
stress_vm_rand_set -> asm_exc_page_fault -> exc_page_fault
-> do_user_addr_fault -> handle_mm_fault -> __handle_mm_fault
-> handle_pte_fault -> do_anonymous_page
-> folio_add_lru_vma -> folio_add_lru
```

对应原因和影响如下：

- 负载操作对应关系：`rand-set` 会在大内存区域内按随机位置写入数据。随机写会不断触碰分散的虚拟页，如果这些页尚未映射或需要写时分配，内核就要进入缺页处理、分配匿名页、建立 PTE，并把新页加入 LRU 等内存管理结构。
- `__x64_sys_close`、`__fput_sync`、`__fput`、`__fsnotify_parent`：由 `stress-ng` 读取系统信息后关闭文件描述符引起，属于 VFS 文件关闭和 fsnotify 文件系统事件通知开销。
- `__x64_sys_openat`、`do_sys_openat2`、`do_filp_open`、`path_openat`、`make_vfsuid`：由启动/探测阶段打开 sysfs/procfs 文件引起，包含路径查找和 VFS 用户/权限上下文处理。
- `__x64_sys_read`、`vfs_read`、`security_file_permission`、`apparmor_file_permission`、`aa_file_perm`：由读取系统文件时触发的 VFS 读路径和 AppArmor 安全策略检查引起。
- `asm_exc_page_fault`、`exc_page_fault`、`do_user_addr_fault`、`handle_mm_fault`、`__handle_mm_fault`：由随机写访问触发缺页处理引起。
- `handle_pte_fault`、`do_anonymous_page`、`folio_add_lru_vma`、`folio_add_lru`：由匿名页分配、页表项建立和把新页加入 LRU 链表引起，是随机写内存负载中更核心的内存管理开销。
- `kmem_cache_free`：由关闭文件、释放内核对象或回收 slab 对象引起，属于资源释放开销。

性能影响上，随机访存不仅让用户态等待数据返回，还会让内核频繁参与页表和物理页管理，导致 CPU 周期分散到 `handle_mm_fault`、`do_anonymous_page`、`folio_add_lru` 等路径中。VFS、fsnotify 和 AppArmor 路径主要来自启动/探测阶段；缺页、匿名页分配和 LRU 维护则直接反映随机写内存的运行期开销。因此 `rand-set` 的火焰图比 `matrixprod` 更扁平，热点也更分散。

### 5. `queens`

`queens` 的主负载是 N 皇后递归搜索和回溯，用户态热点位于 `stress_cpu_queens` / `queens_try`。当前图中也出现了较宽的内核路径，例如：

```text
__GI___getdents64 -> entry_SYSCALL_64_after_hwframe -> do_syscall_64
-> x64_sys_call -> __x64_sys_getdents64 -> iterate_dir
-> kernfs_fop_readdir -> filldir64
```

以及：

```text
open64 -> __libc_open64 -> entry_SYSCALL_64_after_hwframe
-> do_syscall_64 -> x64_sys_call -> __x64_sys_openat
-> do_sys_openat2 -> do_filp_open -> path_openat
-> link_path_walk.part.0.constprop.0 -> walk_component
-> step_into -> __lookup_mnt
```

对应原因和影响如下：

- 负载操作对应关系：`queens` 主循环是在用户态递归搜索和回溯，主要消耗在分支判断和递归调用；图中的较宽内核路径并不是求解 N 皇后本身需要设备或文件系统，而是 `stress-ng` 启动/探测时扫描系统目录、读取 CPU/cache 信息产生的。
- `__x64_sys_getdents64`、`iterate_dir`、`kernfs_fop_readdir`、`filldir64`：由 `stress-ng` 扫描 `/sys` 目录、枚举 CPU/cache 信息引起，属于目录读取和 kernfs 遍历开销。
- `__x64_sys_openat`、`do_sys_openat2`、`do_filp_open`、`path_openat`：由打开 sysfs/procfs 文件引起，属于文件系统路径查找和打开文件开销。
- `link_path_walk.part.0.constprop.0`、`walk_component`、`step_into`、`__lookup_mnt`：由路径解析和挂载点查找引起，属于 VFS 路径遍历/挂载命名空间管理开销。
- `getname`、`getname_flags.part.0`、`strncpy_from_user`：由系统调用把用户态路径名复制到内核态并解析引起。
- 如果采样中出现 `hrtimer_interrupt`、`sysvec_apic_timer_interrupt`、`scheduler_tick` 等函数，则表示定时器中断和调度器 tick；如果出现 `usb_*`、`hid_*`、`input_*`，则表示设备管理/输入设备中断。这些都是系统异步事件，不是 `queens_try` 递归搜索本身。

性能影响上，这些系统调用路径会增加启动阶段开销，并在短时间采样中占据可见宽度；但对 `queens_try` 递归搜索的长期执行性能影响有限。路径解析、目录遍历和挂载点查找会消耗 CPU 并污染 cache/TLB；设备管理或定时器中断则会打断用户态执行，造成少量采样噪声。分析时应区分“采样窗口中的最大系统路径”和“实际负载主循环热点”：前者反映启动/探测成本或系统异步事件，后者才反映分支密集型递归搜索的 CPU 开销。

综合来看，五类负载中 `matrixprod` 和 `int64` 的内核态路径主要是启动与环境探测开销，包括 sysfs/procfs 文件访问、kernfs 读取和动态链接；`read64` 和 `rand-set` 的内核态路径则与缺页、页表和匿名页管理直接相关，性能影响更明显；`queens` 中较宽的内核路径主要来自启动阶段文件/目录访问、VFS 路径解析和挂载点查找，需要与递归搜索主负载区分分析。若某张图中出现 USB/HID/input、thermal、APIC timer 或 scheduler tick 等路径，应标注为设备管理、热管理、定时器中断或调度器异步事件，它们通常是采样噪声或系统背景活动，而不是 stress 方法本身的核心计算逻辑。
