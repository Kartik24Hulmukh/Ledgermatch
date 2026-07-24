# LedgerMatch

LedgerMatch is a local, review-first engine for matching bank deposits to open invoices. It preserves ambiguity instead of silently choosing among equal or competing combinations and emits a deterministic Reconciliation Evidence Bundle for replay and review.

## Status

This repository is a release candidate for local technical evaluation. It is not a hosted upload service, accounting system of record, audit opinion, or substitute for practitioner review. Hosted CI and real-practitioner shadow runs remain external gates.

## Distinctive scope

- deterministic reference, customer, amount, and bounded subset matching;
- no automatic acceptance when multiple exact allocations exist;
- explicit currency, precision, date profile, solver status, and residual policy;
- stable source-row identities and invoice exclusivity;
- deterministic evidence JSON with input hashes and tamper validation;
- spreadsheet-formula neutralization and HTML escaping;
- loopback-only web UI with restrictive browser headers;
- optional AI advisory disabled by default and never authoritative.

## Quick start

```bash
python3 -m app.cli --bank demo_data/bank_statement.csv \
  --invoices demo_data/invoices.csv --out out_demo \
  --currency USD --date-format YMD
```

Local web review:

```bash
python3 -m app.server --host 127.0.0.1 --port 8080
```

Run verification:

```bash
python3 scripts/verify_release.py
```

Build the deterministic source archive:

```bash
python3 scripts/build_release.py --output dist/LedgerMatch-0.4.0-review-ledger.zip
```

## Input contract

The CLI requires an explicit three-letter currency and one date profile:

- `YMD`: `YYYY-MM-DD` or `YYYY/MM/DD`
- `DMY`: day-first formats
- `MDY`: month-first formats

Amounts must use an unambiguous dot decimal and fit the configured precision. One run cannot mix currencies. Duplicate normalized invoice numbers are rejected.

## Outputs

- `matches.csv`: uniquely supported accepted allocations;
- `exceptions.csv`: unresolved, ambiguous, residual-bearing, and invalid candidates;
- `unpaid_invoices.csv`: remaining open invoices;
- `payments_import.csv`: reviewable file handoff, not API writeback;
- `report.html`: escaped local review report;
- `evidence.json`: deterministic Reconciliation Evidence Bundle;
- `evidence.sha256`: output-file digest;
- `profile.json`: replayable currency, date, precision, and tolerance settings.

Validate a bundle independently:

```bash
python3 -m app.validate out_demo/evidence.json --checksum out_demo/evidence.sha256
```

`evidence.json` uses stable internal canonical JSON for hashing. The project does not claim RFC 8785 compliance until official vectors are added.

## Human review ledger

Exception decisions can be recorded without mutating the original evidence bundle:

```bash
python3 -m app.review create \\
  --evidence out_demo/evidence.json \\
  --decisions decisions.json \\
  --out review.ndjson

python3 -m app.review verify \\
  --evidence out_demo/evidence.json \\
  --review review.ndjson \\
  --receipt review.ndjson.receipt.json
```

Allowed decisions are `approve_exact`, `reject`, and `defer`. Manual approval still requires exact conservation, same currency, an unpaid evidence invoice, and no invoice reuse. The SHA-256 chain detects alteration relative to its current head; it does not prevent a storage owner from rewriting both the chain and an unanchored head.

## Matching policy

1. Exact referenced invoice totals.
2. Unique exact subset of referenced invoices.
3. Customer plus unique exact invoice.
4. Customer plus unique exact subset.
5. Unique amount-only invoice in the date window.
6. Everything ambiguous, residual-bearing, limited, or unsupported remains an exception.

A hard-coded score is not presented as probability. Accepted matches carry an evidence class and `exact_unique` solver status.

## Security boundary

The web UI binds to loopback by default, processes uploads in memory, rejects unapproved Host/Origin values, limits request size and rate, applies restrictive browser headers, and returns generic validation errors. It has no multi-user authentication and must not be exposed publicly.

See `SECURITY.md`, `THREAT_MODEL.md`, `PRIVACY.md`, and `DATA_HANDLING.md`.

## Evidence and provenance

The financial-run evidence bundle is separate from software release provenance. W3C PROV and AICPA Audit Data Standards are documented as future mapping profiles, not runtime dependencies. Release packaging is deterministic and carries a file manifest.

## Known limits

- one currency per run;
- two-decimal or zero-decimal precision profiles only;
- bounded subset search; large cases may return `limit_exceeded`;
- no bank connection or QuickBooks/Xero API writeback;
- no OCR;
- no public hosted service;
- external AI advisory is unverified and opt-in only;
- real-customer accuracy, review-time reduction, and willingness to pay remain unverified.

## License

MIT. See `LICENSE`.
