# LedgerMatch Pilot Operator Guide

## Role

The pilot operator is responsible for setting up, running, and recording
the private LedgerMatch pilot. The operator is not a test subject — they
facilitate the evaluation by practitioners.

## Setup

### 1. Verify Source

```bash
sha256sum LedgerMatch-0.4.0-review-ledger-source.zip
# Expected: cc34bc9eb8f9a98fc6f40bab5732105a7f11a9be266a86f15dd4f17125dd8927

unzip -t LedgerMatch-0.4.0-review-ledger-source.zip  # integrity check
unzip -l LedgerMatch-0.4.0-review-ledger-source.zip  # 51 entries
```

### 2. Run Baseline Verification

```bash
cd LedgerMatch-0.4.0
python3 scripts/verify_release.py
```

All gates must pass before proceeding.

### 3. Generate Synthetic Data

```bash
python3 demo_data/generate_demo.py
```

### 4. Prepare Import Profiles

Create at least three import profiles for the three CSV layouts. See
`examples/profile.json` for the format.

### 5. Distribute to Practitioners

Each practitioner receives:
- The verified LedgerMatch source (not a fork — a local copy).
- Synthetic data files.
- Import profiles for their assigned layout.
- The pilot results template (`examples/pilot-results-template.csv`).
- The pilot case template (`examples/pilot-case-template.json`).
- This operator guide.

## Running a Case

### Step 1: Import Data

```bash
python3 -m app.cli reconcile \
  --invoices invoices.csv \
  --deposits bank_statement.csv \
  --profile profile.json \
  --currency USD \
  --out out_pilot/case_001/
```

### Step 2: Review Candidates

The CLI output presents candidate matches. The practitioner must:

1. Review each candidate.
2. Use `approve_exact`, `reject`, or `defer` for each.
3. Record the review decision in the review ledger.

```bash
python3 -m app.cli review-create \
  --evidence out_pilot/case_001/evidence_bundle.json \
  --ledger out_pilot/case_001/review_ledger.jsonl
```

### Step 3: Validate Evidence and Review Ledger

```bash
python3 -m app.cli review-verify \
  --ledger out_pilot/case_001/review_ledger.jsonl
```

Both evidence and review-ledger validation must pass.

### Step 4: Record Results

Enter the case results into the pilot results template CSV:

- `pilot_case_id` — unique identifier for this case.
- `practitioner_id` — pseudonymous identifier (e.g., `prac_001`).
- `currency` — the currency code for this run.
- `deposits_processed` — number of deposits in the case.
- `accepted_matches` — number of matches the practitioner approved.
- `review_exceptions` — number of cases requiring manual exception handling.
- `false_automatic_allocations` — must be 0 for continuation.
- `correct_candidate_retained` — `true` if the correct candidate was in the set.
- `review_minutes_before` — manual reconciliation time.
- `review_minutes_with_ledgermatch` — LedgerMatch-assisted time.
- `evidence_validation` — `true` if evidence bundle validated.
- `review_ledger_validation` — `true` if review ledger validated.
- `repeat_use_requested` — `true` if practitioner would use again.
- `recommendation` — `recommend`, `neutral`, or `do_not_recommend`.
- `payment_or_contribution_signal` — free text, no personal info.
- `notes` — free text, no personal or customer info.

## Validating Results

After all practitioners complete their cases:

```bash
python3 scripts/verify_pilot_result.py examples/pilot-results-template.csv
```

The validator will:
- Check all required columns are present.
- Validate data types (booleans, integers, decimals, currency codes).
- Reject negative values.
- Reject duplicate pilot case IDs.
- Scan notes for privacy violations (emails, account numbers, secrets).
- Compute aggregate factual metrics.
- Report unmet minimum sample requirements.
- **Fail** if any false automatic allocation is found.
- Report evidence and review-ledger failures.
- Never infer demand from synthetic data.

## Post-Pilot

1. Collect all result CSVs from practitioners.
2. Merge into a single results file.
3. Run the validator on the merged file.
4. Record the aggregate summary.
5. Delete all local pilot data (evidence bundles, review ledgers, raw CSVs).
6. Keep only the validated results summary.
7. Do not commit raw pilot data to any repository.

## What Not to Do

- Do not deploy LedgerMatch to a public server during the pilot.
- Do not allow AI to authorize or post financial allocations.
- Do not claim the pilot passed before actual practitioner data is supplied.
- Do not claim customer demand, compliance, or hosted security.
- Do not weaken or skip the continuation gate.
