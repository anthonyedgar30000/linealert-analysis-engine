"""Cycle reconstruction from deterministic event streams."""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

from .models import Event, ReconstructedCycle


@dataclass(slots=True)
class _CycleBuilder:
    id: str
    line_id: str
    station_id: str
    unit_id: str | None
    started_at_ms: int
    events: list[Event] = field(default_factory=list)
    ended_at_ms: int | None = None
    has_fault: bool = False
    forced_status: str | None = None

    def add(self, event: Event) -> None:
        self.events.append(event)
        if event.event_type == "cycle_end":
            self.ended_at_ms = event.timestamp_ms
        if event.event_type == "fault":
            self.has_fault = True
        if self.unit_id is None and event.unit_id is not None:
            self.unit_id = event.unit_id

    def close(self, forced_status: str | None = None) -> ReconstructedCycle:
        status = forced_status or self.forced_status or self._derive_status()
        ordered_events = tuple(sorted(self.events, key=lambda e: (e.timestamp_ms, e.id)))
        return ReconstructedCycle(
            id=self.id,
            line_id=self.line_id,
            station_id=self.station_id,
            unit_id=self.unit_id,
            started_at_ms=self.started_at_ms,
            ended_at_ms=self.ended_at_ms,
            status=status,
            events=ordered_events,
        )

    def _derive_status(self) -> str:
        if self.has_fault:
            return "faulted"
        if self.ended_at_ms is None:
            return "incomplete"
        return "completed"


class CycleReconstructor:
    """Build cycles from explicit IDs or start/end event boundaries."""

    def reconstruct(self, events: tuple[Event, ...] | list[Event]) -> tuple[ReconstructedCycle, ...]:
        ordered_events = sorted(events, key=lambda event: (event.timestamp_ms, event.id))

        explicit_builders: dict[str, _CycleBuilder] = {}
        active_implicit: dict[tuple[str, str], _CycleBuilder] = {}
        closed_implicit: list[ReconstructedCycle] = []

        for event in ordered_events:
            if event.cycle_id:
                builder = explicit_builders.get(event.cycle_id)
                if builder is None:
                    builder = _CycleBuilder(
                        id=event.cycle_id,
                        line_id=event.line_id,
                        station_id=event.station_id,
                        unit_id=event.unit_id,
                        started_at_ms=event.timestamp_ms,
                    )
                    explicit_builders[event.cycle_id] = builder
                builder.add(event)
                continue

            key = (event.line_id, event.station_id)
            if event.event_type == "cycle_start":
                existing = active_implicit.pop(key, None)
                if existing is not None:
                    closed_implicit.append(existing.close(forced_status="incomplete"))

                builder = _CycleBuilder(
                    id=_implicit_cycle_id(event),
                    line_id=event.line_id,
                    station_id=event.station_id,
                    unit_id=event.unit_id,
                    started_at_ms=event.timestamp_ms,
                )
                builder.add(event)
                active_implicit[key] = builder
                continue

            builder = active_implicit.get(key)
            if builder is None:
                builder = _CycleBuilder(
                    id=_orphan_cycle_id(event),
                    line_id=event.line_id,
                    station_id=event.station_id,
                    unit_id=event.unit_id,
                    started_at_ms=event.timestamp_ms,
                    forced_status="incomplete",
                )
                active_implicit[key] = builder

            builder.add(event)
            if event.event_type == "cycle_end":
                closed_implicit.append(builder.close())
                active_implicit.pop(key, None)

        cycles = [
            *closed_implicit,
            *(builder.close() for builder in active_implicit.values()),
            *(builder.close() for builder in explicit_builders.values()),
        ]
        return tuple(sorted(cycles, key=lambda cycle: (cycle.started_at_ms, cycle.id)))


def _implicit_cycle_id(event: Event) -> str:
    return "reconstructed-" + _stable_digest(
        event.line_id,
        event.station_id,
        str(event.timestamp_ms),
        event.id,
    )


def _orphan_cycle_id(event: Event) -> str:
    return "orphan-" + _stable_digest(
        event.line_id,
        event.station_id,
        str(event.timestamp_ms),
        event.id,
    )


def _stable_digest(*parts: str) -> str:
    raw = "|".join(parts).encode("utf-8")
    return hashlib.sha1(raw).hexdigest()[:12]
