# Handover: m2-3-training
_Written: 2026-11-16 · branch: main · last commit: 0c9d5e1 (step 1's build is `fa84160`)_

## Goal
Build Stage 3 (M2.3 Modelling) major step 2, Training, from the plan
`worknotes/m2_3_modelling/plan.md` → "Major step 2: Training" (m2.0 to m2.8). The EDS's words
for step 1 were "Using the plan in m2_3_modelling, start building major step 1"; step 2 is the
same plan's next step and starts on the EDS's word in the new chat. The step ends in the
reviews, one ML audit, one fix round, the Spark batch, the full suite once, review guide 2,
and a stop for the EDS.

## State (done / in progress / not started; uncommitted files)
- **Done: major step 1** (the spec and Foundations). Built 2026-11-14, committed by the EDS,
  review 1 answered and applied 2026-11-16. No plan default A65–A81 was vetoed.
- **Not started: major step 2.** Nothing trains a model yet. No agent has been briefed.
- **Uncommitted** (review 1's small edits; the EDS commits, never Claude unasked):
  `conf/base/TEMPLATE.yml`, `docs/UPDATES.md`, `docs/components/config.md`,
  `docs/components/training.md`, `docs/roadmap.md`, `src/core_modelling/model/encoder.py`,
  `worknotes/log.md`, `worknotes/m2_3_modelling/answers.md`, `worknotes/m2_3_modelling/plan.md`,
  this file. The `.claude/` changes in `git status` are the EDS's harness work, not this topic.
- **Verified after the last edit:** `ruff check .` clean; `tests/test_config_schema.py`,
  `test_encoder.py`, `test_bundle.py` 177 passed. The full suite last ran on 2026-11-14 (936
  passed, 1 stale test corrected and passing on its own rerun).
- **Stored artifacts:** EDA and Feature Checks are current for `cc_acquisition` (rerun 11-14).
  `td_acquisition`'s are stale: rerun them before its first training (step 2's end).

## Decisions in that chat (not yet in docs/decisions.md)
None open. D-139 to D-141 hold the design; the plan's §11 holds A65–A81. Review 1's answers
are in `worknotes/m2_3_modelling/answers.md` → "Review 1 of major step 1":
- The roadmap's dates are not to be edited: the EDS's time will be split with another project
  and the timeline redrawn then (Q658).
- `config/schema.py` stays one file; split it when it passes 1,000 lines (Q659, backlog).
- One file per model library stays (`lgbm_family.py`, `xgb_family.py`, `catboost_family.py`).
- `floor_z` stays 2 and is never derived from the event count; the docs advise 1 or `null`
  below about 300 converting train clients (Q666, `training.md` → the floor).

## Open questions (with the user's latest leaning)
None. The plan's "To settle when this step starts" list at the top of Major step 2 is the
orchestrator's to fix before briefing builders (signatures and a few lines, no design
question); it now includes logging a declared level without a train row (Q663).

## Running agents
None.

## Next steps
1. Show the EDS the routing plan for step 2 (the plan's §7 and each minor step's header give
   agent, model and effort), then start the pieces marked *free* in parallel: **m2.0** (the
   FLAML fact checks, scratch scripts only), **m2.4** (the explanation charts, from
   `worknotes/m2_3_modelling/prototype_explain_charts.py.txt`) and `statistics/calibration.py`.
2. Meanwhile, on the main thread, settle the "To settle when this step starts" list: the
   signatures of `select_features` and the five `training.md` leaves "when built", the
   train-statistics table for the selection rules, the population counts for Training's count
   check in `dataset/frames.py`.
3. **m2.1 The search** (main thread, Fable) once m2.0's table is in; a failed m2.0 item stops
   m2.1 until the EDS decides. Then m2.2 ∥ m2.3, m2.5, m2.6 `run_training`, m2.7, m2.8.

## Gotchas
- **Subagents run no Spark and never the full suite.** The main thread runs Spark in batches,
  one memory-heavy job at a time. On this 8 GB machine Spark failed with "No buffer space
  available" while three agents ran pytest; it passed alone.
- **Old Jupyter kernels are still running** (four `ipykernel` processes on 11-16, one holding a
  Spark JVM of about 2 GB since 11-11). Ask the EDS to close them before step 2's heavy runs.
- **The machine sleeps under background agents** unless kept awake (T41, `keep_awake.sh`).
- **The usage limit** stopped three Opus agents on 11-13: resume each with SendMessage after
  the reset, never re-brief from scratch.
- **Fable's share** was 8% of step 1's new tokens (cap 25 to 30%): keep the main thread, m2.1,
  m2.6 and the ML audit on Fable, everything else on Opus or Sonnet; measure from the
  transcripts at the step's end (`/efficiency`).
- **T38 to T40** (`docs/context/lessons.md`): FLAML median-imputes unless `skip_transform`; a
  custom space without starts runs no search; PySpark's local workers need `PYSPARK_PYTHON`
  (the environment adapter sets it).
- **A family's parameter names are FLAML's** (`log_max_bin`; `n_jobs` for CatBoost), and the
  recipe holds no thread count (the bundle refuses one).
- **The encoder frame differs per family in the search:** CatBoost's FLAML wrapper wants
  `category` columns, LightGBM and XGBoost the integer codes (`training.md` → "The encoder
  and the families", 7).
- **Notebooks:** the Public-API rule applies to notebook 04; only `00_modelling_helper` is
  exempt (A80). Guide cells are the deliverable; no machine-specific numbers.
- **`conf/local/cc_acquisition.yml`** is the EDS's own variant (one more analysis filter, three
  key features) under the same use-case name: running it writes into the base config's
  folders. Use `conf/base/cc_acquisition.yml` for the build's runs.
- **Never prune "What the research found"** in `worknotes/m2_3_modelling/questions.md`.
- `worknotes/m2_3_modelling/review_guide.md` is step 1's guide; step 2's guide replaces it.
- Do not edit `worknotes/sync.md` unless the EDS asks.

## Read first
1. `docs/UPDATES.md` (status table, top log entries).
2. `worknotes/m2_3_modelling/plan.md`: the status table, §4 (the contracts between the
   steps), "Major step 2: Training" whole, §6 to §8, and §11's A65–A81.
3. `docs/components/training.md` (all three levels), then `docs/components/model_bundle.md`
   and `docs/components/config.md` → "The modelling fields (Stage 3)".
4. `docs/decisions.md`: D-139, D-140 (and D-049, D-088, D-094, D-106 as edited).
5. The code step 2 builds on: `src/core_modelling/model/` (`encoder.py`, `families.py`,
   `family_inputs.py`, `lgbm_family.py`, `calibration.py`, `bundle.py`, `scoring.py`),
   `dataset/folds.py`, `dataset/frames.py` (`_training_frame`), `runs.py`,
   `config/identities.py`.
6. `notebooks/00_modelling_helper.ipynb`: the foundations exercised end to end.
7. `worknotes/log.md`, the top two Stage 3 entries.
