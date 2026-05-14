"""JSON-friendly serialization helpers."""

from __future__ import annotations

from typing import Any, Mapping

from .models import AnalysisResult, Event, Finding


def event_from_dict(data: Mapping[str, Any]) -> Event:
    return Event(
        id=str(data["id"]),
        timestamp_ms=int(data["timestamp_ms"]),
        event_type=str(data["event_type"]),
        station_id=str(data["station_id"]),
        line_id=str(data["line_id"]),
        cycle_id=_optional_str(data.get("cycle_id")),
        unit_id=_optional_str(data.get("unit_id")),
        payload=dict(data.get("payload", {})),
    )


def event_to_dict(event: Event) -> dict[str, Any]:
    return {
        "id": event.id,
        "timestamp_ms": event.timestamp_ms,
        "event_type": event.event_type,
        "station_id": event.station_id,
        "line_id": event.line_id,
        "cycle_id": event.cycle_id,
        "unit_id": event.unit_id,
        "payload": dict(event.payload),
    }


def analysis_result_to_dict(result: AnalysisResult) -> dict[str, Any]:
    return {
        "cycle_id": result.cycle_id,
        "status": result.status,
        "summary": dict(result.summary),
        "findings": [_finding_to_dict(finding) for finding in result.findings],
    }


def _finding_to_dict(finding: Finding) -> dict[str, Any]:
    return {
        "rule_id": finding.rule_id,
        "severity": finding.severity,
        "fault_code": finding.fault_code,
        "explanation": finding.explanation,
        "evidence_event_ids": list(finding.evidence_event_ids),
        "details": dict(finding.details),
    }


def _optional_str(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)
