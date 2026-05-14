"""Hardcoded, explainable fault mapping rules for Phase 1."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .models import AnalysisResult, Event, Finding, ReconstructedCycle, TimingAnalysis


@dataclass(frozen=True, slots=True)
class RuleContext:
    cycle: ReconstructedCycle
    timing: TimingAnalysis


class Rule(Protocol):
    id: str

    def evaluate(self, context: RuleContext) -> tuple[Finding, ...]:
        ...


@dataclass(frozen=True, slots=True)
class OperationDurationExceededRule:
    id: str = "operation_duration_exceeded"
    severity: str = "warning"

    def evaluate(self, context: RuleContext) -> tuple[Finding, ...]:
        findings: list[Finding] = []
        for measurement in context.timing.measurements:
            if measurement.relationship != "operation_duration" or not measurement.exceeded_threshold:
                continue
            findings.append(
                Finding(
                    rule_id=self.id,
                    severity=self.severity,
                    fault_code="slow_operation",
                    explanation=(
                        f"Operation {measurement.label} took {measurement.duration_ms} ms, "
                        f"exceeding the {measurement.threshold_ms} ms threshold."
                    ),
                    evidence_event_ids=(measurement.start_event_id, measurement.end_event_id or ""),
                    details={
                        "operation": measurement.label,
                        "duration_ms": measurement.duration_ms,
                        "threshold_ms": measurement.threshold_ms,
                        "relationship": measurement.relationship,
                    },
                )
            )
        return tuple(findings)


@dataclass(frozen=True, slots=True)
class MissingOperationEndRule:
    id: str = "operation_end_missing"
    severity: str = "error"

    def evaluate(self, context: RuleContext) -> tuple[Finding, ...]:
        findings: list[Finding] = []
        for measurement in context.timing.measurements:
            if measurement.relationship != "operation_duration" or not measurement.is_missing_end:
                continue
            findings.append(
                Finding(
                    rule_id=self.id,
                    severity=self.severity,
                    fault_code="missing_operation_end",
                    explanation=(
                        f"Operation {measurement.label} started but no matching operation_end "
                        "event was observed in this cycle."
                    ),
                    evidence_event_ids=(measurement.start_event_id,),
                    details={
                        "operation": measurement.label,
                        "started_at_ms": measurement.started_at_ms,
                        "relationship": measurement.relationship,
                    },
                )
            )
        return tuple(findings)


@dataclass(frozen=True, slots=True)
class CycleDurationExceededRule:
    threshold_ms: int = 15_000
    id: str = "cycle_duration_exceeded"
    severity: str = "warning"

    def evaluate(self, context: RuleContext) -> tuple[Finding, ...]:
        duration_ms = context.cycle.duration_ms
        if duration_ms is None or duration_ms <= self.threshold_ms:
            return ()

        event_ids = (
            context.cycle.events[0].id,
            context.cycle.events[-1].id,
        )
        return (
            Finding(
                rule_id=self.id,
                severity=self.severity,
                fault_code="slow_cycle",
                explanation=(
                    f"Cycle duration was {duration_ms} ms, exceeding the "
                    f"{self.threshold_ms} ms threshold."
                ),
                evidence_event_ids=event_ids,
                details={
                    "duration_ms": duration_ms,
                    "threshold_ms": self.threshold_ms,
                },
            ),
        )


@dataclass(frozen=True, slots=True)
class ExplicitFaultEventRule:
    id: str = "explicit_fault_event"
    severity: str = "error"

    def evaluate(self, context: RuleContext) -> tuple[Finding, ...]:
        findings: list[Finding] = []
        for event in context.cycle.events:
            if event.event_type != "fault":
                continue
            fault_code = str(event.payload.get("fault_code", "explicit_fault"))
            findings.append(
                Finding(
                    rule_id=self.id,
                    severity=self.severity,
                    fault_code=fault_code,
                    explanation=(
                        f"Fault event {event.id} reported code {fault_code} at "
                        f"{event.timestamp_ms} ms."
                    ),
                    evidence_event_ids=(event.id,),
                    details={
                        "reported_fault_code": fault_code,
                        "message": event.payload.get("message"),
                    },
                )
            )
        return tuple(findings)


class RuleEngine:
    """Applies deterministic rules and returns a serializable result."""

    def __init__(self, rules: tuple[Rule, ...] | None = None) -> None:
        self.rules = rules or default_rules()

    def evaluate(self, cycle: ReconstructedCycle, timing: TimingAnalysis) -> AnalysisResult:
        context = RuleContext(cycle=cycle, timing=timing)
        findings: list[Finding] = []
        for rule in self.rules:
            findings.extend(rule.evaluate(context))

        return AnalysisResult(
            cycle_id=cycle.id,
            status=_analysis_status(cycle, findings),
            summary=_summary(cycle),
            findings=tuple(findings),
        )


def default_rules() -> tuple[Rule, ...]:
    return (
        OperationDurationExceededRule(),
        MissingOperationEndRule(),
        CycleDurationExceededRule(),
        ExplicitFaultEventRule(),
    )


def _analysis_status(cycle: ReconstructedCycle, findings: list[Finding]) -> str:
    if cycle.status == "faulted" or any(finding.severity == "error" for finding in findings):
        return "faulted"
    if cycle.status == "incomplete":
        return "incomplete"
    if findings:
        return "warning"
    return "ok"


def _summary(cycle: ReconstructedCycle) -> dict[str, object]:
    return {
        "line_id": cycle.line_id,
        "station_id": cycle.station_id,
        "unit_id": cycle.unit_id,
        "started_at_ms": cycle.started_at_ms,
        "ended_at_ms": cycle.ended_at_ms,
        "duration_ms": cycle.duration_ms,
        "event_count": cycle.event_count,
        "cycle_status": cycle.status,
    }
