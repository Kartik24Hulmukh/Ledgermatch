# LedgerMatch Pilot Data Safety

## Core Rule

**No customer financial data, credentials, API keys, personal information,
or proprietary files may be committed to any repository, cloud storage,
issue tracker, or shared communication channel.**

## Synthetic Data

The preferred approach is to use only synthetic data for pilot evaluation.

### Generating Synthetic Data

```bash
python3 demo_data/generate_demo.py
```

This produces:
- `demo_data/invoices.csv` — synthetic invoice register
- `demo_data/bank_statement.csv` — synthetic bank statement

These files contain no real customer information. They are safe to commit
and share.

## Authorized Pseudonymized Historical Data

If real historical cases must be used for realism:

1. **Documented authority required.** The operator must have documented
   permission to use the data for evaluation purposes. Old data is **not**
   automatically authorized.

2. **Pseudonymization required.** All identifying information must be
   removed or replaced before import:
   - Customer names → `customer_001`, `customer_002`, etc.
   - Account numbers → `acct_001`, `acct_002`, etc.
   - Email addresses → `practitioner_N@synthetic.local`
   - Phone numbers → delete column or replace with `000-000-0000`
   - Addresses → delete column
   - Tax identifiers → delete
   - Reference numbers that could identify a customer → sequential synthetic IDs

3. **Quasi-identifier awareness.** Exact monetary amounts and dates may
   remain sensitive quasi-identifiers even after pseudonymization. They are
   needed for reconciliation but do not guarantee anonymity.

4. **Historical data is described as authorized and pseudonymized**, not
   automatically anonymous.

### Privacy Scanning

Before importing any pseudonymized data into LedgerMatch:

```bash
python3 scripts/verify_pilot_result.py --check-privacy your_data.csv
```

This scans for obvious email patterns, long digit sequences, and common
secret patterns. If any are found, the data must be re-pseudonymized
before use.

**Note:** Regex scanning does not prove de-identification. It is a
supplementary check, not a guarantee.

## Local Storage Only

Pilot data must be stored:

- On the practitioner's local machine.
- In a directory excluded by `.gitignore` (e.g., `out_pilot/`).
- Never in a cloud-synced folder (Dropbox, Google Drive, OneDrive).
- Never in a shared network drive accessible to non-pilot participants.

## Retention Schedule

- **Pilot working copies** (pseudonymized CSVs, evidence bundles, review
  ledgers) should be deleted after the approved retention period (e.g., 90
  days after pilot completion).
- **Generated pilot outputs** (evidence bundles, review ledgers, reports)
  should be deleted after the same retention period.
- **Original accounting records** must NOT be deleted. The retention
  schedule applies only to pilot working copies and generated pilot outputs.
- Only the sanitized result row and validation receipts (PASS/FAIL) are
  retained by the operator beyond the retention period.

## What Not to Commit

The following must never appear in any Git repository:

- Real bank statements
- Real invoice files
- Real customer names or addresses
- Real account numbers
- API keys or tokens
- Database credentials
- Private keys or certificates
- Pilot output files (evidence bundles, review ledgers from real data)
- `.env` files with real credentials

## Breach Response

If real customer data is accidentally committed:

1. **Stop** all pilot activity immediately.
2. **Contact** the pilot operator through the incident-reporting channel.
3. **Rotate** any exposed credentials.
4. **Document** the incident in `BLOCKERS.md`.
5. **Do not resume** the pilot until the breach is fully remediated.
