"""Deterministic timeline reconstruction and incident narratives."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass
from statistics import mean
from typing import Any, Iterable

from .models import AnalysisResult, Event, Finding, ReconstructedCycle, TimingMeasurement
from .timing import TimingAnalyzer


@dataclass(frozen=True, slots=True)
class CycleTimeline:
    cycle_id: str
    cycle_index: int
    status: str
    entries: tuple[dict[str, Any], ...]
    findings: tuple[dict[str, Any], ...]
    narrative: str


@dataclass(frozen=True, slots=True)
class AbnormalSpan:
    fault_code: str
    behavior_pattern: str
    start_cycle_index: int
    end_cycle_index: int
    cycle_ids: tuple[str, ...]
    occurrence_count: int
    confidence_counts: dict[str, int]


@dataclass(frozen=True, slots=True)
class IncidentNarrative:
    fault_code: str
    confidence: str
    behavior_pattern: str
    summary: str
    reason: str
    why_confidence: str
    abnormal_span: dict[str, Any]
    relationship_history: dict[str, Any]
    drift_progression: tuple[dict[str, Any], ...]
    evidence_event_ids: tuple[str, ...]
    cycle_timelines: tuple[dict[str, Any], ...]


class TimelineReconstructor:
    """Build evidence-linked operational explanations without generative AI."""

    def __init__(self, timing_analyzer: TimingAnalyzer | None = None) -> None:
        self.timing_analyzer = timing_analyzer or TimingAnalyzer()

    def build_cycle_timeline(
        self,
        cycle: ReconstructedCycle,
        result: AnalysisResult,
        *,
        cycle_index: int = 0,
    ) -> CycleTimeline:
        measurements = self.timing_analyzer.analyze(cycle).measurements
        entries = tuple(_timeline_entries(cycle, measurements, result.findings))
        finding_dicts = tuple(_finding_summary(finding) for finding in result.findings)
        narrative = _cycle_narrative(cycle_index, entries, result.findings)
        return CycleTimeline(
            cycle_id=cycle.id,
            cycle_index=cycle_index,
            status=result.status,
            entries=entries,
            findings=finding_dicts,
            narrative=narrative,
        )

    def build_incident_narratives(
        self,
        cycles: tuple[ReconstructedCycle, ...],
        results: tuple[AnalysisResult, ...],
    ) -> tuple[IncidentNarrative, ...]:
        result_by_cycle = {result.cycle_id: result for result in results}
        ordered_cycles = tuple(sorted(cycles, key=lambda cycle: (cycle.started_at_ms, cycle.id)))
        cycle_positions = {cycle.id: index for index, cycle in enumerate(ordered_cycles)}
        timelines = {
            cycle.id: self.build_cycle_timeline(
                cycle,
                result_by_cycle[cycle.id],
                cycle_index=cycle_positions[cycle.id],
            )
            for cycle in ordered_cycles
            if cycle.id in result_by_cycle
        }
        measurements_by_cycle = {
            cycle.id: self.timing_analyzer.analyze(cycle).measurements
            for cycle in ordered_cycles
        }

        findings_by_fault: dict[str, list[tuple[int, AnalysisResult, Finding]]] = defaultdict(list)
        for result in results:
            for finding in result.findings:
                findings_by_fault[finding.fault_code].append(
                    (cycle_positions[result.cycle_id], result, finding)
                )

        narratives = [
            self._incident_for_fault(
                fault_code,
                fault_findings,
                timelines,
                measurements_by_cycle,
                ordered_cycles,
            )
            for fault_code, fault_findings in sorted(findings_by_fault.items())
        ]
        return tuple(narratives)

    def _incident_for_fault(
        self,
        fault_code: str,
        fault_findings: list[tuple[int, AnalysisResult, Finding]],
        timelines: dict[str, CycleTimeline],
        measurements_by_cycle: dict[str, tuple[TimingMeasurement, ...]],
        ordered_cycles: tuple[ReconstructedCycle, ...],
    ) -> IncidentNarrative:
        fault_findings = sorted(fault_findings, key=lambda item: (item[0], item[1].cycle_id))
        cycle_indices = tuple(item[0] for item in fault_findings)
        cycle_ids = tuple(item[1].cycle_id for item in fault_findings)
        findings = tuple(item[2] for item in fault_findings)
        representative = findings[0]
        operation = str(representative.details.get("operation", fault_code))
        behavior_pattern = _behavior_pattern(cycle_indices, total_cycles=len(ordered_cycles))
        confidence = _dominant_confidence(findings)
        span = AbnormalSpan(
            fault_code=fault_code,
            behavior_pattern=behavior_pattern,
            start_cycle_index=min(cycle_indices),
            end_cycle_index=max(cycle_indices),
            cycle_ids=cycle_ids,
            occurrence_count=len(cycle_ids),
            confidence_counts=dict(sorted(Counter(finding.confidence for finding in findings).items())),
        )
        history = _relationship_history(operation, measurements_by_cycle)
        drift_progression = tuple(_rolling_progression(operation, measurements_by_cycle, ordered_cycles))
        evidence_ids = tuple(
            dict.fromkeys(event_id for finding in findings for event_id in finding.evidence_event_ids)
        )
        sample_timelines = tuple(
            _cycle_timeline_to_dict(timelines[cycle_id])
            for cycle_id in cycle_ids[:3]
            if cycle_id in timelines
        )
        return IncidentNarrative(
            fault_code=fault_code,
            confidence=confidence,
            behavior_pattern=behavior_pattern,
            summary=_incident_summary(fault_code, operation, span),
            reason=_incident_reason(representative),
            why_confidence=_why_confidence(representative, span),
            abnormal_span=_abnormal_span_to_dict(span),
            relationship_history=history,
            drift_progression=drift_progression,
            evidence_event_ids=evidence_ids,
            cycle_timelines=sample_timelines,
        )


def cycle_timeline_to_dict(timeline: CycleTimeline) -> dict[str, Any]:
    return _cycle_timeline_to_dict(timeline)


def incident_narrative_to_dict(narrative: IncidentNarrative) -> dict[str, Any]:
    return {
        "fault_code": narrative.fault_code,
        "confidence": narrative.confidence,
        "behavior_pattern": narrative.behavior_pattern,
        "summary": narrative.summary,
        "reason": narrative.reason,
        "why_confidence": narrative.why_confidence,
        "abnormal_span": narrative.abnormal_span,
        "relationship_history": narrative.relationship_history,
        "drift_progression": list(narrative.drift_progression),
        "evidence_event_ids": list(narrative.evidence_event_ids),
        "cycle_timelines": list(narrative.cycle_timelines),
    }


def _timeline_entries(
    cycle: ReconstructedCycle,
    measurements: Iterable[TimingMeasurement],
    findings: tuple[Finding, ...],
) -> list[dict[str, Any]]:
    finding_by_start = {
        event_id: finding
        for finding in findings
        for event_id in finding.evidence_event_ids[:1]
    }
    event_by_id = {event.id: event for event in cycle.events}
    entries: list[dict[str, Any]] = []
    for measurement in sorted(measurements, key=lambda item: (item.started_at_ms, item.label)):
        finding = finding_by_start.get(measurement.start_event_id)
        status = "missing" if measurement.is_missing_end else "warning" if finding else "ok"
        entries.append(
            {
                "label": measurement.label,
                "start_event_id": measurement.start_event_id,
                "end_event_id": measurement.end_event_id,
                "start_offset_ms": measurement.started_at_ms - cycle.started_at_ms,
                "duration_ms": measurement.duration_ms,
                "threshold_ms": measurement.threshold_ms,
                "status": status,
                "finding_fault_code": finding.fault_code if finding else None,
                "evidence_event_ids": [
                    event_id
                    for event_id in (measurement.start_event_id, measurement.end_event_id)
                    if event_id is not None and event_id in event_by_id
                ],
            }
        )
    for event in sorted(cycle.events, key=lambda item: (item.timestamp_ms, item.id)):
        if event.event_type in {"operator_intervention", "fault"}:
            entries.append(
                {
                    "label": event.event_type,
                    "event_id": event.id,
                    "start_offset_ms": event.timestamp_ms - cycle.started_at_ms,
                    "duration_ms": None,
                    "threshold_ms": None,
                    "status": "annotation" if event.event_type == "operator_intervention" else "warning",
                    "payload": dict(event.payload),
                    "evidence_event_ids": [event.id],
                }
            )
    return sorted(entries, key=lambda item: (item["start_offset_ms"], item["label"]))


def _finding_summary(finding: Finding) -> dict[str, Any]:
    return {
        "fault_code": finding.fault_code,
        "severity": finding.severity,
        "confidence": finding.confidence,
        "reason": finding.explanation,
        "evidence_event_ids": list(finding.evidence_event_ids),
        "details": dict(finding.details),
    }


def _cycle_narrative(
    cycle_index: int,
    entries: tuple[dict[str, Any], ...],
    findings: tuple[Finding, ...],
) -> str:
    labels = []
    for entry in entries:
        duration = entry.get("duration_ms")
        status = entry["status"]
        suffix = f" (+{duration}ms)" if duration is not None else ""
        if status in {"warning", "missing"}:
            suffix += f" {status.upper()}"
        labels.append(f"{entry['label']}{suffix}")
    if findings:
        fault_codes = ", ".join(finding.fault_code for finding in findings)
        return f"Cycle {cycle_index}: " + " -> ".join(labels) + f". Finding: {fault_codes}."
    return f"Cycle {cycle_index}: " + " -> ".join(labels) + ". No abnormal timing findings."


def _behavior_pattern(cycle_indices: tuple[int, ...], *, total_cycles: int) -> str:
    if len(cycle_indices) == 1:
        return "isolated"
    span = max(cycle_indices) - min(cycle_indices) + 1
    consistency = len(set(cycle_indices)) / span
    if len(cycle_indices) >= 10 and consistency >= 0.70:
        return "sustained"
    if span / total_cycles >= 0.25 or len(cycle_indices) >= 3:
        return "intermittent"
    return "isolated"


def _dominant_confidence(findings: tuple[Finding, ...]) -> str:
    counts = Counter(finding.confidence for finding in findings)
    order = {"high": 2, "medium": 1, "low": 0}
    return max(counts, key=lambda confidence: (counts[confidence], order.get(confidence, -1)))


def _relationship_history(
    operation: str,
    measurements_by_cycle: dict[str, tuple[TimingMeasurement, ...]],
) -> dict[str, Any]:
    durations = [
        measurement.duration_ms
        for measurements in measurements_by_cycle.values()
        for measurement in measurements
        if measurement.label == operation and measurement.duration_ms is not None
    ]
    thresholds = [
        measurement.threshold_ms
        for measurements in measurements_by_cycle.values()
        for measurement in measurements
        if measurement.label == operation
    ]
    if not durations:
        return {"operation": operation, "observed_count": 0}
    threshold = thresholds[0] if thresholds else None
    exceeded_count = sum(1 for duration in durations if threshold is not None and duration > threshold)
    return {
        "operation": operation,
        "observed_count": len(durations),
        "average_duration_ms": round(mean(durations), 2),
        "min_duration_ms": min(durations),
        "max_duration_ms": max(durations),
        "threshold_ms": threshold,
        "exceeded_count": exceeded_count,
    }


def _rolling_progression(
    operation: str,
    measurements_by_cycle: dict[str, tuple[TimingMeasurement, ...]],
    ordered_cycles: tuple[ReconstructedCycle, ...],
    *,
    window_size: int = 10,
) -> list[dict[str, Any]]:
    durations: list[tuple[int, int]] = []
    for index, cycle in enumerate(ordered_cycles):
        measurements = measurements_by_cycle.get(cycle.id, ())
        operation_durations = [
            measurement.duration_ms
            for measurement in measurements
            if measurement.label == operation and measurement.duration_ms is not None
        ]
        if operation_durations:
            durations.append((index, operation_durations[0]))
    if len(durations) < window_size:
        return [
            {"cycle_index": index, "average_duration_ms": duration}
            for index, duration in durations[:6]
        ]

    windows: list[dict[str, Any]] = []
    step = max(1, len(durations) // 6)
    start_offsets = list(range(0, len(durations) - window_size + 1, step))
    if start_offsets[-1] != len(durations) - window_size:
        start_offsets.append(len(durations) - window_size)
    for start in start_offsets[:7]:
        window = durations[start : start + window_size]
        windows.append(
            {
                "cycle_start_index": window[0][0],
                "cycle_end_index": window[-1][0],
                "average_duration_ms": round(mean(duration for _index, duration in window), 2),
            }
        )
    return windows


def _incident_summary(fault_code: str, operation: str, span: AbnormalSpan) -> str:
    operation_name = operation.replace("_", " ")
    return (
        f"{fault_code} affected {span.occurrence_count} cycle(s) from "
        f"{span.start_cycle_index} to {span.end_cycle_index}; behavior appears "
        f"{span.behavior_pattern} for {operation_name}."
    )


def _incident_reason(finding: Finding) -> str:
    details = finding.details
    duration = details.get("duration_ms")
    threshold = details.get("threshold_ms")
    if isinstance(duration, (int, float)) and isinstance(threshold, (int, float)):
        return (
            f"{finding.fault_code} matters because measured duration exceeded threshold "
            f"by {round(duration - threshold, 2)} ms."
        )
    return finding.explanation


def _why_confidence(finding: Finding, span: AbnormalSpan) -> str:
    inputs = dict(finding.details.get("confidence_inputs", {}))
    consistency = inputs.get("evidence_consistency")
    strength = inputs.get("median_relationship_strength")
    occurrence_count = inputs.get("occurrence_count", span.occurrence_count)
    pieces = [
        f"confidence is {finding.confidence}",
        f"{occurrence_count} abnormal occurrence(s)",
        f"span {span.start_cycle_index}-{span.end_cycle_index}",
    ]
    if consistency is not None:
        pieces.append(f"evidence consistency {consistency}")
    if strength is not None:
        pieces.append(f"median relationship strength {strength}")
    return "; ".join(pieces) + "."


def _abnormal_span_to_dict(span: AbnormalSpan) -> dict[str, Any]:
    return {
        "fault_code": span.fault_code,
        "behavior_pattern": span.behavior_pattern,
        "start_cycle_index": span.start_cycle_index,
        "end_cycle_index": span.end_cycle_index,
        "cycle_ids": list(span.cycle_ids),
        "occurrence_count": span.occurrence_count,
        "confidence_counts": span.confidence_counts,
    }


def _cycle_timeline_to_dict(timeline: CycleTimeline) -> dict[str, Any]:
    return {
        "cycle_id": timeline.cycle_id,
        "cycle_index": timeline.cycle_index,
        "status": timeline.status,
        "entries": list(timeline.entries),
        "findings": list(timeline.findings),
        "narrative": timeline.narrative,
    }
