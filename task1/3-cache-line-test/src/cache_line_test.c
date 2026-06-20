// src/cache_line_test.c
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <stdint.h>
#include <time.h>
#include <string.h>
#include <errno.h>
#include <unistd.h>

#ifndef CACHE_ALIGN
#define CACHE_ALIGN 64
#endif

static volatile uint64_t global_sink = 0;

static inline uint64_t now_ns(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC_RAW, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ULL + (uint64_t)ts.tv_nsec;
}

static void usage(const char *prog) {
    fprintf(stderr,
            "Usage: %s <array_size_mb> <stride_bytes> <repeat>\n"
            "Example: %s 256 64 20\n",
            prog, prog);
}

__attribute__((noinline))
static uint64_t run_stride_read(uint8_t *buf, size_t size_bytes,
                                size_t stride_bytes, int repeat,
                                uint64_t *access_count) {
    uint64_t sum = 0;
    uint64_t accesses = 0;

    for (int r = 0; r < repeat; r++) {
        for (size_t i = 0; i + sizeof(uint64_t) <= size_bytes; i += stride_bytes) {
            sum += *(uint64_t *)(buf + i);
            accesses++;
        }
    }

    *access_count = accesses;
    global_sink = sum;
    return sum;
}

int main(int argc, char **argv) {
    if (argc != 4) {
        usage(argv[0]);
        return 1;
    }

    size_t array_size_mb = strtoull(argv[1], NULL, 10);
    size_t stride_bytes  = strtoull(argv[2], NULL, 10);
    int repeat           = atoi(argv[3]);

    if (array_size_mb < 16) {
        fprintf(stderr, "array_size_mb should be >= 16MB\n");
        return 1;
    }

    if (stride_bytes < 1) {
        fprintf(stderr, "stride_bytes should be >= 1\n");
        return 1;
    }

    if (repeat <= 0) {
        fprintf(stderr, "repeat should be > 0\n");
        return 1;
    }

    size_t size_bytes = array_size_mb * 1024ULL * 1024ULL;

    uint8_t *buf = NULL;
    int ret = posix_memalign((void **)&buf, CACHE_ALIGN, size_bytes);
    if (ret != 0 || buf == NULL) {
        fprintf(stderr, "posix_memalign failed: %s\n", strerror(ret));
        return 1;
    }

    // 初始化数组，确保页面真实分配，避免第一次访问全是缺页影响结果。
    for (size_t i = 0; i < size_bytes; i++) {
        buf[i] = (uint8_t)(i & 0xff);
    }

    // warm up
    uint64_t warm_accesses = 0;
    run_stride_read(buf, size_bytes, stride_bytes, 1, &warm_accesses);

    uint64_t accesses = 0;
    uint64_t start = now_ns();
    uint64_t sum = run_stride_read(buf, size_bytes, stride_bytes, repeat, &accesses);
    uint64_t end = now_ns();

    double elapsed_ns = (double)(end - start);
    double elapsed_s = elapsed_ns / 1e9;
    double ns_per_access = elapsed_ns / (double)accesses;

    // 每次显式读取 uint64_t，即 8 字节。这里是程序有效读取吞吐，不是总线真实带宽。
    double effective_mb = ((double)accesses * sizeof(uint64_t)) / (1024.0 * 1024.0);
    double effective_mbps = effective_mb / elapsed_s;

    printf("array_size_mb,stride_bytes,repeat,accesses,elapsed_ns,ns_per_access,effective_MBps,sum\n");
    printf("%zu,%zu,%d,%llu,%.0f,%.3f,%.3f,%llu\n",
           array_size_mb,
           stride_bytes,
           repeat,
           (unsigned long long)accesses,
           elapsed_ns,
           ns_per_access,
           effective_mbps,
           (unsigned long long)sum);

    free(buf);
    return 0;
}