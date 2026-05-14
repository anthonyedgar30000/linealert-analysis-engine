# linealert-analysis-engine

Phase 1 backend-only implementation for deterministic production-line event
analysis.

## Phase 1 scope

- Event ingestion into SQLite
- SQLite persistence for events, reconstructed cycles, and analysis results
- Cycle reconstruction from explicit cycle IDs or `cycle_start` / `cycle_end`
  boundaries
- Deterministic timing analysis based on configurable event relationships
- Simple explainable fault mapping with hardcoded rules
- Unit tests for timing logic
- Demo event generator

There is no frontend or AI/LLM integration in Phase 1.

## Database schema

```sql
CREATE TABLE events (
    id TEXT PRIMARY KEY,
    timestamp_ms INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    station_id TEXT NOT NULL,
    line_id TEXT NOT NULL,
    cycle_id TEXT,
    unit_id TEXT,
    payload_json TEXT NOT NULL,
    ingested_at_ms INTEGER NOT NULL
);

CREATE TABLE cycles (
    id TEXT PRIMARY KEY,
    line_id TEXT NOT NULL,
    station_id TEXT NOT NULL,
    unit_id TEXT,
    started_at_ms INTEGER NOT NULL,
    ended_at_ms INTEGER,
    status TEXT NOT NULL,
    event_count INTEGER NOT NULL
);

CREATE TABLE analysis_results (
    id TEXT PRIMARY KEY,
    cycle_id TEXT NOT NULL,
    created_at_ms INTEGER NOT NULL,
    status TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    findings_json TEXT NOT NULL
);
```

## Event model

Events are immutable dataclasses with:

- `id`
- `timestamp_ms`
- `event_type`
- `station_id`
- `line_id`
- optional `cycle_id`
- optional `unit_id`
- structured `payload`

Phase 1 event types used by the demo are `cycle_start`, `operation_start`,
`operation_end`, `fault`, and `cycle_end`.

## Cycle reconstruction

The reconstructor sorts events by `(timestamp_ms, id)`.

1. Events with an explicit `cycle_id` are grouped by that ID.
2. Events without a `cycle_id` start a reconstructed cycle on `cycle_start`.
3. Subsequent same-line/station events attach to the active cycle until
   `cycle_end`.
4. A new `cycle_start` closes any still-active implicit cycle as `incomplete`.
5. Fault events mark a cycle as `faulted`; otherwise closed cycles are
   `completed` and open cycles are `incomplete`.

## Timing analysis strategy

Timing checks are represented as `EventRelationship` definitions. The default
relationship measures `operation_start` to matching `operation_end` events by
the payload key `operation`, with a 5,000 ms threshold.

New relationships can be added by constructing `TimingAnalyzer` with additional
`EventRelationship` objects. The analyzer loop does not need to change.

## Rule engine

The rule engine applies hardcoded deterministic rules:

- `operation_duration_exceeded` -> `slow_operation`
- `operation_end_missing` -> `missing_operation_end`
- `cycle_duration_exceeded` -> `slow_cycle`
- `explicit_fault_event` -> reported fault code

Every finding includes severity, fault code, explanation, evidence event IDs,
and structured details.

## Sample analysis output

```json
{
  "cycle_id": "cycle-002",
  "status": "faulted",
  "summary": {
    "line_id": "line-a",
    "station_id": "station-1",
    "unit_id": "unit-002",
    "started_at_ms": 1710000010000,
    "ended_at_ms": 1710000019000,
    "duration_ms": 9000,
    "event_count": 5,
    "cycle_status": "faulted"
  },
  "findings": [
    {
      "rule_id": "operation_duration_exceeded",
      "severity": "warning",
      "fault_code": "slow_operation",
      "explanation": "Operation weld took 8200 ms, exceeding the 5000 ms threshold.",
      "evidence_event_ids": ["evt-006", "evt-007"],
      "details": {
        "operation": "weld",
        "duration_ms": 8200,
        "threshold_ms": 5000,
        "relationship": "operation_duration"
      }
    },
    {
      "rule_id": "explicit_fault_event",
      "severity": "error",
      "fault_code": "weld_timeout",
      "explanation": "Fault event evt-008 reported code weld_timeout at 1710000018500 ms.",
      "evidence_event_ids": ["evt-008"],
      "details": {
        "reported_fault_code": "weld_timeout",
        "message": "Weld operation exceeded takt time"
      }
    }
  ]
}
```

## Usage

Run tests:

```bash
python3 -m unittest discover -s tests
```

Generate demo events:

```bash
python3 scripts/generate_demo_events.py --output demo_events.jsonl
```

Generate events, ingest them into SQLite, and print analysis:

```bash
python3 scripts/generate_demo_events.py --output demo_events.jsonl --database demo.db
```
