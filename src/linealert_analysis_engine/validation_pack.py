"""Deterministic validation datasets for the Phase 1 timing/rule engine."""

from __future__ import annotations

import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from random import Random
from typing import Any

from .models import AnalysisResult, Event
from .serialization import analysis_result_to_dict, event_to_dict
from .service import AnalysisService
from .storage import SQLiteStore
from .timing import EventRelationship, TimingAnalyzer


CYCLE_COUNT = 30
MESSY_CYCLE_COUNT = 240
LINE_ID = "line-a"
STATION_ID = "tamp-station-1"


@dataclass(frozen=True, slots=True)
class ExpectedOutcome:
    cycle_count: int
    status_counts: dict[str, int]
    fault_code_counts: dict[str, int]
    confidence_counts: dict[str, int] | None = None


@dataclass(frozen=True, slots=True)
class ValidationDataset:
    name: str
    description: str
    events: tuple[Event, ...]
    expected: ExpectedOutcome


@dataclass(frozen=True, slots=True)
class ValidationComparison:
    dataset_name: str
    passed: bool
    expected: dict[str, Any]
    actual: dict[str, Any]
    mismatches: tuple[str, ...]
    sample_outputs: tuple[dict[str, Any], ...]


def validation_relationships() -> tuple[EventRelationship, ...]:
    """Relationships used by the tamp-station validation pack."""

    return (
        _operation_relationship("product_detect", threshold_ms=250),
        _operation_relationship("tamp_extend", threshold_ms=700),
        _operation_relationship("index_transfer", threshold_ms=1_050),
        _operation_relationship("tamp_return", threshold_ms=900),
    )


def build_validation_datasets() -> tuple[ValidationDataset, ...]:
    return (
        _normal_cycles(),
        _slow_tamp_return(),
        _delayed_tamp_extend(),
        _missing_product_detect(),
        _out_of_order_event_sequence(),
        _speed_dependent_drift(),
        _random_timing_jitter(),
        _messy_acceptable_noise(),
        _messy_intermittent_faults(),
        _messy_partial_borderline_faults(),
        _messy_overlapping_symptoms(),
        _messy_gradual_drift(),
    )


def run_validation_dataset(dataset: ValidationDataset) -> tuple[AnalysisResult, ...]:
    """Run a dataset through SQLite-backed ingestion and analysis."""

    with tempfile.TemporaryDirectory() as temp_dir:
        store = SQLiteStore(Path(temp_dir) / f"{dataset.name}.db")
        try:
            service = AnalysisService(
                store,
                timing_analyzer=TimingAnalyzer(validation_relationships()),
            )
            service.ingest_events(dataset.events)
            return service.analyze_all()
        finally:
            store.close()


def compare_dataset(dataset: ValidationDataset) -> ValidationComparison:
    actual_results = run_validation_dataset(dataset)
    actual = summarize_results(actual_results)
    expected = expected_to_dict(dataset.expected)
    mismatches = tuple(_mismatches(expected, actual))
    samples = tuple(analysis_result_to_dict(result) for result in _interesting_samples(actual_results))
    return ValidationComparison(
        dataset_name=dataset.name,
        passed=not mismatches,
        expected=expected,
        actual=actual,
        mismatches=mismatches,
        sample_outputs=samples,
    )


def compare_all_datasets() -> tuple[ValidationComparison, ...]:
    return tuple(compare_dataset(dataset) for dataset in build_validation_datasets())


def summarize_results(results: tuple[AnalysisResult, ...]) -> dict[str, Any]:
    status_counts: Counter[str] = Counter(result.status for result in results)
    fault_code_counts: Counter[str] = Counter(
        finding.fault_code for result in results for finding in result.findings
    )
    confidence_counts: Counter[str] = Counter(
        finding.confidence for result in results for finding in result.findings
    )
    summary = {
        "cycle_count": len(results),
        "status_counts": dict(sorted(status_counts.items())),
        "fault_code_counts": dict(sorted(fault_code_counts.items())),
    }
    summary["confidence_counts"] = dict(sorted(confidence_counts.items()))
    return summary


def expected_to_dict(expected: ExpectedOutcome) -> dict[str, Any]:
    expected_dict = {
        "cycle_count": expected.cycle_count,
        "status_counts": dict(sorted(expected.status_counts.items())),
        "fault_code_counts": dict(sorted(expected.fault_code_counts.items())),
    }
    if expected.confidence_counts is not None:
        expected_dict["confidence_counts"] = dict(sorted(expected.confidence_counts.items()))
    return expected_dict


def dataset_to_jsonl(dataset: ValidationDataset) -> str:
    return "\n".join(
        _to_stable_json_line(event_to_dict(event)) for event in dataset.events
    )


def _normal_cycles() -> ValidationDataset:
    return ValidationDataset(
        name="normal_cycles",
        description="Nominal tamp-station cycles with all timing relationships under threshold.",
        events=_build_events("normal_cycles", _normal_profile),
        expected=ExpectedOutcome(
            cycle_count=CYCLE_COUNT,
            status_counts={"ok": CYCLE_COUNT},
            fault_code_counts={},
        ),
    )


def _slow_tamp_return() -> ValidationDataset:
    fault_count = _count_matching(lambda index: index % 4 == 0)
    return ValidationDataset(
        name="slow_tamp_return",
        description="Tamp return exceeds its deterministic threshold on known cycles.",
        events=_build_events(
            "slow_tamp_return",
            lambda index: _normal_profile(index)
            | {"tamp_return_ms": 1_180 if index % 4 == 0 else 620},
        ),
        expected=ExpectedOutcome(
            cycle_count=CYCLE_COUNT,
            status_counts={"ok": CYCLE_COUNT - fault_count, "warning": fault_count},
            fault_code_counts={"slow_tamp_return": fault_count},
        ),
    )


def _delayed_tamp_extend() -> ValidationDataset:
    fault_count = _count_matching(lambda index: index % 5 == 1)
    return ValidationDataset(
        name="delayed_tamp_extend",
        description="Tamp extend is delayed beyond threshold on known cycles.",
        events=_build_events(
            "delayed_tamp_extend",
            lambda index: _normal_profile(index)
            | {"tamp_extend_ms": 940 if index % 5 == 1 else 520},
        ),
        expected=ExpectedOutcome(
            cycle_count=CYCLE_COUNT,
            status_counts={"ok": CYCLE_COUNT - fault_count, "warning": fault_count},
            fault_code_counts={"delayed_tamp_extend": fault_count},
        ),
    )


def _missing_product_detect() -> ValidationDataset:
    fault_count = _count_matching(lambda index: index % 6 == 2)
    return ValidationDataset(
        name="missing_product_detect",
        description="Product detect start events are missing their matching completion event.",
        events=_build_events(
            "missing_product_detect",
            lambda index: _normal_profile(index)
            | {"missing_product_detect_end": index % 6 == 2},
        ),
        expected=ExpectedOutcome(
            cycle_count=CYCLE_COUNT,
            status_counts={"faulted": fault_count, "ok": CYCLE_COUNT - fault_count},
            fault_code_counts={"missing_product_detect": fault_count},
        ),
    )


def _out_of_order_event_sequence() -> ValidationDataset:
    events = _build_events("out_of_order_event_sequence", _normal_profile)
    reordered = tuple(reversed(events))
    return ValidationDataset(
        name="out_of_order_event_sequence",
        description="Events arrive in reverse order but retain accurate event timestamps.",
        events=reordered,
        expected=ExpectedOutcome(
            cycle_count=CYCLE_COUNT,
            status_counts={"ok": CYCLE_COUNT},
            fault_code_counts={},
        ),
    )


def _speed_dependent_drift() -> ValidationDataset:
    def profile(index: int) -> dict[str, Any]:
        base = _normal_profile(index)
        high_speed = index >= 18
        drift_ms = 780 + max(0, index - 18) * 45
        return base | {
            "speed_profile": "high" if high_speed else "normal",
            "index_transfer_ms": drift_ms if high_speed else 760,
        }

    fault_count = _count_matching(lambda index: index >= 25)
    return ValidationDataset(
        name="speed_dependent_drift",
        description="High-speed cycles drift until index transfer exceeds its threshold.",
        events=_build_events("speed_dependent_drift", profile),
        expected=ExpectedOutcome(
            cycle_count=CYCLE_COUNT,
            status_counts={"ok": CYCLE_COUNT - fault_count, "warning": fault_count},
            fault_code_counts={"speed_dependent_drift": fault_count},
        ),
    )


def _random_timing_jitter() -> ValidationDataset:
    random = Random(42)

    def profile(index: int) -> dict[str, Any]:
        base = _normal_profile(index)
        return base | {
            "product_detect_ms": 80 + random.randint(-20, 35),
            "tamp_extend_ms": 520 + random.randint(-70, 95),
            "index_transfer_ms": 760 + random.randint(-90, 130),
            "tamp_return_ms": 620 + random.randint(-85, 120),
            "jitter_seed": 42,
        }

    return ValidationDataset(
        name="random_timing_jitter",
        description="Deterministic random jitter remains below thresholds and should not fault.",
        events=_build_events("random_timing_jitter", profile),
        expected=ExpectedOutcome(
            cycle_count=CYCLE_COUNT,
            status_counts={"ok": CYCLE_COUNT},
            fault_code_counts={},
        ),
    )


def _messy_acceptable_noise() -> ValidationDataset:
    random = Random(108)

    def profile(index: int) -> dict[str, Any]:
        speed = "fast" if index % 17 in (0, 1, 2, 3) else "normal"
        skipped = index % 53 == 11
        operator_intervention = index % 29 in (3, 4)
        return _normal_profile(index) | {
            "product_detect_ms": 90 + random.randint(-35, 60),
            "tamp_extend_ms": 525 + random.randint(-95, 150),
            "index_transfer_ms": (825 if speed == "fast" else 760) + random.randint(-120, 180),
            "tamp_return_ms": 640 + random.randint(-110, 190),
            "speed_profile": speed,
            "skipped_cycle": skipped,
            "operator_intervention": operator_intervention,
            "timestamp_noise_ms": random.randint(-18, 18),
        }

    return ValidationDataset(
        name="messy_acceptable_noise",
        description=(
            "Noisy timestamps, planned cycle skips, operator interventions, and varying speed "
            "that remain degraded-but-acceptable."
        ),
        events=_build_events("messy_acceptable_noise", profile, cycle_count=MESSY_CYCLE_COUNT),
        expected=ExpectedOutcome(
            cycle_count=MESSY_CYCLE_COUNT,
            status_counts={"ok": MESSY_CYCLE_COUNT},
            fault_code_counts={},
            confidence_counts={},
        ),
    )


def _messy_intermittent_faults() -> ValidationDataset:
    random = Random(209)
    fault_indices = {17, 41, 88, 149, 203}

    def profile(index: int) -> dict[str, Any]:
        borderline_fault = index in fault_indices
        return _normal_profile(index) | {
            "product_detect_ms": 85 + random.randint(-20, 30),
            "tamp_extend_ms": 535 + random.randint(-60, 90),
            "index_transfer_ms": 780 + random.randint(-80, 130),
            "tamp_return_ms": (960 + random.randint(-30, 25)) if borderline_fault else 640 + random.randint(-70, 145),
            "operator_intervention": index in {40, 41, 87, 148, 149},
            "timestamp_noise_ms": random.randint(-22, 22),
        }

    return ValidationDataset(
        name="messy_intermittent_faults",
        description="Sparse borderline tamp-return faults mixed with operator intervention and noise.",
        events=_build_events("messy_intermittent_faults", profile, cycle_count=MESSY_CYCLE_COUNT),
        expected=ExpectedOutcome(
            cycle_count=MESSY_CYCLE_COUNT,
            status_counts={"ok": MESSY_CYCLE_COUNT - len(fault_indices), "warning": len(fault_indices)},
            fault_code_counts={"slow_tamp_return": len(fault_indices)},
            confidence_counts={"low": len(fault_indices)},
        ),
    )


def _messy_partial_borderline_faults() -> ValidationDataset:
    random = Random(310)
    fault_indices = {42, 119, 177}
    expected_fault_count = 4

    def profile(index: int) -> dict[str, Any]:
        partial_fault = index in fault_indices
        return _normal_profile(index) | {
            "product_detect_ms": 95 + random.randint(-25, 45),
            "tamp_extend_ms": (708 + random.randint(0, 10)) if partial_fault else 540 + random.randint(-80, 145),
            "index_transfer_ms": 790 + random.randint(-95, 170),
            "tamp_return_ms": 650 + random.randint(-90, 165),
            "speed_profile": "slow" if index % 37 in (5, 6, 7) else "normal",
            "operator_intervention": index % 71 == 0,
            "timestamp_noise_ms": random.randint(-20, 20),
        }

    return ValidationDataset(
        name="messy_partial_borderline_faults",
        description="A few weak tamp-extend excursions just over threshold in otherwise noisy cycles.",
        events=_build_events("messy_partial_borderline_faults", profile, cycle_count=MESSY_CYCLE_COUNT),
        expected=ExpectedOutcome(
            cycle_count=MESSY_CYCLE_COUNT,
            status_counts={"ok": MESSY_CYCLE_COUNT - expected_fault_count, "warning": expected_fault_count},
            fault_code_counts={"delayed_tamp_extend": expected_fault_count},
            confidence_counts={"low": expected_fault_count},
        ),
    )


def _messy_overlapping_symptoms() -> ValidationDataset:
    random = Random(411)
    extend_fault_indices = set(range(70, 82)) | {132, 133}
    return_fault_indices = set(range(74, 86))
    warning_cycles = extend_fault_indices | return_fault_indices

    def profile(index: int) -> dict[str, Any]:
        return _normal_profile(index) | {
            "product_detect_ms": 88 + random.randint(-20, 50),
            "tamp_extend_ms": (760 + random.randint(-15, 35)) if index in extend_fault_indices else 530 + random.randint(-70, 130),
            "index_transfer_ms": 795 + random.randint(-85, 145),
            "tamp_return_ms": (945 + random.randint(-8, 35)) if index in return_fault_indices else 645 + random.randint(-80, 150),
            "speed_profile": "fast" if 68 <= index <= 90 else "normal",
            "operator_intervention": index in {73, 74, 82, 83},
            "timestamp_noise_ms": random.randint(-18, 18),
        }

    return ValidationDataset(
        name="messy_overlapping_symptoms",
        description="Overlapping tamp extend and return symptoms around speed changes and interventions.",
        events=_build_events("messy_overlapping_symptoms", profile, cycle_count=MESSY_CYCLE_COUNT),
        expected=ExpectedOutcome(
            cycle_count=MESSY_CYCLE_COUNT,
            status_counts={"ok": MESSY_CYCLE_COUNT - len(warning_cycles), "warning": len(warning_cycles)},
            fault_code_counts={
                "delayed_tamp_extend": len(extend_fault_indices),
                "slow_tamp_return": len(return_fault_indices),
            },
            confidence_counts={
                "high": len(return_fault_indices),
                "medium": len(extend_fault_indices),
            },
        ),
    )


def _messy_gradual_drift() -> ValidationDataset:
    random = Random(512)

    def profile(index: int) -> dict[str, Any]:
        drift_ms = 760 + max(0, index - 120) * 4
        return _normal_profile(index) | {
            "product_detect_ms": 90 + random.randint(-20, 35),
            "tamp_extend_ms": 530 + random.randint(-70, 120),
            "index_transfer_ms": drift_ms + random.randint(-18, 18),
            "tamp_return_ms": 645 + random.randint(-70, 140),
            "speed_profile": "fast" if index >= 120 else "normal",
            "operator_intervention": index in {151, 178, 211},
            "timestamp_noise_ms": random.randint(-12, 12),
        }

    fault_count = 46
    return ValidationDataset(
        name="messy_gradual_drift",
        description="Hundreds-cycle speed-dependent drift with weak early signals becoming sustained.",
        events=_build_events("messy_gradual_drift", profile, cycle_count=MESSY_CYCLE_COUNT),
        expected=ExpectedOutcome(
            cycle_count=MESSY_CYCLE_COUNT,
            status_counts={"ok": MESSY_CYCLE_COUNT - fault_count, "warning": fault_count},
            fault_code_counts={"speed_dependent_drift": fault_count},
            confidence_counts={"high": fault_count},
        ),
    )


def _build_events(
    dataset_name: str,
    profile_for_index: Any,
    *,
    cycle_count: int = CYCLE_COUNT,
) -> tuple[Event, ...]:
    events: list[Event] = []
    for index in range(cycle_count):
        events.extend(_cycle_events(dataset_name, index, profile_for_index(index)))
    return tuple(events)


def _cycle_events(dataset_name: str, index: int, profile: dict[str, Any]) -> tuple[Event, ...]:
    cycle_id = f"{dataset_name}-cycle-{index:03d}"
    unit_id = f"{dataset_name}-unit-{index:03d}"
    base_ms = 1_710_000_000_000 + index * 10_000
    speed_profile = str(profile.get("speed_profile", "normal"))
    timestamp_noise_ms = int(profile.get("timestamp_noise_ms", 0))

    if profile.get("skipped_cycle", False):
        return (
            _event(dataset_name, index, "cycle-start", base_ms, "cycle_start", cycle_id, unit_id),
            _event(
                dataset_name,
                index,
                "planned-cycle-skip",
                base_ms + 180 + timestamp_noise_ms,
                "operator_intervention",
                cycle_id,
                unit_id,
                payload={"reason": "planned_cycle_skip", "speed_profile": speed_profile},
            ),
            _event(dataset_name, index, "cycle-end", base_ms + 360, "cycle_end", cycle_id, unit_id),
        )

    product_start = base_ms + 100 + timestamp_noise_ms
    product_end = product_start + int(profile["product_detect_ms"]) - timestamp_noise_ms
    extend_start = base_ms + 350 - timestamp_noise_ms
    extend_end = extend_start + int(profile["tamp_extend_ms"]) + timestamp_noise_ms
    transfer_start = extend_end + 120
    transfer_end = transfer_start + int(profile["index_transfer_ms"]) - timestamp_noise_ms
    return_start = transfer_end + 120
    return_end = return_start + int(profile["tamp_return_ms"]) + timestamp_noise_ms
    cycle_end = return_end + 120

    events = [
        _event(dataset_name, index, "cycle-start", base_ms, "cycle_start", cycle_id, unit_id),
        _operation_event(
            dataset_name,
            index,
            "product-detect-start",
            product_start,
            "operation_start",
            cycle_id,
            unit_id,
            "product_detect",
            speed_profile,
        ),
    ]
    if not profile.get("missing_product_detect_end", False):
        events.append(
            _operation_event(
                dataset_name,
                index,
                "product-detect-end",
                product_end,
                "operation_end",
                cycle_id,
                unit_id,
                "product_detect",
                speed_profile,
            )
        )
    events.extend(
        [
            _operation_event(
                dataset_name,
                index,
                "tamp-extend-start",
                extend_start,
                "operation_start",
                cycle_id,
                unit_id,
                "tamp_extend",
                speed_profile,
            ),
            _operation_event(
                dataset_name,
                index,
                "tamp-extend-end",
                extend_end,
                "operation_end",
                cycle_id,
                unit_id,
                "tamp_extend",
                speed_profile,
            ),
            _operation_event(
                dataset_name,
                index,
                "index-transfer-start",
                transfer_start,
                "operation_start",
                cycle_id,
                unit_id,
                "index_transfer",
                speed_profile,
            ),
            _operation_event(
                dataset_name,
                index,
                "index-transfer-end",
                transfer_end,
                "operation_end",
                cycle_id,
                unit_id,
                "index_transfer",
                speed_profile,
            ),
            _operation_event(
                dataset_name,
                index,
                "tamp-return-start",
                return_start,
                "operation_start",
                cycle_id,
                unit_id,
                "tamp_return",
                speed_profile,
            ),
            _operation_event(
                dataset_name,
                index,
                "tamp-return-end",
                return_end,
                "operation_end",
                cycle_id,
                unit_id,
                "tamp_return",
                speed_profile,
            ),
            _event(dataset_name, index, "cycle-end", cycle_end, "cycle_end", cycle_id, unit_id),
        ]
    )
    if profile.get("operator_intervention", False):
        events.insert(
            -1,
            _event(
                dataset_name,
                index,
                "operator-intervention",
                transfer_end + 60,
                "operator_intervention",
                cycle_id,
                unit_id,
                payload={"reason": "manual_observation", "speed_profile": speed_profile},
            ),
        )
    return tuple(events)


def _normal_profile(index: int) -> dict[str, Any]:
    del index
    return {
        "product_detect_ms": 80,
        "tamp_extend_ms": 520,
        "index_transfer_ms": 760,
        "tamp_return_ms": 620,
        "speed_profile": "normal",
    }


def _operation_relationship(operation: str, *, threshold_ms: int) -> EventRelationship:
    return EventRelationship(
        name="operation_duration",
        start_event_type="operation_start",
        end_event_type="operation_end",
        threshold_ms=threshold_ms,
        match_payload_keys=("operation",),
        label_payload_key="operation",
        payload_equals=(("operation", operation),),
    )


def _operation_event(
    dataset_name: str,
    cycle_index: int,
    event_name: str,
    timestamp_ms: int,
    event_type: str,
    cycle_id: str,
    unit_id: str,
    operation: str,
    speed_profile: str,
) -> Event:
    return _event(
        dataset_name,
        cycle_index,
        event_name,
        timestamp_ms,
        event_type,
        cycle_id,
        unit_id,
        payload={"operation": operation, "speed_profile": speed_profile},
    )


def _event(
    dataset_name: str,
    cycle_index: int,
    event_name: str,
    timestamp_ms: int,
    event_type: str,
    cycle_id: str,
    unit_id: str,
    payload: dict[str, Any] | None = None,
) -> Event:
    return Event(
        id=f"{dataset_name}-c{cycle_index:03d}-{event_name}",
        timestamp_ms=timestamp_ms,
        event_type=event_type,
        station_id=STATION_ID,
        line_id=LINE_ID,
        cycle_id=cycle_id,
        unit_id=unit_id,
        payload=payload or {},
    )


def _count_matching(predicate: Any, *, cycle_count: int = CYCLE_COUNT) -> int:
    return sum(1 for index in range(cycle_count) if predicate(index))


def _mismatches(expected: dict[str, Any], actual: dict[str, Any]) -> list[str]:
    messages: list[str] = []
    for key in expected:
        if expected[key] != actual[key]:
            messages.append(f"{key}: expected {expected[key]!r}, got {actual[key]!r}")
    return messages


def _interesting_samples(results: tuple[AnalysisResult, ...]) -> list[AnalysisResult]:
    faulted_or_warning = [result for result in results if result.findings]
    if faulted_or_warning:
        return faulted_or_warning[:2]
    return list(results[:1])


def _to_stable_json_line(value: dict[str, Any]) -> str:
    import json

    return json.dumps(value, sort_keys=True)
