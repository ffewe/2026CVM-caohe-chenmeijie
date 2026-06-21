#include <math.h>
#include <pthread.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <time.h>

#ifndef MATRIX_SIZE
#define MATRIX_SIZE 96
#endif

typedef struct {
    int seconds;
    int worker_id;
    double checksum;
} worker_args_t;

static void fill_matrix(double *matrix, int size, double seed) {
    for (int i = 0; i < size * size; ++i) {
        matrix[i] = fmod(seed + (double)(i * 17), 97.0) / 13.0;
    }
}

static double matrix_hotspot(const double *a, const double *b, double *out, int size) {
    double checksum = 0.0;
    for (int row = 0; row < size; ++row) {
        for (int col = 0; col < size; ++col) {
            double acc = 0.0;
            for (int k = 0; k < size; ++k) {
                acc += a[row * size + k] * b[k * size + col];
            }
            out[row * size + col] = acc;
            checksum += acc;
        }
    }
    return checksum;
}

static double xor_shift_mix(uint64_t *state) {
    *state ^= *state << 13;
    *state ^= *state >> 7;
    *state ^= *state << 17;
    return (double)(*state % 1000003ULL) / 97.0;
}

static double synthetic_hot_loop(double *buffer, int count, uint64_t *state) {
    double checksum = 0.0;
    for (int round = 0; round < 4000; ++round) {
        for (int i = 0; i < count; ++i) {
            buffer[i] = sin(buffer[i] + xor_shift_mix(state)) * cos(buffer[i] * 0.5);
            checksum += buffer[i];
        }
    }
    return checksum;
}

static void *worker_main(void *opaque) {
    worker_args_t *args = (worker_args_t *)opaque;
    const int size = MATRIX_SIZE;
    const int elements = size * size;
    double *a = malloc(sizeof(double) * elements);
    double *b = malloc(sizeof(double) * elements);
    double *out = malloc(sizeof(double) * elements);
    double *buffer = malloc(sizeof(double) * 4096);
    if (!a || !b || !out || !buffer) {
        fprintf(stderr, "worker %d allocation failed\n", args->worker_id);
        free(a);
        free(b);
        free(out);
        free(buffer);
        args->checksum = 0.0;
        return NULL;
    }

    fill_matrix(a, size, 1.0 + args->worker_id);
    fill_matrix(b, size, 7.0 + args->worker_id);
    fill_matrix(buffer, 64, 11.0 + args->worker_id);

    const time_t deadline = time(NULL) + args->seconds;
    uint64_t state = 0x12345678abcdefULL + (uint64_t)args->worker_id * 97ULL;
    double checksum = 0.0;

    while (time(NULL) < deadline) {
      checksum += matrix_hotspot(a, b, out, size);
      checksum += synthetic_hot_loop(buffer, 4096, &state);
      fill_matrix(a, size, checksum + args->worker_id);
      fill_matrix(b, size, checksum / 3.0 + args->worker_id);
    }

    args->checksum = checksum;
    free(a);
    free(b);
    free(out);
    free(buffer);
    return NULL;
}

int main(int argc, char **argv) {
    int seconds = 60;
    int threads = 4;
    if (argc > 1) {
        seconds = atoi(argv[1]);
    }
    if (argc > 2) {
        threads = atoi(argv[2]);
    }
    if (seconds <= 0 || threads <= 0) {
        fprintf(stderr, "usage: %s [seconds] [threads]\n", argv[0]);
        return 1;
    }

    pthread_t *handles = calloc((size_t)threads, sizeof(pthread_t));
    worker_args_t *workers = calloc((size_t)threads, sizeof(worker_args_t));
    if (!handles || !workers) {
        fprintf(stderr, "thread allocation failed\n");
        free(handles);
        free(workers);
        return 1;
    }

    for (int i = 0; i < threads; ++i) {
        workers[i].seconds = seconds;
        workers[i].worker_id = i;
        workers[i].checksum = 0.0;
        if (pthread_create(&handles[i], NULL, worker_main, &workers[i]) != 0) {
            fprintf(stderr, "failed to start worker %d\n", i);
            threads = i;
            break;
        }
    }

    double total_checksum = 0.0;
    for (int i = 0; i < threads; ++i) {
        pthread_join(handles[i], NULL);
        total_checksum += workers[i].checksum;
    }

    printf("threads=%d checksum=%f\n", threads, total_checksum);
    free(handles);
    free(workers);
    return 0;
}
