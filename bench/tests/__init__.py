"""Tests for the bench module infrastructure.

These tests verify that the benchmark infrastructure itself works
correctly (pattern definitions, dataset download, engine drivers)
without actually running full benchmarks (which are too slow for CI).
"""

import os
import tempfile
import unittest
from pathlib import Path

from bench.patterns import (
    ALL_BENCH_CASES,
    BenchCase,
    get_case,
    all_cases,
)
from bench.datasets.synth import generate_all
from bench.datasets.download import data_dir


class TestPatternDefinitions(unittest.TestCase):
    """Verify pattern definitions are well-formed."""

    def test_all_cases_have_names(self):
        for c in ALL_BENCH_CASES:
            self.assertTrue(c.name, f"case has no name: {c}")
            self.assertTrue(c.pattern, f"case {c.name} has no pattern")
            self.assertIn(c.mode, ("search", "match"),
                          f"case {c.name} has invalid mode: {c.mode}")
            self.assertTrue(c.dataset, f"case {c.name} has no dataset")

    def test_names_are_unique(self):
        names = [c.name for c in ALL_BENCH_CASES]
        self.assertEqual(len(names), len(set(names)),
                         f"duplicate names: {[n for n in names if names.count(n) > 1]}")

    def test_get_case(self):
        c = get_case("literal_needle_haystack")
        self.assertEqual(c.name, "literal_needle_haystack")
        self.assertEqual(c.pattern, "needle")

    def test_get_case_unknown_raises(self):
        with self.assertRaises(KeyError):
            get_case("nonexistent_case_xyz")

    def test_all_cases_returns_same_as_constant(self):
        self.assertEqual(all_cases(), ALL_BENCH_CASES)

    def test_portable_re_flags(self):
        """Cases known to cause ReDoS must be marked portable_re=False."""
        known_redos = ["dotstar_no_match", "dotstar_match_end",
                       "redos_no_match", "email_noise_no_match"]
        for name in known_redos:
            c = get_case(name)
            self.assertFalse(c.portable_re,
                             f"ReDoS case {name} should have portable_re=False")


class TestSyntheticDatasetGeneration(unittest.TestCase):
    """Verify synthetic dataset generation works."""

    def test_generate_all_creates_files(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            dest = Path(tmpdir)
            big_size = 1024  # small for testing
            ready = generate_all(dest, big_size, force=True)
            self.assertGreater(len(ready), 0)
            for name in ready:
                small_path = dest / name / "small"
                big_path = dest / name / "big"
                self.assertTrue(small_path.exists(), f"{name}/small missing")
                self.assertTrue(big_path.exists(), f"{name}/big missing")
                self.assertGreater(small_path.stat().st_size, 0)
                self.assertGreaterEqual(big_path.stat().st_size, big_size)


class TestBenchCaseDataclass(unittest.TestCase):
    """Verify BenchCase dataclass behavior."""

    def test_frozen(self):
        c = BenchCase(name="test", pattern="abc", dataset="test", mode="search")
        with self.assertRaises(AttributeError):
            c.name = "changed"

    def test_defaults(self):
        c = BenchCase(name="test", pattern="abc", dataset="test", mode="search")
        self.assertTrue(c.portable_re)
        self.assertTrue(c.portable_rust)
        self.assertIsNone(c.expected_count)
        self.assertEqual(c.notes, "")


class TestRe2cPatternConversion(unittest.TestCase):
    """Verify re2c pattern conversion logic."""

    def test_literal_string(self):
        from bench.run_bench import Re2cEngine
        self.assertEqual(Re2cEngine._pattern_to_re2c("needle"), '"needle"')

    def test_char_class(self):
        from bench.run_bench import Re2cEngine
        self.assertEqual(Re2cEngine._pattern_to_re2c("[0-9]+"), "[0-9] +")

    def test_mixed_pattern(self):
        from bench.run_bench import Re2cEngine
        result = Re2cEngine._pattern_to_re2c("[0-9]+[.][0-9]+")
        self.assertIn("[0-9]", result)
        self.assertIn("[.]", result)
        self.assertIn("+", result)

    def test_escape_sequence(self):
        from bench.run_bench import Re2cEngine
        result = Re2cEngine._pattern_to_re2c("\\d+")
        self.assertIn("\\d", result)

    def test_alternation(self):
        from bench.run_bench import Re2cEngine
        result = Re2cEngine._pattern_to_re2c("a|b")
        self.assertIn('"a"', result)
        self.assertIn("|", result)
        self.assertIn('"b"', result)


class TestShimOutput(unittest.TestCase):
    """Verify shim output parsing."""

    def test_parse_shim_output(self):
        from bench.run_bench import _parse_shim_output
        best, mean = _parse_shim_output("best_ms=1.234 mean_ms=2.345")
        self.assertAlmostEqual(best, 1.234)
        self.assertAlmostEqual(mean, 2.345)

    def test_parse_shim_output_empty(self):
        from bench.run_bench import _parse_shim_output
        best, mean = _parse_shim_output("")
        self.assertIsNone(best)
        self.assertIsNone(mean)


if __name__ == "__main__":
    unittest.main()
