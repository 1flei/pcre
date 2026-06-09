#!/usr/bin/env python3
"""pcre native benchmark -- compile_to_executable harness.

Produces a standalone native binary that runs the entire benchmark
(file I/O, regex matching, clock_gettime timing) without any Python
runtime, exactly like re2c's C harness.

Usage (build phase):
    python pcre_native_bench.py --build --pattern PATTERN --mode MODE \
        --output /path/to/binary

Usage (run phase -- the compiled binary):
    ./binary DATA_FILE WARMUP REPEATS

The build phase compiles the regex via pcre's pipeline (pattern -> TNFA ->
TDFA -> T-BMA -> LLVM native), which registers the native function via
meta.compile_generated.  Then a @compile main() is defined that references
the native function, and compile_to_executable() links everything into
a standalone binary.
"""

import argparse
import sys

# ---------------------------------------------------------------------------
# Parse build args BEFORE any heavy imports, so --help is fast.
# ---------------------------------------------------------------------------
_parser = argparse.ArgumentParser()
_parser.add_argument("--build", action="store_true",
                     help="Compile to standalone binary instead of running")
_parser.add_argument("--pattern", default=None,
                     help="Regex pattern (required for --build)")
_parser.add_argument("--mode", default="search", choices=["search", "match"],
                     help="Regex mode (required for --build)")
_parser.add_argument("--output", default=None,
                     help="Output binary path (for --build)")
_args, _remaining = _parser.parse_known_args()

if not _args.build:
    # Should not be invoked directly without --build.
    # The compiled binary is what you run.
    print("Usage: python pcre_native_bench.py --build --pattern PATTERN "
          "--mode MODE [--output PATH]", file=sys.stderr)
    sys.exit(1)

# ---------------------------------------------------------------------------
# Compile regex at module level.
# This triggers meta.compile_generated which registers the native function
# so it will be included by compile_to_executable().
# ---------------------------------------------------------------------------
from pcre import compile as regex_compile

_compiled = regex_compile(_args.pattern)

if _args.mode == "match":
    _regex_fn = _compiled.generate_match_fn()
    _has_tags = _compiled._match_ctypes_struct is not None
    _num_slots = len(_compiled._match_bma.tag_names) if _has_tags else 0
else:
    _regex_fn = _compiled.generate_search_fn()
    _has_tags = True  # search always has tags
    _num_slots = _compiled.search_num_slots

# ---------------------------------------------------------------------------
# PythoC native harness
# ---------------------------------------------------------------------------
from pythoc import i8, i32, i64, u8, u64, f64, ptr, compile, seq
from pythoc.decorators.extern import extern
from pythoc.libc.stdio import printf, fopen, fclose, fread, fseek, ftell
from pythoc.libc.stdlib import malloc, free, atoi
from pythoc.libc.string import memset


# --- Timing (matches re2c harness) ---

@compile
class Timespec:
    tv_sec: i64
    tv_nsec: i64


@extern(lib='c')
def clock_gettime(clk_id: i32, tp: ptr[Timespec]) -> i32:
    pass


@compile
def now_ms() -> f64:
    ts: Timespec = Timespec()
    clock_gettime(1, ptr(ts))
    return f64(ts.tv_sec) * 1000.0 + f64(ts.tv_nsec) / 1e6


# --- File reading ---

SEEK_END: i32 = 2


@compile
def read_file_size(path: ptr[i8]) -> i64:
    fp: ptr[i8] = fopen(path, "rb")
    if fp == 0:
        return -1
    fseek(fp, 0, SEEK_END)
    sz: i64 = ftell(fp)
    fclose(fp)
    return sz


@compile
def read_file_data(path: ptr[i8], buf: ptr[i8], sz: i64) -> i32:
    fp: ptr[i8] = fopen(path, "rb")
    if fp == 0:
        return -1
    fread(buf, 1, sz, fp)
    fclose(fp)
    return 0


# --- Benchmark entry point ---
# Two variants: tagged (match with tags / search) and untagged (match no tags).
# The correct one is selected at module level based on _has_tags.

if _has_tags:

    @compile
    def main(argc: i32, argv: ptr[ptr[i8]]) -> i32:
        # argv[1] = data_file, argv[2] = warmup, argv[3] = repeats
        if argc < 4:
            printf("Usage: prog DATA_FILE WARMUP REPEATS\n")
            return 1

        path: ptr[i8] = argv[1]
        warmup: i32 = atoi(argv[2])
        repeats: i32 = atoi(argv[3])

        # Read data file
        sz: i64 = read_file_size(path)
        if sz < 0:
            printf("Cannot open %s\n", path)
            return 1
        data: ptr[i8] = ptr[i8](malloc(sz))
        if read_file_data(path, data, sz) < 0:
            free(data)
            return 1

        # Allocate out buffer for tags
        out: ptr[i64] = ptr[i64](malloc(_num_slots * 8))
        memset(out, 0, _num_slots * 8)

        n: u64 = u64(sz)

        # Warmup
        for wi in seq(warmup):
            _r: u8 = _regex_fn(n, data, out)

        # Timed runs
        best_ms: f64 = 1e18
        total_ms: f64 = 0.0
        for ri in seq(repeats):
            t0: f64 = now_ms()
            _r = _regex_fn(n, data, out)
            t1: f64 = now_ms()
            elapsed: f64 = t1 - t0
            if elapsed < best_ms:
                best_ms = elapsed
            total_ms = total_ms + elapsed

        printf("best_ms=%.3f mean_ms=%.3f\n", best_ms, total_ms / repeats)

        free(out)
        free(data)
        return 0

else:

    @compile
    def main(argc: i32, argv: ptr[ptr[i8]]) -> i32:
        # argv[1] = data_file, argv[2] = warmup, argv[3] = repeats
        if argc < 4:
            printf("Usage: prog DATA_FILE WARMUP REPEATS\n")
            return 1

        path: ptr[i8] = argv[1]
        warmup: i32 = atoi(argv[2])
        repeats: i32 = atoi(argv[3])

        # Read data file
        sz: i64 = read_file_size(path)
        if sz < 0:
            printf("Cannot open %s\n", path)
            return 1
        data: ptr[i8] = ptr[i8](malloc(sz))
        if read_file_data(path, data, sz) < 0:
            free(data)
            return 1

        n: u64 = u64(sz)

        # Warmup
        for wi in seq(warmup):
            _r: u8 = _regex_fn(n, data)

        # Timed runs
        best_ms: f64 = 1e18
        total_ms: f64 = 0.0
        for ri in seq(repeats):
            t0: f64 = now_ms()
            _r = _regex_fn(n, data)
            t1: f64 = now_ms()
            elapsed: f64 = t1 - t0
            if elapsed < best_ms:
                best_ms = elapsed
            total_ms = total_ms + elapsed

        printf("best_ms=%.3f mean_ms=%.3f\n", best_ms, total_ms / repeats)

        free(data)
        return 0


# ---------------------------------------------------------------------------
# Build the standalone executable
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    from pythoc import compile_to_executable
    compile_to_executable(output_path=_args.output)
