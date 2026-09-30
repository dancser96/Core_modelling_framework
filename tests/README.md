# tests

**Now (Phase 2 build-out): light tests.**
- Correctness invariants (`CLAUDE.md` §4): time separation, OOT non-overlap, train-only sampling,
  calibration iff downsampled, lineage exclusion, batch-write completeness.
- Config migrations: old configs still load (`CLAUDE.md` §2).
- One end-to-end test on a synthetic panel with **real local PySpark** (no stubs; see
  `docs/components/test_harness.md`).

**Before migration into the bank:** every function tested, internal CI/CD and Sonar checks
passing.

Run with `pytest` (configured to collect only this folder; `legacy/` is excluded). "No tests ran"
is expected until the first tests exist.
