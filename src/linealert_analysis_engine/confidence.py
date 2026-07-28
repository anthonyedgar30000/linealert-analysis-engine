"""Aggregate confidence scoring for deterministic findings."""

from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import replace
from statistics import median
from typing import Any

from .models import AnalysisResult, Finding


class ConfidenceScorer:
    """Assign low/medium/high confidence using dataset-level evidence.

    Scores combine:
    - evidence consistency: how dense repeated findings are inside their span
    - repeated occurrence: how often the same fault appears
    - relationship strength: how far timing evidence is beyond threshold
    - duration of abnormal behavior: how much of the analyzed window is covered
    """

    def score(self, results: tuple[AnalysisResult, ...]) -> tuple[AnalysisResult, ...]:
        if not results:
            return ()

        positions = {result.cycle_id: index for index, result in enumerate(results)}
        stats = _fault_stats(results, positions)
        scored: list[AnalysisResult] = []
        for result in results:
            findings = tuple(
                replace(
                    finding,
                    confidence=_confidence_for(
                        finding,
                        stats[finding.fault_code],
                        total_cycles=len(results),
                    ),
                    details=_details_with_confidence_inputs(
                        finding.details,
                        stats[finding.fault_code],
                        total_cycles=len(results),
                    ),
                )
                for finding in result.findings
            )
            scored.append(replace(result, findings=findings))
        return tuple(scored)


def _fault_stats(
    results: tuple[AnalysisResult, ...],
    positions: dict[str, int],
) -> dict[str, dict[str, Any]]:
    cycle_positions: dict[str, list[int]] = defaultdict(list)
    strengths: dict[str, list[float]] = defaultdict(list)
    for result in results:
        seen_faults: set[str] = set()
        for finding in result.findings:
            seen_faults.add(finding.fault_code)
            strengths[finding.fault_code].append(_relationship_strength(finding))
        for fault_code in seen_faults:
            cycle_positions[fault_code].append(positions[result.cycle_id])

    stats: dict[str, dict[str, Any]] = {}
    for fault_code, fault_positions in cycle_positions.items():
        span = max(fault_positions) - min(fault_positions) + 1
        count = len(fault_positions)
        stats[fault_code] = {
            "occurrence_count": count,
            "span_cycles": span,
            "evidence_consistency": count / span if span else 0.0,
            "median_relationship_strength": median(strengths[fault_code]),
        }
    return stats


def _confidence_for(finding: Finding, stats: dict[str, Any], *, total_cycles: int) -> str:
    count = int(stats["occurrence_count"])
    consistency = float(stats["evidence_consistency"])
    strength = float(stats["median_relationship_strength"])
    duration_ratio = float(stats["span_cycles"]) / total_cycles

    score = 0
    if count >= 10:
        score += 2
    elif count >= 3:
        score += 1

    if count >= 3 and consistency >= 0.75:
        score += 2
    elif count >= 3 and consistency >= 0.45:
        score += 1

    if strength >= 0.25:
        score += 2
    elif strength >= 0.05:
        score += 1

    if consistency >= 0.25 and duration_ratio >= 0.60:
        score += 2
    elif consistency >= 0.25 and duration_ratio >= 0.25:
        score += 1

    if finding.severity == "error":
        score += 1

    if score >= 5:
        return "high"
    if score >= 3:
        return "medium"
    return "low"


def _relationship_strength(finding: Finding) -> float:
    duration_ms = finding.details.get("duration_ms")
    threshold_ms = finding.details.get("threshold_ms")
    if isinstance(duration_ms, (int, float)) and isinstance(threshold_ms, (int, float)) and threshold_ms:
        return max(0.0, (float(duration_ms) - float(threshold_ms)) / float(threshold_ms))
    if finding.rule_id == "operation_end_missing":
        return 1.0
    if finding.rule_id == "explicit_fault_event":
        return 0.75
    return 0.0


def _details_with_confidence_inputs(
    details: Any,
    stats: dict[str, Any],
    *,
    total_cycles: int,
) -> dict[str, Any]:
    enriched = dict(details)
    enriched["confidence_inputs"] = {
        "occurrence_count": stats["occurrence_count"],
        "total_cycles": total_cycles,
        "span_cycles": stats["span_cycles"],
        "evidence_consistency": round(stats["evidence_consistency"], 3),
        "median_relationship_strength": round(stats["median_relationship_strength"], 3),
    }
    return enriched
