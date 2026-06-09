#!/usr/bin/env bash
# One-click benchmark runner for pcre.
#
# Usage:
#   ./bench/run-bench.sh                          # pcre vs python-re
#   ./bench/run-bench.sh --engines pcre,re,re2c   # add re2c
#   ./bench/run-bench.sh --engines pcre,re,re2c,rust  # all engines
#   ./bench/run-bench.sh --small                  # quick run
#   ./bench/run-bench.sh --output results/my.json # save results
#
# Prerequisites (local):
#   - Python 3.10+
#   - re2c (for re2c engine): yum install re2c
#   - gcc (for re2c engine): usually pre-installed
#   - Rust toolchain (for rust engine): curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

# Defaults
ENGINES="${PCRE_BENCH_ENGINES:-pcre,re}"
USE_SMALL=""
OUTPUT="${PCRE_BENCH_OUTPUT:-}"
EXTRA_ARGS=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --engines)
            ENGINES="$2"
            shift 2
            ;;
        --small)
            USE_SMALL="--small"
            shift
            ;;
        --output|-o)
            OUTPUT="$2"
            shift 2
            ;;
        --verbose|-v)
            EXTRA_ARGS="$EXTRA_ARGS --verbose"
            shift
            ;;
        --help|-h)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Options:"
            echo "  --engines LIST   Comma-separated engine list (default: pcre,re)"
            echo "                   Available: pcre, pcre-native, re, re2c, rust"
            echo "  --small          Use small dataset files (quick run)"
            echo "  --output PATH    Save JSON results to PATH"
            echo "  --verbose        Enable verbose logging"
            echo "  --help           Show this help"
            echo ""
            echo "Prerequisites (local):"
            echo "  re2c:  yum install re2c  (for re2c engine)"
            echo "  gcc:   usually pre-installed  (for re2c engine)"
            echo "  rust:  https://rustup.rs  (for rust engine)"
            exit 0
            ;;
        *)
            EXTRA_ARGS="$EXTRA_ARGS $1"
            shift
            ;;
    esac
done

OUTPUT_ARG=""
if [[ -n "$OUTPUT" ]]; then
    OUTPUT_ARG="--output $OUTPUT"
    mkdir -p "$(dirname "$OUTPUT")"
fi

# Check prerequisites for selected engines
echo "=== Checking prerequisites ==="
cd "$PROJECT_ROOT"

IFS=',' read -ra ENGINE_LIST <<< "$ENGINES"
for eng in "${ENGINE_LIST[@]}"; do
    case "$eng" in
        re2c)
            if ! command -v re2c &>/dev/null; then
                echo "WARNING: re2c not found. Install: yum install re2c"
            else
                echo "  re2c: $(re2c --version 2>&1 | head -1)"
            fi
            if ! command -v gcc &>/dev/null; then
                echo "WARNING: gcc not found (needed by re2c engine)"
            fi
            ;;
        rust)
            if ! command -v cargo &>/dev/null; then
                echo "WARNING: cargo not found. Install: https://rustup.rs"
            else
                echo "  rust: $(rustc --version 2>&1)"
            fi
            ;;
    esac
done

echo "=== Ensuring datasets are available ==="
PYTHONPATH="$PROJECT_ROOT" python -m bench.datasets.download

echo "=== Running local benchmarks ==="
PYTHONPATH="$PROJECT_ROOT" python -m bench.run_bench \
    --engines "$ENGINES" \
    $USE_SMALL \
    $OUTPUT_ARG \
    $EXTRA_ARGS

echo ""
echo "=== Benchmark complete ==="
