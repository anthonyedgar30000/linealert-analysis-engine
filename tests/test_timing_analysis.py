import unittest
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from linealert_analysis_engine.models import Event, ReconstructedCycle
from linealert_analysis_engine.rules import RuleEngine
from linealert_analysis_engine.timing import EventRelationship, TimingAnalyzer


class TimingAnalysisTests(unittest.TestCase):
    def test_operation_duration_exceeded_maps_to_explainable_finding(self) -> None:
        cycle = _cycle(
            Event("evt-1", 1_000, "cycle_start", "station-1", "line-a", "cycle-1"),
            Event(
                "evt-2",
                1_100,
                "operation_start",
                "station-1",
                "line-a",
                "cycle-1",
                payload={"operation": "weld"},
            ),
            Event(
                "evt-3",
                7_300,
                "operation_end",
                "station-1",
                "line-a",
                "cycle-1",
                payload={"operation": "weld"},
            ),
            Event("evt-4", 7_500, "cycle_end", "station-1", "line-a", "cycle-1"),
        )

        timing = TimingAnalyzer().analyze(cycle)
        result = RuleEngine().evaluate(cycle, timing)

        self.assertEqual(result.status, "warning")
        self.assertEqual(len(result.findings), 1)
        finding = result.findings[0]
        self.assertEqual(finding.rule_id, "operation_duration_exceeded")
        self.assertEqual(finding.fault_code, "slow_operation")
        self.assertEqual(finding.details["duration_ms"], 6_200)
        self.assertEqual(finding.details["threshold_ms"], 5_000)
        self.assertEqual(finding.evidence_event_ids, ("evt-2", "evt-3"))

    def test_missing_operation_end_maps_to_fault(self) -> None:
        cycle = _cycle(
            Event("evt-1", 1_000, "cycle_start", "station-1", "line-a", "cycle-1"),
            Event(
                "evt-2",
                1_100,
                "operation_start",
                "station-1",
                "line-a",
                "cycle-1",
                payload={"operation": "inspect"},
            ),
            Event("evt-3", 3_000, "cycle_end", "station-1", "line-a", "cycle-1"),
        )

        timing = TimingAnalyzer().analyze(cycle)
        result = RuleEngine().evaluate(cycle, timing)

        self.assertEqual(result.status, "faulted")
        self.assertEqual(len(result.findings), 1)
        finding = result.findings[0]
        self.assertEqual(finding.rule_id, "operation_end_missing")
        self.assertEqual(finding.fault_code, "missing_operation_end")
        self.assertEqual(finding.evidence_event_ids, ("evt-2",))

    def test_custom_relationship_can_be_added_without_analyzer_changes(self) -> None:
        cycle = _cycle(
            Event("evt-1", 1_000, "cycle_start", "station-1", "line-a", "cycle-1"),
            Event(
                "evt-2",
                1_100,
                "robot_wait_start",
                "station-1",
                "line-a",
                "cycle-1",
                payload={"robot": "r7"},
            ),
            Event(
                "evt-3",
                1_450,
                "robot_wait_end",
                "station-1",
                "line-a",
                "cycle-1",
                payload={"robot": "r7"},
            ),
            Event("evt-4", 2_000, "cycle_end", "station-1", "line-a", "cycle-1"),
        )
        relationship = EventRelationship(
            name="robot_wait",
            start_event_type="robot_wait_start",
            end_event_type="robot_wait_end",
            threshold_ms=300,
            match_payload_keys=("robot",),
            label_payload_key="robot",
        )

        timing = TimingAnalyzer([relationship]).analyze(cycle)

        self.assertEqual(len(timing.measurements), 1)
        measurement = timing.measurements[0]
        self.assertEqual(measurement.relationship, "robot_wait")
        self.assertEqual(measurement.label, "r7")
        self.assertEqual(measurement.duration_ms, 350)
        self.assertTrue(measurement.exceeded_threshold)


def _cycle(*events: Event) -> ReconstructedCycle:
    return ReconstructedCycle(
        id="cycle-1",
        line_id="line-a",
        station_id="station-1",
        unit_id=None,
        started_at_ms=events[0].timestamp_ms,
        ended_at_ms=events[-1].timestamp_ms,
        status="completed",
        events=events,
    )


if __name__ == "__main__":
    unittest.main()
