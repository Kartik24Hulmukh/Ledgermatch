# Changelog

## 0.4.0 — review-ledger release candidate

- adds deterministic human adjudication for reconciliation exceptions;
- binds review events to the evidence `run_id` with a SHA-256 hash chain;
- enforces exact conservation, currency, unpaid status, and invoice exclusivity for manual approvals;
- adds review receipts, independent verification, event schema, and adversarial tamper tests;
- records the 24 July 2026 repository and frontier review.

## 0.3.0 — evidence-review release candidate

- adds replayable profile output and profile-driven execution;
- adds standalone evidence and checksum validation;
- upgrades the evidence schema to 1.1 with stricter semantic checks;
- adds evidence downloads to the local web result;
- adds seeded randomized accounting-invariant tests;
- documents standards mappings and non-claims.

## 0.2.0 — local review release candidate

- preserves equal-amount and multiple-subset ambiguity;
- rejects mixed currency, excess precision, duplicate invoice numbers, and profile-incompatible dates;
- adds stable source-row identity, evidence classes, solver status, and residual policy;
- adds deterministic evidence bundle and validator;
- neutralizes spreadsheet formulas and escapes HTML;
- changes web default to loopback and adds Host/Origin and browser-policy controls;
- fixes deterministic server shutdown in tests;
- adds governance, CI, release verifier, Gumloop prompts, and deterministic packaging.
