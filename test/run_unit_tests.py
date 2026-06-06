#!/usr/bin/env python
"""Run all unit tests."""

import argparse
import os
import sys
import unittest

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def resolve_verbosity() -> int:
    parser = argparse.ArgumentParser(description="Run unit tests")
    parser.add_argument("--quiet", action="store_true", help="Only print summary and failures")
    parser.add_argument("--verbose", action="store_true", help="Print each test name")
    args = parser.parse_args()

    if args.quiet and args.verbose:
        parser.error("--quiet and --verbose cannot be used together")

    if args.quiet:
        return 0
    if args.verbose:
        return 2
    return 1


if __name__ == '__main__':
    # Discover unit tests.
    # pcre puts pure-Python unit tests in test/ (not test/unit/),
    # so we search the test directory for unit test files.
    loader = unittest.TestLoader()
    test_dir = os.path.dirname(__file__)

    # If test/unit/ exists, prefer it; otherwise search test/ directly
    unit_dir = os.path.join(test_dir, 'unit')
    if os.path.isdir(unit_dir):
        start_dir = unit_dir
    else:
        start_dir = test_dir

    suite = loader.discover(start_dir, pattern='test_regex_unit.py')
    # Also discover TDFA consistency tests
    tdfa_suite = loader.discover(start_dir, pattern='test_regex_tdfa.py')
    suite.addTests(tdfa_suite)

    runner = unittest.TextTestRunner(verbosity=resolve_verbosity())
    result = runner.run(suite)

    sys.exit(0 if result.wasSuccessful() else 1)
