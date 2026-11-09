# Handover: m2-2-major-step-3
_Written: 2026-11-09 (after the SDS's review 1 and its answers; the build-end version is in git history once
committed) · branch: main · last commit: 35e3020 (EDA for final review); everything below is
uncommitted on top of it_

## Goal
Stage 2's major step 3, **Feature Checks**, is built; the SDS's review 1 and their answers
Q539–Q545 are applied. What remains: the answers to Q546–Q547, the SDS's code review (round 2)
with its guide `worknotes/m2_2_understanding/feature_checks_review_guide.md` and the helper
notebook `notebooks/00_eda_fc_helper.ipynb` beside it, the fixes from it, a commit when the SDS
asks. The SDS extends the synthetic data in another chat (`worknotes/synthetic_trap_coverage.md`).

## State
- **Built (2026-11-06/07):** the five steps (`feature_checks/{findings,measures,steps}.py`), the
  decisions and the stage (`decisions.py`, `run.py`, `report.py`, `core_modelling/run.py`
  `STAGES`), the trap acceptance test (`tests/test_traps.py`, marker `traps`), notebook 03, the
  docs, version 0.3.0; the table formats moved to `reporting/formats.py`.
- **Review 1 applied (2026-11-09):** R42–R55 and Q532–Q538, recorded verbatim with outcomes in
  `worknotes/m2_2_understanding/answers.md` ("Feature Checks review 1"). PSI tiers
  (`psi_note_min` 0.10 note, `psi_max` 0.25 flag: `psi_window_large`, `psi_latest_large`); a
  `measure` per finding and the held table's `flag_values`; `client_constant`'s detail empty and
  its separate table gone; the redundancy cluster summary first, then the feature table; the
  exclude call's `evidence`; captions styled inside the Styler, larger report headings; notebook
  03's data access (`build_frames` in step 1, step 8's three checks, decisions step 9, report
  step 10, the walk-through splits `client_constant`); the trap test's count bound and
  `EXPECTED_HOLDS` removed. V91 rewritten, V92–V97 added (`plan.md` §9); D-134 extended; T36.
- **Answers applied (2026-11-09):** Q539–Q545, R57–R58 ("Feature Checks review 1, answers"):
  Cohen's h/d for the rare-value effect (`rare_effect_max` 0.8, capped at 3); no check skips for
  support, details with support, SE and significance judged at the threshold; `too_strong` on the
  higher of the plain and EDA's best-order window concordance; EDA's `concordance_per_period`
  (stored, shown, read by Feature Checks); null sets; the relative instability range;
  `leakage.dominant_share_min`; the trap test's `NEVER_ON_LEGITIMATE` guard; the helper notebook
  (three readers made public). The ML audit's fixes (T37, V103). V98–V103; D-134, D-135; T37.
- **Checked (review 1):** code review (fixed: two stale step numbers in the notebook, a tie in
  `flag_values`, a caption, a rename, a docstring), compatibility "safe" (0.3.0 absorbs it, no
  `schema_version` bump in 0.x), ML audit "safe" (its point became Q545).
- **Tests (after the answers):** every touched pure test; `test_eda.py`, `test_feature_checks.py`,
  `test_run.py` (49 passed); `test_traps.py` alone (12 passed, 4 min 43 s); `test_eda_modules.py`
  (27 passed); EDA and Feature Checks on canonical and `dev` for both configs (card 42 held on
  both, term deposit 28 canonical and 23 `dev`); notebooks 03 and 00 end to end on a scratch
  copy. The full suite last ran at the build's end (592 passed): run it before the commit.
- **A duplicate session** (the chat reopened while the old one kept running) did part of the
  answers round in parallel; it stood down and its changes are reconciled.

## Open questions (defaults not applied)
Q546 split `steps.py` (about 920 lines) into a package before the code review (default yes);
Q547 a floor leaf on `concordance_unstable`'s relative range, default 0.05 (two signal-less
digital flags held on the canonical term-deposit config). Details:
`worknotes/m2_2_understanding/feature_checks_questions.md`.

## Next steps
1. The answers to Q546–Q547 and the SDS's code review. Record the answers verbatim in
   `answers.md` before any compaction; apply them in one round; the full suite before the commit;
   clear notebook 02's outputs (15, from the SDS's run) before the commit.
2. Commit only when the SDS asks (main, with a message).
3. Then M2.3 (Training): `resolve_features` (held = excluded without a final decision), the
   ledger's `cluster`, a per-run marker to cross-check the ledger against `feature_checks.json`.

## Gotchas
- **Memory:** one Spark job at a time; the SDS's Jupyter kernels may hold Spark JVMs (never kill
  them). Run `test_traps.py` in its own process. **Every background Spark run under a deadline**
  (T36): `perl -e 'alarm shift; exec @ARGV' <seconds> <command>`.
- **Running anything that writes** (Feature Checks, notebook 03) on a scratch copy of
  `data/cc_acquisition` with an environment file whose `roots.data` points at the copy; the
  runner `scratchpad/review3/run_notebook.py` executes notebook 03's code cells with
  `$CORE_MODELLING_ENVIRONMENT`.

## Read first
1. `worknotes/m2_2_understanding/feature_checks_review_guide.md`, then
   `feature_checks_questions.md`.
2. `docs/components/feature_checks.md` (Level 1–2), `plan.md` §9 V74–V97.
