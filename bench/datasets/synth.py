#!/usr/bin/env python3
"""
Synthetic dataset generation for regex benchmarks.

Creates datasets that complement the re2c benchmark data with
patterns specifically useful for testing pcre's TDFA / T-BMA
behaviour at scale.
"""

from __future__ import annotations

import logging
import random
from pathlib import Path

logger = logging.getLogger(__name__)

# Deterministic seed for reproducibility.
_SEED = 42


def _write_if_needed(path: Path, data: bytes, force: bool = False) -> None:
    if not force and path.exists():
        logger.info("%s already exists, skipping", path)
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    logger.info("wrote %s (%d bytes)", path, len(data))


def _pad_to_size(base: bytes, target: int) -> bytes:
    """Repeat *base* to reach *target* bytes."""
    if len(base) == 0:
        return b""
    reps = target // len(base) + 1
    return (base * reps)[:target]


def _generate_dotstar_no_match(target: int) -> bytes:
    """Haystack of 'x' with no 'a' -- ``a.*z`` never matches."""
    return b"x" * target


def _generate_dotstar_match_end(target: int) -> bytes:
    """Haystack of 'a' ending with single 'z' -- ``a.*z`` matches at end."""
    return b"a" * (target - 1) + b"z"


def _generate_redos_haystack(target: int) -> bytes:
    """Haystack of 'a' * N with no trailing 'b' -- (a+)+b never matches."""
    return b"a" * target


def _generate_email_noise(target: int) -> bytes:
    """Haystack of interleaved '@' noise -- catastrophic for backtracking."""
    chunk = b"abc@def@ghi@jkl@"
    return _pad_to_size(chunk, target)


def _generate_keyword_haystack(target: int) -> bytes:
    """Haystack with random C/Python keywords scattered in filler text."""
    rng = random.Random(_SEED)
    keywords = (
        b"return", b"while", b"for", b"if", b"else", b"switch",
        b"break", b"continue", b"void", b"int", b"char", b"struct",
    )
    filler = b"  "
    parts = []
    total = 0
    while total < target:
        kw = rng.choice(keywords)
        parts.append(filler + kw)
        total += len(filler) + len(kw)
    return b"".join(parts)[:target]


def _generate_url_haystack(target: int) -> bytes:
    """Haystack with URLs and non-URL filler."""
    rng = random.Random(_SEED)
    urls = (
        b"https://example.com/path",
        b"http://test.org/api/v1",
        b"https://github.com/user/repo",
    )
    filler = b"some text here "
    parts = []
    total = 0
    while total < target:
        if rng.random() < 0.1:
            parts.append(rng.choice(urls))
        else:
            parts.append(filler)
        total += len(parts[-1])
    return b"".join(parts)[:target]


def _generate_ipv4_haystack(target: int) -> bytes:
    """Haystack with random IPv4-like addresses."""
    rng = random.Random(_SEED)
    parts = []
    total = 0
    while total < target:
        octets = ".".join(str(rng.randint(0, 255)) for _ in range(4))
        entry = octets.encode() + b" "
        parts.append(entry)
        total += len(entry)
    return b"".join(parts)[:target]


def _generate_timestamp_haystack(target: int) -> bytes:
    """Haystack with ISO-8601 timestamps and filler."""
    rng = random.Random(_SEED)
    stamps = (
        b"2024-01-15T10:30:00Z",
        b"2024-06-01T12:00:00+08:00",
        b"2023-12-31T23:59:59.999Z",
    )
    filler = b"log entry at "
    parts = []
    total = 0
    while total < target:
        if rng.random() < 0.2:
            parts.append(filler + rng.choice(stamps) + b" ")
        else:
            parts.append(b"regular log line\n")
        total += len(parts[-1])
    return b"".join(parts)[:target]


def _generate_literal_needle_haystack(target: int) -> bytes:
    """Large haystack with 'needle' at the very end."""
    return b"x" * (target - 6) + b"needle"


# ---- synthetic dataset definitions ----
# Each entry: (name, small_builder, description)
_SYNTHETIC_DATASETS = {
    "dotstar_no_match": (
        _generate_dotstar_no_match,
        "all-x haystack -- a.*z never matches",
    ),
    "dotstar_match_end": (
        _generate_dotstar_match_end,
        "all-a + single-z -- a.*z matches at end",
    ),
    "redos_no_match": (
        _generate_redos_haystack,
        "all-a haystack -- (a+)+b never matches (ReDoS)",
    ),
    "email_noise": (
        _generate_email_noise,
        "interleaved @ noise -- catastrophic for backtracking",
    ),
    "keyword_filler": (
        _generate_keyword_haystack,
        "C keywords scattered in filler text",
    ),
    "url_filler": (
        _generate_url_haystack,
        "URLs scattered in filler text",
    ),
    "ipv4_filler": (
        _generate_ipv4_haystack,
        "random IPv4 addresses separated by spaces",
    ),
    "timestamp_filler": (
        _generate_timestamp_haystack,
        "ISO-8601 timestamps in log-style text",
    ),
    "literal_needle_end": (
        _generate_literal_needle_haystack,
        "large haystack with 'needle' at the end",
    ),
}


def generate_all(dest: Path, big_size: int, force: bool = False) -> list[str]:
    """Generate all synthetic datasets under *dest*.

    Returns the list of dataset names that were successfully created.
    """
    ready = []
    small_size = 64 * 1024  # 64 KiB for small files

    for name, (builder, desc) in _SYNTHETIC_DATASETS.items():
        d = dest / name
        small_path = d / "small"
        big_path = d / "big"

        if not force and small_path.exists() and big_path.exists():
            logger.info("synthetic dataset %s already present, skipping", name)
            ready.append(name)
            continue

        logger.info("generating synthetic dataset: %s (%s)", name, desc)
        small_data = builder(small_size)
        big_data = builder(big_size)

        _write_if_needed(small_path, small_data, force=force)
        _write_if_needed(big_path, big_data, force=force)
        ready.append(name)

    return ready
