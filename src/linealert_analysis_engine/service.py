"""Application service that wires ingestion, reconstruction, and analysis."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .models import AnalysisResult, Event, ReconstructedCycle
from .reconstruction import CycleReconstructor
from .rules import RuleEngine
from .serialization import event_from_dict
from .storage import SQLiteStore
from .timing import TimingAnalyzer


class AnalysisService:
    """Small backend facade used by scripts and future API handlers."""

    def __init__(
        self,
        store: SQLiteStore,
        *,
        reconstructor: CycleReconstructor | None = None,
        timing_analyzer: TimingAnalyzer | None = None,
        rule_engine: RuleEngine | None = None,
    ) -> None:
        self.store = store
        self.reconstructor = reconstructor or CycleReconstructor()
        self.timing_analyzer = timing_analyzer or TimingAnalyzer()
        self.rule_engine = rule_engine or RuleEngine()

    def ingest_event(self, event: Event | Mapping[str, Any]) -> None:
        self.store.ingest_event(_coerce_event(event))

    def ingest_events(self, events: Iterable[Event | Mapping[str, Any]]) -> None:
        self.store.ingest_events(_coerce_event(event) for event in events)

    def reconstruct_cycles(self) -> tuple[ReconstructedCycle, ...]:
        cycles = self.reconstructor.reconstruct(self.store.list_events())
        self.store.upsert_cycles(cycles)
        return cycles

    def analyze_cycle(self, cycle: ReconstructedCycle) -> AnalysisResult:
        timing = self.timing_analyzer.analyze(cycle)
        result = self.rule_engine.evaluate(cycle, timing)
        self.store.save_analysis(result)
        return result

    def analyze_all(self) -> tuple[AnalysisResult, ...]:
        return tuple(self.analyze_cycle(cycle) for cycle in self.reconstruct_cycles())


def _coerce_event(event: Event | Mapping[str, Any]) -> Event:
    if isinstance(event, Event):
        return event
    return event_from_dict(event)
