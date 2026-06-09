#!/usr/bin/env bash
# Build the Rust regex benchmark shim.
#
# This script builds the Rust regex benchmark binary that is used
# by the cross-engine benchmark runner.  It requires the Rust
# toolchain and the rust-regex source to be available.
#
# Usage:
#   ./bench/build-shims.sh
#   RUST_REGEX_PATH=/path/to/regex ./bench/build-shims.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

RUST_REGEX_PATH="${RUST_REGEX_PATH:-$PROJECT_ROOT/../regex}"
SHIM_DIR="$SCRIPT_DIR/shims/rust_regex_bench"

echo "=== Building Rust regex benchmark shim ==="

if [[ ! -d "$RUST_REGEX_PATH" ]]; then
    echo "ERROR: rust-regex source not found at $RUST_REGEX_PATH"
    echo "Set RUST_REGEX_PATH to the rust-lang/regex repo root."
    exit 1
fi

if ! command -v cargo &>/dev/null; then
    echo "ERROR: cargo not found. Install Rust toolchain first."
    exit 1
fi

# Set up vendor directory with the regex crate source.
VENDOR_DIR="$SHIM_DIR/vendor"
mkdir -p "$VENDOR_DIR"

# Copy or symlink the regex crate.
if [[ -L "$VENDOR_DIR/regex" ]]; then
    rm "$VENDOR_DIR/regex"
fi
if [[ -d "$VENDOR_DIR/regex" ]]; then
    rm -rf "$VENDOR_DIR/regex"
fi

# Use symlink for local development.
ln -s "$RUST_REGEX_PATH" "$VENDOR_DIR/regex"

echo "Using regex crate from: $RUST_REGEX_PATH"

# Build.
cd "$SHIM_DIR"
cargo build --release

# Copy binary to accessible location.
mkdir -p "$SCRIPT_DIR/bin"
cp target/release/rust-regex-bench "$SCRIPT_DIR/bin/"
echo "Built: $SCRIPT_DIR/bin/rust-regex-bench"

echo "=== Done ==="
