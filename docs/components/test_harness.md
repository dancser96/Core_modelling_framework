# Test harness (synthetic panel + local Spark)
**Status:** designing · **Legacy:** `tests/smoke_test.py` (stub-based — do not copy its stubs)

## Purpose
Real data never leaves the bank, so correctness outside rests on a realistic synthetic panel run
through **real** local PySpark. Stubs hid every environment bug in the crunch (T15).

## Phase 2 requirements
1. A synthetic monthly panel generator matching the real panel's shape:
   - id, month, numeric and categorical features, activity columns for targets
   - adjustable population size and positive rate (e.g. 0.04% → 10%)
   - optional segment heterogeneity
2. Pytest fixtures: a small local SparkSession (session-scoped); a tiny panel for unit tests and a
   larger one for the e2e test.
3. One end-to-end test running every built stage on the synthetic panel via the public API.
4. Invariant tests (`CLAUDE.md` §4) and config-migration tests.

## Design constraints
- The generator is plain functions, readable in one sitting. No test framework beyond pytest.
- Tests must run on both dev machines (WSL2, macOS) with the pinned versions and Java 11.

## Open questions
- Does a leakage-injection option in the generator (a planted leaking feature) belong in the first
  version? It would make leakage-screen tests trivial.
