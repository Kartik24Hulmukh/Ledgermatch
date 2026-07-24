#!/usr/bin/env python3
"""Pilot result validator for LedgerMatch private pilot.

Validates pilot-results CSV files against the required schema, checks for
privacy violations, computes aggregate factual metrics, and enforces the
continuation gate (false automatic allocations must be zero).

Uses only the Python standard library.

Schema version: 2.1
"""

import csv
import json
import re
import statistics
import sys
from pathlib import Path

SCHEMA_VERSION = "2.1"

REQUIRED_COLUMNS = [
    "pilot_case_id",
    "session_id",
    "practitioner_id",
    "role_category",
    "data_origin",
    "direct_reconciliation_experience",
    "consent_received",
    "real_participant_attestation",
    "operator_attestation",
    "input_layout_id",
    "currency",
    "deposits_processed",
    "accepted_matches",
    "review_exceptions",
    "genuine_ambiguous_cases",
    "false_automatic_allocations",
    "candidate_expected_cases",
    "correct_candidate_retained_cases",
    "review_minutes_baseline",
    "baseline_method",
    "review_minutes_with_ledgermatch",
    "evidence_validation",
    "review_ledger_validation",
    "repeat_use_response",
    "recommendation",
    "support_signal",
    "notes",
]

INTEGER_COLUMNS = {
    "deposits_processed",
    "accepted_matches",
    "review_exceptions",
    "genuine_ambiguous_cases",
    "false_automatic_allocations",
    "candidate_expected_cases",
    "correct_candidate_retained_cases",
    "review_minutes_baseline",
    "review_minutes_with_ledgermatch",
}

BOOLEAN_COLUMNS = {
    "direct_reconciliation_experience",
    "consent_received",
    "real_participant_attestation",
    "operator_attestation",
    "evidence_validation",
    "review_ledger_validation",
}

ENUM_COLUMNS = {
    "data_origin": {"synthetic", "authorized_pseudonymized_historical"},
    "baseline_method": {
        "measured_counterbalanced",
        "measured_matched_case_set",
        "retrospective_estimate",
    },
    "repeat_use_response": {"yes", "no", "undecided"},
    "recommendation": {"recommend", "neutral", "do_not_recommend"},
    "support_signal": {
        "willing_to_pay",
        "willing_to_contribute",
        "neither",
        "undecided",
    },
}

VALID_CURRENCIES = {
    "USD", "EUR", "GBP", "INR", "JPY", "CAD", "AUD", "CHF", "CNY",
    "SGD", "HKD", "NZD", "SEK", "NOK", "DKK", "MXN", "BRL", "ZAR",
    "AED", "SAR",
}

# Text-capable fields for privacy scanning — all fields get email+secret
# scanning; only free-text fields (notes, support_signal) also get
# long-digit-sequence scanning.  Identifier fields (pilot_case_id,
# session_id, input_layout_id) are excluded from digit scanning to avoid
# false positives on legitimate IDs.
TEXT_FIELDS_EMAIL_SECRET = [
    "pilot_case_id",
    "session_id",
    "practitioner_id",
    "role_category",
    "input_layout_id",
    "notes",
    "support_signal",
]

TEXT_FIELDS_DIGIT_SCAN = [
    "notes",
    "support_signal",
]

# Privacy patterns
EMAIL_RE = re.compile(
    r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}"
)
ACCOUNT_NUMBER_RE = re.compile(r"\b\d{10,}\b")
SECRET_PATTERNS = [
    re.compile(r"(?i)api[_-]?key\s*[:=]\s*\S+"),
    re.compile(r"(?i)secret\s*[:=]\s*\S+"),
    re.compile(r"(?i)password\s*[:=]\s*\S+"),
    re.compile(r"(?i)token\s*[:=]\s*\S+"),
    re.compile(r"-----BEGIN [A-Z ]+PRIVATE KEY-----"),
    re.compile(r"ghp_[A-Za-z0-9]{36}"),
    re.compile(r"sk_[A-Za-z0-9]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
]

# Minimum sample requirements
MIN_PRACTITIONERS = 5
MIN_HISTORICAL_CASES = 30
MIN_AMBIGUOUS_CASES = 10
MIN_INPUT_LAYOUTS = 3
MIN_CURRENCIES = 2
MIN_AMBIGUOUS_CONTRIBUTORS = 3
MAX_SINGLE_PRACTITIONER_SHARE = 0.5


class ValidationError(Exception):
    pass


def _parse_int(value, column, row_num):
    try:
        iv = int(value)
    except (ValueError, TypeError):
        raise ValidationError(
            f"Row {row_num}: column '{column}' has malformed integer value"
        )
    return iv


def _parse_bool(value, column, row_num):
    vl = str(value).strip().lower()
    if vl in ("true", "1", "yes"):
        return True
    if vl in ("false", "0", "no"):
        return False
    raise ValidationError(
        f"Row {row_num}: column '{column}' has malformed boolean value"
    )


def _check_privacy(text, row_num, column, scan_digits=True):
    """Scan text for obvious privacy violations.

    Does NOT echo detected sensitive values in error messages.
    Does NOT claim that regex scanning proves de-identification.
    """
    violations = []
    if EMAIL_RE.search(text):
        violations.append(
            f"Row {row_num}: column '{column}' contains a possible email pattern"
        )
    if scan_digits and ACCOUNT_NUMBER_RE.search(text):
        violations.append(
            f"Row {row_num}: column '{column}' contains a possible long digit sequence"
        )
    for pat in SECRET_PATTERNS:
        if pat.search(text):
            violations.append(
                f"Row {row_num}: column '{column}' contains a possible secret pattern"
            )
    return violations


def _scan_privacy_csv(filepath):
    """Scan a local CSV file for privacy patterns without treating it
    as a pilot-results file.

    Returns a list of findings (row, column, pattern_type).
    Does NOT echo detected sensitive values.
    """
    path = Path(filepath)
    if not path.exists():
        return [{"error": f"File not found: {filepath}"}]

    findings = []
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            return [{"error": "File is empty or has no header row"}]

        for i, row in enumerate(reader, start=2):
            for col in reader.fieldnames:
                text = str(row.get(col, ""))
                if EMAIL_RE.search(text):
                    findings.append({"row": i, "column": col, "pattern": "email"})
                if ACCOUNT_NUMBER_RE.search(text):
                    findings.append({"row": i, "column": col, "pattern": "long_digit_sequence"})
                for pat in SECRET_PATTERNS:
                    if pat.search(text):
                        findings.append({"row": i, "column": col, "pattern": "secret"})
                        break

    return findings


def _is_real_row(parsed):
    """Determine whether a parsed row qualifies as real practitioner evidence.

    A real row is defined ONLY by:
    - data_origin = authorized_pseudonymized_historical
    - direct_reconciliation_experience = true
    - consent_received = true
    - real_participant_attestation = true
    - operator_attestation = true

    Validation failures (evidence_validation, review_ledger_validation) do
    NOT remove a row from the real sample.  They are reported as adverse
    cases and set the continuation gate to FAIL.
    """
    return (
        parsed.get("data_origin") == "authorized_pseudonymized_historical"
        and parsed.get("direct_reconciliation_experience") is True
        and parsed.get("consent_received") is True
        and parsed.get("real_participant_attestation") is True
        and parsed.get("operator_attestation") is True
    )


def _compute_block_aggregate(rows):
    """Compute aggregate metrics for a list of parsed rows (real or synthetic)."""
    agg = {}
    if not rows:
        return agg

    agg["case_count"] = len(rows)
    agg["practitioners"] = sorted(set(r["practitioner_id"] for r in rows))
    agg["practitioner_count"] = len(agg["practitioners"])
    agg["currencies_tested"] = sorted(set(r["currency"] for r in rows))
    agg["input_layouts"] = sorted(set(r["input_layout_id"] for r in rows))
    agg["input_layout_count"] = len(agg["input_layouts"])

    agg["total_deposits_processed"] = sum(r["deposits_processed"] for r in rows)
    agg["total_accepted_matches"] = sum(r["accepted_matches"] for r in rows)
    agg["total_review_exceptions"] = sum(r["review_exceptions"] for r in rows)
    agg["total_genuine_ambiguous_cases"] = sum(r["genuine_ambiguous_cases"] for r in rows)
    agg["total_false_automatic_allocations"] = sum(r["false_automatic_allocations"] for r in rows)

    # Candidate retention rate
    total_expected = sum(r["candidate_expected_cases"] for r in rows)
    total_retained = sum(r["correct_candidate_retained_cases"] for r in rows)
    if total_expected == 0:
        agg["candidate_retention_rate"] = None
        agg["candidate_retention_rate_note"] = "not applicable — zero candidate_expected_cases"
    else:
        agg["candidate_retention_rate"] = total_retained / total_expected

    # Validation pass rates
    agg["evidence_validation_pass_rate"] = sum(1 for r in rows if r["evidence_validation"]) / len(rows)
    agg["review_ledger_validation_pass_rate"] = sum(1 for r in rows if r["review_ledger_validation"]) / len(rows)

    # Adverse cases (validation failures)
    agg["evidence_failures"] = sum(1 for r in rows if not r["evidence_validation"])
    agg["review_ledger_failures"] = sum(1 for r in rows if not r["review_ledger_validation"])
    agg["adverse_cases"] = [
        {
            "pilot_case_id": r["pilot_case_id"],
            "practitioner_id": r["practitioner_id"],
            "evidence_validation": r["evidence_validation"],
            "review_ledger_validation": r["review_ledger_validation"],
            "false_automatic_allocations": r["false_automatic_allocations"],
        }
        for r in rows
        if not r["evidence_validation"]
        or not r["review_ledger_validation"]
        or r["false_automatic_allocations"] > 0
    ]

    # Repeat-use response distribution
    repeat_dist = {}
    for r in rows:
        resp = r.get("repeat_use_response", "undecided")
        repeat_dist[resp] = repeat_dist.get(resp, 0) + 1
    agg["repeat_use_response_counts"] = repeat_dist

    # Support signal distribution
    support_dist = {}
    for r in rows:
        sig = r.get("support_signal", "undecided")
        support_dist[sig] = support_dist.get(sig, 0) + 1
    agg["support_signal_counts"] = support_dist

    # Recommendation counts
    recommendations = {}
    for r in rows:
        recommendations[r["recommendation"]] = recommendations.get(r["recommendation"], 0) + 1
    agg["recommendation_counts"] = recommendations

    # Median review times — measured only
    measured_baseline = [
        r["review_minutes_baseline"]
        for r in rows
        if r.get("baseline_method", "").startswith("measured")
    ]
    measured_ledger = [
        r["review_minutes_with_ledgermatch"]
        for r in rows
        if r.get("baseline_method", "").startswith("measured")
    ]
    retrospective_baseline = [
        r["review_minutes_baseline"]
        for r in rows
        if r.get("baseline_method") == "retrospective_estimate"
    ]

    agg["median_review_minutes_baseline_measured"] = (
        statistics.median(measured_baseline) if measured_baseline else None
    )
    agg["median_review_minutes_with_ledgermatch_measured"] = (
        statistics.median(measured_ledger) if measured_ledger else None
    )
    agg["median_review_minutes_baseline_retrospective"] = (
        statistics.median(retrospective_baseline) if retrospective_baseline else None
    )
    agg["retrospective_estimates_reported_separately"] = bool(retrospective_baseline)

    # Per-practitioner median times
    practitioner_times = {}
    for r in rows:
        pid = r["practitioner_id"]
        if pid not in practitioner_times:
            practitioner_times[pid] = {"baseline_measured": [], "ledger_measured": []}
        if r.get("baseline_method", "").startswith("measured"):
            practitioner_times[pid]["baseline_measured"].append(r["review_minutes_baseline"])
            practitioner_times[pid]["ledger_measured"].append(r["review_minutes_with_ledgermatch"])
    agg["per_practitioner_median_times"] = {}
    for pid in sorted(practitioner_times):
        times = practitioner_times[pid]
        entry = {}
        if times["baseline_measured"]:
            entry["median_baseline_measured"] = statistics.median(times["baseline_measured"])
            entry["median_ledger_measured"] = statistics.median(times["ledger_measured"])
        if entry:
            agg["per_practitioner_median_times"][pid] = entry

    return agg


def validate_csv(filepath):
    """Validate a pilot-results CSV file.

    Returns a dict with:
      - errors: list of error strings (empty if valid)
      - warnings: list of warning strings
      - aggregate: dict with .real, .synthetic, .combined blocks
      - continuation_gate: 'PENDING' | 'FAIL' | 'PASS'
      - overall_status: 'INSUFFICIENT_SAMPLE' | 'KILL_CONDITION' | 'SAMPLE_MET'
      - sample_requirements: dict of requirement status
      - row_count: number of data rows
      - schema_version: current schema version string
      - privacy_note: heuristic scanning disclaimer
    """
    errors = []
    warnings = []
    rows = []

    path = Path(filepath)
    if not path.exists():
        return {
            "errors": [f"File not found: {filepath}"],
            "warnings": [],
            "aggregate": {},
            "continuation_gate": "PENDING",
            "overall_status": "INSUFFICIENT_SAMPLE",
            "sample_requirements": {},
            "row_count": 0,
            "schema_version": SCHEMA_VERSION,
            "privacy_note": "Privacy scanning is heuristic and does not prove de-identification.",
        }

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            errors.append("File is empty or has no header row")
            return {
                "errors": errors,
                "warnings": warnings,
                "aggregate": {},
                "continuation_gate": "PENDING",
                "overall_status": "INSUFFICIENT_SAMPLE",
                "sample_requirements": {},
                "row_count": 0,
                "schema_version": SCHEMA_VERSION,
                "privacy_note": "Privacy scanning is heuristic and does not prove de-identification.",
            }

        # Check required columns
        missing = [c for c in REQUIRED_COLUMNS if c not in reader.fieldnames]
        if missing:
            errors.append(f"Missing required columns: {', '.join(missing)}")
            return {
                "errors": errors,
                "warnings": warnings,
                "aggregate": {},
                "continuation_gate": "PENDING",
                "overall_status": "INSUFFICIENT_SAMPLE",
                "sample_requirements": {},
                "row_count": 0,
                "schema_version": SCHEMA_VERSION,
                "privacy_note": "Privacy scanning is heuristic and does not prove de-identification.",
            }

        # Check for extra columns (warning, not error)
        extra = [c for c in reader.fieldnames if c not in REQUIRED_COLUMNS]
        if extra:
            warnings.append(f"Extra columns present: {', '.join(extra)}")

        seen_case_ids = set()
        seen_session_ids = set()
        for i, row in enumerate(reader, start=2):
            row_errors = []

            # Check for empty required fields
            for col in REQUIRED_COLUMNS:
                if col not in row or str(row[col]).strip() == "":
                    if col != "notes":
                        row_errors.append(f"Row {i}: column '{col}' is empty")

            if row_errors:
                errors.extend(row_errors)
                continue

            # Check for duplicate pilot_case_id
            case_id = row["pilot_case_id"].strip()
            if case_id in seen_case_ids:
                errors.append(f"Row {i}: duplicate pilot_case_id")
            seen_case_ids.add(case_id)

            # Check for duplicate session_id
            session_id = row["session_id"].strip()
            if session_id in seen_session_ids:
                errors.append(f"Row {i}: duplicate session_id")
            seen_session_ids.add(session_id)

            # Validate currency
            currency = row["currency"].strip().upper()
            if currency not in VALID_CURRENCIES:
                errors.append(f"Row {i}: unsupported currency")

            # Validate integers
            parsed = {}
            for col in INTEGER_COLUMNS:
                try:
                    val = _parse_int(row[col], col, i)
                except ValidationError as e:
                    errors.append(str(e))
                    val = 0
                parsed[col] = val
                if val < 0:
                    errors.append(f"Row {i}: column '{col}' has negative value")

            # Validate booleans
            for col in BOOLEAN_COLUMNS:
                try:
                    parsed[col] = _parse_bool(row[col], col, i)
                except ValidationError as e:
                    errors.append(str(e))
                    parsed[col] = False

            # Validate enum fields
            for col, allowed in ENUM_COLUMNS.items():
                val = row[col].strip().lower()
                if val not in allowed:
                    errors.append(f"Row {i}: column '{col}' has invalid value")
                parsed[col] = val

            # Validate input_layout_id is non-empty
            layout_id = row["input_layout_id"].strip()
            if not layout_id:
                errors.append(f"Row {i}: column 'input_layout_id' is empty")
            parsed["input_layout_id"] = layout_id

            # Validation invariants
            dp = parsed.get("deposits_processed", 0)
            am = parsed.get("accepted_matches", 0)
            re_exc = parsed.get("review_exceptions", 0)
            ga = parsed.get("genuine_ambiguous_cases", 0)
            faa = parsed.get("false_automatic_allocations", 0)
            cec = parsed.get("candidate_expected_cases", 0)
            crc = parsed.get("correct_candidate_retained_cases", 0)

            if am + re_exc != dp:
                errors.append(
                    f"Row {i}: accepted_matches + review_exceptions does not equal deposits_processed"
                )
            if ga > re_exc:
                errors.append(f"Row {i}: genuine_ambiguous_cases exceeds review_exceptions")
            if faa > am:
                errors.append(f"Row {i}: false_automatic_allocations exceeds accepted_matches")
            if crc > cec:
                errors.append(f"Row {i}: correct_candidate_retained_cases exceeds candidate_expected_cases")

            # Privacy checks — email+secret on all text fields, digit scan only on free-text
            for col in TEXT_FIELDS_EMAIL_SECRET:
                text = str(row.get(col, ""))
                violations = _check_privacy(text, i, col, scan_digits=False)
                errors.extend(violations)
            for col in TEXT_FIELDS_DIGIT_SCAN:
                text = str(row.get(col, ""))
                violations = _check_privacy(text, i, col, scan_digits=True)
                errors.extend(violations)

            parsed["pilot_case_id"] = case_id
            parsed["practitioner_id"] = row["practitioner_id"].strip()
            parsed["session_id"] = session_id
            parsed["role_category"] = row["role_category"].strip()
            parsed["currency"] = currency
            parsed["notes"] = row.get("notes", "").strip()
            rows.append(parsed)

    # Separate real and synthetic rows
    real_rows = [r for r in rows if _is_real_row(r)]
    synthetic_rows = [r for r in rows if not _is_real_row(r)]

    # Check for practitioner_id spanning both synthetic and real
    real_pids = set(r["practitioner_id"] for r in real_rows)
    synthetic_pids = set(r["practitioner_id"] for r in synthetic_rows)
    shared_pids = real_pids & synthetic_pids
    if shared_pids:
        for pid in sorted(shared_pids):
            warnings.append(
                f"practitioner_id '{pid}' appears with both synthetic and real data_origin"
            )

    # Compute aggregate blocks
    aggregate = {
        "real": _compute_block_aggregate(real_rows),
        "synthetic": _compute_block_aggregate(synthetic_rows),
        "combined": _compute_block_aggregate(rows),
    }

    # Sample requirements from REAL rows only
    real_agg = aggregate["real"]
    real_case_count = real_agg.get("case_count", 0)
    real_prac_count = real_agg.get("practitioner_count", 0)
    real_ambiguous = real_agg.get("total_genuine_ambiguous_cases", 0)
    real_layout_count = real_agg.get("input_layout_count", 0)
    real_currencies = real_agg.get("currencies_tested", [])

    # Ambiguous-case contributors: distinct real practitioners with genuine_ambiguous_cases > 0
    ambiguous_contributors = set(
        r["practitioner_id"]
        for r in real_rows
        if r["genuine_ambiguous_cases"] > 0
    )

    # Single-practitioner concentration
    if real_case_count > 0:
        prac_case_counts = {}
        for r in real_rows:
            prac_case_counts[r["practitioner_id"]] = prac_case_counts.get(r["practitioner_id"], 0) + 1
        max_share = max(prac_case_counts.values()) / real_case_count
    else:
        max_share = 0.0

    sample_requirements = {
        "min_practitioners": {
            "required": MIN_PRACTITIONERS,
            "actual": real_prac_count,
            "met": real_prac_count >= MIN_PRACTITIONERS,
        },
        "min_historical_cases": {
            "required": MIN_HISTORICAL_CASES,
            "actual": real_case_count,
            "met": real_case_count >= MIN_HISTORICAL_CASES,
        },
        "min_ambiguous_cases": {
            "required": MIN_AMBIGUOUS_CASES,
            "actual": real_ambiguous,
            "met": real_ambiguous >= MIN_AMBIGUOUS_CASES,
        },
        "min_input_layouts": {
            "required": MIN_INPUT_LAYOUTS,
            "actual": real_layout_count,
            "met": real_layout_count >= MIN_INPUT_LAYOUTS,
        },
        "min_currencies": {
            "required": MIN_CURRENCIES,
            "actual": len(real_currencies),
            "met": len(real_currencies) >= MIN_CURRENCIES,
        },
        "min_practitioners_contributing_ambiguous_cases": {
            "required": MIN_AMBIGUOUS_CONTRIBUTORS,
            "actual": len(ambiguous_contributors),
            "met": len(ambiguous_contributors) >= MIN_AMBIGUOUS_CONTRIBUTORS,
        },
        "max_single_practitioner_case_share": {
            "limit": MAX_SINGLE_PRACTITIONER_SHARE,
            "actual": max_share,
            "met": max_share <= MAX_SINGLE_PRACTITIONER_SHARE,
        },
    }

    # Continuation gate — three-state
    has_kill = False
    total_false = real_agg.get("total_false_automatic_allocations", 0)
    if total_false > 0:
        has_kill = True
        errors.append("CONTINUATION GATE FAILED: false automatic allocation(s) found. Zero tolerance.")
    if real_agg.get("evidence_failures", 0) > 0:
        has_kill = True
        errors.append("CONTINUATION GATE FAILED: evidence validation failed for one or more real cases.")
    if real_agg.get("review_ledger_failures", 0) > 0:
        has_kill = True
        errors.append("CONTINUATION GATE FAILED: review-ledger validation failed for one or more real cases.")

    # Also check synthetic rows for kill conditions (they still fail the gate)
    synth_false = synthetic_agg_total_false = aggregate["synthetic"].get("total_false_automatic_allocations", 0)
    if synth_false > 0:
        has_kill = True
        errors.append("CONTINUATION GATE FAILED: false automatic allocation(s) found in synthetic rows.")

    if has_kill:
        continuation_gate = "FAIL"
    elif real_case_count == 0:
        continuation_gate = "PENDING"
    else:
        continuation_gate = "PASS"

    # Overall status
    all_samples_met = all(sr["met"] for sr in sample_requirements.values())
    if has_kill:
        overall_status = "KILL_CONDITION"
    elif all_samples_met and continuation_gate == "PASS":
        overall_status = "SAMPLE_MET"
    else:
        overall_status = "INSUFFICIENT_SAMPLE"

    return {
        "errors": errors,
        "warnings": warnings,
        "aggregate": aggregate,
        "continuation_gate": continuation_gate,
        "overall_status": overall_status,
        "sample_requirements": sample_requirements,
        "row_count": len(rows),
        "schema_version": SCHEMA_VERSION,
        "privacy_note": "Privacy scanning is heuristic and does not prove de-identification.",
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/verify_pilot_result.py <results.csv>")
        print("       python3 scripts/verify_pilot_result.py --check-privacy <file.csv>")
        sys.exit(2)

    if sys.argv[1] == "--check-privacy":
        if len(sys.argv) < 3:
            print("Usage: python3 scripts/verify_pilot_result.py --check-privacy <file.csv>")
            sys.exit(2)
        filepath = sys.argv[2]
        findings = _scan_privacy_csv(filepath)
        print(json.dumps({
            "findings": findings,
            "note": "Regex scanning does not prove de-identification.",
        }, indent=2))
        if any("error" in f for f in findings):
            sys.exit(1)
        if findings:
            sys.exit(1)
        sys.exit(0)

    filepath = sys.argv[1]
    result = validate_csv(filepath)

    print(json.dumps(result, indent=2, default=str))

    if result["errors"]:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
