"""Tests for the pilot result validator (schema v2.0).

Tests cover:
- synthetic rows excluded from real counts
- missing human attestations excluded
- review exceptions not counted as ambiguous
- currencies not counted as layouts
- explicit layout counting
- explicit ambiguous-case counting
- count partition mismatch
- ambiguous count greater than exceptions
- false allocations greater than accepted matches
- candidate retention numerator greater than denominator
- zero candidate denominator
- median calculations
- retrospective times excluded from measured comparison
- repeat-use undecided
- support-signal enums
- privacy scanning across all text fields
- privacy scanner does not echo detected values
- documented --check-privacy mode
- deterministic aggregate output
- current 64 regression tests still passing (via verify_release)
"""

import csv
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.verify_pilot_result import validate_csv, REQUIRED_COLUMNS, SCHEMA_VERSION


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


def _valid_real_row(case_id="case_001", practitioner="prac_001"):
    return {
        "pilot_case_id": case_id,
        "session_id": "session_001",
        "practitioner_id": practitioner,
        "role_category": "accountant",
        "data_origin": "authorized_pseudonymized_historical",
        "direct_reconciliation_experience": "true",
        "consent_received": "true",
        "real_participant_attestation": "true",
        "operator_attestation": "true",
        "input_layout_id": "layout_a",
        "currency": "USD",
        "deposits_processed": "10",
        "accepted_matches": "8",
        "review_exceptions": "2",
        "genuine_ambiguous_cases": "1",
        "false_automatic_allocations": "0",
        "candidate_expected_cases": "10",
        "correct_candidate_retained_cases": "9",
        "review_minutes_baseline": "30",
        "baseline_method": "measured_counterbalanced",
        "review_minutes_with_ledgermatch": "15",
        "evidence_validation": "true",
        "review_ledger_validation": "true",
        "repeat_use_response": "yes",
        "recommendation": "recommend",
        "support_signal": "willing_to_pay",
        "notes": "case ran smoothly",
    }


def _valid_synthetic_row(case_id="case_001", practitioner="synthetic_prac_001"):
    return {
        "pilot_case_id": case_id,
        "session_id": "session_001",
        "practitioner_id": practitioner,
        "role_category": "synthetic",
        "data_origin": "synthetic",
        "direct_reconciliation_experience": "true",
        "consent_received": "true",
        "real_participant_attestation": "true",
        "operator_attestation": "true",
        "input_layout_id": "layout_a",
        "currency": "USD",
        "deposits_processed": "10",
        "accepted_matches": "8",
        "review_exceptions": "2",
        "genuine_ambiguous_cases": "1",
        "false_automatic_allocations": "0",
        "candidate_expected_cases": "10",
        "correct_candidate_retained_cases": "9",
        "review_minutes_baseline": "30",
        "baseline_method": "measured_counterbalanced",
        "review_minutes_with_ledgermatch": "15",
        "evidence_validation": "true",
        "review_ledger_validation": "true",
        "repeat_use_response": "yes",
        "recommendation": "recommend",
        "support_signal": "willing_to_contribute",
        "notes": "synthetic rehearsal",
    }


class TestPilotResultValidationV2(unittest.TestCase):

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
        self.assertEqual(result["schema_version"], "2.0")

    # --- Valid completed rows ---

    def test_valid_completed_real_rows(self):
        """Valid real rows should pass with correct aggregate."""
        rows = [
            _valid_real_row("case_001", "prac_001"),
            _valid_real_row("case_002", "prac_002"),
        ]
        path = self._make(rows)
        result = validate_csv(path)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["row_count"], 2)
        self.assertEqual(result["aggregate"]["real_cases"], 2)
        self.assertEqual(result["aggregate"]["real_practitioners"], 2)
        self.assertEqual(result["continuation_gate"], "PASS")

    # --- Synthetic rows excluded from real counts ---

    def test_synthetic_rows_excluded_from_real_counts(self):
        """Synthetic rows should not count toward real sample requirements."""
        rows = [
            _valid_synthetic_row("case_001", "synthetic_prac_001"),
            _valid_synthetic_row("case_002", "synthetic_prac_002"),
        ]
        path = self._make(rows)
        result = validate_csv(path)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["aggregate"]["real_cases"], 0)
        self.assertEqual(result["aggregate"]["real_practitioners"], 0)
        self.assertEqual(result["aggregate"]["synthetic_cases"], 2)
        sr = result["sample_requirements"]
        self.assertFalse(sr["min_practitioners"]["met"])
        self.assertFalse(sr["min_historical_cases"]["met"])

    # --- Missing human attestations excluded ---

    def test_missing_attestations_excluded_from_real(self):
        """Rows missing attestations should not count as real."""
        row = _valid_real_row()
        row["real_participant_attestation"] = "false"
        path = self._make([row])
        result = validate_csv(path)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["aggregate"]["real_cases"], 0)
        self.assertEqual(result["aggregate"]["real_practitioners"], 0)

    def test_missing_consent_excluded_from_real(self):
        """Rows without consent should not count as real."""
        row = _valid_real_row()
        row["consent_received"] = "false"
        path = self._make([row])
        result = validate_csv(path)
        self.assertEqual(result["aggregate"]["real_cases"], 0)

    def test_missing_evidence_validation_excluded_from_real(self):
        """Rows with evidence_validation=false should not count as real."""
        row = _valid_real_row()
        row["evidence_validation"] = "false"
        path = self._make([row])
        result = validate_csv(path)
        self.assertEqual(result["aggregate"]["real_cases"], 0)

    # --- Review exceptions not counted as ambiguous ---

    def test_review_exceptions_not_counted_as_ambiguous(self):
        """review_exceptions should not be used as ambiguous case count."""
        row = _valid_real_row()
        row["review_exceptions"] = "5"
        row["genuine_ambiguous_cases"] = "1"
        row["deposits_processed"] = "15"
        row["accepted_matches"] = "10"
        path = self._make([row])
        result = validate_csv(path)
        self.assertEqual(result["aggregate"]["real_genuine_ambiguous_cases"], 1)
        self.assertNotEqual(
            result["aggregate"]["real_genuine_ambiguous_cases"],
            result["aggregate"]["total_review_exceptions"],
        )

    # --- Currencies not counted as layouts ---

    def test_currencies_not_counted_as_layouts(self):
        """Currencies and layouts should be counted independently."""
        rows = [
            _valid_real_row("case_001", "prac_001"),
        ]
        rows[0]["currency"] = "USD"
        rows[0]["input_layout_id"] = "layout_a"
        rows.append(_valid_real_row("case_002", "prac_001"))
        rows[1]["currency"] = "EUR"
        rows[1]["input_layout_id"] = "layout_a"
        path = self._make(rows)
        result = validate_csv(path)
        self.assertEqual(result["aggregate"]["real_input_layouts"], 1)
        self.assertEqual(len(result["aggregate"]["real_currencies_tested"]), 2)

    # --- Explicit layout counting ---

    def test_explicit_layout_counting(self):
        """Layouts should be counted from unique input_layout_id values."""
        rows = [
            _valid_real_row("case_001", "prac_001"),
            _valid_real_row("case_002", "prac_001"),
            _valid_real_row("case_003", "prac_001"),
        ]
        rows[0]["input_layout_id"] = "layout_a"
        rows[1]["input_layout_id"] = "layout_b"
        rows[2]["input_layout_id"] = "layout_c"
        path = self._make(rows)
        result = validate_csv(path)
        self.assertEqual(result["aggregate"]["real_input_layouts"], 3)

    # --- Explicit ambiguous-case counting ---

    def test_explicit_ambiguous_case_counting(self):
        """Ambiguous cases should come from genuine_ambiguous_cases field."""
        rows = [
            _valid_real_row("case_001", "prac_001"),
            _valid_real_row("case_002", "prac_001"),
        ]
        rows[0]["genuine_ambiguous_cases"] = "3"
        rows[0]["review_exceptions"] = "5"
        rows[0]["deposits_processed"] = "15"
        rows[0]["accepted_matches"] = "10"
        rows[1]["genuine_ambiguous_cases"] = "2"
        rows[1]["review_exceptions"] = "4"
        rows[1]["deposits_processed"] = "14"
        rows[1]["accepted_matches"] = "10"
        path = self._make(rows)
        result = validate_csv(path)
        self.assertEqual(result["aggregate"]["real_genuine_ambiguous_cases"], 5)

    # --- Count partition mismatch ---

    def test_count_partition_mismatch(self):
        """accepted_matches + review_exceptions must equal deposits_processed."""
        row = _valid_real_row()
        row["deposits_processed"] = "10"
        row["accepted_matches"] = "5"
        row["review_exceptions"] = "3"
        # 5 + 3 != 10
        path = self._make([row])
        result = validate_csv(path)
        self.assertTrue(any("does not equal deposits_processed" in e for e in result["errors"]))

    # --- Ambiguous count greater than exceptions ---

    def test_ambiguous_count_greater_than_exceptions(self):
        """genuine_ambiguous_cases must not exceed review_exceptions."""
        row = _valid_real_row()
        row["review_exceptions"] = "1"
        row["genuine_ambiguous_cases"] = "2"
        # 2 > 1
        path = self._make([row])
        result = validate_csv(path)
        self.assertTrue(any("exceeds" in e and "review_exceptions" in e for e in result["errors"]))

    # --- False allocations greater than accepted matches ---

    def test_false_allocations_greater_than_accepted(self):
        """false_automatic_allocations must not exceed accepted_matches."""
        row = _valid_real_row()
        row["accepted_matches"] = "5"
        row["false_automatic_allocations"] = "6"
        path = self._make([row])
        result = validate_csv(path)
        self.assertTrue(any("false_automatic_allocations exceeds" in e for e in result["errors"]))

    # --- Candidate retention numerator greater than denominator ---

    def test_candidate_retention_numerator_greater_than_denominator(self):
        """correct_candidate_retained_cases must not exceed candidate_expected_cases."""
        row = _valid_real_row()
        row["candidate_expected_cases"] = "5"
        row["correct_candidate_retained_cases"] = "6"
        path = self._make([row])
        result = validate_csv(path)
        self.assertTrue(any("correct_candidate_retained_cases exceeds" in e for e in result["errors"]))

    # --- Zero candidate denominator ---

    def test_zero_candidate_denominator(self):
        """Zero candidate_expected_cases should report rate as null."""
        row = _valid_real_row()
        row["candidate_expected_cases"] = "0"
        row["correct_candidate_retained_cases"] = "0"
        path = self._make([row])
        result = validate_csv(path)
        self.assertIsNone(result["aggregate"]["candidate_retention_rate"])
        self.assertIn("candidate_retention_rate_note", result["aggregate"])

    def test_nonzero_candidate_denominator(self):
        """Nonzero denominator should produce a numeric rate."""
        row = _valid_real_row()
        row["candidate_expected_cases"] = "10"
        row["correct_candidate_retained_cases"] = "8"
        path = self._make([row])
        result = validate_csv(path)
        self.assertEqual(result["aggregate"]["candidate_retention_rate"], 0.8)

    # --- Median calculations ---

    def test_median_calculations(self):
        """Median review times should be computed from measured rows."""
        rows = [
            _valid_real_row("case_001", "prac_001"),
            _valid_real_row("case_002", "prac_001"),
            _valid_real_row("case_003", "prac_001"),
        ]
        rows[0]["review_minutes_baseline"] = "20"
        rows[1]["review_minutes_baseline"] = "30"
        rows[2]["review_minutes_baseline"] = "40"
        rows[0]["review_minutes_with_ledgermatch"] = "10"
        rows[1]["review_minutes_with_ledgermatch"] = "15"
        rows[2]["review_minutes_with_ledgermatch"] = "20"
        path = self._make(rows)
        result = validate_csv(path)
        self.assertEqual(result["aggregate"]["median_review_minutes_baseline_measured"], 30)
        self.assertEqual(result["aggregate"]["median_review_minutes_with_ledgermatch_measured"], 15)

    # --- Retrospective times excluded from measured comparison ---

    def test_retrospective_times_excluded_from_measured(self):
        """Retrospective estimates should be reported separately."""
        rows = [
            _valid_real_row("case_001", "prac_001"),
            _valid_real_row("case_002", "prac_001"),
        ]
        rows[0]["baseline_method"] = "measured_counterbalanced"
        rows[0]["review_minutes_baseline"] = "30"
        rows[1]["baseline_method"] = "retrospective_estimate"
        rows[1]["review_minutes_baseline"] = "60"
        path = self._make(rows)
        result = validate_csv(path)
        self.assertEqual(result["aggregate"]["median_review_minutes_baseline_measured"], 30)
        self.assertEqual(result["aggregate"]["median_review_minutes_baseline_retrospective"], 60)
        self.assertTrue(result["aggregate"]["retrospective_estimates_reported_separately"])

    # --- Repeat-use undecided ---

    def test_repeat_use_undecided(self):
        """repeat_use_response should accept 'undecided'."""
        row = _valid_real_row()
        row["repeat_use_response"] = "undecided"
        path = self._make([row])
        result = validate_csv(path)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["aggregate"]["repeat_use_response_counts"]["undecided"], 1)

    # --- Support-signal enums ---

    def test_support_signal_willing_to_pay(self):
        row = _valid_real_row()
        row["support_signal"] = "willing_to_pay"
        path = self._make([row])
        result = validate_csv(path)
        self.assertEqual(result["errors"], [])

    def test_support_signal_neither(self):
        row = _valid_real_row()
        row["support_signal"] = "neither"
        path = self._make([row])
        result = validate_csv(path)
        self.assertEqual(result["errors"], [])

    def test_support_signal_invalid(self):
        row = _valid_real_row()
        row["support_signal"] = "maybe"
        path = self._make([row])
        result = validate_csv(path)
        self.assertTrue(any("support_signal" in e and "invalid" in e for e in result["errors"]))

    # --- Privacy scanning across all text fields ---

    def test_email_in_practitioner_id_detected(self):
        """Email in practitioner_id should be flagged."""
        row = _valid_real_row()
        row["practitioner_id"] = "john@example.com"
        path = self._make([row])
        result = validate_csv(path)
        self.assertTrue(any("email" in e.lower() for e in result["errors"]))

    def test_email_in_session_id_detected(self):
        """Email in session_id should be flagged."""
        row = _valid_real_row()
        row["session_id"] = "test@domain.com"
        path = self._make([row])
        result = validate_csv(path)
        self.assertTrue(any("email" in e.lower() for e in result["errors"]))

    def test_account_number_in_role_category_detected(self):
        """Long digit sequence in role_category should be flagged."""
        row = _valid_real_row()
        row["role_category"] = "1234567890"
        path = self._make([row])
        result = validate_csv(path)
        self.assertTrue(any("digit" in e.lower() for e in result["errors"]))

    def test_secret_in_notes_detected(self):
        """Secret pattern in notes should be flagged."""
        row = _valid_real_row()
        row["notes"] = "api_key=abc123secretkey"
        path = self._make([row])
        result = validate_csv(path)
        self.assertTrue(any("secret" in e.lower() for e in result["errors"]))

    # --- Privacy scanner does not echo detected values ---

    def test_privacy_scanner_does_not_echo_values(self):
        """Error messages should not contain the detected sensitive value."""
        row = _valid_real_row()
        row["notes"] = "contact john@example.com for details"
        path = self._make([row])
        result = validate_csv(path)
        for e in result["errors"]:
            if "email" in e.lower():
                self.assertNotIn("john@example.com", e)

    # --- Documented --check-privacy mode ---

    def test_check_privacy_mode_clean_file(self):
        """--check-privacy on a clean file should return no findings."""
        fd, path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["name", "amount"])
            writer.writerow(["customer_001", "100.00"])
        self._temp_paths.append(path)
        result = subprocess.run(
            [sys.executable, "scripts/verify_pilot_result.py", "--check-privacy", path],
            capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        data = json.loads(result.stdout)
        self.assertEqual(data["findings"], [])
        self.assertIn("does not prove", data["note"])
        self.assertEqual(result.returncode, 0)

    def test_check_privacy_mode_detects_email(self):
        """--check-privacy should detect email patterns."""
        fd, path = tempfile.mkstemp(suffix=".csv")
        with os.fdopen(fd, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["name", "email"])
            writer.writerow(["test", "john@example.com"])
        self._temp_paths.append(path)
        result = subprocess.run(
            [sys.executable, "scripts/verify_pilot_result.py", "--check-privacy", path],
            capture_output=True, text=True, cwd=os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        )
        data = json.loads(result.stdout)
        self.assertTrue(len(data["findings"]) > 0)
        self.assertEqual(data["findings"][0]["pattern"], "email")
        self.assertEqual(result.returncode, 1)

    # --- Deterministic aggregate output ---

    def test_deterministic_aggregate_output(self):
        """Same input should produce identical aggregate output."""
        rows = [
            _valid_real_row("case_001", "prac_001"),
            _valid_real_row("case_002", "prac_002"),
        ]
        path1 = self._make(rows)
        path2 = self._make(rows)
        r1 = validate_csv(path1)
        r2 = validate_csv(path2)
        self.assertEqual(r1["aggregate"], r2["aggregate"])
        self.assertEqual(r1["continuation_gate"], r2["continuation_gate"])

    # --- Missing columns ---

    def test_missing_columns(self):
        """Missing required columns should produce an error."""
        row = _valid_real_row()
        cols = [c for c in REQUIRED_COLUMNS if c != "currency"]
        path = self._make([row], columns=cols)
        result = validate_csv(path)
        self.assertTrue(any("Missing required columns" in e for e in result["errors"]))

    # --- Malformed numbers ---

    def test_malformed_number(self):
        """Non-integer in an integer column should error."""
        row = _valid_real_row()
        row["deposits_processed"] = "ten"
        path = self._make([row])
        result = validate_csv(path)
        self.assertTrue(any("malformed integer" in e.lower() for e in result["errors"]))

    # --- Malformed booleans ---

    def test_malformed_boolean(self):
        """Non-boolean in a boolean column should error."""
        row = _valid_real_row()
        row["evidence_validation"] = "maybe"
        path = self._make([row])
        result = validate_csv(path)
        self.assertTrue(any("malformed boolean" in e.lower() for e in result["errors"]))

    # --- Duplicate IDs ---

    def test_duplicate_ids(self):
        """Duplicate pilot_case_id should error."""
        rows = [
            _valid_real_row("case_001", "prac_001"),
            _valid_real_row("case_001", "prac_002"),
        ]
        path = self._make(rows)
        result = validate_csv(path)
        self.assertTrue(any("duplicate pilot_case_id" in e for e in result["errors"]))

    # --- Negative values ---

    def test_negative_values(self):
        """Negative integers should error."""
        row = _valid_real_row()
        row["review_minutes_baseline"] = "-5"
        path = self._make([row])
        result = validate_csv(path)
        self.assertTrue(any("negative" in e.lower() for e in result["errors"]))

    # --- False-allocation kill gate ---

    def test_false_allocation_kill_gate(self):
        """Any false automatic allocation should fail the continuation gate."""
        row = _valid_real_row()
        row["false_automatic_allocations"] = "1"
        row["accepted_matches"] = "8"
        path = self._make([row])
        result = validate_csv(path)
        self.assertEqual(result["continuation_gate"], "FAIL")
        self.assertTrue(any("CONTINUATION GATE FAILED" in e for e in result["errors"]))

    def test_zero_false_allocation_passes_gate(self):
        """Zero false automatic allocations should pass the continuation gate."""
        row = _valid_real_row()
        row["false_automatic_allocations"] = "0"
        path = self._make([row])
        result = validate_csv(path)
        self.assertEqual(result["continuation_gate"], "PASS")

    # --- Evidence validation failure gate ---

    def test_evidence_validation_failure_fails_gate(self):
        """Evidence validation failure should fail the continuation gate."""
        row = _valid_real_row()
        row["evidence_validation"] = "false"
        path = self._make([row])
        result = validate_csv(path)
        self.assertEqual(result["continuation_gate"], "FAIL")

    # --- Review-ledger validation failure gate ---

    def test_review_ledger_validation_failure_fails_gate(self):
        """Review-ledger validation failure should fail the continuation gate."""
        row = _valid_real_row()
        row["review_ledger_validation"] = "false"
        path = self._make([row])
        result = validate_csv(path)
        self.assertEqual(result["continuation_gate"], "FAIL")

    # --- Insufficient sample reporting ---

    def test_insufficient_sample_reporting(self):
        """Small dataset should report unmet minimum requirements."""
        rows = [_valid_real_row("case_001", "prac_001")]
        path = self._make(rows)
        result = validate_csv(path)
        sr = result["sample_requirements"]
        self.assertFalse(sr["min_practitioners"]["met"])
        self.assertFalse(sr["min_historical_cases"]["met"])

    # --- Sufficient sample reporting ---

    def test_sufficient_sample_reporting(self):
        """Large dataset should report met minimum requirements."""
        rows = []
        for i in range(35):
            row = _valid_real_row(f"case_{i:03d}", f"prac_{i % 6:03d}")
            row["currency"] = ["USD", "EUR", "GBP"][i % 3]
            row["input_layout_id"] = ["layout_a", "layout_b", "layout_c"][i % 3]
            row["genuine_ambiguous_cases"] = "1" if i < 12 else "0"
            rows.append(row)
        path = self._make(rows)
        result = validate_csv(path)
        sr = result["sample_requirements"]
        self.assertTrue(sr["min_practitioners"]["met"])
        self.assertTrue(sr["min_historical_cases"]["met"])
        self.assertTrue(sr["min_ambiguous_cases"]["met"])
        self.assertTrue(sr["min_input_layouts"]["met"])

    # --- File not found ---

    def test_file_not_found(self):
        """Non-existent file should produce an error."""
        result = validate_csv("/nonexistent/path/file.csv")
        self.assertTrue(any("File not found" in e for e in result["errors"]))

    # --- Does not infer demand from synthetic data ---

    def test_does_not_infer_demand(self):
        """Validator should not claim demand from synthetic data."""
        rows = [_valid_synthetic_row()]
        path = self._make(rows)
        result = validate_csv(path)
        agg = result["aggregate"]
        self.assertNotIn("customer_demand", agg)
        self.assertNotIn("market_validation", agg)
        self.assertEqual(agg["real_cases"], 0)

    # --- Invalid data_origin ---

    def test_invalid_data_origin(self):
        """Invalid data_origin should error."""
        row = _valid_real_row()
        row["data_origin"] = "anonymous"
        path = self._make([row])
        result = validate_csv(path)
        self.assertTrue(any("data_origin" in e and "invalid" in e for e in result["errors"]))

    # --- Invalid baseline_method ---

    def test_invalid_baseline_method(self):
        """Invalid baseline_method should error."""
        row = _valid_real_row()
        row["baseline_method"] = "guess"
        path = self._make([row])
        result = validate_csv(path)
        self.assertTrue(any("baseline_method" in e and "invalid" in e for e in result["errors"]))

    # --- Empty input_layout_id ---

    def test_empty_input_layout_id(self):
        """Empty input_layout_id should error."""
        row = _valid_real_row()
        row["input_layout_id"] = ""
        path = self._make([row])
        result = validate_csv(path)
        self.assertTrue(any("input_layout_id" in e for e in result["errors"]))

    # --- Per-practitioner median times ---

    def test_per_practitioner_median_times(self):
        """Per-practitioner median times should be computed when data exists."""
        rows = [
            _valid_real_row("case_001", "prac_001"),
            _valid_real_row("case_002", "prac_001"),
        ]
        rows[0]["review_minutes_baseline"] = "20"
        rows[1]["review_minutes_baseline"] = "40"
        path = self._make(rows)
        result = validate_csv(path)
        ppt = result["aggregate"]["per_practitioner_median_times"]
        self.assertIn("prac_001", ppt)
        self.assertEqual(ppt["prac_001"]["median_baseline_measured"], 30)


if __name__ == "__main__":
    unittest.main()
