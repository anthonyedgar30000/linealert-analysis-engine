"""Application service that wires ingestion, reconstruction, and analysis."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from .confidence import ConfidenceScorer
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
        confidence_scorer: ConfidenceScorer | None = None,
    ) -> None:
        self.store = store
        self.reconstructor = reconstructor or CycleReconstructor()
        self.timing_analyzer = timing_analyzer or TimingAnalyzer()
        self.rule_engine = rule_engine or RuleEngine()
        self.confidence_scorer = confidence_scorer or ConfidenceScorer()

    def ingest_event(self, event: Event | Mapping[str, Any]) -> None:
        self.store.ingest_event(_coerce_event(event))

    def ingest_events(self, events: Iterable[Event | Mapping[str, Any]]) -> None:
        self.store.ingest_events(_coerce_event(event) for event in events)

    def reconstruct_cycles(self) -> tuple[ReconstructedCycle, ...]:
        cycles = self.reconstructor.reconstruct(self.store.list_events())
        self.store.upsert_cycles(cycles)
        return cycles

    def analyze_cycle(self, cycle: ReconstructedCycle) -> AnalysisResult:
        result = self.confidence_scorer.score((self._evaluate_cycle(cycle),))[0]
        self.store.save_analysis(result)
        return result

    def analyze_cycles(self, cycles: Iterable[ReconstructedCycle]) -> tuple[AnalysisResult, ...]:
        results = tuple(self._evaluate_cycle(cycle) for cycle in cycles)
        scored_results = self.confidence_scorer.score(results)
        for result in scored_results:
            self.store.save_analysis(result)
        return scored_results

    def analyze_all(self) -> tuple[AnalysisResult, ...]:
        return self.analyze_cycles(self.reconstruct_cycles())

    def _evaluate_cycle(self, cycle: ReconstructedCycle) -> AnalysisResult:
        timing = self.timing_analyzer.analyze(cycle)
        return self.rule_engine.evaluate(cycle, timing)


def _coerce_event(event: Event | Mapping[str, Any]) -> Event:
    if isinstance(event, Event):
        return event
    return event_from_dict(event)
