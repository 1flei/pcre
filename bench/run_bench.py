"""
Cross-engine regex benchmark runner.

Benchmarks pcre (Python-level) and pcre-native (raw native call) against:
  - Python ``re``
  - re2c (C native, compiled via the re2c toolchain)
  - rust-regex (Rust native, via a small Rust shim)

``pcre`` measures the full Python-level call including ctypes overhead;
``pcre-native`` measures only the compiled native function execution,
bypassing ctypes argument conversion and buffer management.

All engines are invoked as subprocesses with internal timing, so
measurement overhead is consistent and each engine runs in its
native optimal environment.

Usage:
    python -m bench.run_bench
    python -m bench.run_bench --cases literal_needle,dotstar_a_z_no_match
    python -m bench.run_bench --engines pcre,pcre-native,re,rust
    python -m bench.run_bench --output results/bench_20260608.json
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

# Ensure the project root is on sys.path.
_PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from bench.datasets.download import data_dir
from bench.patterns import ALL_BENCH_CASES, BenchCase, get_case

logger = logging.getLogger(__name__)

# ============================================================================
# Timing infrastructure
# ============================================================================

_DEFAULT_WARMUP = 2
_DEFAULT_REPEATS = 5


@dataclass
class TimingResult:
    """Result of benchmarking a single (engine, case, size) triple."""

    engine: str
    case_name: str
    size: int
    best_ms: Optional[float] = None
    mean_ms: Optional[float] = None
    status: str = "ok"  # "ok", "timeout", "error", "skip", "build_error"
    error_msg: str = ""


def _clean_harness_cache(case_build_dir: Path) -> None:
    """Remove PythoC build cache for the harness so it recompiles.

    The harness script is shared across cases, but its @compile main()
    references a different _regex_fn per case.  PythoC's incremental
    compilation caches .o/.deps by source file path and cannot detect
    that the module-level variable changed.  We delete the harness
    cache so every case gets a fresh compile, just like gcc -O3
    recompiles from scratch for each re2c case.
    """
    build_dir = Path("build")
    if not build_dir.exists():
        return
    for pattern in ["bench/shims/pcre_native_bench.o",
                    "bench/shims/pcre_native_bench.deps",
                    "bench/shims/pcre_native_bench*.o",
                    "bench/shims/pcre_native_bench*.deps",
                    "pcre/codegen.meta.*.o",
                    "pcre/codegen.meta.*.deps"]:
        for p in build_dir.glob(pattern):
            p.unlink(missing_ok=True)


def _parse_shim_output(stdout: str) -> tuple[Optional[float], Optional[float]]:
    """Parse 'best_ms=X.XXX mean_ms=Y.YYY' from shim output."""
    best_ms = None
    mean_ms = None
    for part in stdout.strip().split():
        if part.startswith("best_ms="):
            try:
                best_ms = float(part.split("=", 1)[1])
            except ValueError:
                pass
        elif part.startswith("mean_ms="):
            try:
                mean_ms = float(part.split("=", 1)[1])
            except ValueError:
                pass
    return best_ms, mean_ms


def _run_subprocess(cmd: list[str], timeout: float = 300.0) -> TimingResult:
    """Run a shim subprocess and return a TimingResult."""
    name = cmd[0]
    try:
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout)
        if result.returncode != 0:
            return TimingResult(
                name, "", 0, status="error",
                error_msg=result.stderr.strip()[:200])
        best_ms, mean_ms = _parse_shim_output(result.stdout)
        if best_ms is not None:
            tr = TimingResult(name, "", 0, best_ms, mean_ms)
            return tr
        return TimingResult(
            name, "", 0, status="error",
            error_msg=f"unexpected output: {result.stdout.strip()[:200]}")
    except subprocess.TimeoutExpired:
        return TimingResult(name, "", 0, status="timeout")
    except Exception as e:
        return TimingResult(name, "", 0, status="error", error_msg=str(e)[:200])


# ============================================================================
# Base class for subprocess-based engines
# ============================================================================

class SubprocessEngine:
    """Base class for engines invoked as subprocesses."""

    name: str = ""

    def prepare(self, case: BenchCase) -> bool:
        """Prepare the engine for a given case (compile pattern, etc.)."""
        return True

    def search(self, case: BenchCase, data_path: Path,
               warmup: int, repeats: int) -> TimingResult:
        """Run the benchmark and return a TimingResult."""
        raise NotImplementedError

    def check_available(self) -> bool:
        """Check if this engine is available."""
        return True

    def close(self) -> None:
        """Clean up resources."""
        pass


# ============================================================================
# Engine: Python re / pcre (subprocess via python_regex_bench.py)
# ============================================================================

class PythonEngine(SubprocessEngine):
    """Benchmark driver for Python re or pcre, via subprocess."""

    def __init__(self, engine: str = "re") -> None:
        assert engine in ("re", "pcre")
        self._engine = engine
        self.name = engine if engine == "pcre" else "python-re"
        self._shim = Path(__file__).parent / "shims" / "python_regex_bench.py"

    def prepare(self, case: BenchCase) -> bool:
        if self._engine == "re" and not case.portable_re:
            return False
        return True

    def search(self, case: BenchCase, data_path: Path,
               warmup: int, repeats: int) -> TimingResult:
        cmd = [
            sys.executable, str(self._shim),
            "--engine", self._engine,
            "--pattern", case.pattern,
            "--data", str(data_path),
            "--mode", case.mode,
            "--warmup", str(warmup),
            "--repeats", str(repeats),
        ]
        tr = _run_subprocess(cmd)
        tr.engine = self.name
        return tr


# ============================================================================
# Engine: re2c (re2c -> gcc -> subprocess)
# ============================================================================

class Re2cEngine(SubprocessEngine):
    """Benchmark driver for re2c-compiled regex.

    For each benchmark case, we:
      1. Generate a .re file from the pattern
      2. Run ``re2c`` to produce C code
      3. Compile with ``gcc -O3`` into a binary (with re2c_harness.c)
      4. Run the binary as a subprocess for timing
    """

    name = "re2c"

    def __init__(self) -> None:
        self._build_dir: Path = Path(__file__).parent / "_build_re2c"
        self._available = False
        self._compiled: dict[str, str] = {}  # case_name -> binary path
        self._failed: set[str] = set()

    @staticmethod
    def _pattern_to_re2c(pattern: str) -> str:
        """Convert a regex pattern to re2c syntax.

        re2c requires double-quoted strings for multi-character literals,
        while Python re / Rust regex / pcre treat bare letters as literals.
        We quote runs of non-special characters.
        """
        # Characters that are special in regex/re2c and should not be quoted.
        special = set('.|*+?()[]{}\\^$')
        result = []
        literal_buf = []

        def flush_literal():
            if literal_buf:
                s = "".join(literal_buf)
                # re2c uses double-quoted strings for literals.
                # Escape internal double quotes and backslashes.
                s = s.replace("\\", "\\\\").replace('"', '\\"')
                result.append(f'"{s}"')
                literal_buf.clear()

        i = 0
        while i < len(pattern):
            ch = pattern[i]
            if ch == '\\' and i + 1 < len(pattern):
                # Escape sequence: flush any pending literal, pass through.
                flush_literal()
                result.append(pattern[i:i + 2])
                i += 2
            elif ch in special:
                flush_literal()
                if ch == '[':
                    # Character class: find the closing bracket.
                    j = i + 1
                    if j < len(pattern) and pattern[j] == '^':
                        j += 1
                    if j < len(pattern) and pattern[j] == ']':
                        j += 1
                    while j < len(pattern) and pattern[j] != ']':
                        if pattern[j] == '\\' and j + 1 < len(pattern):
                            j += 2
                        else:
                            j += 1
                    if j < len(pattern):
                        j += 1  # include the ']'
                    result.append(pattern[i:j])
                    i = j
                else:
                    result.append(ch)
                    i += 1
            else:
                # Regular character: buffer it as a literal.
                literal_buf.append(ch)
                i += 1

        flush_literal()
        return " ".join(result)

    def check_available(self) -> bool:
        """Check if re2c and gcc are on PATH."""
        try:
            r = subprocess.run(
                ["re2c", "--version"], capture_output=True, text=True, timeout=5)
            if r.returncode != 0:
                logger.warning("re2c not available")
                return False
        except FileNotFoundError:
            logger.warning("re2c not found on PATH")
            return False
        try:
            subprocess.run(
                ["gcc", "--version"], capture_output=True, text=True,
                timeout=5, check=True)
        except (FileNotFoundError, subprocess.CalledProcessError):
            logger.warning("gcc not found on PATH")
            return False
        self._available = True
        return True

    def _generate_re_file(self, case: BenchCase, re_path: Path) -> None:
        """Write a .re file for the given pattern.

        For match mode: try matching at position 0 only.
        For search mode: try matching at every position (match_at in a loop).
        """
        pattern = self._pattern_to_re2c(case.pattern)
        if case.mode == "match":
            re_content = f"""\
#include <stddef.h>

int match(const char *data, size_t len) {{
    const char *YYCURSOR = data;
    const char *YYLIMIT = data + len;
    const char *YYMARKER;
    /*!re2c
        re2c:define:YYCTYPE = char;
        re2c:yyfill:enable = 0;
        {pattern} {{ return 1; }}
        * {{ return 0; }}
    */
}}
"""
        else:
            # search mode: match_at helper + scan loop.
            re_content = f"""\
#include <stddef.h>

static int match_at(const char *YYCURSOR, const char *YYLIMIT) {{
    const char *YYMARKER;
    /*!re2c
        re2c:define:YYCTYPE = char;
        re2c:yyfill:enable = 0;
        {pattern} {{ return 1; }}
        * {{ return 0; }}
    */
}}

int match(const char *data, size_t len) {{
    const char *limit = data + len;
    for (const char *p = data; p < limit; p++) {{
        if (match_at(p, limit)) return 1;
    }}
    return 0;
}}
"""
        re_path.write_text(re_content)

    def prepare(self, case: BenchCase) -> bool:
        """Generate .re, run re2c, compile with gcc."""
        if not self._available:
            return False
        if case.name in self._compiled:
            return True
        if case.name in self._failed:
            return False

        self._build_dir.mkdir(parents=True, exist_ok=True)
        case_build = self._build_dir / case.name
        case_build.mkdir(parents=True, exist_ok=True)

        re_path = case_build / f"{case.name}.re"
        c_path = case_build / f"{case.name}.c"
        bin_path = case_build / f"re2c_{case.name}"
        harness = Path(__file__).parent / "shims" / "re2c_harness.c"

        # Step 1: Write .re file.
        self._generate_re_file(case, re_path)

        # Step 2: Run re2c to generate C.
        try:
            r = subprocess.run(
                ["re2c", "-o", str(c_path), str(re_path)],
                capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                logger.warning("re2c failed for %s: %s", case.name,
                               r.stderr.strip()[:200])
                self._failed.add(case.name)
                return False
        except Exception as e:
            logger.warning("re2c error for %s: %s", case.name, e)
            self._failed.add(case.name)
            return False

        # Step 3: Compile with gcc.
        try:
            r = subprocess.run(
                ["gcc", "-O3", "-o", str(bin_path),
                 str(c_path), str(harness)],
                capture_output=True, text=True, timeout=30)
            if r.returncode != 0:
                logger.warning("gcc failed for %s: %s", case.name,
                               r.stderr.strip()[:200])
                self._failed.add(case.name)
                return False
        except Exception as e:
            logger.warning("gcc error for %s: %s", case.name, e)
            self._failed.add(case.name)
            return False

        self._compiled[case.name] = str(bin_path)
        return True

    def search(self, case: BenchCase, data_path: Path,
               warmup: int, repeats: int) -> TimingResult:
        if case.name not in self._compiled:
            return TimingResult(self.name, case.name, 0, status="skip")
        cmd = [
            self._compiled[case.name],
            "--data", str(data_path),
            "--warmup", str(warmup),
            "--repeats", str(repeats),
        ]
        tr = _run_subprocess(cmd)
        tr.engine = self.name
        return tr

    def close(self) -> None:
        """Clean up build artifacts."""
        if self._build_dir.exists():
            shutil.rmtree(self._build_dir, ignore_errors=True)


# ============================================================================
# Engine: pcre-native (subprocess, native fn only, no ctypes boxing)
# ============================================================================

class PcreNativeEngine(SubprocessEngine):
    """Benchmark driver for pcre native compiled executable.

    Like re2c, this compiles a per-case standalone binary via
    PythoC's compile_to_executable().  The entire benchmark loop
    (file I/O, regex matching, clock_gettime timing) runs in native
    code with no Python runtime overhead.

    Flow (mirrors Re2cEngine):
      1. prepare(): run the harness script with --build to produce a binary
      2. search(): execute the binary with data/warmup/repeats args
    """

    name = "pcre-native"

    def __init__(self) -> None:
        self._shim = Path(__file__).parent / "shims" / "pcre_native_bench.py"
        self._build_dir: Path = Path(__file__).parent / "_build_pcre_native"
        self._available = False
        self._compiled: dict[str, str] = {}  # case_name -> binary path
        self._failed: set[str] = set()

    def check_available(self) -> bool:
        if not self._shim.exists():
            logger.warning("pcre-native shim not found at %s", self._shim)
            return False
        try:
            import pcre  # noqa: F401
        except ImportError:
            logger.warning("pcre package not importable")
            return False
        self._available = True
        return True

    def prepare(self, case: BenchCase) -> bool:
        """Compile a per-case standalone binary."""
        if not self._available:
            return False
        if case.name in self._compiled:
            return True
        if case.name in self._failed:
            return False

        self._build_dir.mkdir(parents=True, exist_ok=True)
        case_build = self._build_dir / case.name
        case_build.mkdir(parents=True, exist_ok=True)
        bin_path = case_build / f"pcre_native_{case.name}"

        if bin_path.exists():
            self._compiled[case.name] = str(bin_path)
            return True

        # Clean per-case build cache so PythoC recompiles the harness
        # (the same harness script references different _regex_fn per case).
        _clean_harness_cache(case_build)

        cmd = [
            sys.executable, str(self._shim),
            "--build",
            "--pattern", case.pattern,
            "--mode", case.mode,
            "--output", str(bin_path),
        ]
        try:
            r = subprocess.run(
                cmd, capture_output=True, text=True, timeout=120)
            if r.returncode != 0:
                logger.warning("pcre-native build failed for %s: %s",
                               case.name, r.stderr.strip()[:200])
                self._failed.add(case.name)
                return False
        except Exception as e:
            logger.warning("pcre-native build error for %s: %s",
                           case.name, e)
            self._failed.add(case.name)
            return False

        if not bin_path.exists():
            logger.warning("pcre-native binary not found for %s", case.name)
            self._failed.add(case.name)
            return False

        self._compiled[case.name] = str(bin_path)
        return True

    def search(self, case: BenchCase, data_path: Path,
               warmup: int, repeats: int) -> TimingResult:
        if case.name not in self._compiled:
            return TimingResult(self.name, case.name, 0, status="skip")
        cmd = [
            self._compiled[case.name],
            str(data_path),
            str(warmup),
            str(repeats),
        ]
        tr = _run_subprocess(cmd)
        tr.engine = self.name
        return tr

    def close(self) -> None:
        """Clean up build artifacts."""
        if self._build_dir.exists():
            shutil.rmtree(self._build_dir, ignore_errors=True)


# ============================================================================
# Engine: rust-regex (subprocess via rust_regex_bench binary)
# ============================================================================

class RustRegexEngine(SubprocessEngine):
    """Benchmark driver for the Rust regex crate, via subprocess."""

    name = "rust-regex"

    def __init__(self) -> None:
        self._shim_bin: Optional[str] = None
        self._available = False

    def check_available(self) -> bool:
        """Check if the Rust regex shim is built (or build it)."""
        # Ensure cargo is on PATH (rustup installs to ~/.cargo/bin).
        cargo_home = Path.home() / ".cargo"
        if cargo_home.exists():
            os.environ["PATH"] = str(cargo_home / "bin") + os.pathsep + os.environ.get("PATH", "")

        shim_src = Path(__file__).parent / "shims" / "rust_regex_bench"
        cargo_toml = shim_src / "Cargo.toml"

        # Look for pre-built binary.
        bin_path = shim_src / "target" / "release" / "rust-regex-bench"
        if bin_path.exists():
            self._shim_bin = str(bin_path)
            self._available = True
            return True

        # Try to build it.
        if not cargo_toml.exists():
            logger.warning("Rust shim Cargo.toml not found")
            return False

        try:
            logger.info("Building rust-regex shim (first run)...")
            subprocess.run(
                ["cargo", "build", "--release"],
                cwd=str(shim_src),
                capture_output=True, timeout=120, check=True)
            if bin_path.exists():
                self._shim_bin = str(bin_path)
                self._available = True
                return True
        except Exception as e:
            logger.warning("Failed to build rust-regex shim: %s", e)

        return False

    def prepare(self, case: BenchCase) -> bool:
        if not self._available:
            return False
        if not case.portable_rust:
            return False
        return True

    def search(self, case: BenchCase, data_path: Path,
               warmup: int, repeats: int) -> TimingResult:
        if not self._shim_bin:
            return TimingResult(self.name, case.name, 0, status="skip")
        cmd = [
            self._shim_bin,
            "--pattern", case.pattern,
            "--data", str(data_path),
            "--mode", case.mode,
            "--warmup", str(warmup),
            "--repeats", str(repeats),
        ]
        tr = _run_subprocess(cmd)
        tr.engine = self.name
        return tr


# ============================================================================
# Engine registry
# ============================================================================

ENGINE_CLASSES = {
    "pcre": lambda: PythonEngine("pcre"),
    "pcre-native": PcreNativeEngine,
    "re": lambda: PythonEngine("re"),
    "re2c": Re2cEngine,
    "rust": RustRegexEngine,
}


# ============================================================================
# Runner
# ============================================================================

@dataclass
class BenchConfig:
    """Configuration for a benchmark run."""

    cases: list[str] = field(default_factory=list)  # empty = all
    engines: list[str] = field(default_factory=lambda: ["pcre", "pcre-native", "re"])
    use_small: bool = False
    warmup: int = _DEFAULT_WARMUP
    repeats: int = _DEFAULT_REPEATS
    output: Optional[str] = None


def _fmt_time(t: Optional[float]) -> str:
    if t is None:
        return "     -"
    if t < 1.0:
        return f"{t * 1000:>7.1f}us"
    if t < 1000.0:
        return f"{t:>7.2f}ms"
    return f"{t / 1000:>7.3f}s"


def _fmt_ratio(a: Optional[float], b: Optional[float]) -> str:
    if a is None or b is None or b < 1e-9:
        return "    N/A"
    return f"{a / b:>7.1f}x"


def run_benchmarks(config: BenchConfig) -> list[TimingResult]:
    """Execute the full benchmark suite and return results."""
    # Determine cases.
    if config.cases:
        cases = [get_case(n) for n in config.cases]
    else:
        cases = list(ALL_BENCH_CASES)

    # Initialize engines.
    engines: list[SubprocessEngine] = []
    for eng_name in config.engines:
        factory = ENGINE_CLASSES.get(eng_name)
        if factory is None:
            logger.error("Unknown engine %r; available: %s",
                         eng_name, sorted(ENGINE_CLASSES))
            continue
        eng = factory()
        if hasattr(eng, "check_available"):
            if not eng.check_available():
                logger.warning("Engine %s not available, skipping", eng_name)
                continue
        engines.append(eng)

    if not engines:
        logger.error("No engines available")
        return []

    # Prepare engines (compile patterns, build native code, etc.).
    logger.info("Preparing engines...")
    active_cases = []
    for case in cases:
        any_ready = False
        for eng in engines:
            if eng.prepare(case):
                any_ready = True
        if any_ready:
            active_cases.append(case)
        else:
            logger.warning("Case %s skipped: no engine could prepare it",
                           case.name)

    logger.info("Running %d cases with %d engines",
                len(active_cases), len(engines))

    # Run benchmarks.
    results: list[TimingResult] = []
    file_label = "small" if config.use_small else "big"

    for case in active_cases:
        print(f"\n{'=' * 80}")
        print(f"  {case.name}: /{case.pattern}/  [{case.mode}, {file_label}]")
        if case.notes:
            print(f"  {case.notes}")
        print(f"{'=' * 80}")

        # Find data file.
        data_path = data_dir() / case.dataset / file_label
        if not data_path.exists():
            logger.warning("Dataset %s not found at %s", case.dataset,
                           data_path)
            for eng in engines:
                results.append(TimingResult(
                    eng.name, case.name, 0, status="skip",
                    error_msg="dataset not found"))
            continue

        size = data_path.stat().st_size

        # Header.
        header = (f"  {'engine':>14s}  {'best':>10s}  {'mean':>10s}  "
                  f"{'vs pcre':>10s}")
        print(header)
        print("-" * 80)

        pcre_best: Optional[float] = None

        for eng in engines:
            r = eng.search(case, data_path, config.warmup, config.repeats)
            r.case_name = case.name
            r.size = size
            results.append(r)

            if eng.name == "pcre" and r.best_ms is not None:
                pcre_best = r.best_ms

            status_mark = ""
            if r.status != "ok":
                status_mark = f"  [{r.status}]"
                if r.error_msg:
                    status_mark += f" {r.error_msg[:50]}"

            if r.best_ms is not None and pcre_best is not None:
                ratio = _fmt_ratio(r.best_ms, pcre_best)
            else:
                ratio = "    -"
            print(f"  {eng.name:>14s}  {_fmt_time(r.best_ms):>10s}  "
                  f"{_fmt_time(r.mean_ms):>10s}  {ratio:>10s}{status_mark}")
            sys.stdout.flush()

    # Clean up.
    for eng in engines:
        eng.close()

    return results


def results_to_json(results: list[TimingResult], config: BenchConfig) -> dict:
    """Convert results to a JSON-serializable dict."""
    return {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
        "config": {
            "engines": config.engines,
            "cases": config.cases or [c.name for c in ALL_BENCH_CASES],
            "use_small": config.use_small,
            "warmup": config.warmup,
            "repeats": config.repeats,
        },
        "results": [
            {
                "engine": r.engine,
                "case": r.case_name,
                "size": r.size,
                "best_ms": r.best_ms,
                "mean_ms": r.mean_ms,
                "status": r.status,
                "error": r.error_msg if r.error_msg else None,
            }
            for r in results
        ],
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Cross-engine regex benchmark runner")
    parser.add_argument(
        "--cases", default="",
        help="Comma-separated case names (default: all)")
    parser.add_argument(
        "--engines", default="pcre,pcre-native,re",
        help="Comma-separated engine names: pcre,pcre-native,re,re2c,rust (default: pcre,pcre-native,re)")
    parser.add_argument(
        "--small", action="store_true",
        help="Use small dataset files instead of big")
    parser.add_argument(
        "--output", "-o", default=None,
        help="JSON file to write results to")
    parser.add_argument(
        "--warmup", type=int, default=_DEFAULT_WARMUP)
    parser.add_argument(
        "--repeats", type=int, default=_DEFAULT_REPEATS)
    parser.add_argument(
        "--verbose", "-v", action="store_true")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )

    # Ensure datasets are available.
    from bench.datasets.download import ensure_all
    logger.info("Checking datasets...")
    datasets = ensure_all()
    logger.info("Datasets ready: %d", len(datasets))

    config = BenchConfig(
        cases=[s.strip() for s in args.cases.split(",") if s.strip()],
        engines=[s.strip() for s in args.engines.split(",") if s.strip()],
        use_small=args.small,
        warmup=args.warmup,
        repeats=args.repeats,
        output=args.output,
    )

    results = run_benchmarks(config)

    if config.output:
        out_path = Path(config.output)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        with open(out_path, "w") as f:
            json.dump(results_to_json(results, config), f, indent=2)
        print(f"\nResults saved to {out_path}")

    # Print summary.
    ok = sum(1 for r in results if r.status == "ok")
    total = len(results)
    print(f"\nSummary: {ok}/{total} benchmarks completed successfully")


if __name__ == "__main__":
    main()
