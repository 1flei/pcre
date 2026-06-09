"""
Cross-engine benchmark pattern definitions.

Defines pattern / dataset / expected-result triples for benchmarking
pcre against Python re, re2c, and rust-regex.  Each ``BenchCase``
specifies a regex pattern (in the common subset understood by all
engines), which dataset file to search, and a verification count.

Pattern syntax is restricted to the intersection of what pcre,
Python re, re2c, and rust-regex all support:

  - literals, concatenation, alternation (|)
  - character classes: [abc], [a-z], [^...]
  - dot (.)
  - quantifiers: ?, *, +
  - anchors: ^, $
  - shorthand classes: \\d, \\w, \\s (and complements)
  - grouping: (...)

NOT supported (and thus avoided here):
  - {n,m} quantifiers (use repeated chars instead)
  - backreferences, lookaround, named groups
  - pcre-specific {tag} extension
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class BenchCase:
    """A single cross-engine benchmark case."""

    name: str
    pattern: str
    dataset: str            # dataset directory name under bench/datasets/data/
    mode: str               # "search" or "match" (anchored)
    expected_count: Optional[int] = None  # expected number of matches in "big" file
    portable_re: bool = True    # can Python re handle it without catastrophic backtracking?
    portable_rust: bool = True  # can rust-regex handle it?
    notes: str = ""


# ---------------------------------------------------------------------------
# Real-world patterns adapted from popular regex benchmark suites.
# These stress different aspects: literal scan, alternation, bounded states,
# backtracking gap, char class selectivity, and dotstar paths.
# ---------------------------------------------------------------------------

REAL_WORLD_CASES: tuple[BenchCase, ...] = (
    # -- HTTP parsing: multi-alternation, char classes, mixed length --
    BenchCase(
        name="http_request_line",
        pattern="[A-Z]+[ ][^ ]+[ ]HTTP/[0-9][.][0-9]",
        dataset="http",
        mode="search",
        expected_count=3661,
        notes="HTTP request line detection in log data.",
    ),
    BenchCase(
        name="uri_with_scheme",
        pattern="[a-zA-Z][a-zA-Z0-9+.-]*://[^ ]+",
        dataset="uri",
        mode="search",
        expected_count=1929,
        notes="URI detection with scheme and authority.",
    ),
    BenchCase(
        name="apache_ip_v4",
        pattern="[0-9]+[.][0-9]+[.][0-9]+[.][0-9]+",
        dataset="apache",
        mode="search",
        expected_count=177855,
        notes="IPv4 address extraction from Apache logs.",
    ),
    BenchCase(
        name="datetime_clf",
        pattern="[A-Za-z]+[ ][A-Za-z]+[ ][0-9]+[ ][0-9]+[ ][0-9:-]+",
        dataset="datetime",
        mode="search",
        expected_count=15000,
        notes="CLF datetime pattern in log data.",
    ),
    BenchCase(
        name="email_simple",
        pattern="[a-z0-9]+@[a-z0-9]+[.][a-z]+",
        dataset="email",
        mode="search",
        expected_count=961,
        notes="Simple email detection.",
    ),
    BenchCase(
        name="ipv4_standalone",
        pattern="[0-9]+[.][0-9]+[.][0-9]+[.][0-9]+",
        dataset="ipv4",
        mode="search",
        expected_count=66,
        notes="IPv4 address detection.",
    ),

    # -- Number parsing: floating point, scientific notation --
    BenchCase(
        name="float_number",
        pattern="[0-9]+[.][0-9]+",
        dataset="numbers2",
        mode="search",
        expected_count=5237,
        notes="Floating-point number detection.",
    ),

    # -- Identifier patterns: char class + quantifier --
    BenchCase(
        name="identifier_c_style",
        pattern="[a-zA-Z_][a-zA-Z0-9_]*",
        dataset="keyword_filler",
        mode="search",
        notes="C-style identifier detection in keyword text.",
    ),

    # -- Timestamps: fixed-width, high selectivity --
    BenchCase(
        name="iso8601_timestamp",
        pattern="[0-9][0-9][0-9][0-9]-[0-9][0-9]-[0-9][0-9]T[0-9][0-9]:[0-9][0-9]:[0-9][0-9]",
        dataset="timestamp_filler",
        mode="search",
        notes="ISO 8601 timestamp in log text.",
    ),

    # -- URL detection: alternation + char class --
    BenchCase(
        name="http_url",
        pattern="https?://[a-zA-Z0-9.]+",
        dataset="url_filler",
        mode="search",
        notes="HTTP(S) URL detection in mixed text.",
    ),

    # -- IPv4 in noise: same pattern, harder haystack --
    BenchCase(
        name="ipv4_in_noise",
        pattern="[0-9]+[.][0-9]+[.][0-9]+[.][0-9]+",
        dataset="ipv4_filler",
        mode="search",
        notes="IPv4 in address filler data.",
    ),
)


# ---------------------------------------------------------------------------
# Alternation scaling: how do engines handle growing branch counts?
# ---------------------------------------------------------------------------

ALTERNATION_CASES: tuple[BenchCase, ...] = (
    BenchCase(
        name="alt2_branches",
        pattern="a|b",
        dataset="alt1",
        mode="search",
        expected_count=510,
        notes="2-branch alternation baseline.",
    ),
    BenchCase(
        name="alt4_branches",
        pattern="a|b|c|d",
        dataset="alt1",
        mode="search",
        expected_count=510,
        notes="4-branch alternation.",
    ),
    BenchCase(
        name="alt8_branches",
        pattern="a|b|c|d|e|f|g|h",
        dataset="alt1",
        mode="search",
        expected_count=510,
        notes="8-branch alternation.",
    ),
    BenchCase(
        name="cat2_alternation",
        pattern="[a-z]+|[0-9]+",
        dataset="cat2",
        mode="search",
        notes="2-branch word|number alternation.",
    ),
    BenchCase(
        name="cat4_alternation",
        pattern="[a-z]+|[0-9]+|[A-Z]+|[^a-zA-Z0-9]+",
        dataset="cat4",
        mode="search",
        notes="4-branch token class alternation.",
    ),
    BenchCase(
        name="cat8_alternation",
        pattern="[a-z]+|[A-Z]+|[0-9]+|[a-z]+[0-9]+|[A-Z]+[0-9]+|[0-9]+[a-z]+|[0-9]+[A-Z]+|[^a-zA-Z0-9]+",
        dataset="cat8",
        mode="search",
        notes="8-branch token class alternation.",
    ),
)


# ---------------------------------------------------------------------------
# Backtracking / DFA advantage: patterns where backtracking engines suffer.
# These are the most meaningful differentiators between engine families.
# ---------------------------------------------------------------------------

BACKTRACKING_STRESS_CASES: tuple[BenchCase, ...] = (
    BenchCase(
        name="dotstar_no_match",
        pattern="a.*z",
        dataset="dotstar_no_match",
        mode="search",
        portable_re=False,
        notes="a.*z on all-x haystack -- DFA linear, backtracking quadratic.",
    ),
    BenchCase(
        name="dotstar_match_end",
        pattern="a.*z",
        dataset="dotstar_match_end",
        mode="search",
        portable_re=False,
        notes="a.*z on all-a + z haystack -- worst case for naive matching.",
    ),
    BenchCase(
        name="redos_no_match",
        pattern="(a+)+b",
        dataset="redos_no_match",
        mode="search",
        portable_re=False,
        notes="(a+)+b on all-a haystack -- exponential for backtracking engines.",
    ),
    BenchCase(
        name="email_noise_no_match",
        pattern="[a-z]+@[a-z]+[.][a-z]+",
        dataset="email_noise",
        mode="search",
        portable_re=False,
        notes="Email pattern on @-heavy noise -- catastrophic for re.",
    ),
    BenchCase(
        name="literal_needle_haystack",
        pattern="needle",
        dataset="literal_needle_end",
        mode="search",
        notes="Literal search, needle at end of 64KB haystack.",
    ),
)


# ---------------------------------------------------------------------------
# Concatenation depth: patterns with many concatenated sub-patterns
# stress the state space and transition logic of the DFA/TDFA.
# ---------------------------------------------------------------------------

CONCAT_DEPTH_CASES: tuple[BenchCase, ...] = (
    BenchCase(
        name="number_words1",
        pattern="[0-9]+",
        dataset="words1",
        mode="search",
        expected_count=57,
        notes="Digit runs in word data.",
    ),
    BenchCase(
        name="number_words2",
        pattern="[0-9]+",
        dataset="words2",
        mode="search",
        notes="Digit runs in larger word data.",
    ),
    BenchCase(
        name="rep_number",
        pattern="[0-9]+",
        dataset="rep",
        mode="search",
        notes="Digit runs in repetitive number data.",
    ),
)


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------

ALL_BENCH_CASES: tuple[BenchCase, ...] = (
    REAL_WORLD_CASES + ALTERNATION_CASES + BACKTRACKING_STRESS_CASES
    + CONCAT_DEPTH_CASES
)

_CASES_BY_NAME: dict[str, BenchCase] = {c.name: c for c in ALL_BENCH_CASES}


def get_case(name: str) -> BenchCase:
    """Look up a benchmark case by name."""
    try:
        return _CASES_BY_NAME[name]
    except KeyError as exc:
        raise KeyError(
            f"Unknown benchmark case {name!r}; registered: "
            f"{sorted(_CASES_BY_NAME)}"
        ) from exc


def all_cases() -> tuple[BenchCase, ...]:
    """Return every registered benchmark case."""
    return ALL_BENCH_CASES
