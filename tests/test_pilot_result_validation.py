"""Tests for the pilot result validator (schema v2.1).

Tests cover:
- header-only file returns PENDING, never PASS
- zero real rows returns INSUFFICIENT_SAMPLE
- synthetic rows excluded from aggregate.real
- real rows excluded from aggregate.synthetic
- medians differ correctly between real, synthetic, and combined blocks
- a real row with failing evidence validation still counts as a real case
- a real row with failing validation sets continuation_gate FAIL
- adverse case counting
- min_currencies gate with one currency fails and with two passes
- ambiguous-case contributor floor
- single-practitioner share above 0.5 is flagged
- duplicate session_id rejected
- practitioner_id spanning synthetic and real is flagged
- deterministic JSON output ordering
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
"""

import csv
import json
import os
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from scripts.verify_pilot_result import validate_csv, REQUIRED_COLUMNS, SCHEMA_VERSION


def _write_csv(rows, columns=None):
    if columns is None:
        columns = REQUIRED_COLUMNS
    fd, path = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=columns, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(row)
    return path


def _valid_real_row(case_id="case_001", practitioner="prac_001", session="session_001"):
    return {
        "pilot_case_id": case_id,
        "session_id": session,
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


def _valid_synthetic_row(case_id="case_001", practitioner="synthetic_prac_001", session="session_001"):
    return {
        "pilot_case_id": case_id,
        "session_id": session,
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

    # --- DEFECT 18: header-only returns PENDING, never PASS ---

    def test_header_only_returns_pending(self):
        """Header-only file should return continuation_gate PENDING, never PASS."""
        path = self._make([])
        result = validate_csv(path)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["continuation_gate"], "PENDING")
        self.assertEqual(result["overall_status"], "INSUFFICIENT_SAMPLE")

    def test_zero_real_rows_returns_insufficient_sample(self):
        """Zero real rows should return overall_status INSUFFICIENT_SAMPLE."""
        rows = [_valid_synthetic_row()]
        path = self._make(rows)
        result = validate_csv(path)
        self.assertEqual(result["overall_status"], "INSUFFICIENT_SAMPLE")
        self.assertEqual(result["continuation_gate"], "PENDING")

    # --- DEFECT 19: synthetic rows excluded from aggregate.real ---

    def test_synthetic_rows_excluded_from_aggregate_real(self):
        """Synthetic rows should not appear in aggregate.real."""
        rows = [_valid_synthetic_row("s1", "sp1", "ss1")]
        path = self._make(rows)
        result = validate_csv(path)
        self.assertEqual(result["aggregate"]["real"], {})
        self.assertEqual(result["aggregate"]["synthetic"]["case_count"], 1)
        self.assertEqual(result["aggregate"]["combined"]["case_count"], 1)

    def test_real_rows_excluded_from_aggregate_synthetic(self):
        """Real rows should not appear in aggregate.synthetic."""
        rows = [_valid_real_row("r1", "rp1", "rs1")]
        path = self._make(rows)
        result = validate_csv(path)
        self.assertEqual(result["aggregate"]["synthetic"], {})
        self.assertEqual(result["aggregate"]["real"]["case_count"], 1)

    def test_medians_differ_between_blocks(self):
        """Medians should differ correctly between real, synthetic, and combined."""
        rows = [
            _valid_real_row("r1", "rp1", "rs1"),
            _valid_real_row("r2", "rp1", "rs2"),
            _valid_synthetic_row("s1", "sp1", "ss1"),
        ]
        rows[0]["review_minutes_baseline"] = "20"
        rows[1]["review_minutes_baseline"] = "40"
        rows[2]["review_minutes_baseline"] = "100"
        path = self._make(rows)
        result = validate_csv(path)
        self.assertEqual(result["aggregate"]["real"]["median_review_minutes_baseline_measured"], 30)
        self.assertEqual(result["aggregate"]["synthetic"]["median_review_minutes_baseline_measured"], 100)
        self.assertEqual(result["aggregate"]["combined"]["median_review_minutes_baseline_measured"], 40)

    # --- DEFECT 20: survivorship bias ---

    def test_real_row_with_failing_evidence_still_counts(self):
        """A real row with evidence_validation=false should still count as real."""
        row = _valid_real_row()
        row["evidence_validation"] = "false"
        path = self._make([row])
        result = validate_csv(path)
        self.assertEqual(result["aggregate"]["real"]["case_count"], 1)
        self.assertEqual(result["aggregate"]["real"]["evidence_failures"], 1)

    def test_real_row_with_failing_validation_sets_gate_fail(self):
        """A real row with failing validation should set continuation_gate FAIL."""
        row = _valid_real_row()
        row["evidence_validation"] = "false"
        path = self._make([row])
        result = validate_csv(path)
        self.assertEqual(result["continuation_gate"], "FAIL")
        self.assertEqual(result["overall_status"], "KILL_CONDITION")

    def test_adverse_case_counting(self):
        """Adverse cases should be counted and listed."""
        rows = [
            _valid_real_row("r1", "rp1", "rs1"),
            _valid_real_row("r2", "rp1", "rs2"),
        ]
        rows[1]["evidence_validation"] = "false"
        path = self._make(rows)
        result = validate_csv(path)
        self.assertEqual(len(result["aggregate"]["real"]["adverse_cases"]), 1)
        self.assertEqual(result["aggregate"]["real"]["adverse_cases"][0]["pilot_case_id"], "r2")

    # --- DEFECT 21: currency requirement ---

    def test_min_currencies_one_fails(self):
        """One currency should fail min_currencies."""
        rows = [_valid_real_row("r1", "rp1", "rs1")]
        path = self._make(rows)
        result = validate_csv(path)
        self.assertFalse(result["sample_requirements"]["min_currencies"]["met"])

    def test_min_currencies_two_passes(self):
        """Two currencies should pass min_currencies."""
        rows = [
            _valid_real_row("r1", "rp1", "rs1"),
            _valid_real_row("r2", "rp1", "rs2"),
        ]
        rows[1]["currency"] = "EUR"
        path = self._make(rows)
        result = validate_csv(path)
        self.assertTrue(result["sample_requirements"]["min_currencies"]["met"])

    # --- DEFECT 22: concentration control ---

    def test_ambiguous_case_contributor_floor(self):
        """Fewer than 3 practitioners contributing ambiguous cases should fail."""
        rows = [
            _valid_real_row("r1", "rp1", "rs1"),
            _valid_real_row("r2", "rp1", "rs2"),
        ]
        rows[0]["genuine_ambiguous_cases"] = "5"
        rows[1]["genuine_ambiguous_cases"] = "5"
        path = self._make(rows)
        result = validate_csv(path)
        self.assertFalse(result["sample_requirements"]["min_practitioners_contributing_ambiguous_cases"]["met"])

    def test_single_practitioner_share_above_half_flagged(self):
        """Single practitioner with >50% of cases should be flagged."""
        rows = [
            _valid_real_row("r1", "rp1", "rs1"),
            _valid_real_row("r2", "rp1", "rs2"),
            _valid_real_row("r3", "rp2", "rs3"),
        ]
        # rp1 has 2/3 = 0.667 > 0.5
        path = self._make(rows)
        result = validate_csv(path)
        self.assertFalse(result["sample_requirements"]["max_single_practitioner_case_share"]["met"])

    def test_single_practitioner_share_at_half_passes(self):
        """Single practitioner with exactly 50% should pass."""
        rows = [
            _valid_real_row("r1", "rp1", "rs1"),
            _valid_real_row("r2", "rp2", "rs2"),
        ]
        path = self._make(rows)
        result = validate_csv(path)
        self.assertTrue(result["sample_requirements"]["max_single_practitioner_case_share"]["met"])

    # --- ADDITIONAL HARDENING ---

    def test_duplicate_session_id_rejected(self):
        """Duplicate session_id should be rejected."""
        rows = [
            _valid_real_row("r1", "rp1", "shared_session"),
            _valid_real_row("r2", "rp1", "shared_session"),
        ]
        path = self._make(rows)
        result = validate_csv(path)
        self.assertTrue(any("duplicate session_id" in e for e in result["errors"]))

    def test_practitioner_spanning_synthetic_and_real_flagged(self):
        """practitioner_id in both synthetic and real should be flagged as warning."""
        rows = [
            _valid_real_row("r1", "shared_pid", "rs1"),
            _valid_synthetic_row("s1", "shared_pid", "ss1"),
        ]
        path = self._make(rows)
        result = validate_csv(path)
        self.assertTrue(any("shared_pid" in w and "both" in w for w in result["warnings"]))

    def test_deterministic_json_output_ordering(self):
        """Same input should produce identical JSON output."""
        rows = [
            _valid_real_row("r1", "rp1", "rs1"),
            _valid_real_row("r2", "rp2", "rs2"),
        ]
        path1 = self._make(rows)
        path2 = self._make(rows)
        r1 = validate_csv(path1)
        r2 = validate_csv(path2)
        self.assertEqual(json.dumps(r1, sort_keys=True, default=str),
                         json.dumps(r2, sort_keys=True, default=str))

    # --- Existing tests (adapted for v2.1) ---

    def test_valid_empty_template(self):
        path = self._make([])
        result = validate_csv(path)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["row_count"], 0)
        self.assertEqual(result["continuation_gate"], "PENDING")
        self.assertEqual(result["schema_version"], "2.1")

    def test_valid_completed_real_rows(self):
        rows = [
            _valid_real_row("case_001", "prac_001", "session_001"),
            _valid_real_row("case_002", "prac_002", "session_002"),
        ]
        path = self._make(rows)
        result = validate_csv(path)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["row_count"], 2)
        self.assertEqual(result["aggregate"]["real"]["case_count"], 2)
        self.assertEqual(result["aggregate"]["real"]["practitioner_count"], 2)
        self.assertEqual(result["continuation_gate"], "PASS")

    def test_synthetic_rows_excluded_from_real_counts(self):
        rows = [
            _valid_synthetic_row("s1", "sp1", "ss1"),
            _valid_synthetic_row("s2", "sp2", "ss2"),
        ]
        path = self._make(rows)
        result = validate_csv(path)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["aggregate"]["real"], {})
        self.assertEqual(result["aggregate"]["synthetic"]["case_count"], 2)
        sr = result["sample_requirements"]
        self.assertFalse(sr["min_practitioners"]["met"])
        self.assertFalse(sr["min_historical_cases"]["met"])

    def test_missing_attestations_excluded_from_real(self):
        row = _valid_real_row()
        row["real_participant_attestation"] = "false"
        path = self._make([row])
        result = validate_csv(path)
        self.assertEqual(result["aggregate"]["real"], {})

    def test_missing_consent_excluded_from_real(self):
        row = _valid_real_row()
        row["consent_received"] = "false"
        path = self._make([row])
        result = validate_csv(path)
        self.assertEqual(result["aggregate"]["real"], {})

    def test_review_exceptions_not_counted_as_ambiguous(self):
        row = _valid_real_row()
        row["review_exceptions"] = "5"
        row["genuine_ambiguous_cases"] = "1"
        row["deposits_processed"] = "15"
        row["accepted_matches"] = "10"
        path = self._make([row])
        result = validate_csv(path)
        self.assertEqual(result["aggregate"]["real"]["total_genuine_ambiguous_cases"], 1)

    def test_currencies_not_counted_as_layouts(self):
        rows = [
            _valid_real_row("r1", "rp1", "rs1"),
            _valid_real_row("r2", "rp1", "rs2"),
        ]
        rows[0]["currency"] = "USD"
        rows[1]["currency"] = "EUR"
        path = self._make(rows)
        result = validate_csv(path)
        self.assertEqual(result["aggregate"]["real"]["input_layout_count"], 1)
        self.assertEqual(len(result["aggregate"]["real"]["currencies_tested"]), 2)

    def test_explicit_layout_counting(self):
        rows = [
            _valid_real_row("r1", "rp1", "rs1"),
            _valid_real_row("r2", "rp1", "rs2"),
            _valid_real_row("r3", "rp1", "rs3"),
        ]
        rows[0]["input_layout_id"] = "layout_a"
        rows[1]["input_layout_id"] = "layout_b"
        rows[2]["input_layout_id"] = "layout_c"
        path = self._make(rows)
        result = validate_csv(path)
        self.assertEqual(result["aggregate"]["real"]["input_layout_count"], 3)

    def test_explicit_ambiguous_case_counting(self):
        rows = [
            _valid_real_row("r1", "rp1", "rs1"),
            _valid_real_row("r2", "rp1", "rs2"),
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
        self.assertEqual(result["aggregate"]["real"]["total_genuine_ambiguous_cases"], 5)

    def test_count_partition_mismatch(self):
        row = _valid_real_row()
        row["deposits_processed"] = "10"
        row["accepted_matches"] = "5"
        row["review_exceptions"] = "3"
        path = self._make([row])
        result = validate_csv(path)
        self.assertTrue(any("does not equal deposits_processed" in e for e in result["errors"]))

    def test_ambiguous_count_greater_than_exceptions(self):
        row = _valid_real_row()
        row["review_exceptions"] = "1"
        row["genuine_ambiguous_cases"] = "2"
        path = self._make([row])
        result = validate_csv(path)
        self.assertTrue(any("exceeds" in e and "review_exceptions" in e for e in result["errors"]))

    def test_false_allocations_greater_than_accepted(self):
        row = _valid_real_row()
        row["accepted_matches"] = "5"
        row["false_automatic_allocations"] = "6"
        path = self._make([row])
        result = validate_csv(path)
        self.assertTrue(any("false_automatic_allocations exceeds" in e for e in result["errors"]))

    def test_candidate_retention_numerator_greater_than_denominator(self):
        row = _valid_real_row()
        row["candidate_expected_cases"] = "5"
        row["correct_candidate_retained_cases"] = "6"
        path = self._make([row])
        result = validate_csv(path)
        self.assertTrue(any("correct_candidate_retained_cases exceeds" in e for e in result["errors"]))

    def test_zero_candidate_denominator(self):
        row = _valid_real_row()
        row["candidate_expected_cases"] = "0"
        row["correct_candidate_retained_cases"] = "0"
        path = self._make([row])
        result = validate_csv(path)
        self.assertIsNone(result["aggregate"]["real"]["candidate_retention_rate"])

    def test_nonzero_candidate_denominator(self):
        row = _valid_real_row()
        row["candidate_expected_cases"] = "10"
        row["correct_candidate_retained_cases"] = "8"
        path = self._make([row])
        result = validate_csv(path)
        self.assertEqual(result["aggregate"]["real"]["candidate_retention_rate"], 0.8)

    def test_median_calculations(self):
        rows = [
            _valid_real_row("c1", "p1", "s1"),
            _valid_real_row("c2", "p1", "s2"),
            _valid_real_row("c3", "p1", "s3"),
        ]
        rows[0]["review_minutes_baseline"] = "20"
        rows[1]["review_minutes_baseline"] = "30"
        rows[2]["review_minutes_baseline"] = "40"
        rows[0]["review_minutes_with_ledgermatch"] = "10"
        rows[1]["review_minutes_with_ledgermatch"] = "15"
        rows[2]["review_minutes_with_ledgermatch"] = "20"
        path = self._make(rows)
        result = validate_csv(path)
        self.assertEqual(result["aggregate"]["real"]["median_review_minutes_baseline_measured"], 30)
        self.assertEqual(result["aggregate"]["real"]["median_review_minutes_with_ledgermatch_measured"], 15)

    def test_retrospective_times_excluded_from_measured(self):
        rows = [
            _valid_real_row("c1", "p1", "s1"),
            _valid_real_row("c2", "p1", "s2"),
        ]
        rows[0]["baseline_method"] = "measured_counterbalanced"
        rows[0]["review_minutes_baseline"] = "30"
        rows[1]["baseline_method"] = "retrospective_estimate"
        rows[1]["review_minutes_baseline"] = "60"
        path = self._make(rows)
        result = validate_csv(path)
        self.assertEqual(result["aggregate"]["real"]["median_review_minutes_baseline_measured"], 30)
        self.assertEqual(result["aggregate"]["real"]["median_review_minutes_baseline_retrospective"], 60)

    def test_repeat_use_undecided(self):
        row = _valid_real_row()
        row["repeat_use_response"] = "undecided"
        path = self._make([row])
        result = validate_csv(path)
        self.assertEqual(result["errors"], [])
        self.assertEqual(result["aggregate"]["real"]["repeat_use_response_counts"]["undecided"], 1)

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

    def test_email_in_practitioner_id_detected(self):
        row = _valid_real_row()
        row["practitioner_id"] = "john@example.com"
        path = self._make([row])
        result = validate_csv(path)
        self.assertTrue(any("email" in e.lower() for e in result["errors"]))

    def test_email_in_session_id_detected(self):
        row = _valid_real_row()
        row["session_id"] = "test@domain.com"
        path = self._make([row])
        result = validate_csv(path)
        self.assertTrue(any("email" in e.lower() for e in result["errors"]))

    def test_secret_in_notes_detected(self):
        row = _valid_real_row()
        row["notes"] = "api_key=abc123secretkey"
        path = self._make([row])
        result = validate_csv(path)
        self.assertTrue(any("secret" in e.lower() for e in result["errors"]))

    def test_privacy_scanner_does_not_echo_values(self):
        row = _valid_real_row()
        row["notes"] = "contact john@example.com for details"
        path = self._make([row])
        result = validate_csv(path)
        for e in result["errors"]:
            if "email" in e.lower():
                self.assertNotIn("john@example.com", e)

    def test_check_privacy_mode_clean_file(self):
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

    def test_deterministic_aggregate_output(self):
        rows = [
            _valid_real_row("c1", "p1", "s1"),
            _valid_real_row("c2", "p2", "s2"),
        ]
        path1 = self._make(rows)
        path2 = self._make(rows)
        r1 = validate_csv(path1)
        r2 = validate_csv(path2)
        self.assertEqual(r1["aggregate"], r2["aggregate"])
        self.assertEqual(r1["continuation_gate"], r2["continuation_gate"])

    def test_missing_columns(self):
        row = _valid_real_row()
        cols = [c for c in REQUIRED_COLUMNS if c != "currency"]
        path = self._make([row], columns=cols)
        result = validate_csv(path)
        self.assertTrue(any("Missing required columns" in e for e in result["errors"]))

    def test_malformed_number(self):
        row = _valid_real_row()
        row["deposits_processed"] = "ten"
        path = self._make([row])
        result = validate_csv(path)
        self.assertTrue(any("malformed integer" in e.lower() for e in result["errors"]))

    def test_malformed_boolean(self):
        row = _valid_real_row()
        row["evidence_validation"] = "maybe"
        path = self._make([row])
        result = validate_csv(path)
        self.assertTrue(any("malformed boolean" in e.lower() for e in result["errors"]))

    def test_duplicate_case_ids(self):
        rows = [
            _valid_real_row("case_001", "p1", "s1"),
            _valid_real_row("case_001", "p2", "s2"),
        ]
        path = self._make(rows)
        result = validate_csv(path)
        self.assertTrue(any("duplicate pilot_case_id" in e for e in result["errors"]))

    def test_negative_values(self):
        row = _valid_real_row()
        row["review_minutes_baseline"] = "-5"
        path = self._make([row])
        result = validate_csv(path)
        self.assertTrue(any("negative" in e.lower() for e in result["errors"]))

    def test_false_allocation_kill_gate(self):
        row = _valid_real_row()
        row["false_automatic_allocations"] = "1"
        row["accepted_matches"] = "8"
        path = self._make([row])
        result = validate_csv(path)
        self.assertEqual(result["continuation_gate"], "FAIL")
        self.assertTrue(any("CONTINUATION GATE FAILED" in e for e in result["errors"]))

    def test_zero_false_allocation_passes_gate(self):
        row = _valid_real_row()
        row["false_automatic_allocations"] = "0"
        path = self._make([row])
        result = validate_csv(path)
        self.assertEqual(result["continuation_gate"], "PASS")

    def test_evidence_validation_failure_fails_gate(self):
        row = _valid_real_row()
        row["evidence_validation"] = "false"
        path = self._make([row])
        result = validate_csv(path)
        self.assertEqual(result["continuation_gate"], "FAIL")

    def test_review_ledger_validation_failure_fails_gate(self):
        row = _valid_real_row()
        row["review_ledger_validation"] = "false"
        path = self._make([row])
        result = validate_csv(path)
        self.assertEqual(result["continuation_gate"], "FAIL")

    def test_insufficient_sample_reporting(self):
        rows = [_valid_real_row("c1", "p1", "s1")]
        path = self._make(rows)
        result = validate_csv(path)
        sr = result["sample_requirements"]
        self.assertFalse(sr["min_practitioners"]["met"])
        self.assertFalse(sr["min_historical_cases"]["met"])

    def test_sufficient_sample_reporting(self):
        rows = []
        for i in range(35):
            row = _valid_real_row(f"c{i:03d}", f"p{i % 6:03d}", f"s{i:03d}")
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
        self.assertTrue(sr["min_currencies"]["met"])

    def test_file_not_found(self):
        result = validate_csv("/nonexistent/path/file.csv")
        self.assertTrue(any("File not found" in e for e in result["errors"]))

    def test_does_not_infer_demand(self):
        rows = [_valid_synthetic_row()]
        path = self._make(rows)
        result = validate_csv(path)
        agg = result["aggregate"]
        self.assertNotIn("customer_demand", agg)
        self.assertNotIn("market_validation", agg)
        self.assertEqual(result["aggregate"]["real"], {})

    def test_invalid_data_origin(self):
        row = _valid_real_row()
        row["data_origin"] = "anonymous"
        path = self._make([row])
        result = validate_csv(path)
        self.assertTrue(any("data_origin" in e and "invalid" in e for e in result["errors"]))

    def test_invalid_baseline_method(self):
        row = _valid_real_row()
        row["baseline_method"] = "guess"
        path = self._make([row])
        result = validate_csv(path)
        self.assertTrue(any("baseline_method" in e and "invalid" in e for e in result["errors"]))

    def test_empty_input_layout_id(self):
        row = _valid_real_row()
        row["input_layout_id"] = ""
        path = self._make([row])
        result = validate_csv(path)
        self.assertTrue(any("input_layout_id" in e for e in result["errors"]))

    def test_per_practitioner_median_times(self):
        rows = [
            _valid_real_row("c1", "p1", "s1"),
            _valid_real_row("c2", "p1", "s2"),
        ]
        rows[0]["review_minutes_baseline"] = "20"
        rows[1]["review_minutes_baseline"] = "40"
        path = self._make(rows)
        result = validate_csv(path)
        ppt = result["aggregate"]["real"]["per_practitioner_median_times"]
        self.assertIn("p1", ppt)
        self.assertEqual(ppt["p1"]["median_baseline_measured"], 30)

    def test_privacy_note_in_output(self):
        """Output should include privacy scanning heuristic disclaimer."""
        path = self._make([])
        result = validate_csv(path)
        self.assertIn("privacy_note", result)
        self.assertIn("heuristic", result["privacy_note"].lower())

    def test_sample_met_overall_status(self):
        """When all samples met and gate PASS, overall_status should be SAMPLE_MET."""
        rows = []
        for i in range(35):
            row = _valid_real_row(f"c{i:03d}", f"p{i % 6:03d}", f"s{i:03d}")
            row["currency"] = ["USD", "EUR", "GBP"][i % 3]
            row["input_layout_id"] = ["layout_a", "layout_b", "layout_c"][i % 3]
            row["genuine_ambiguous_cases"] = "1" if i < 12 else "0"
            rows.append(row)
        path = self._make(rows)
        result = validate_csv(path)
        self.assertEqual(result["overall_status"], "SAMPLE_MET")


if __name__ == "__main__":
    unittest.main()
