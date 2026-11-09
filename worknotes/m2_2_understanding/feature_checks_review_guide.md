# Stage 2 Feature Checks (major step 3): the review guide for the SDS, round 2
_Written 2026-11-09. Round 1 covered the notebook, the report, the questions and the vetoes
(R42–R55); your answers Q539–Q545 and R57–R58 are built too (all recorded with their outcomes in
`answers.md`). This round is the code · the design: D-134 and D-135 and
`docs/components/feature_checks.md` · the build's decisions to veto: `plan.md` §9 V74–V103 ·
open: Q546–Q547 in `feature_checks_questions.md` · about two and a half hours_

**Status.** Built on Opus: four code agents on disjoint files (EDA, Feature Checks' steps, its
report, the helper notebook) and a doc agent; then one code review, the compatibility check
("safe": 0.3.0 absorbs it, a ratio-era `rare_effect_max` refused at load) and the ML audit
(xhigh; its five fixes applied: T37, V103). Tests: every touched pure test; `test_eda.py`,
`test_feature_checks.py`, `test_run.py` (49 passed); `test_traps.py` alone (12 passed, 4 min 43
s, the Q545 guard included); EDA's module tests (27 passed); EDA and Feature Checks on the
canonical and the `dev` data for both configs; notebooks 03 and 00 end to end on a scratch copy.
Nothing committed. A duplicate session ran part of this round in parallel after the chat was
reopened; its changes are reconciled (no duplicate records, one version of every file).

**Keep open beside the code: `notebooks/00_eda_fc_helper.ipynb`.** It reads the stored
artifacts read-only (no Spark, no entry) and shows each table's grain, columns, a few telling
rows and the functions that write and read it: `eda.json`, `cells`, `ranking`,
`client_constant`, `correlation`, `concordance_per_period` and EDA's other tables, the ledger,
`feature_checks.json`, `findings`, `unavailable`, `per_period`, `clusters`,
`proposed_decisions`, the audit log. Run `02_eda` and `03_feature_checks` first; set `NUMERIC`
and `CATEGORICAL` to follow two candidates through every table.

## Read in this order
1. **The hold-out core:** `config/replay.py` `open_flags`, `ledger.py` `resolve_features`; then
   `feature_checks/decisions.py` (`flag_entries`, `proposed_decisions`, `held_summary` with
   `flag_values`).
2. **`feature_checks/findings.py`** (20 findings: kind, `measure`, text), then
   **`feature_checks/steps.py`** (about 920 lines: Q546 asks whether to split it first) against
   `feature_checks.md`'s finding table: `check_inputs` and the stale-EDA refusals,
   `check_quality` (the null sets, `_null_sets`), `check_leakage` (`_too_strong` on the higher of
   the plain and best-order window concordance, `_minority_effect` on Cohen's h/d, the
   significance phrase `_evidence`), `check_time_alignment` (`_lagged_se`, the flip),
   `check_stability` (the PSI tiers, the relative range, `_heterogeneity` and `_period_ses`),
   `check_redundancy`. What right looks like: no check skips for support; every "not available"
   decided before computing; significance judged with the SE at the threshold.
3. **`tasks.py`**: `_cohens_h`, `_cohens_d`, `_pooled_variance` and the per-task `rare_effect`
   entries; **`feature_checks/measures.py`**: `effective_se`, `lagged_concordance`,
   `period_psi`, the label-free `per_period_table`.
4. **EDA's side:** `eda/ranking.py` (`_best_order`, `concordance_best_order_window`),
   `eda/deep_dives.py` (`concordance_per_period`), `eda/run.py` (its phase), `eda/report.py`
   (`_per_period_view`).
5. **`feature_checks/run.py`** (the flow and the write order) and **`report.py`** (the held
   values, the redundancy views, the PSI-only per-period view, the chart from EDA's table).
6. **Read this test: `tests/test_traps.py`**: the mapping, `NOT_CHECKS`, the null controls and
   `NEVER_ON_LEGITIMATE` as the false-positive checks, the D-088 counts, the bin rule.
7. **The shared files:** `reporting/formats.py`, `reporting/html.py` (the caption inside the
   Styler), `reporting/blocks.py`, `config/schema.py` (`Leakage`, `Stability`),
   `config/replay.py` (20 loggable Feature Checks leaves).

## Measured on the synthetic data
- Canonical card config: 42 held (46 before the answers: Cohen's h at 0.8 releases `segment`
  and the three travel-spend minorities, every trap still held); no flag reads "not
  significant".
- Canonical term-deposit config: 28 held, two of them `concordance_unstable` on signal-less
  digital flags (Q547).
- `dev`: card 42 held, term deposit 23 (about 35 events per period: no flag fires "not
  significant", so dropping the support skips cost no hold there); every trap caught; the null
  controls and the legitimate columns raise no leak or lag flag.

## What I would look at first
- **Q546 (split `steps.py`) before reading it**, and **Q547 (the range floor)**.
- **`_evidence` and `_period_ses`**: the two places the ML audit corrected (T37).
- **`_minority_effect` on Cohen's h** against your Q539.

## Known limits (documented in `feature_checks.md`)
Cochran's Q across periods that share clients is conservative; Cohen's h's SE is about 20% small
at tiny expected counts; `signal_kept`'s SE leaves out the window's own noise; as the window's
signal nears 0.5 Cochran's Q alone decides `concordance_unstable` (Q547); a crash between the
ledger save and the folder write leaves the ledger's informational columns one run ahead (the
hold-out reads the log).
