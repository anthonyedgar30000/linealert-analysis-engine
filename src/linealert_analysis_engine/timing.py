"""Deterministic timing analysis built from reusable event relationships."""

from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass
from typing import Deque, Iterable

from .models import Event, ReconstructedCycle, TimingAnalysis, TimingMeasurement


@dataclass(frozen=True, slots=True)
class EventRelationship:
    """Defines one measurable start/end relationship.

    Adding a new timing check should usually mean registering another
    relationship here, not changing the analyzer loop.
    """

    name: str
    start_event_type: str
    end_event_type: str
    threshold_ms: int
    match_payload_keys: tuple[str, ...] = ()
    label_payload_key: str | None = None
    default_label: str = "default"

    def match_key(self, event: Event) -> tuple[object, ...]:
        return tuple(event.payload.get(key) for key in self.match_payload_keys)

    def label_for(self, event: Event) -> str:
        if self.label_payload_key is None:
            return self.default_label
        return str(event.payload.get(self.label_payload_key, self.default_label))


class TimingAnalyzer:
    """Extract timing measurements from ordered cycle events."""

    def __init__(self, relationships: Iterable[EventRelationship] | None = None) -> None:
        self.relationships = tuple(relationships or default_relationships())

    def analyze(self, cycle: ReconstructedCycle) -> TimingAnalysis:
        ordered_events = sorted(cycle.events, key=lambda event: (event.timestamp_ms, event.id))
        open_starts: dict[tuple[str, tuple[object, ...]], Deque[Event]] = defaultdict(deque)
        measurements: list[TimingMeasurement] = []

        relationships_by_start = defaultdict(list)
        relationships_by_end = defaultdict(list)
        for relationship in self.relationships:
            relationships_by_start[relationship.start_event_type].append(relationship)
            relationships_by_end[relationship.end_event_type].append(relationship)

        for event in ordered_events:
            for relationship in relationships_by_start[event.event_type]:
                open_starts[(relationship.name, relationship.match_key(event))].append(event)

            for relationship in relationships_by_end[event.event_type]:
                key = (relationship.name, relationship.match_key(event))
                starts = open_starts[key]
                if not starts:
                    continue

                start_event = starts.popleft()
                measurements.append(
                    TimingMeasurement(
                        relationship=relationship.name,
                        label=relationship.label_for(start_event),
                        start_event_id=start_event.id,
                        end_event_id=event.id,
                        started_at_ms=start_event.timestamp_ms,
                        ended_at_ms=event.timestamp_ms,
                        duration_ms=event.timestamp_ms - start_event.timestamp_ms,
                        threshold_ms=relationship.threshold_ms,
                    )
                )

        for relationship in self.relationships:
            for (name, _match_key), starts in open_starts.items():
                if name != relationship.name:
                    continue
                for start_event in starts:
                    measurements.append(
                        TimingMeasurement(
                            relationship=relationship.name,
                            label=relationship.label_for(start_event),
                            start_event_id=start_event.id,
                            end_event_id=None,
                            started_at_ms=start_event.timestamp_ms,
                            ended_at_ms=None,
                            duration_ms=None,
                            threshold_ms=relationship.threshold_ms,
                        )
                    )

        return TimingAnalysis(measurements=tuple(measurements))


def default_relationships() -> tuple[EventRelationship, ...]:
    return (
        EventRelationship(
            name="operation_duration",
            start_event_type="operation_start",
            end_event_type="operation_end",
            threshold_ms=5_000,
            match_payload_keys=("operation",),
            label_payload_key="operation",
        ),
    )
