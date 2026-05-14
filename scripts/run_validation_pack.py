#!/usr/bin/env python3
"""Generate and validate deterministic Phase 1 demo datasets."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from linealert_analysis_engine.validation_pack import (
    build_validation_datasets,
    compare_dataset,
    dataset_to_jsonl,
)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Optional directory for dataset JSONL and expected/actual summaries.",
    )
    args = parser.parse_args()

    comparisons = []
    for dataset in build_validation_datasets():
        comparison = compare_dataset(dataset)
        comparisons.append(comparison)

        if args.output_dir is not None:
            dataset_dir = args.output_dir / dataset.name
            dataset_dir.mkdir(parents=True, exist_ok=True)
            (dataset_dir / "events.jsonl").write_text(dataset_to_jsonl(dataset) + "\n", encoding="utf-8")
            (dataset_dir / "expected.json").write_text(
                json.dumps(comparison.expected, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (dataset_dir / "actual.json").write_text(
                json.dumps(comparison.actual, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )
            (dataset_dir / "sample_outputs.json").write_text(
                json.dumps(comparison.sample_outputs, indent=2, sort_keys=True) + "\n",
                encoding="utf-8",
            )

    report = [
        {
            "dataset": comparison.dataset_name,
            "passed": comparison.passed,
            "expected": comparison.expected,
            "actual": comparison.actual,
            "mismatches": list(comparison.mismatches),
            "sample_outputs": list(comparison.sample_outputs),
        }
        for comparison in comparisons
    ]
    print(json.dumps(report, indent=2, sort_keys=True))

    return 0 if all(comparison.passed for comparison in comparisons) else 1


if __name__ == "__main__":
    raise SystemExit(main())
