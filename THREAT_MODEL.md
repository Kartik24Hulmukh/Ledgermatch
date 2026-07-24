# Threat model

## Assets

Financial CSV content, customer names, invoice references, evidence bundles, exported payments, API credentials, and repository integrity.

## Trust boundaries

- local filesystem and CLI process;
- browser to loopback HTTP server;
- optional external AI provider;
- GitHub contribution and release pipeline.

## Primary threats and controls

- False allocation: ambiguity is never auto-accepted; exclusivity and conservation are validated.
- Malformed financial data: strict profiles, row caps, precision checks, and fail-closed parsing.
- Spreadsheet execution: user-controlled CSV cells are formula-neutralized.
- HTML injection: all report values are escaped.
- Local service exposure: loopback default, explicit unsafe bind, Host/Origin checks, request limits, no-store, restrictive CSP.
- Data leakage: in-memory web processing and external advisory disabled by default.
- Tampering: input hashes, deterministic evidence, bundle hash, and standalone validation.
- Supply-chain alteration: least-privilege CI, deterministic archive, file manifest, and checksum.

## Residual risks

No authentication or tenant isolation; no formal accounting assurance; bounded solver may return limits; local malware can read process memory; AI opt-in can transmit sensitive data; practitioner outcomes are unverified.
