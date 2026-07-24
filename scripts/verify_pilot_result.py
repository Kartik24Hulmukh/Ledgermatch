#!/usr/bin/env python3
"""Pilot result validator for LedgerMatch private pilot.

Validates pilot-results CSV files against the required schema, checks for
privacy violations, computes aggregate factual metrics, and enforces the
continuation gate (false automatic allocations must be zero).

Uses only the Python standard library.
"""

import csv
import json
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path

REQUIRED_COLUMNS = [
    "pilot_case_id",
    "practitioner_id",
    "currency",
    "deposits_processed",
    "accepted_matches",
    "review_exceptions",
    "false_automatic_allocations",
    "correct_candidate_retained",
    "review_minutes_before",
    "review_minutes_with_ledgermatch",
    "evidence_validation",
    "review_ledger_validation",
    "repeat_use_requested",
    "recommendation",
    "payment_or_contribution_signal",
    "notes",
]

INTEGER_COLUMNS = {
    "deposits_processed",
    "accepted_matches",
    "review_exceptions",
    "false_automatic_allocations",
    "review_minutes_before",
    "review_minutes_with_ledgermatch",
}

BOOLEAN_COLUMNS = {
    "correct_candidate_retained",
    "evidence_validation",
    "review_ledger_validation",
    "repeat_use_requested",
}

VALID_CURRENCIES = {
    "USD", "EUR", "GBP", "INR", "JPY", "CAD", "AUD", "CHF", "CNY",
    "SGD", "HKD", "NZD", "SEK", "NOK", "DKK", "MXN", "BRL", "ZAR",
    "AED", "SAR",
}

VALID_RECOMMENDATIONS = {"recommend", "neutral", "do_not_recommend"}

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
            f"value '{value}'"
        )
    return iv


def _parse_bool(value, column, row_num):
    vl = str(value).strip().lower()
    if vl in ("true", "1", "yes"):
        return True
    if vl in ("false", "0", "no"):
        return False
    raise ValidationError(
        f"Row {row_num}: column '{column}' has malformed boolean "
        f"value '{value}'"
    )


def _check_privacy(text, row_num, column):
    """Scan free-text fields for obvious privacy violations."""
    violations = []
    if EMAIL_RE.search(text):
        violations.append(
            f"Row {row_num}: column '{column}' contains an email address"
        )
    if ACCOUNT_NUMBER_RE.search(text):
        violations.append(
            f"Row {row_num}: column '{column}' contains a long digit "
            f"sequence (possible account number)"
        )
    for pat in SECRET_PATTERNS:
        if pat.search(text):
            violations.append(
                f"Row {row_num}: column '{column}' contains a possible "
                f"secret pattern"
            )
    return violations


def validate_csv(filepath):
    """Validate a pilot-results CSV file.

    Returns a dict with:
      - errors: list of error strings (empty if valid)
      - warnings: list of warning strings
      - aggregate: dict of aggregate factual metrics
      - continuation_gate: 'PASS' or 'FAIL'
      - sample_requirements: dict of requirement status
      - row_count: number of data rows
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
                    if col not in ("payment_or_contribution_signal", "notes"):
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
                    f"Row {i}: duplicate pilot_case_id '{case_id}'"
                )
            seen_ids.add(case_id)

            # Validate currency
            currency = row["currency"].strip().upper()
            if currency not in VALID_CURRENCIES:
                errors.append(
                    f"Row {i}: unsupported currency '{row['currency']}'"
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
                        f"Row {i}: column '{col}' has negative value {val}"
                    )

            # Validate booleans
            for col in BOOLEAN_COLUMNS:
                try:
                    parsed[col] = _parse_bool(row[col], col, i)
                except ValidationError as e:
                    errors.append(str(e))
                    parsed[col] = False

            # Validate recommendation
            rec = row["recommendation"].strip().lower()
            if rec not in VALID_RECOMMENDATIONS:
                errors.append(
                    f"Row {i}: invalid recommendation '{row['recommendation']}'"
                )

            # Privacy checks on free-text fields
            for col in ("notes", "payment_or_contribution_signal"):
                text = row.get(col, "")
                violations = _check_privacy(text, i, col)
                errors.extend(violations)

            parsed["pilot_case_id"] = case_id
            parsed["practitioner_id"] = row["practitioner_id"].strip()
            parsed["currency"] = currency
            parsed["recommendation"] = rec
            parsed["payment_or_contribution_signal"] = row.get(
                "payment_or_contribution_signal", ""
            ).strip()
            parsed["notes"] = row.get("notes", "").strip()
            rows.append(parsed)

    # Compute aggregate metrics
    aggregate = {}
    if rows:
        aggregate["total_cases"] = len(rows)
        aggregate["unique_practitioners"] = len(
            set(r["practitioner_id"] for r in rows)
        )
        aggregate["currencies_tested"] = sorted(
            set(r["currency"] for r in rows)
        )
        aggregate["total_deposits_processed"] = sum(
            r["deposits_processed"] for r in rows
        )
        aggregate["total_accepted_matches"] = sum(
            r["accepted_matches"] for r in rows
        )
        aggregate["total_review_exceptions"] = sum(
            r["review_exceptions"] for r in rows
        )
        aggregate["total_false_automatic_allocations"] = sum(
            r["false_automatic_allocations"] for r in rows
        )
        aggregate["correct_candidate_retention_rate"] = (
            sum(1 for r in rows if r["correct_candidate_retained"])
            / len(rows)
        )
        aggregate["evidence_validation_pass_rate"] = (
            sum(1 for r in rows if r["evidence_validation"])
            / len(rows)
        )
        aggregate["review_ledger_validation_pass_rate"] = (
            sum(1 for r in rows if r["review_ledger_validation"])
            / len(rows)
        )
        aggregate["repeat_use_request_rate"] = (
            sum(1 for r in rows if r["repeat_use_requested"])
            / len(rows)
        )
        aggregate["avg_review_minutes_before"] = (
            sum(r["review_minutes_before"] for r in rows) / len(rows)
        )
        aggregate["avg_review_minutes_with_ledgermatch"] = (
            sum(r["review_minutes_with_ledgermatch"] for r in rows)
            / len(rows)
        )
        recommendations = {}
        for r in rows:
            recommendations[r["recommendation"]] = (
                recommendations.get(r["recommendation"], 0) + 1
            )
        aggregate["recommendation_counts"] = recommendations

    # Check sample requirements
    sample_requirements = {
        "min_practitioners": {
            "required": MIN_PRACTITIONERS,
            "actual": aggregate.get("unique_practitioners", 0),
            "met": aggregate.get("unique_practitioners", 0) >= MIN_PRACTITIONERS,
        },
        "min_historical_cases": {
            "required": MIN_HISTORICAL_CASES,
            "actual": aggregate.get("total_cases", 0),
            "met": aggregate.get("total_cases", 0) >= MIN_HISTORICAL_CASES,
        },
        "min_ambiguous_cases": {
            "required": MIN_AMBIGUOUS_CASES,
            "actual": aggregate.get("total_review_exceptions", 0),
            "met": aggregate.get("total_review_exceptions", 0)
            >= MIN_AMBIGUOUS_CASES,
        },
        "min_input_layouts": {
            "required": MIN_INPUT_LAYOUTS,
            "actual": len(aggregate.get("currencies_tested", [])),
            "met": len(aggregate.get("currencies_tested", []))
            >= MIN_INPUT_LAYOUTS,
        },
    }

    # Continuation gate: fail if any false automatic allocations
    total_false = aggregate.get("total_false_automatic_allocations", 0)
    if total_false > 0:
        continuation_gate = "FAIL"
        errors.append(
            f"CONTINUATION GATE FAILED: {total_false} false automatic "
            f"allocation(s) found. Zero tolerance."
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
    }


def main():
    if len(sys.argv) < 2:
        print("Usage: python3 scripts/verify_pilot_result.py <results.csv>")
        sys.exit(2)

    filepath = sys.argv[1]
    result = validate_csv(filepath)

    print(json.dumps(result, indent=2, default=str))

    if result["errors"]:
        sys.exit(1)
    else:
        sys.exit(0)


if __name__ == "__main__":
    main()
