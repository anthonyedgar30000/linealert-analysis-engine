"""Structured troubleshooting knowledge base models and loaders.

This module is intentionally schema-oriented. It does not encode Peter's real
decision tree; it provides a stable format for loading that knowledge later.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping


REQUIRED_ENTRY_FIELDS = (
    "symptom_category",
    "observed_operator_symptom",
    "related_fault_code",
    "possible_causes",
    "distinguishing_questions",
    "machine_signals_to_check",
    "timing_relationships_to_check",
    "recommended_checks",
    "recommended_fixes",
    "escalation_condition",
    "notes_from_expert",
    "confidence_adjustment_rules",
)


@dataclass(frozen=True, slots=True)
class ConfidenceAdjustmentRule:
    """Deterministic confidence adjustment metadata from expert knowledge."""

    condition: str
    adjustment: str
    rationale: str


@dataclass(frozen=True, slots=True)
class TroubleshootingEntry:
    """One structured troubleshooting node/path entry."""

    id: str
    symptom_category: str
    observed_operator_symptom: str
    related_fault_code: str
    possible_causes: tuple[str, ...]
    distinguishing_questions: tuple[str, ...]
    machine_signals_to_check: tuple[str, ...]
    timing_relationships_to_check: tuple[str, ...]
    recommended_checks: tuple[str, ...]
    recommended_fixes: tuple[str, ...]
    escalation_condition: str
    notes_from_expert: str
    confidence_adjustment_rules: tuple[ConfidenceAdjustmentRule, ...]
    is_placeholder: bool = False


@dataclass(frozen=True, slots=True)
class TroubleshootingKnowledgeBase:
    """Loaded troubleshooting entries plus source metadata."""

    schema_version: int
    source: str
    entries: tuple[TroubleshootingEntry, ...]
    is_placeholder: bool = False

    def entries_for_fault_code(self, fault_code: str) -> tuple[TroubleshootingEntry, ...]:
        return tuple(entry for entry in self.entries if entry.related_fault_code == fault_code)


class TroubleshootingKnowledgeError(ValueError):
    """Raised when a troubleshooting knowledge file is structurally invalid."""


def load_troubleshooting_knowledge(path: str | Path) -> TroubleshootingKnowledgeBase:
    """Load troubleshooting knowledge from JSON, YAML, or YML."""

    path = Path(path)
    suffix = path.suffix.lower()
    raw = path.read_text(encoding="utf-8")
    if suffix == ".json":
        data = json.loads(raw)
    elif suffix in {".yaml", ".yml"}:
        data = _load_yaml(raw)
    else:
        raise TroubleshootingKnowledgeError(
            f"Unsupported troubleshooting knowledge extension {path.suffix!r}; use .json, .yaml, or .yml."
        )
    return troubleshooting_knowledge_from_dict(data)


def troubleshooting_knowledge_from_dict(data: Mapping[str, Any]) -> TroubleshootingKnowledgeBase:
    if not isinstance(data, Mapping):
        raise TroubleshootingKnowledgeError("Knowledge base root must be an object.")

    schema_version = data.get("schema_version")
    if not isinstance(schema_version, int):
        raise TroubleshootingKnowledgeError("schema_version must be an integer.")

    source = data.get("source")
    if not isinstance(source, str) or not source:
        raise TroubleshootingKnowledgeError("source must be a non-empty string.")

    entries_data = data.get("entries")
    if not isinstance(entries_data, list):
        raise TroubleshootingKnowledgeError("entries must be a list.")

    entries = tuple(_entry_from_dict(entry_data, index) for index, entry_data in enumerate(entries_data))
    if not entries:
        raise TroubleshootingKnowledgeError("entries must contain at least one troubleshooting entry.")

    return TroubleshootingKnowledgeBase(
        schema_version=schema_version,
        source=source,
        entries=entries,
        is_placeholder=bool(data.get("is_placeholder", False)),
    )


def troubleshooting_knowledge_to_dict(kb: TroubleshootingKnowledgeBase) -> dict[str, Any]:
    return {
        "schema_version": kb.schema_version,
        "source": kb.source,
        "is_placeholder": kb.is_placeholder,
        "entries": [_entry_to_dict(entry) for entry in kb.entries],
    }


def _entry_from_dict(data: Any, index: int) -> TroubleshootingEntry:
    if not isinstance(data, Mapping):
        raise TroubleshootingKnowledgeError(f"Entry {index} must be an object.")

    missing = [field for field in REQUIRED_ENTRY_FIELDS if field not in data]
    if missing:
        raise TroubleshootingKnowledgeError(f"Entry {index} missing required fields: {', '.join(missing)}.")

    entry_id = data.get("id", f"entry_{index:03d}")
    if not isinstance(entry_id, str) or not entry_id:
        raise TroubleshootingKnowledgeError(f"Entry {index} id must be a non-empty string.")

    return TroubleshootingEntry(
        id=entry_id,
        symptom_category=_required_string(data, "symptom_category", index),
        observed_operator_symptom=_required_string(data, "observed_operator_symptom", index),
        related_fault_code=_required_string(data, "related_fault_code", index),
        possible_causes=_required_string_tuple(data, "possible_causes", index),
        distinguishing_questions=_required_string_tuple(data, "distinguishing_questions", index),
        machine_signals_to_check=_required_string_tuple(data, "machine_signals_to_check", index),
        timing_relationships_to_check=_required_string_tuple(data, "timing_relationships_to_check", index),
        recommended_checks=_required_string_tuple(data, "recommended_checks", index),
        recommended_fixes=_required_string_tuple(data, "recommended_fixes", index),
        escalation_condition=_required_string(data, "escalation_condition", index),
        notes_from_expert=_required_string(data, "notes_from_expert", index),
        confidence_adjustment_rules=tuple(
            _confidence_adjustment_rule_from_dict(rule, index)
            for rule in _required_list(data, "confidence_adjustment_rules", index)
        ),
        is_placeholder=bool(data.get("is_placeholder", False)),
    )


def _confidence_adjustment_rule_from_dict(data: Any, entry_index: int) -> ConfidenceAdjustmentRule:
    if not isinstance(data, Mapping):
        raise TroubleshootingKnowledgeError(
            f"Entry {entry_index} confidence_adjustment_rules items must be objects."
        )
    return ConfidenceAdjustmentRule(
        condition=_required_string(data, "condition", entry_index),
        adjustment=_required_string(data, "adjustment", entry_index),
        rationale=_required_string(data, "rationale", entry_index),
    )


def _entry_to_dict(entry: TroubleshootingEntry) -> dict[str, Any]:
    return {
        "id": entry.id,
        "is_placeholder": entry.is_placeholder,
        "symptom_category": entry.symptom_category,
        "observed_operator_symptom": entry.observed_operator_symptom,
        "related_fault_code": entry.related_fault_code,
        "possible_causes": list(entry.possible_causes),
        "distinguishing_questions": list(entry.distinguishing_questions),
        "machine_signals_to_check": list(entry.machine_signals_to_check),
        "timing_relationships_to_check": list(entry.timing_relationships_to_check),
        "recommended_checks": list(entry.recommended_checks),
        "recommended_fixes": list(entry.recommended_fixes),
        "escalation_condition": entry.escalation_condition,
        "notes_from_expert": entry.notes_from_expert,
        "confidence_adjustment_rules": [
            {
                "condition": rule.condition,
                "adjustment": rule.adjustment,
                "rationale": rule.rationale,
            }
            for rule in entry.confidence_adjustment_rules
        ],
    }


def _required_string(data: Mapping[str, Any], key: str, entry_index: int) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise TroubleshootingKnowledgeError(f"Entry {entry_index} field {key} must be a non-empty string.")
    return value


def _required_string_tuple(data: Mapping[str, Any], key: str, entry_index: int) -> tuple[str, ...]:
    values = _required_list(data, key, entry_index)
    if not all(isinstance(value, str) and value for value in values):
        raise TroubleshootingKnowledgeError(
            f"Entry {entry_index} field {key} must contain only non-empty strings."
        )
    return tuple(values)


def _required_list(data: Mapping[str, Any], key: str, entry_index: int) -> list[Any]:
    value = data.get(key)
    if not isinstance(value, list) or not value:
        raise TroubleshootingKnowledgeError(f"Entry {entry_index} field {key} must be a non-empty list.")
    return value


def _load_yaml(raw: str) -> Any:
    """Load YAML with PyYAML when present, otherwise a small dependency-free subset."""

    try:
        import yaml  # type: ignore[import-not-found]
    except ModuleNotFoundError:
        return _parse_simple_yaml(raw)
    return yaml.safe_load(raw)


def _parse_simple_yaml(raw: str) -> Any:
    lines = [
        (len(line) - len(line.lstrip(" ")), line.strip())
        for line in raw.splitlines()
        if line.strip() and not line.strip().startswith("#")
    ]
    if not lines:
        raise TroubleshootingKnowledgeError("YAML file is empty.")
    parsed, next_index = _parse_yaml_block(lines, 0, lines[0][0])
    if next_index != len(lines):
        raise TroubleshootingKnowledgeError("YAML parser stopped before consuming the full file.")
    return parsed


def _parse_yaml_block(
    lines: list[tuple[int, str]],
    index: int,
    indent: int,
) -> tuple[Any, int]:
    if index >= len(lines):
        return {}, index
    current_indent, text = lines[index]
    if current_indent < indent:
        return {}, index
    if text.startswith("- "):
        return _parse_yaml_list(lines, index, current_indent)
    return _parse_yaml_dict(lines, index, current_indent)


def _parse_yaml_dict(
    lines: list[tuple[int, str]],
    index: int,
    indent: int,
) -> tuple[dict[str, Any], int]:
    result: dict[str, Any] = {}
    while index < len(lines):
        current_indent, text = lines[index]
        if current_indent < indent:
            break
        if current_indent > indent:
            raise TroubleshootingKnowledgeError(f"Unexpected YAML indentation at line content {text!r}.")
        if text.startswith("- "):
            break
        key, value = _split_yaml_key_value(text)
        if value == "":
            child, index = _parse_yaml_block(lines, index + 1, indent + 2)
            result[key] = child
        else:
            result[key] = _parse_yaml_scalar(value)
            index += 1
    return result, index


def _parse_yaml_list(
    lines: list[tuple[int, str]],
    index: int,
    indent: int,
) -> tuple[list[Any], int]:
    result: list[Any] = []
    while index < len(lines):
        current_indent, text = lines[index]
        if current_indent < indent:
            break
        if current_indent != indent or not text.startswith("- "):
            break

        item_text = text[2:].strip()
        if item_text == "":
            child, index = _parse_yaml_block(lines, index + 1, indent + 2)
            result.append(child)
            continue

        if ":" in item_text:
            key, value = _split_yaml_key_value(item_text)
            item: dict[str, Any] = {key: _parse_yaml_scalar(value)} if value else {}
            index += 1
            if index < len(lines) and lines[index][0] > indent:
                child, index = _parse_yaml_block(lines, index, indent + 2)
                if not isinstance(child, Mapping):
                    raise TroubleshootingKnowledgeError("YAML list item continuation must be a mapping.")
                item.update(child)
            result.append(item)
            continue

        result.append(_parse_yaml_scalar(item_text))
        index += 1
    return result, index


def _split_yaml_key_value(text: str) -> tuple[str, str]:
    if ":" not in text:
        raise TroubleshootingKnowledgeError(f"Expected YAML key/value pair, got {text!r}.")
    key, value = text.split(":", 1)
    key = key.strip()
    if not key:
        raise TroubleshootingKnowledgeError(f"YAML key cannot be empty in {text!r}.")
    return key, value.strip()


def _parse_yaml_scalar(value: str) -> Any:
    if value in {"[]", "{}"}:
        return [] if value == "[]" else {}
    lowered = value.lower()
    if lowered == "true":
        return True
    if lowered == "false":
        return False
    if lowered == "null":
        return None
    if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
        return value[1:-1]
    try:
        return int(value)
    except ValueError:
        return value
