# Contributing

1. Open an issue describing the accounting invariant or user problem.
2. Use synthetic data only.
3. Keep authoritative matching deterministic and local.
4. Add a regression test for every defect.
5. Run `python3 scripts/verify_release.py`.
6. Open a focused pull request; do not combine correctness, governance, and renaming changes.

A match-changing pull request must document conservation, exclusivity, ambiguity, determinism, and failure behavior. No pull request may weaken review requirements for ambiguous results.
