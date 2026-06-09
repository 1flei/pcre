# pcre

Compile-time regex engine for [PythoC](https://github.com/1flei/PythoC).

Parses regex patterns at Python compile time, builds a Tagged NFA -> TDFA -> Tagged Boyer-Moore automaton, and generates native `@compile` functions with LLVM codegen via PythoC.

## Quick start

```python
from pcre import compile

r = compile("[a-z]+@[a-z]+\\.[a-z]+")
r.match(b"foo@bar.com")             # (True, {})
r.search(b"email: a@b.c")           # (True, {'start': 7, 'end': 12})
```

## Pipeline

```
pattern -> parse (AST) -> TNFA -> TDFA -> TaggedOPCSBMA -> AST -> meta.compile_generated -> LLVM native code
```

## Dependencies

- `pythoc`

## Benchmarks

The `bench/` directory contains a cross-engine benchmark suite that compares pcre against Python `re`, re2c, and Rust's `regex` crate.

### Quick benchmark (local, pcre vs Python re)

```bash
# Ensure datasets are downloaded
python -m bench.datasets.download

# Run benchmark
python -m bench.run_bench --engines pcre,re
```

### Full benchmark (all engines, Docker)

```bash
# Build Docker image with all engines
./bench/run-bench.sh --docker --engines pcre,re,rust

# Or use docker compose directly
docker compose -f bench/docker-compose.yml build
docker compose -f bench/docker-compose.yml run bench
```

### Benchmark options

```bash
# Quick run with small files
python -m bench.run_bench --small

# Specific cases only
python -m bench.run_bench --cases literal_needle,dotstar_a_z_no_match

# Save results to JSON
python -m bench.run_bench --output bench/results/bench_$(date +%Y%m%d).json

# Adjust timing parameters
python -m bench.run_bench --warmup 3 --repeats 10 --budget 10.0
```

### Dataset management

Datasets are sourced from the [re2c benchmark suite](https://github.com/skvadrik/re2c/tree/master/benchmarks/_data) and supplemented with synthetic stress-test data:

```bash
# Download/generate all datasets
python -m bench.datasets.download

# Force regenerate
python -m bench.datasets.download --force

# Custom dataset directory
PCRE_DATASET_DIR=/path/to/data python -m bench.datasets.download
```

### Available engines

| Engine | Name | Notes |
|--------|------|-------|
| pcre (Python-level) | `pcre` | TDFA / T-BMA via PythoC, called through ctypes |
| pcre-native | `pcre-native` | Same native code, benchmarked via PythoC `@compile` harness (no ctypes overhead) |
| Python `re` | `re` | stdlib backtracking engine |
| Rust `regex` | `rust` | Requires Docker or local Rust toolchain |
| re2c | `re2c` | Requires Docker or built re2c benchmark suite |

### Available benchmark cases

Run `python -m bench.run_bench --help` for the full list, or see `bench/patterns.py`.

### One-click script

```bash
# Local run (pcre vs re)
./bench/run-bench.sh

# Docker run (all engines)
./bench/run-bench.sh --docker

# With options
./bench/run-bench.sh --engines pcre,re --small --output my_results.json
```
