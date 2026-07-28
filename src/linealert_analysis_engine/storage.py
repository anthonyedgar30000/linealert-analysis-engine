"""SQLite persistence for events, reconstructed cycles, and analyses."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any, Iterable

from .models import AnalysisResult, Event, Finding, ReconstructedCycle


SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS events (
    id TEXT PRIMARY KEY,
    timestamp_ms INTEGER NOT NULL,
    event_type TEXT NOT NULL,
    station_id TEXT NOT NULL,
    line_id TEXT NOT NULL,
    cycle_id TEXT,
    unit_id TEXT,
    payload_json TEXT NOT NULL,
    ingested_at_ms INTEGER NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_events_order
    ON events (timestamp_ms, id);

CREATE INDEX IF NOT EXISTS idx_events_cycle_id
    ON events (cycle_id);

CREATE INDEX IF NOT EXISTS idx_events_line_station
    ON events (line_id, station_id, timestamp_ms);

CREATE TABLE IF NOT EXISTS cycles (
    id TEXT PRIMARY KEY,
    line_id TEXT NOT NULL,
    station_id TEXT NOT NULL,
    unit_id TEXT,
    started_at_ms INTEGER NOT NULL,
    ended_at_ms INTEGER,
    status TEXT NOT NULL,
    event_count INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS analysis_results (
    id TEXT PRIMARY KEY,
    cycle_id TEXT NOT NULL,
    created_at_ms INTEGER NOT NULL,
    status TEXT NOT NULL,
    summary_json TEXT NOT NULL,
    findings_json TEXT NOT NULL,
    FOREIGN KEY (cycle_id) REFERENCES cycles(id)
);
"""


class SQLiteStore:
    """Small repository wrapper around SQLite.

    The class intentionally exposes explicit methods instead of hiding SQL
    behind a large ORM so tests can inspect behavior and schema directly.
    """

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)
        self.connection = sqlite3.connect(self.path)
        self.connection.row_factory = sqlite3.Row
        self.init_schema()

    def close(self) -> None:
        self.connection.close()

    def init_schema(self) -> None:
        self.connection.executescript(SCHEMA_SQL)
        self.connection.commit()

    def ingest_event(self, event: Event, *, ingested_at_ms: int | None = None) -> None:
        ingested_at_ms = ingested_at_ms if ingested_at_ms is not None else _now_ms()
        self.connection.execute(
            """
            INSERT INTO events (
                id, timestamp_ms, event_type, station_id, line_id, cycle_id,
                unit_id, payload_json, ingested_at_ms
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                timestamp_ms = excluded.timestamp_ms,
                event_type = excluded.event_type,
                station_id = excluded.station_id,
                line_id = excluded.line_id,
                cycle_id = excluded.cycle_id,
                unit_id = excluded.unit_id,
                payload_json = excluded.payload_json,
                ingested_at_ms = excluded.ingested_at_ms
            """,
            (
                event.id,
                event.timestamp_ms,
                event.event_type,
                event.station_id,
                event.line_id,
                event.cycle_id,
                event.unit_id,
                json.dumps(dict(event.payload), sort_keys=True),
                ingested_at_ms,
            ),
        )
        self.connection.commit()

    def ingest_events(self, events: Iterable[Event]) -> None:
        with self.connection:
            for event in events:
                self.connection.execute(
                    """
                    INSERT INTO events (
                        id, timestamp_ms, event_type, station_id, line_id,
                        cycle_id, unit_id, payload_json, ingested_at_ms
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        timestamp_ms = excluded.timestamp_ms,
                        event_type = excluded.event_type,
                        station_id = excluded.station_id,
                        line_id = excluded.line_id,
                        cycle_id = excluded.cycle_id,
                        unit_id = excluded.unit_id,
                        payload_json = excluded.payload_json,
                        ingested_at_ms = excluded.ingested_at_ms
                    """,
                    (
                        event.id,
                        event.timestamp_ms,
                        event.event_type,
                        event.station_id,
                        event.line_id,
                        event.cycle_id,
                        event.unit_id,
                        json.dumps(dict(event.payload), sort_keys=True),
                        _now_ms(),
                    ),
                )

    def list_events(self) -> tuple[Event, ...]:
        rows = self.connection.execute(
            """
            SELECT id, timestamp_ms, event_type, station_id, line_id, cycle_id,
                   unit_id, payload_json
            FROM events
            ORDER BY timestamp_ms ASC, id ASC
            """
        ).fetchall()
        return tuple(_event_from_row(row) for row in rows)

    def upsert_cycle(self, cycle: ReconstructedCycle) -> None:
        self.connection.execute(
            """
            INSERT INTO cycles (
                id, line_id, station_id, unit_id, started_at_ms, ended_at_ms,
                status, event_count
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                line_id = excluded.line_id,
                station_id = excluded.station_id,
                unit_id = excluded.unit_id,
                started_at_ms = excluded.started_at_ms,
                ended_at_ms = excluded.ended_at_ms,
                status = excluded.status,
                event_count = excluded.event_count
            """,
            (
                cycle.id,
                cycle.line_id,
                cycle.station_id,
                cycle.unit_id,
                cycle.started_at_ms,
                cycle.ended_at_ms,
                cycle.status,
                cycle.event_count,
            ),
        )
        self.connection.commit()

    def upsert_cycles(self, cycles: Iterable[ReconstructedCycle]) -> None:
        with self.connection:
            for cycle in cycles:
                self.connection.execute(
                    """
                    INSERT INTO cycles (
                        id, line_id, station_id, unit_id, started_at_ms,
                        ended_at_ms, status, event_count
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        line_id = excluded.line_id,
                        station_id = excluded.station_id,
                        unit_id = excluded.unit_id,
                        started_at_ms = excluded.started_at_ms,
                        ended_at_ms = excluded.ended_at_ms,
                        status = excluded.status,
                        event_count = excluded.event_count
                    """,
                    (
                        cycle.id,
                        cycle.line_id,
                        cycle.station_id,
                        cycle.unit_id,
                        cycle.started_at_ms,
                        cycle.ended_at_ms,
                        cycle.status,
                        cycle.event_count,
                    ),
                )

    def save_analysis(self, result: AnalysisResult, *, created_at_ms: int | None = None) -> None:
        created_at_ms = created_at_ms if created_at_ms is not None else _now_ms()
        self.connection.execute(
            """
            INSERT INTO analysis_results (
                id, cycle_id, created_at_ms, status, summary_json, findings_json
            ) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                created_at_ms = excluded.created_at_ms,
                status = excluded.status,
                summary_json = excluded.summary_json,
                findings_json = excluded.findings_json
            """,
            (
                f"{result.cycle_id}:{created_at_ms}",
                result.cycle_id,
                created_at_ms,
                result.status,
                json.dumps(dict(result.summary), sort_keys=True),
                json.dumps([_finding_to_dict(finding) for finding in result.findings], sort_keys=True),
            ),
        )
        self.connection.commit()


def _event_from_row(row: sqlite3.Row) -> Event:
    payload: dict[str, Any] = json.loads(row["payload_json"])
    return Event(
        id=row["id"],
        timestamp_ms=row["timestamp_ms"],
        event_type=row["event_type"],
        station_id=row["station_id"],
        line_id=row["line_id"],
        cycle_id=row["cycle_id"],
        unit_id=row["unit_id"],
        payload=payload,
    )


def _finding_to_dict(finding: Finding) -> dict[str, Any]:
    return {
        "rule_id": finding.rule_id,
        "severity": finding.severity,
        "fault_code": finding.fault_code,
        "confidence": finding.confidence,
        "explanation": finding.explanation,
        "evidence_event_ids": list(finding.evidence_event_ids),
        "details": dict(finding.details),
    }


def _now_ms() -> int:
    return int(time.time() * 1000)
