#!/usr/bin/env python3
"""
Dataset download and construction for regex benchmarks.

Reuses data from the re2c benchmark suite (already cloned at the
configured path) and generates additional large-scale haystacks
for stress-testing at various sizes.

Datasets are stored under ``bench/datasets/data/`` and organized by
category (http, uri, email, ipv4, datetime, apache, words, etc.).
Each category has a ``small`` and a ``big`` file; ``big`` is ~16 MiB
by default (same as re2c's convention).

Usage:
    python -m bench.datasets.download
    PCRE_DATASET_DIR=/custom/path python -m bench.datasets.download
"""

from __future__ import annotations

import logging
import os
import shutil
import sys
from pathlib import Path

logger = logging.getLogger(__name__)

# Default location for generated data.
_DEFAULT_DATA_DIR = Path(__file__).parent / "data"

# Default path to the re2c repo (cloned alongside pcre).
_DEFAULT_RE2C_PATH = Path(__file__).resolve().parents[3] / "re2c"

# Target size for "big" data files (16 MiB, same as re2c).
BIG_FILE_SIZE = 16 * 1024 * 1024

# Datasets available in the re2c benchmark suite.
RE2C_DATASETS = (
    "alt1", "alt2", "alt4",
    "apache", "cat2", "cat4", "cat8",
    "datetime", "email", "http", "ipv4",
    "numbers1", "numbers2", "rep",
    "uri", "words1", "words2", "words3",
)


def data_dir() -> Path:
    """Return the dataset root directory (env-overridable)."""
    env = os.environ.get("PCRE_DATASET_DIR")
    if env:
        return Path(env)
    return _DEFAULT_DATA_DIR


def re2c_path() -> Path:
    """Return the path to the re2c repo (env-overridable)."""
    env = os.environ.get("RE2C_PATH")
    if env:
        return Path(env)
    return _DEFAULT_RE2C_PATH


def _copy_small(re2c_data: Path, dest: Path, name: str) -> bool:
    """Copy a ``small`` file from the re2c benchmark data."""
    src = re2c_data / name / "small"
    if not src.exists():
        logger.warning("re2c dataset %s/small not found at %s", name, src)
        return False
    dst_dir = dest / name
    dst_dir.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst_dir / "small")
    logger.info("copied %s/small (%d bytes)", name, src.stat().st_size)
    return True


def _generate_big(dest: Path, name: str) -> None:
    """Generate a ``big`` file by repeating ``small`` up to BIG_FILE_SIZE."""
    small_path = dest / name / "small"
    big_path = dest / name / "big"
    if not small_path.exists():
        logger.warning("small file missing for %s, skipping big generation", name)
        return
    if big_path.exists() and big_path.stat().st_size >= BIG_FILE_SIZE:
        logger.info("big file already exists for %s, skipping", name)
        return

    small_data = small_path.read_bytes()
    small_len = len(small_data)
    if small_len == 0:
        logger.warning("small file for %s is empty, skipping big generation", name)
        return

    total = 0
    with open(big_path, "wb") as f:
        while total < BIG_FILE_SIZE:
            f.write(small_data)
            total += small_len
    logger.info("generated %s/big (%d bytes)", name, total)


def download_re2c_datasets(force: bool = False) -> list[str]:
    """Copy datasets from the re2c repo into the local data directory.

    Returns the list of dataset names that were successfully set up.
    """
    re2c = re2c_path()
    re2c_data = re2c / "benchmarks" / "_data"
    if not re2c_data.exists():
        logger.error(
            "re2c benchmark data not found at %s. "
            "Set RE2C_PATH to the re2c repo root.", re2c_data)
        return []

    dest = data_dir()
    dest.mkdir(parents=True, exist_ok=True)
    ready = []

    for name in RE2C_DATASETS:
        if not force:
            small = dest / name / "small"
            big = dest / name / "big"
            if small.exists() and big.exists() and big.stat().st_size >= BIG_FILE_SIZE:
                logger.info("dataset %s already present, skipping", name)
                ready.append(name)
                continue

        if _copy_small(re2c_data, dest, name):
            _generate_big(dest, name)
            ready.append(name)

    return ready


def generate_synthetic_datasets(force: bool = False) -> list[str]:
    """Generate additional synthetic benchmark datasets.

    These complement the re2c datasets with patterns specifically
    useful for testing pcre's TDFA / T-BMA pathologies.
    """
    from bench.datasets.synth import generate_all
    dest = data_dir()
    dest.mkdir(parents=True, exist_ok=True)
    return generate_all(dest, BIG_FILE_SIZE, force=force)


def ensure_all(force: bool = False) -> list[str]:
    """Ensure all benchmark datasets are available.

    Returns the list of dataset names that are ready.
    """
    datasets = download_re2c_datasets(force=force)
    datasets += generate_synthetic_datasets(force=force)
    return sorted(set(datasets))


def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(levelname)s: %(message)s",
    )
    force = "--force" in sys.argv
    ready = ensure_all(force=force)
    print(f"\nDatasets ready: {len(ready)}")
    for name in ready:
        d = data_dir() / name
        sizes = []
        for f in ("small", "big"):
            p = d / f
            if p.exists():
                sizes.append(f"{f}={p.stat().st_size:,}")
        print(f"  {name}: {', '.join(sizes)}")


if __name__ == "__main__":
    main()
