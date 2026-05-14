import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from linealert_analysis_engine.validation_pack import (  # noqa: E402
    CYCLE_COUNT,
    build_validation_datasets,
    compare_dataset,
    run_validation_dataset,
)


class ValidationPackTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.datasets = {dataset.name: dataset for dataset in build_validation_datasets()}
        cls.comparisons = {
            name: compare_dataset(dataset)
            for name, dataset in cls.datasets.items()
        }

    def test_each_dataset_generates_expected_cycle_volume(self) -> None:
        for dataset in self.datasets.values():
            with self.subTest(dataset=dataset.name):
                self.assertEqual(dataset.expected.cycle_count, CYCLE_COUNT)
                self.assertGreaterEqual(dataset.expected.cycle_count, 20)
                self.assertLessEqual(dataset.expected.cycle_count, 50)

    def test_all_validation_datasets_match_expected_outcomes(self) -> None:
        for comparison in self.comparisons.values():
            with self.subTest(dataset=comparison.dataset_name):
                self.assertTrue(comparison.passed, comparison.mismatches)

    def test_normal_cycles_stay_normal(self) -> None:
        comparison = self.comparisons["normal_cycles"]

        self.assertEqual(comparison.actual["status_counts"], {"ok": CYCLE_COUNT})
        self.assertEqual(comparison.actual["fault_code_counts"], {})

    def test_known_faults_are_detected(self) -> None:
        expected_faults = {
            "slow_tamp_return": "slow_tamp_return",
            "delayed_tamp_extend": "delayed_tamp_extend",
            "speed_dependent_drift": "speed_dependent_drift",
        }

        for dataset_name, fault_code in expected_faults.items():
            with self.subTest(dataset=dataset_name):
                counts = self.comparisons[dataset_name].actual["fault_code_counts"]
                self.assertGreater(counts.get(fault_code, 0), 0)

    def test_jitter_does_not_create_false_positives(self) -> None:
        comparison = self.comparisons["random_timing_jitter"]

        self.assertEqual(comparison.actual["status_counts"], {"ok": CYCLE_COUNT})
        self.assertEqual(comparison.actual["fault_code_counts"], {})

    def test_missing_events_are_flagged(self) -> None:
        comparison = self.comparisons["missing_product_detect"]

        self.assertGreater(comparison.actual["fault_code_counts"].get("missing_product_detect", 0), 0)
        self.assertIn("faulted", comparison.actual["status_counts"])

    def test_out_of_order_sequence_reconstructs_without_false_faults(self) -> None:
        comparison = self.comparisons["out_of_order_event_sequence"]

        self.assertEqual(comparison.actual["status_counts"], {"ok": CYCLE_COUNT})
        self.assertEqual(comparison.actual["fault_code_counts"], {})

    def test_abnormal_timing_relationships_are_explained_clearly(self) -> None:
        results = run_validation_dataset(self.datasets["slow_tamp_return"])
        finding = next(finding for result in results for finding in result.findings)

        self.assertEqual(finding.fault_code, "slow_tamp_return")
        self.assertIn("tamp return", finding.explanation)
        self.assertIn("exceeding", finding.explanation)
        self.assertEqual(finding.details["operation"], "tamp_return")
        self.assertGreater(finding.details["duration_ms"], finding.details["threshold_ms"])
        self.assertEqual(len(finding.evidence_event_ids), 2)


if __name__ == "__main__":
    unittest.main()
