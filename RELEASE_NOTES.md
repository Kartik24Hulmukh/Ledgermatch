# 0.4.0 review-ledger release candidate

This release adds a deterministic, tamper-evident human-review ledger bound to the original Reconciliation Evidence Bundle.

## Added

- `python3 -m app.review create` and `verify` commands.
- SHA-256 chained NDJSON review events and a separate receipt.
- Exact-conservation, currency, unpaid-invoice, and invoice-exclusivity gates for manual approvals.
- `approve_exact`, `reject`, and `defer` decisions with controlled reason codes.
- Detection tests for event edits, reordering, deletion, receipt mismatch, nonconserving allocations, and invoice reuse.
- Review-ledger event JSON schema.
- 24 July 2026 repository and frontier research note.

## Research decision

The 145 supplied repository entries were identical to the previously reviewed catalog, so the existing per-entry matrix remains authoritative. Current research elevated AuditWeave and transparency-log patterns for immediate use. Splink and `dpss` remain candidate-generation and benchmark tracks rather than authoritative runtime dependencies.

## Boundary

The chain provides tamper evidence relative to its current head. It does not prevent an actor who controls storage from rewriting the full chain and an unanchored head. External anchoring, hosted CI, name clearance, public hosting, and practitioner outcome validation remain external gates.
