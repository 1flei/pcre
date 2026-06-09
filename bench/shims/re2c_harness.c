/*
 * re2c benchmark harness.
 *
 * Compiled together with re2c-generated .c code that provides:
 *   int match(const char *data, size_t len);
 *
 * Build per-pattern:
 *   re2c -o <case>.c <case>.re
 *   gcc -O3 -o re2c_<case> <case>.c bench/re2c_harness.c
 *
 * Usage:
 *   ./re2c_<case> --data FILE --warmup N --repeats N
 *
 * Output:
 *   best_ms=X.XXX mean_ms=Y.YYY
 */

#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

/* Provided by the re2c-generated .c file. */
int match(const char *data, size_t len);

static char *read_file(const char *path, size_t *out_len) {
    FILE *f = fopen(path, "rb");
    if (!f) {
        fprintf(stderr, "Cannot open %s\n", path);
        return NULL;
    }
    fseek(f, 0, SEEK_END);
    long sz = ftell(f);
    fseek(f, 0, SEEK_SET);
    char *buf = (char *)malloc((size_t)sz + 1);
    if (!buf) {
        fclose(f);
        return NULL;
    }
    fread(buf, 1, (size_t)sz, f);
    buf[sz] = '\0';
    fclose(f);
    *out_len = (size_t)sz;
    return buf;
}

static double now_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return ts.tv_sec * 1000.0 + ts.tv_nsec / 1e6;
}

int main(int argc, char **argv) {
    const char *data_file = NULL;
    int warmup = 2;
    int repeats = 5;

    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--data") == 0 && i + 1 < argc)
            data_file = argv[++i];
        else if (strcmp(argv[i], "--warmup") == 0 && i + 1 < argc)
            warmup = atoi(argv[++i]);
        else if (strcmp(argv[i], "--repeats") == 0 && i + 1 < argc)
            repeats = atoi(argv[++i]);
    }

    if (!data_file) {
        fprintf(stderr, "Usage: %s --data FILE [--warmup N] [--repeats N]\n",
                argv[0]);
        return 1;
    }

    size_t len;
    char *data = read_file(data_file, &len);
    if (!data) return 1;

    /* Warmup */
    for (int i = 0; i < warmup; i++) {
        volatile int r = match(data, len);
        (void)r;
    }

    /* Measured runs */
    double best_ms = 1e18;
    double total_ms = 0.0;
    for (int i = 0; i < repeats; i++) {
        double t0 = now_ms();
        volatile int r = match(data, len);
        (void)r;
        double t1 = now_ms();
        double ms = t1 - t0;
        if (ms < best_ms) best_ms = ms;
        total_ms += ms;
    }

    printf("best_ms=%.3f mean_ms=%.3f\n", best_ms, total_ms / repeats);

    free(data);
    return 0;
}
