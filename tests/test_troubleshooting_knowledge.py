import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from linealert_analysis_engine.troubleshooting import (  # noqa: E402
    TroubleshootingKnowledgeError,
    load_troubleshooting_knowledge,
    troubleshooting_knowledge_from_dict,
    troubleshooting_knowledge_to_dict,
)


ROOT = Path(__file__).resolve().parents[1]


class TroubleshootingKnowledgeTests(unittest.TestCase):
    def test_loads_placeholder_json_knowledge_base(self) -> None:
        kb = load_troubleshooting_knowledge(ROOT / "examples" / "troubleshooting_placeholder.json")

        self.assertEqual(kb.schema_version, 1)
        self.assertTrue(kb.is_placeholder)
        self.assertEqual(len(kb.entries), 1)
        entry = kb.entries[0]
        self.assertTrue(entry.is_placeholder)
        self.assertEqual(entry.related_fault_code, "PLACEHOLDER_RELATED_LINEALERT_FAULT_CODE")
        self.assertTrue(entry.possible_causes[0].startswith("PLACEHOLDER:"))
        self.assertEqual(entry.confidence_adjustment_rules[0].adjustment, "PLACEHOLDER: increase | decrease | no_change")

    def test_loads_placeholder_yaml_template(self) -> None:
        kb = load_troubleshooting_knowledge(ROOT / "examples" / "troubleshooting_template.yaml")

        self.assertTrue(kb.is_placeholder)
        self.assertEqual(kb.entries[0].id, "placeholder_entry_001")
        self.assertIn("PLACEHOLDER", kb.entries[0].notes_from_expert)

    def test_round_trips_to_dict(self) -> None:
        kb = load_troubleshooting_knowledge(ROOT / "examples" / "troubleshooting_placeholder.json")

        as_dict = troubleshooting_knowledge_to_dict(kb)

        self.assertEqual(as_dict["schema_version"], 1)
        self.assertEqual(as_dict["entries"][0]["id"], "placeholder_entry_001")
        self.assertEqual(
            as_dict["entries"][0]["confidence_adjustment_rules"][0]["condition"],
            "PLACEHOLDER: deterministic condition using evidence fields",
        )

    def test_entries_can_be_found_by_related_fault_code(self) -> None:
        kb = load_troubleshooting_knowledge(ROOT / "examples" / "troubleshooting_placeholder.json")

        matches = kb.entries_for_fault_code("PLACEHOLDER_RELATED_LINEALERT_FAULT_CODE")

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0].id, "placeholder_entry_001")

    def test_missing_required_field_fails_validation(self) -> None:
        data = {
            "schema_version": 1,
            "source": "test",
            "entries": [
                {
                    "id": "bad_entry",
                    "symptom_category": "placeholder",
                }
            ],
        }

        with self.assertRaisesRegex(TroubleshootingKnowledgeError, "missing required fields"):
            troubleshooting_knowledge_from_dict(data)

    def test_empty_lists_fail_validation(self) -> None:
        data = {
            "schema_version": 1,
            "source": "test",
            "entries": [
                {
                    "id": "bad_entry",
                    "symptom_category": "placeholder",
                    "observed_operator_symptom": "placeholder",
                    "related_fault_code": "placeholder",
                    "possible_causes": [],
                    "distinguishing_questions": ["placeholder"],
                    "machine_signals_to_check": ["placeholder"],
                    "timing_relationships_to_check": ["placeholder"],
                    "recommended_checks": ["placeholder"],
                    "recommended_fixes": ["placeholder"],
                    "escalation_condition": "placeholder",
                    "notes_from_expert": "placeholder",
                    "confidence_adjustment_rules": [
                        {
                            "condition": "placeholder",
                            "adjustment": "no_change",
                            "rationale": "placeholder",
                        }
                    ],
                }
            ],
        }

        with self.assertRaisesRegex(TroubleshootingKnowledgeError, "possible_causes"):
            troubleshooting_knowledge_from_dict(data)

    def test_unsupported_extension_fails(self) -> None:
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "knowledge.txt"
            path.write_text("{}", encoding="utf-8")

            with self.assertRaisesRegex(TroubleshootingKnowledgeError, "Unsupported"):
                load_troubleshooting_knowledge(path)


if __name__ == "__main__":
    unittest.main()
