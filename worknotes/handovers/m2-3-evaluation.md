# Handover: m2-3-evaluation
_Checkpoint written: 2026-11-17 (not started; ready to start) · branch: main · last commit: 1749370_

## Goal
Build Stage 3 (M2.3 Modelling) major step 3, Evaluation, from
`worknotes/m2_3_modelling/plan.md` → "Major step 3: Evaluation" (m3.1 to m3.11). The step ends
in the ML audit of the whole chain, Training through Evaluation, `compat-guardian`, one fix
round, the Spark batch, the full suite with the acceptance and slow tests, review guide 3, the
docs, version 0.4.0, and a stop for the EDS. Commit only on the EDS's word.

## What the EDS decided (2026-11-17)
- **Steps 2 and 3 are reviewed together.** Step 3 builds on step 2's contracts as built and
  nothing waits for a review of step 2. A contract the joint review changes is fixed in both.
- **Step 2's review stays open:** review guide 2 (`worknotes/m2_3_modelling/review_guide.md`),
  the defaults A82 to A91 (A91 is settled by Q668 and Q669), the floor's optimism on a
  non-monotone feature (A88), and whether the budgets of 60 and 200 are enough
  (`docs/components/training.md` → Open questions). Close none of them.
- **Q667 to Q673 are answered**, all at their default; the record is
  `worknotes/m2_3_modelling/answers.md`. `questions.md` holds no open question.

## State of the repo
- Major step 2 (Training) is built and uncommitted: 53 changed or new files on top of
  `1749370`. Step 3's reviews read diffs, so a commit of step 2 first keeps them clean; that
  is the EDS's call.
- Run on 2026-11-16 after the last code edit: full suite 1028 passed, 15 deselected; the slow
  four-family test 4 passed; notebooks 03, 04 and the helper ran end to end on `dev`.
- Changed since that suite, text only: one display string and one caption in
  `training/views.py`, a guide cell of notebook 04, a comment in `conf/base/TEMPLATE.yml`
  (`ruff` clean; `tests/test_code_rules.py` 3 passed, `tests/test_config_schema.py` 136
  passed).
- The EDS's local data: EDA and Feature Checks were rerun for both example configs on 11-16
  (EDA's stage json is at version 5); Training was not run there.

## Readiness (checked 2026-11-17 against the built code)
No blocker and no question for the EDS. Everything the plan names as built exists. The facts
the check found are in the plan, under "To settle when this step starts" → "From the readiness
check"; three stale lines of the plan were corrected (`stage2/`'s contents, the public-API
test file, the name `compute_contributions`).

## Start
1. Run the chat on Opus (plan §7, last paragraph: Fable was 40% of the spend since 11-09).
   Fable does the ML audit of the whole chain and nothing else.
2. Read: the plan's step 3 section, §4 (the contracts), §6 to §8; `docs/components/evaluation.md`;
   `docs/components/training.md` for what Training writes.
3. First piece, on the main thread: the "to settle" list. It fixes the score cells (bin count,
   columns), the shape of `client_weights`, the signatures of `metric_tables` and
   `feature_table`, where `slice_metrics`'s `population` comes from, the baseline columns in
   `dataset/frames.py`, and the run parameter on `Stage`, `run()` and the CLI. m3.1 and m3.3
   are briefed only after it.
4. Then: m3.1 and m3.2 in parallel; m3.3; m3.4; m3.5, m3.6, m3.8 and m3.9 in parallel; m3.7;
   m3.10; m3.11.

## Working rules from step 2 (the EDS, 2026-11-17)
- **The build never stops for a question** (D-072 (s); Q667 stopped step 2): take the default,
  build on, and put it first in review guide 3. The EDS looks again when the step is built.
- **Compact.** Step 2's main thread passed 600k tokens without one compaction, because
  compaction is let through only right after this file is written as the last tool call.
- Every code or test piece is a `builder`, every doc piece a `doc-writer`; pass `model` and
  `effort` as the plan's minor step names them.
- A fix goes back to the builder that wrote the code (`SendMessage`), never to the main thread.
- This file is rewritten at the end of every minor step, as the last tool call, so compaction
  keeps the main thread under 300k tokens.
- Subagents run no Spark and never the full suite. The main thread runs Spark as single
  background commands, one memory-heavy job at a time, and not while agents run pytest.
- One combined review per minor step; one ML audit and one fix round for the step.

## Running
Nothing.

## Next
The first piece above, then m3.1 and m3.2.
