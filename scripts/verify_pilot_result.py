#!/usr/bin/env python3
"""Pilot result validator for LedgerMatch private pilot.

Validates pilot-results CSV files against the required schema, checks for
privacy violations, computes aggregate factual metrics, and enforces the
continuation gate (false automatic allocations must be zero).

Uses only the Python standard library.

Schema version: 2.0
"""

import csv
import json
import re
import statistics
import sys
from pathlib import Path

SCHEMA_VERSION = "2.0"

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

# Text-capable fields for privacy scanning
TEXT_FIELDS = [
    "pilot_case_id",
    "session_id",
    "practitioner_id",
    "role_category",
    "input_layout_id",
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


class ValidationError(Exception):
    pass


def _parse_int(value, column, row_num):
    try:
        iv = int(value)
    except (ValueError, TypeError):
        raise ValidationError(
            f"Row {row_num}: column '{column}' has malformed integer "
            f"value"
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


def _check_privacy(text, row_num, column):
    """Scan text for obvious privacy violations.

    Does NOT echo detected sensitive values in error messages.
    Does NOT claim that regex scanning proves de-identification.
    """
    violations = []
    if EMAIL_RE.search(text):
        violations.append(
            f"Row {row_num}: column '{column}' contains a possible "
            f"email pattern"
        )
    if ACCOUNT_NUMBER_RE.search(text):
        violations.append(
            f"Row {row_num}: column '{column}' contains a possible "
            f"long digit sequence"
        )
    for pat in SECRET_PATTERNS:
        if pat.search(text):
            violations.append(
                f"Row {row_num}: column '{column}' contains a possible "
                f"secret pattern"
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
                    findings.append(
                        {"row": i, "column": col, "pattern": "email"}
                    )
                if ACCOUNT_NUMBER_RE.search(text):
                    findings.append(
                        {"row": i, "column": col, "pattern": "long_digit_sequence"}
                    )
                for pat in SECRET_PATTERNS:
                    if pat.search(text):
                        findings.append(
                            {"row": i, "column": col, "pattern": "secret"}
                        )
                        break

    return findings


def _is_real_row(parsed):
    """Determine whether a parsed row qualifies as real practitioner evidence."""
    return (
        parsed.get("data_origin") == "authorized_pseudonymized_historical"
        and parsed.get("direct_reconciliation_experience") is True
        and parsed.get("consent_received") is True
        and parsed.get("real_participant_attestation") is True
        and parsed.get("operator_attestation") is True
        and parsed.get("evidence_validation") is True
        and parsed.get("review_ledger_validation") is True
    )


def validate_csv(filepath):
    """Validate a pilot-results CSV file.

    Returns a dict with:
      - errors: list of error strings (empty if valid)
      - warnings: list of warning strings
      - aggregate: dict of aggregate factual metrics
      - continuation_gate: 'PASS' or 'FAIL'
      - sample_requirements: dict of requirement status
      - row_count: number of data rows
      - schema_version: current schema version string
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
            "continuation_gate": "FAIL",
            "sample_requirements": {},
            "row_count": 0,
            "schema_version": SCHEMA_VERSION,
        }

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames is None:
            errors.append("File is empty or has no header row")
            return {
                "errors": errors,
                "warnings": warnings,
                "aggregate": {},
                "continuation_gate": "FAIL",
                "sample_requirements": {},
                "row_count": 0,
                "schema_version": SCHEMA_VERSION,
            }

        # Check required columns
        missing = [c for c in REQUIRED_COLUMNS if c not in reader.fieldnames]
        if missing:
            errors.append(f"Missing required columns: {', '.join(missing)}")
            return {
                "errors": errors,
                "warnings": warnings,
                "aggregate": {},
                "continuation_gate": "FAIL",
                "sample_requirements": {},
                "row_count": 0,
                "schema_version": SCHEMA_VERSION,
            }

        # Check for extra columns (warning, not error)
        extra = [c for c in reader.fieldnames if c not in REQUIRED_COLUMNS]
        if extra:
            warnings.append(f"Extra columns present: {', '.join(extra)}")

        seen_ids = set()
        for i, row in enumerate(reader, start=2):
            row_errors = []

            # Check for empty required fields
            for col in REQUIRED_COLUMNS:
                if col not in row or str(row[col]).strip() == "":
                    if col != "notes":
                        row_errors.append(
                            f"Row {i}: column '{col}' is empty"
                        )

            if row_errors:
                errors.extend(row_errors)
                continue

            # Check for duplicate pilot_case_id
            case_id = row["pilot_case_id"].strip()
            if case_id in seen_ids:
                errors.append(
                    f"Row {i}: duplicate pilot_case_id"
                )
            seen_ids.add(case_id)

            # Validate currency
            currency = row["currency"].strip().upper()
            if currency not in VALID_CURRENCIES:
                errors.append(
                    f"Row {i}: unsupported currency"
                )

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
                    errors.append(
                        f"Row {i}: column '{col}' has negative value"
                    )

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
                    errors.append(
                        f"Row {i}: column '{col}' has invalid value"
                    )
                parsed[col] = val

            # Validate input_layout_id is non-empty
            layout_id = row["input_layout_id"].strip()
            if not layout_id:
                errors.append(
                    f"Row {i}: column 'input_layout_id' is empty"
                )
            parsed["input_layout_id"] = layout_id

            # Validation invariants
            dp = parsed.get("deposits_processed", 0)
            am = parsed.get("accepted_matches", 0)
            re_exc = parsed.get("review_exceptions", 0)
            ga = parsed.get("genuine_ambiguous_cases", 0)
            faa = parsed.get("false_automatic_allocations", 0)
            cec = parsed.get("candidate_expected_cases", 0)
            crc = parsed.get("correct_candidate_retained_cases", 0)

            # accepted_matches + review_exceptions must equal deposits_processed
            if am + re_exc != dp:
                errors.append(
                    f"Row {i}: accepted_matches + review_exceptions "
                    f"does not equal deposits_processed"
                )

            # genuine_ambiguous_cases must not exceed review_exceptions
            if ga > re_exc:
                errors.append(
                    f"Row {i}: genuine_ambiguous_cases exceeds "
                    f"review_exceptions"
                )

            # false_automatic_allocations must not exceed accepted_matches
            if faa > am:
                errors.append(
                    f"Row {i}: false_automatic_allocations exceeds "
                    f"accepted_matches"
                )

            # correct_candidate_retained_cases must not exceed candidate_expected_cases
            if crc > cec:
                errors.append(
                    f"Row {i}: correct_candidate_retained_cases exceeds "
                    f"candidate_expected_cases"
                )

            # Privacy checks on ALL text-capable fields
            for col in TEXT_FIELDS:
                text = str(row.get(col, ""))
                violations = _check_privacy(text, i, col)
                errors.extend(violations)

            parsed["pilot_case_id"] = case_id
            parsed["practitioner_id"] = row["practitioner_id"].strip()
            parsed["session_id"] = row["session_id"].strip()
            parsed["role_category"] = row["role_category"].strip()
            parsed["currency"] = currency
            parsed["notes"] = row.get("notes", "").strip()
            rows.append(parsed)

    # Separate real and synthetic rows
    real_rows = [r for r in rows if _is_real_row(r)]
    synthetic_rows = [r for r in rows if not _is_real_row(r)]

    # Compute aggregate metrics from ALL rows
    aggregate = {}
    if rows:
        aggregate["total_cases"] = len(rows)
        aggregate["real_cases"] = len(real_rows)
        aggregate["synthetic_cases"] = len(synthetic_rows)

        # Real practitioner counts from qualifying real rows only
        real_practitioners = set(r["practitioner_id"] for r in real_rows)
        aggregate["real_practitioners"] = len(real_practitioners)

        # Real historical cases from qualifying real rows only
        aggregate["real_historical_cases"] = len(real_rows)

        # Genuine ambiguous cases from explicit field in real rows
        aggregate["real_genuine_ambiguous_cases"] = sum(
            r["genuine_ambiguous_cases"] for r in real_rows
        )

        # Input layouts from unique input_layout_id in real rows
        real_layouts = set(r["input_layout_id"] for r in real_rows)
        aggregate["real_input_layouts"] = len(real_layouts)

        # Currencies from unique currency in real rows
        aggregate["real_currencies_tested"] = sorted(
            set(r["currency"] for r in real_rows)
        )

        # Totals across all rows
        aggregate["total_deposits_processed"] = sum(
            r["deposits_processed"] for r in rows
        )
        aggregate["total_accepted_matches"] = sum(
            r["accepted_matches"] for r in rows
        )
        aggregate["total_review_exceptions"] = sum(
            r["review_exceptions"] for r in rows
        )
        aggregate["total_genuine_ambiguous_cases"] = sum(
            r["genuine_ambiguous_cases"] for r in rows
        )
        aggregate["total_false_automatic_allocations"] = sum(
            r["false_automatic_allocations"] for r in rows
        )

        # Candidate retention rate: sum(retained) / sum(expected)
        total_expected = sum(r["candidate_expected_cases"] for r in rows)
        total_retained = sum(r["correct_candidate_retained_cases"] for r in rows)
        if total_expected == 0:
            aggregate["candidate_retention_rate"] = None
            aggregate["candidate_retention_rate_note"] = (
                "not applicable — zero candidate_expected_cases"
            )
        else:
            aggregate["candidate_retention_rate"] = (
                total_retained / total_expected
            )

        # Validation pass rates
        aggregate["evidence_validation_pass_rate"] = (
            sum(1 for r in rows if r["evidence_validation"]) / len(rows)
        )
        aggregate["review_ledger_validation_pass_rate"] = (
            sum(1 for r in rows if r["review_ledger_validation"]) / len(rows)
        )

        # Repeat-use response distribution
        repeat_dist = {}
        for r in rows:
            resp = r.get("repeat_use_response", "undecided")
            repeat_dist[resp] = repeat_dist.get(resp, 0) + 1
        aggregate["repeat_use_response_counts"] = repeat_dist

        # Support signal distribution
        support_dist = {}
        for r in rows:
            sig = r.get("support_signal", "undecided")
            support_dist[sig] = support_dist.get(sig, 0) + 1
        aggregate["support_signal_counts"] = support_dist

        # Median review times (measured only, excluding retrospective estimates)
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

        if measured_baseline:
            aggregate["median_review_minutes_baseline_measured"] = (
                statistics.median(measured_baseline)
            )
        else:
            aggregate["median_review_minutes_baseline_measured"] = None

        if measured_ledger:
            aggregate["median_review_minutes_with_ledgermatch_measured"] = (
                statistics.median(measured_ledger)
            )
        else:
            aggregate["median_review_minutes_with_ledgermatch_measured"] = None

        if retrospective_baseline:
            aggregate["median_review_minutes_baseline_retrospective"] = (
                statistics.median(retrospective_baseline)
            )
            aggregate["retrospective_estimates_reported_separately"] = True
        else:
            aggregate["median_review_minutes_baseline_retrospective"] = None
            aggregate["retrospective_estimates_reported_separately"] = False

        # Per-practitioner median times (if sufficient data)
        practitioner_times = {}
        for r in rows:
            pid = r["practitioner_id"]
            if pid not in practitioner_times:
                practitioner_times[pid] = {
                    "baseline_measured": [],
                    "ledger_measured": [],
                }
            if r.get("baseline_method", "").startswith("measured"):
                practitioner_times[pid]["baseline_measured"].append(
                    r["review_minutes_baseline"]
                )
                practitioner_times[pid]["ledger_measured"].append(
                    r["review_minutes_with_ledgermatch"]
                )
        aggregate["per_practitioner_median_times"] = {}
        for pid, times in practitioner_times.items():
            entry = {}
            if times["baseline_measured"]:
                entry["median_baseline_measured"] = statistics.median(
                    times["baseline_measured"]
                )
                entry["median_ledger_measured"] = statistics.median(
                    times["ledger_measured"]
                )
            if entry:
                aggregate["per_practitioner_median_times"][pid] = entry

        # Recommendation counts
        recommendations = {}
        for r in rows:
            recommendations[r["recommendation"]] = (
                recommendations.get(r["recommendation"], 0) + 1
            )
        aggregate["recommendation_counts"] = recommendations

    # Check sample requirements from REAL rows only
    sample_requirements = {
        "min_practitioners": {
            "required": MIN_PRACTITIONERS,
            "actual": aggregate.get("real_practitioners", 0),
            "met": aggregate.get("real_practitioners", 0) >= MIN_PRACTITIONERS,
        },
        "min_historical_cases": {
            "required": MIN_HISTORICAL_CASES,
            "actual": aggregate.get("real_historical_cases", 0),
            "met": aggregate.get("real_historical_cases", 0)
            >= MIN_HISTORICAL_CASES,
        },
        "min_ambiguous_cases": {
            "required": MIN_AMBIGUOUS_CASES,
            "actual": aggregate.get("real_genuine_ambiguous_cases", 0),
            "met": aggregate.get("real_genuine_ambiguous_cases", 0)
            >= MIN_AMBIGUOUS_CASES,
        },
        "min_input_layouts": {
            "required": MIN_INPUT_LAYOUTS,
            "actual": aggregate.get("real_input_layouts", 0),
            "met": aggregate.get("real_input_layouts", 0)
            >= MIN_INPUT_LAYOUTS,
        },
    }

    # Continuation gate: fail if any false automatic allocations
    total_false = aggregate.get("total_false_automatic_allocations", 0)
    if total_false > 0:
        continuation_gate = "FAIL"
        errors.append(
            f"CONTINUATION GATE FAILED: false automatic allocation(s) "
            f"found. Zero tolerance."
        )
    elif any(not r["evidence_validation"] for r in rows):
        continuation_gate = "FAIL"
        errors.append(
            "CONTINUATION GATE FAILED: evidence validation failed for "
            "one or more cases."
        )
    elif any(not r["review_ledger_validation"] for r in rows):
        continuation_gate = "FAIL"
        errors.append(
            "CONTINUATION GATE FAILED: review-ledger validation failed "
            "for one or more cases."
        )
    else:
        continuation_gate = "PASS"

    return {
        "errors": errors,
        "warnings": warnings,
        "aggregate": aggregate,
        "continuation_gate": continuation_gate,
        "sample_requirements": sample_requirements,
        "row_count": len(rows),
        "schema_version": SCHEMA_VERSION,
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
        print(json.dumps({"findings": findings, "note": "Regex scanning does not prove de-identification."}, indent=2))
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
