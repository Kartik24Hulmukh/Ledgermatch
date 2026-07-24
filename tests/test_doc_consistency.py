"""Documentation-consistency tests.

Verifies that pilot documentation does not contradict the validator
implementation. Specifically:

- PILOT_PROTOCOL.md must not list evidence_validation or
  review_ledger_validation as a real-row qualification condition.
- Documented minimum sample requirements must match the constants in
  scripts/verify_pilot_result.py.
- Old v1.0 field names must not appear in PILOT_PROTOCOL.md.
"""

import os
import re
import unittest

DOCS_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "docs",
)
PROTOCOL_PATH = os.path.join(DOCS_DIR, "PILOT_PROTOCOL.md")


class TestDocConsistency(unittest.TestCase):

    def _read_protocol(self):
        with open(PROTOCOL_PATH, encoding="utf-8") as f:
            return f.read()

    def test_protocol_does_not_list_validation_as_real_row_qualifier(self):
        """PILOT_PROTOCOL.md must not list evidence_validation or
        review_ledger_validation as a condition for a row to qualify
        as real practitioner evidence."""
        text = self._read_protocol()
        # Find the Counting Rules section
        counting_start = text.find("## Counting Rules")
        counting_end = text.find("##", counting_start + 1)
        if counting_start == -1:
            self.fail("Counting Rules section not found in PILOT_PROTOCOL.md")
        if counting_end == -1:
            counting_end = len(text)
        counting_section = text[counting_start:counting_end]
        # Check that evidence_validation and review_ledger_validation
        # are NOT listed as qualification conditions
        self.assertNotIn(
            "evidence_validation",
            counting_section,
            "PILOT_PROTOCOL.md Counting Rules still lists evidence_validation "
            "as a real-row qualification condition — contradicts Defect 20 fix",
        )
        self.assertNotIn(
            "review_ledger_validation",
            counting_section,
            "PILOT_PROTOCOL.md Counting Rules still lists review_ledger_validation "
            "as a real-row qualification condition — contradicts Defect 20 fix",
        )

    def test_documented_minimums_match_validator_constants(self):
        """The minimums documented in PILOT_PROTOCOL.md must match the
        constants in scripts/verify_pilot_result.py."""
        # Import the constants
        import sys
        sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
        from scripts.verify_pilot_result import (
            MIN_PRACTITIONERS,
            MIN_HISTORICAL_CASES,
            MIN_AMBIGUOUS_CASES,
            MIN_INPUT_LAYOUTS,
            MIN_CURRENCIES,
            MIN_AMBIGUOUS_CONTRIBUTORS,
            MAX_SINGLE_PRACTITIONER_SHARE,
        )

        text = self._read_protocol()

        # Check each documented minimum matches the constant
        # Practitioners: 5
        self.assertIn(f"| Practitioners | {MIN_PRACTITIONERS} |", text)
        # Historical cases: 30
        self.assertIn(f"| Historical cases | {MIN_HISTORICAL_CASES} |", text)
        # Genuine ambiguous cases: 10
        self.assertIn(f"| Genuine ambiguous cases | {MIN_AMBIGUOUS_CASES} |", text)
        # Input layouts: 3
        self.assertIn(f"| Input layouts | {MIN_INPUT_LAYOUTS} |", text)
        # Currencies: 2
        self.assertIn(f"| Currencies | {MIN_CURRENCIES} |", text)
        # Distinct practitioners contributing ambiguous cases: 3
        self.assertIn(
            f"| Distinct practitioners contributing ambiguous cases | {MIN_AMBIGUOUS_CONTRIBUTORS} |",
            text,
        )
        # Maximum share: 0.5
        self.assertIn(
            f"| Maximum share of real cases from any single practitioner | {MAX_SINGLE_PRACTITIONER_SHARE} |",
            text,
        )

    def test_old_field_names_absent_from_protocol(self):
        """Old v1.0 field names must not appear in PILOT_PROTOCOL.md."""
        text = self._read_protocol()
        old_fields = [
            "payment_or_contribution_signal",
            "repeat_use_requested",
            "review_minutes_before",
        ]
        for field in old_fields:
            self.assertNotIn(
                field,
                text,
                f"PILOT_PROTOCOL.md still references old field '{field}'",
            )


if __name__ == "__main__":
    unittest.main()
