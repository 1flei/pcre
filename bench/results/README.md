# Benchmark results directory.

Results are stored as JSON files with the following structure:

```json
{
  "timestamp": "2026-06-09T11:00:00",
  "config": {
    "engines": ["pcre", "pcre-native", "re"],
    "cases": ["literal_needle_haystack", "dotstar_no_match", ...],
    "use_small": false,
    "warmup": 2,
    "repeats": 5
  },
  "results": [
    {
      "engine": "pcre-native",
      "case": "literal_needle_haystack",
      "size": 16777216,
      "best_ms": 4.5,
      "mean_ms": 4.7,
      "status": "ok"
    },
    ...
  ]
}
```

Do not commit large result files; use .gitignore patterns for dated results.
