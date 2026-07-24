# Standards mapping

LedgerMatch separates financial-run evidence from software-release provenance. The mappings below define extension points; they are not compliance claims.

## Reconciliation Evidence Bundle 1.1

| LedgerMatch field | Intended purpose | Future mapping |
|---|---|---|
| `run_id` | deterministic identity for inputs, profile, configuration, and engine | W3C PROV activity identifier |
| `input_hashes` | immutable source-file receipts | W3C PROV entity derivation |
| `matches` | rule-supported proposed allocations | AICPA order-to-cash settlement relationship |
| `exceptions` | unresolved review queue | review/control-event extension |
| `unpaid_invoices` | open-item snapshot after proposals | AICPA order-to-cash open receivable |
| `bundle_sha256` | internal tamper receipt | release-independent evidence digest |

## RFC 8785 boundary

The runtime uses sorted-key, compact UTF-8 JSON for internal deterministic hashing. It does not claim RFC 8785 compatibility. That claim requires official number, Unicode, and canonicalization vectors plus cross-runtime tests.

## W3C PROV boundary

A future exporter may represent each run as an activity, input files as entities, and the operator/engine as agents. Core matching must not depend on an RDF or semantic-web runtime.

## AICPA Audit Data Standards boundary

Future import/export profiles may map invoice, customer, payment, and general-ledger identifiers. Field names and control totals must be tested against licensed source material and practitioner samples before any conformance statement.

## in-toto and SLSA boundary

Release provenance is separate from reconciliation evidence. Hosted CI may later emit signed source/build attestations. A local ZIP checksum does not establish hosted provenance or a SLSA level.
