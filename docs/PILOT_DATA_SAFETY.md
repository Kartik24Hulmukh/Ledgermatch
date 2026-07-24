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

## De-identification

If real historical cases must be used for realism:

1. **Remove all customer names** — replace with `customer_001`,
   `customer_002`, etc.
2. **Remove all account numbers** — replace with `acct_001`, `acct_002`,
   etc.
3. **Remove all email addresses** — replace with `practitioner_N@synthetic.local`.
4. **Remove all phone numbers** — delete the column or replace with
   `000-000-0000`.
5. **Remove all addresses** — delete the column.
6. **Remove all reference numbers** that could identify a real customer —
   replace with sequential synthetic identifiers.
7. **Preserve monetary amounts, dates, and currencies** — these are needed
   for reconciliation testing but do not identify customers.

### De-identification Verification

Before importing any de-identified data into LedgerMatch:

```bash
python3 scripts/verify_pilot_result.py --check-privacy your_data.csv
```

This scans for obvious email patterns, long digit sequences (account
numbers), and common secret patterns. If any are found, the data must be
re-de-identified before use.

## Local Storage Only

Pilot data must be stored:

- On the practitioner's local machine.
- In a directory excluded by `.gitignore` (e.g., `out_pilot/`).
- Never in a cloud-synced folder (Dropbox, Google Drive, OneDrive).
- Never in a shared network drive accessible to non-pilot participants.

## Data Retention

- Pilot data should be deleted after the pilot is complete and results are
  recorded.
- The pilot results template (`examples/pilot-results-template.csv`)
  captures the factual measurements. No raw financial data should be in
  the results file.
- The `notes` column in the results template must not contain personal or
  customer information.

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
2. **Contact** the repository owner to force-push the removal (only
   acceptable for non-main branches with no other consumers).
3. **Rotate** any exposed credentials.
4. **Document** the incident in `BLOCKERS.md`.
5. **Do not resume** the pilot until the breach is fully remediated.
