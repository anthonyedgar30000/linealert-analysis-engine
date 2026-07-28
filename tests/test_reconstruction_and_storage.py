import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from linealert_analysis_engine.models import Event
from linealert_analysis_engine.reconstruction import CycleReconstructor
from linealert_analysis_engine.service import AnalysisService
from linealert_analysis_engine.storage import SQLiteStore


class ReconstructionAndStorageTests(unittest.TestCase):
    def test_reconstructs_implicit_cycle_boundaries(self) -> None:
        events = (
            Event("evt-1", 1_000, "cycle_start", "station-1", "line-a", unit_id="unit-1"),
            Event(
                "evt-2",
                1_500,
                "operation_start",
                "station-1",
                "line-a",
                unit_id="unit-1",
                payload={"operation": "weld"},
            ),
            Event(
                "evt-3",
                2_500,
                "operation_end",
                "station-1",
                "line-a",
                unit_id="unit-1",
                payload={"operation": "weld"},
            ),
            Event("evt-4", 3_000, "cycle_end", "station-1", "line-a", unit_id="unit-1"),
        )

        cycles = CycleReconstructor().reconstruct(events)

        self.assertEqual(len(cycles), 1)
        self.assertEqual(cycles[0].status, "completed")
        self.assertEqual(cycles[0].started_at_ms, 1_000)
        self.assertEqual(cycles[0].ended_at_ms, 3_000)
        self.assertEqual(cycles[0].event_count, 4)

    def test_service_persists_events_cycles_and_analysis(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            store = SQLiteStore(Path(temp_dir) / "analysis.db")
            service = AnalysisService(store)
            service.ingest_events(
                [
                    {
                        "id": "evt-1",
                        "timestamp_ms": 1_000,
                        "event_type": "cycle_start",
                        "station_id": "station-1",
                        "line_id": "line-a",
                        "cycle_id": "cycle-1",
                        "payload": {},
                    },
                    {
                        "id": "evt-2",
                        "timestamp_ms": 1_100,
                        "event_type": "operation_start",
                        "station_id": "station-1",
                        "line_id": "line-a",
                        "cycle_id": "cycle-1",
                        "payload": {"operation": "weld"},
                    },
                    {
                        "id": "evt-3",
                        "timestamp_ms": 7_000,
                        "event_type": "operation_end",
                        "station_id": "station-1",
                        "line_id": "line-a",
                        "cycle_id": "cycle-1",
                        "payload": {"operation": "weld"},
                    },
                    {
                        "id": "evt-4",
                        "timestamp_ms": 7_100,
                        "event_type": "cycle_end",
                        "station_id": "station-1",
                        "line_id": "line-a",
                        "cycle_id": "cycle-1",
                        "payload": {},
                    },
                ]
            )

            results = service.analyze_all()

            self.assertEqual(len(results), 1)
            self.assertEqual(results[0].cycle_id, "cycle-1")
            self.assertEqual(results[0].findings[0].fault_code, "slow_operation")
            store.close()


if __name__ == "__main__":
    unittest.main()
