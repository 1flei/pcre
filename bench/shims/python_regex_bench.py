#!/usr/bin/env python3
"""Python regex benchmark shim (subprocess).

Used for both Python re and pcre engines.  Does all timing internally
and prints results to stdout in a machine-readable format.

Usage:
    python python_regex_bench.py --engine re --pattern PATTERN \
        --data FILE --mode search|match --warmup N --repeats N

Output:
    best_ms=X.XXX mean_ms=Y.YYY
"""

import argparse
import sys
import time


def _bench(fn, warmup, repeats):
    """Run fn with warmup + repeats, return (best_ms, mean_ms)."""
    for _ in range(warmup):
        fn()

    timings = []
    for _ in range(repeats):
        t0 = time.perf_counter()
        fn()
        elapsed = time.perf_counter() - t0
        timings.append(elapsed)

    best = min(timings) * 1000.0
    mean = sum(timings) / len(timings) * 1000.0
    return best, mean


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--engine", required=True, choices=["re", "pcre"])
    parser.add_argument("--pattern", required=True)
    parser.add_argument("--data", required=True)
    parser.add_argument("--mode", default="search", choices=["search", "match"])
    parser.add_argument("--warmup", type=int, default=2)
    parser.add_argument("--repeats", type=int, default=5)
    args = parser.parse_args()

    # Read data.
    with open(args.data, "rb") as f:
        data = f.read()

    if args.engine == "re":
        import re
        compiled = re.compile(args.pattern.encode("latin1"))
        if args.mode == "match":
            fn = lambda: bool(compiled.match(data))
        else:
            fn = lambda: compiled.search(data) is not None
    else:
        from pcre import compile as regex_compile
        compiled = regex_compile(args.pattern)
        # Prime the JIT by doing one dummy call.
        if args.mode == "match":
            compiled.match(b"")
            fn = lambda: compiled.match(data)
        else:
            compiled.search(b"")
            fn = lambda: compiled.search(data)

    best_ms, mean_ms = _bench(fn, args.warmup, args.repeats)
    print(f"best_ms={best_ms:.3f} mean_ms={mean_ms:.3f}")


if __name__ == "__main__":
    main()
