# Gumloop chat prompt

Use the attached LedgerMatch source ZIP as the candidate base. First ask for and verify the exact LedgerMatch GitHub repository URL; the known AccessDoc URL is not valid for this project.

1. Safely extract the ZIP and verify its SHA-256 and manifest.
2. Clone the exact LedgerMatch repository and compare its default-branch tree with the package. Stop writes if unrelated.
3. Run `python3 scripts/verify_release.py` and record the complete receipt.
4. Create `release/ledgermatch-0.4.0-review-ledger` from the current default branch.
5. Apply the package without deleting unrelated approved files.
6. Run tests with ResourceWarning treated as an error, hostile export/HTML cases, evidence tamper checks, review-ledger edit/reorder/delete/receipt checks, server boundary tests, deterministic replay, and deterministic archive builds.
7. Push only the feature branch and open a pull request. Include commit SHA, PR URL, hosted CI URLs, test counts, package SHA, blocker ledger, and a human review checklist.
8. Do not merge. After hosted checks pass, ask for explicit confirmation identifying the PR number before any merge.
9. Keep renaming as a separate later pull request because LedgerMatch has name collisions.
10. Do not deploy a public upload service, add autonomous financial decisions, or claim customer outcomes.
