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
- Deterministic validation pack for expected Phase 1 outcomes
- Messy reality validation datasets with low/medium/high confidence scoring
- Deterministic cycle timelines and operational incident narratives
- Structured troubleshooting knowledge-base loader for future expert decision
  tree ingestion

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

Every finding includes severity, confidence, fault code, explanation, evidence
event IDs, and structured details.

Confidence is scored after all cycles in a run are analyzed. The scorer uses
deterministic inputs only:

- evidence consistency across the abnormal span
- repeated occurrence count
- relationship strength versus threshold
- duration of abnormal behavior across the analyzed window

## Timeline and incident reconstruction

`TimelineReconstructor` builds deterministic, evidence-linked operational
explanations from reconstructed cycles and scored analysis results.

It emits:

- per-cycle event timelines with operation durations, thresholds, statuses, and
  evidence event IDs
- abnormal spans grouped by finding code
- behavior pattern classification: `isolated`, `intermittent`, or `sustained`
- relationship history summaries such as average/min/max duration and threshold
  exceedance count
- rolling drift progression windows for long-running timing changes
- human-readable narratives generated only from measured events, findings, and
  confidence inputs

No LLM, AI-generated explanation, recommendation engine, frontend, or chat
interface is used.

## Troubleshooting knowledge base

The troubleshooting knowledge base is a structured import format for Peter's
real label-machine troubleshooting decision tree. The current repository only
contains placeholder examples; they are not Peter's actual knowledge.

Supported file types:

- JSON
- YAML/YML using a dependency-free subset, with optional PyYAML support if it is
  installed by the runtime

Required entry fields:

- `symptom_category`
- `observed_operator_symptom`
- `related_fault_code`
- `possible_causes`
- `distinguishing_questions`
- `machine_signals_to_check`
- `timing_relationships_to_check`
- `recommended_checks`
- `recommended_fixes`
- `escalation_condition`
- `notes_from_expert`
- `confidence_adjustment_rules`

Example placeholder entry:

```json
{
  "schema_version": 1,
  "source": "PLACEHOLDER TEMPLATE - replace with Peter's real label-machine troubleshooting tree",
  "is_placeholder": true,
  "entries": [
    {
      "id": "placeholder_entry_001",
      "is_placeholder": true,
      "symptom_category": "PLACEHOLDER: symptom category from Peter's tree",
      "observed_operator_symptom": "PLACEHOLDER: operator-visible symptom text goes here",
      "related_fault_code": "PLACEHOLDER_RELATED_LINEALERT_FAULT_CODE",
      "possible_causes": ["PLACEHOLDER: possible cause from real expert tree"],
      "distinguishing_questions": ["PLACEHOLDER: question Peter uses to distinguish this path"],
      "machine_signals_to_check": ["PLACEHOLDER: machine signal or sensor name to verify"],
      "timing_relationships_to_check": ["PLACEHOLDER: LineAlert timing relationship name"],
      "recommended_checks": ["PLACEHOLDER: safe inspection/check step from Peter"],
      "recommended_fixes": ["PLACEHOLDER: fix action from Peter's real tree"],
      "escalation_condition": "PLACEHOLDER: condition where operator should escalate",
      "notes_from_expert": "PLACEHOLDER: Peter's notes or context go here.",
      "confidence_adjustment_rules": [
        {
          "condition": "PLACEHOLDER: deterministic condition using evidence fields",
          "adjustment": "PLACEHOLDER: increase | decrease | no_change",
          "rationale": "PLACEHOLDER: expert rationale for confidence adjustment"
        }
      ]
    }
  ]
}
```

To add Peter's real entries later:

1. Copy `examples/troubleshooting_placeholder.json` or
   `examples/troubleshooting_template.yaml`.
2. Keep `schema_version: 1`.
3. Replace every `PLACEHOLDER` value with Peter's real symptom, cause, question,
   signal, timing relationship, check, fix, escalation, and expert-note text.
4. Set `is_placeholder` to `false` at the root and entry level.
5. Set `related_fault_code` to the LineAlert finding code the entry should map
   to, such as a timing-derived fault code.
6. Load it with `load_troubleshooting_knowledge(path)`; no core code changes are
   needed if the schema is preserved.

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
      "confidence": "medium",
      "explanation": "Operation weld took 8200 ms, exceeding the 5000 ms threshold.",
      "evidence_event_ids": ["evt-006", "evt-007"],
      "details": {
        "operation": "weld",
        "duration_ms": 8200,
        "threshold_ms": 5000,
        "relationship": "operation_duration",
        "confidence_inputs": {
          "occurrence_count": 1,
          "total_cycles": 3,
          "span_cycles": 1,
          "evidence_consistency": 1.0,
          "median_relationship_strength": 0.64
        }
      }
    },
    {
      "rule_id": "explicit_fault_event",
      "severity": "error",
      "fault_code": "weld_timeout",
      "confidence": "medium",
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

Run the validation pack:

```bash
python3 scripts/run_validation_pack.py --output-dir validation_output
```

The validation pack generates deterministic expected-vs-actual datasets:

- `normal_cycles`
- `slow_tamp_return`
- `delayed_tamp_extend`
- `missing_product_detect`
- `out_of_order_event_sequence`
- `speed_dependent_drift`
- `random_timing_jitter`
- `messy_acceptable_noise`
- `messy_intermittent_faults`
- `messy_partial_borderline_faults`
- `messy_overlapping_symptoms`
- `messy_gradual_drift`

For each dataset it stores expected summaries, runs SQLite-backed ingestion and
analysis, compares actual to expected, and can write generated events plus
sample outputs and incident narratives to disk.

The original validation datasets generate 30 cycles each. Messy datasets
generate 240 cycles each so intermittent faults, weak signals, cycle skips,
operator interventions, noisy timestamps, varying speed, degraded acceptable
behavior, overlapping fault domains, and gradual drift can be assessed without
AI or frontend code.

Example incident narrative output:

```json
{
  "fault_code": "slow_tamp_return",
  "confidence": "low",
  "behavior_pattern": "intermittent",
  "summary": "slow_tamp_return affected 5 cycle(s) from 17 to 203; behavior appears intermittent for tamp return.",
  "reason": "slow_tamp_return matters because measured duration exceeded threshold by 51 ms.",
  "why_confidence": "confidence is low; 5 abnormal occurrence(s); span 17-203; evidence consistency 0.027; median relationship strength 0.041.",
  "relationship_history": {
    "operation": "tamp_return",
    "observed_count": 240,
    "threshold_ms": 900,
    "exceeded_count": 5
  }
}
```
