#!/usr/bin/env python3
"""Generate deterministic demo events and optionally run Phase 1 analysis."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from linealert_analysis_engine.serialization import analysis_result_to_dict, event_to_dict
from linealert_analysis_engine.service import AnalysisService
from linealert_analysis_engine.storage import SQLiteStore
from linealert_analysis_engine.models import Event


BASE_TS_MS = 1_710_000_000_000


def demo_events() -> tuple[Event, ...]:
    return (
        Event("evt-001", BASE_TS_MS, "cycle_start", "station-1", "line-a", "cycle-001", "unit-001"),
        Event(
            "evt-002",
            BASE_TS_MS + 100,
            "operation_start",
            "station-1",
            "line-a",
            "cycle-001",
            "unit-001",
            {"operation": "weld"},
        ),
        Event(
            "evt-003",
            BASE_TS_MS + 4_300,
            "operation_end",
            "station-1",
            "line-a",
            "cycle-001",
            "unit-001",
            {"operation": "weld"},
        ),
        Event(
            "evt-004",
            BASE_TS_MS + 4_800,
            "cycle_end",
            "station-1",
            "line-a",
            "cycle-001",
            "unit-001",
        ),
        Event(
            "evt-005",
            BASE_TS_MS + 10_000,
            "cycle_start",
            "station-1",
            "line-a",
            "cycle-002",
            "unit-002",
        ),
        Event(
            "evt-006",
            BASE_TS_MS + 10_100,
            "operation_start",
            "station-1",
            "line-a",
            "cycle-002",
            "unit-002",
            {"operation": "weld"},
        ),
        Event(
            "evt-007",
            BASE_TS_MS + 18_300,
            "operation_end",
            "station-1",
            "line-a",
            "cycle-002",
            "unit-002",
            {"operation": "weld"},
        ),
        Event(
            "evt-008",
            BASE_TS_MS + 18_500,
            "fault",
            "station-1",
            "line-a",
            "cycle-002",
            "unit-002",
            {"fault_code": "weld_timeout", "message": "Weld operation exceeded takt time"},
        ),
        Event(
            "evt-009",
            BASE_TS_MS + 19_000,
            "cycle_end",
            "station-1",
            "line-a",
            "cycle-002",
            "unit-002",
        ),
        Event(
            "evt-010",
            BASE_TS_MS + 25_000,
            "cycle_start",
            "station-1",
            "line-a",
            None,
            "unit-003",
        ),
        Event(
            "evt-011",
            BASE_TS_MS + 25_200,
            "operation_start",
            "station-1",
            "line-a",
            None,
            "unit-003",
            {"operation": "inspect"},
        ),
        Event(
            "evt-012",
            BASE_TS_MS + 29_000,
            "cycle_end",
            "station-1",
            "line-a",
            None,
            "unit-003",
        ),
    )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("demo_events.jsonl"),
        help="Path for generated JSONL events.",
    )
    parser.add_argument(
        "--database",
        type=Path,
        default=None,
        help="Optional SQLite database path. If set, events are ingested and analyzed.",
    )
    args = parser.parse_args()

    events = demo_events()
    with args.output.open("w", encoding="utf-8") as handle:
        for event in events:
            handle.write(json.dumps(event_to_dict(event), sort_keys=True) + "\n")

    print(f"Wrote {len(events)} demo events to {args.output}")

    if args.database is not None:
        store = SQLiteStore(args.database)
        try:
            service = AnalysisService(store)
            service.ingest_events(events)
            results = service.analyze_all()
            print(json.dumps([analysis_result_to_dict(result) for result in results], indent=2, sort_keys=True))
        finally:
            store.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
