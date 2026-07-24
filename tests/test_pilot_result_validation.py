"""Tests for the pilot result validator.

Tests cover:
- valid empty template
- valid completed rows
- missing columns
- malformed numbers
- malformed booleans
- duplicate IDs
- negative values
- privacy-pattern detection
- false-allocation kill gate
- insufficient sample reporting
- deterministic aggregate output
"""

import csv
import io
import json
import os
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.verify_pilot_result import validate_csv, REQUIRED_COLUMNS


def _write_csv(rows, columns=None):
    """Write a CSV file from a list of dicts and return the path."""
    if columns is None:
        columns = REQUIRED_COLUMNS
    fd, path = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def _valid_row(case_id="case_001", practitioner="prac_001"):
    return {
        "pilot_case_id": case_id,
        "practitioner_id": practitioner,
        "currency": "USD",
        "deposits_processed": "10",
        "accepted_matches": "8",
        "review_exceptions": "2",
        "false_automatic_allocations": "0",
        "correct_candidate_retained": "true",
        "review_minutes_before": "30",
        "review_minutes_with_ledgermatch": "15",
        "evidence_validation": "true",
        "review_ledger_validation": "true",
        "repeat_use_requested": "true",
        "recommendation": "recommend",
        "payment_or_contribution_signal": "would pay monthly",
        "notes": "case ran smoothly",
    }


class TestPilotResultValidation(unittest.TestCase):

    def setUp(self):
        self._temp_paths = []

    def tearDown(self):
        for p in self._temp_paths:
            try:
                os.unlink(p)
            except OSError:
                pass

    def _make(self, rows, columns=None):
        path = _write_csv(rows, columns)
        self._temp_paths.append(path)
        return path

    # --- Valid empty template ---

    def test_valid_empty_template(self):
        """Empty template (header only) should have no errors."""
        path = self._make([])
        result = validate_csv(path)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["row_count"], 0)
        self.assertEqual(result["continuation_gate"], "PASS")

    # --- Valid completed rows ---

    def test_valid_completed_rows(self):
        """A few valid rows should pass with correct aggregate."""
        rows = [
            _valid_row("case_001", "prac_001"),
            _valid_row("case_002", "prac_002"),
        ]
        path = self._make(rows)
        result = validate_csv(path)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["row_count"], 2)
        self.assertEqual(result["aggregate"]["total_cases"], 2)
        self.assertEqual(result["aggregate"]["unique_practitioners"], 2)
        self.assertEqual(result["continuation_gate"], "PASS")

    # --- Missing columns ---

    def test_missing_columns(self):
        """Missing required columns should produce an error."""
        rows = [_valid_row()]
        # Drop the 'currency' column
        cols = [c for c in REQUIRED_COLUMNS if c != "currency"]
        path = self._make(rows, columns=cols)
        result = validate_csv(path)
        self.assertTrue(any("Missing required columns" in e for e in result["errors"]))
        self.assertEqual(result["continuation_gate"], "FAIL")

    # --- Malformed numbers ---

    def test_malformed_number(self):
        """Non-integer in an integer column should error."""
        row = _valid_row()
        row["deposits_processed"] = "ten"
        path = self._make([row])
        result = validate_csv(path)
        self.assertTrue(any("malformed integer" in e.lower() for e in result["errors"]))

    # --- Malformed booleans ---

    def test_malformed_boolean(self):
        """Non-boolean in a boolean column should error."""
        row = _valid_row()
        row["evidence_validation"] = "maybe"
        path = self._make([row])
        result = validate_csv(path)
        self.assertTrue(any("malformed boolean" in e.lower() for e in result["errors"]))

    # --- Duplicate IDs ---

    def test_duplicate_ids(self):
        """Duplicate pilot_case_id should error."""
        rows = [
            _valid_row("case_001", "prac_001"),
            _valid_row("case_001", "prac_002"),
        ]
        path = self._make(rows)
        result = validate_csv(path)
        self.assertTrue(any("duplicate pilot_case_id" in e for e in result["errors"]))

    # --- Negative values ---

    def test_negative_values(self):
        """Negative integers should error."""
        row = _valid_row()
        row["review_minutes_before"] = "-5"
        path = self._make([row])
        result = validate_csv(path)
        self.assertTrue(any("negative value" in e.lower() for e in result["errors"]))

    # --- Privacy-pattern detection ---

    def test_email_in_notes_detected(self):
        """Email addresses in notes should be flagged."""
        row = _valid_row()
        row["notes"] = "contact john@example.com for details"
        path = self._make([row])
        result = validate_csv(path)
        self.assertTrue(any("email" in e.lower() for e in result["errors"]))

    def test_account_number_in_notes_detected(self):
        """Long digit sequences in notes should be flagged."""
        row = _valid_row()
        row["notes"] = "account 1234567890 was reconciled"
        path = self._make([row])
        result = validate_csv(path)
        self.assertTrue(any("account number" in e.lower() or "digit" in e.lower() for e in result["errors"]))

    def test_secret_pattern_in_notes_detected(self):
        """Secret patterns in notes should be flagged."""
        row = _valid_row()
        row["notes"] = "api_key=abc123secretkey"
        path = self._make([row])
        result = validate_csv(path)
        self.assertTrue(any("secret" in e.lower() for e in result["errors"]))

    def test_github_token_pattern_detected(self):
        """GitHub PAT pattern should be flagged."""
        row = _valid_row()
        row["payment_or_contribution_signal"] = "found token ghp_" + "a" * 36
        path = self._make([row])
        result = validate_csv(path)
        self.assertTrue(any("secret" in e.lower() for e in result["errors"]))

    # --- False-allocation kill gate ---

    def test_false_allocation_kill_gate(self):
        """Any false automatic allocation should fail the continuation gate."""
        row = _valid_row()
        row["false_automatic_allocations"] = "1"
        path = self._make([row])
        result = validate_csv(path)
        self.assertEqual(result["continuation_gate"], "FAIL")
        self.assertTrue(any("CONTINUATION GATE FAILED" in e for e in result["errors"]))
        self.assertTrue(any("false automatic" in e.lower() for e in result["errors"]))

    def test_zero_false_allocation_passes_gate(self):
        """Zero false automatic allocations should pass the continuation gate."""
        row = _valid_row()
        row["false_automatic_allocations"] = "0"
        path = self._make([row])
        result = validate_csv(path)
        self.assertEqual(result["continuation_gate"], "PASS")

    def test_evidence_validation_failure_fails_gate(self):
        """Evidence validation failure should fail the continuation gate."""
        row = _valid_row()
        row["evidence_validation"] = "false"
        path = self._make([row])
        result = validate_csv(path)
        self.assertEqual(result["continuation_gate"], "FAIL")
        self.assertTrue(any("evidence validation" in e.lower() for e in result["errors"]))

    def test_review_ledger_validation_failure_fails_gate(self):
        """Review-ledger validation failure should fail the continuation gate."""
        row = _valid_row()
        row["review_ledger_validation"] = "false"
        path = self._make([row])
        result = validate_csv(path)
        self.assertEqual(result["continuation_gate"], "FAIL")
        self.assertTrue(any("review-ledger" in e.lower() for e in result["errors"]))

    # --- Insufficient sample reporting ---

    def test_insufficient_sample_reporting(self):
        """Small dataset should report unmet minimum requirements."""
        rows = [_valid_row("case_001", "prac_001")]
        path = self._make(rows)
        result = validate_csv(path)
        sr = result["sample_requirements"]
        self.assertFalse(sr["min_practitioners"]["met"])
        self.assertFalse(sr["min_historical_cases"]["met"])
        self.assertFalse(sr["min_ambiguous_cases"]["met"])

    def test_sufficient_sample_reporting(self):
        """Large dataset should report met minimum requirements."""
        rows = []
        for i in range(35):
            row = _valid_row(f"case_{i:03d}", f"prac_{i % 6:03d}")
            row["currency"] = ["USD", "EUR", "GBP"][i % 3]
            row["review_exceptions"] = "1" if i < 12 else "0"
            rows.append(row)
        path = self._make(rows)
        result = validate_csv(path)
        sr = result["sample_requirements"]
        self.assertTrue(sr["min_practitioners"]["met"])
        self.assertTrue(sr["min_historical_cases"]["met"])
        self.assertTrue(sr["min_ambiguous_cases"]["met"])
        self.assertTrue(sr["min_input_layouts"]["met"])

    # --- Deterministic aggregate output ---

    def test_deterministic_aggregate_output(self):
        """Same input should produce identical aggregate output."""
        rows = [
            _valid_row("case_001", "prac_001"),
            _valid_row("case_002", "prac_002"),
        ]
        path1 = self._make(rows)
        path2 = self._make(rows)
        r1 = validate_csv(path1)
        r2 = validate_csv(path2)
        self.assertEqual(r1["aggregate"], r2["aggregate"])
        self.assertEqual(r1["continuation_gate"], r2["continuation_gate"])

    # --- Unsupported currency ---

    def test_unsupported_currency(self):
        """Unsupported currency code should error."""
        row = _valid_row()
        row["currency"] = "XYZ"
        path = self._make([row])
        result = validate_csv(path)
        self.assertTrue(any("unsupported currency" in e.lower() for e in result["errors"]))

    # --- Invalid recommendation ---

    def test_invalid_recommendation(self):
        """Invalid recommendation value should error."""
        row = _valid_row()
        row["recommendation"] = "maybe"
        path = self._make([row])
        result = validate_csv(path)
        self.assertTrue(any("invalid recommendation" in e.lower() for e in result["errors"]))

    # --- File not found ---

    def test_file_not_found(self):
        """Non-existent file should produce an error."""
        result = validate_csv("/nonexistent/path/file.csv")
        self.assertTrue(any("File not found" in e for e in result["errors"]))
        self.assertEqual(result["continuation_gate"], "FAIL")

    # --- Does not infer demand from synthetic data ---

    def test_does_not_infer_demand(self):
        """Validator should not claim demand from synthetic data."""
        rows = [_valid_row()]
        path = self._make(rows)
        result = validate_csv(path)
        # The aggregate should contain factual metrics only
        agg = result["aggregate"]
        self.assertNotIn("customer_demand", agg)
        self.assertNotIn("market_validation", agg)
        # The continuation gate should pass on factual correctness,
        # not on demand signals
        self.assertEqual(result["continuation_gate"], "PASS")


if __name__ == "__main__":
    unittest.main()
