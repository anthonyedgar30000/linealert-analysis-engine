"""Domain models used by ingestion, reconstruction, and analysis."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping


Payload = Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class Event:
    """A deterministic, append-only production line event."""

    id: str
    timestamp_ms: int
    event_type: str
    station_id: str
    line_id: str
    cycle_id: str | None = None
    unit_id: str | None = None
    payload: Payload = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ReconstructedCycle:
    """A cycle reconstructed from ordered events."""

    id: str
    line_id: str
    station_id: str
    unit_id: str | None
    started_at_ms: int
    ended_at_ms: int | None
    status: str
    events: tuple[Event, ...]

    @property
    def event_count(self) -> int:
        return len(self.events)

    @property
    def duration_ms(self) -> int | None:
        if self.ended_at_ms is None:
            return None
        return self.ended_at_ms - self.started_at_ms


@dataclass(frozen=True, slots=True)
class TimingMeasurement:
    """Duration measured between a configured start/end relationship."""

    relationship: str
    label: str
    start_event_id: str
    end_event_id: str | None
    started_at_ms: int
    ended_at_ms: int | None
    duration_ms: int | None
    threshold_ms: int

    @property
    def is_missing_end(self) -> bool:
        return self.end_event_id is None

    @property
    def exceeded_threshold(self) -> bool:
        return self.duration_ms is not None and self.duration_ms > self.threshold_ms


@dataclass(frozen=True, slots=True)
class TimingAnalysis:
    """Raw timing facts extracted from a cycle before fault mapping."""

    measurements: tuple[TimingMeasurement, ...]


@dataclass(frozen=True, slots=True)
class Finding:
    """Explainable result emitted by a deterministic rule."""

    rule_id: str
    severity: str
    fault_code: str
    explanation: str
    evidence_event_ids: tuple[str, ...]
    details: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    """Serializable analysis output for one reconstructed cycle."""

    cycle_id: str
    status: str
    summary: Mapping[str, Any]
    findings: tuple[Finding, ...]
