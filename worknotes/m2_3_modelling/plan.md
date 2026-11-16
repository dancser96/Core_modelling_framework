# Stage 3 (M2.3 Modelling): the build plan
_Written 2026-11-13 for the EDS's approval · from the settled design: `answers.md` (68 questions,
A1–A51) and `questions.md` (the research note, the settled design in one table, the spec list),
beside this file · nothing is specified in the owner docs or coded before the EDS approves this
plan (`CLAUDE.md` §1 step 1) · revised the same day on the EDS's word: three major steps, and
less ceremony around two chats · the plan's own defaults, A52–A64, are in §11, to veto by number_

**Where it stands (2026-11-13): the design is closed; this plan is waiting for approval.** Three
major steps, each ending in the EDS's review with a review guide: the spec with Foundations,
Training, Evaluation. Thirty-four minor steps, each ending in the review subagents. A second
chat can build the next step while the EDS reviews the current one: a step owns its files, and
the shapes the next step reads are listed in §4. Fable orchestrates each step's chat, writes
the three pieces that need the whole picture and runs one ML audit per major step; Opus and
Sonnet build the rest (§7).

| Major step | State | Chat | Review 1 | Review 2 | Closed |
|---|---|---|---|---|---|
| 1 The spec and Foundations | built 2026-11-14; committed (`fa84160`); review 1's remarks applied 2026-11-16 | chat 1 | done 2026-11-16: A65–A81 not vetoed, Q658–Q666 answered (`answers.md`) | | |
| 2 Training | — | | | | |
| 3 Evaluation | — | | | | |

Each chat sets its row when it starts, at each review and when the step closes.

## 1. What is built, and what is deliberately left out
**Built (version 0.4.0 at the end):** everything in the table of `questions.md` → "0. The settled
design": the frames' folds and Evaluation's frames, the encoder, four model families with their
round trips and monotone constraints, the bundle with one `model_hash`, numbered runs, the
search (FLAML, one search per family), selection by three rules, fold models and calibration,
the per-run ledger, the sign-off, scoring in Spark, metrics with client-bootstrap intervals,
baselines, strata, seventeen report views, the model card, the drift reference, `compare_runs`,
notebooks `04_training`, `05_evaluation` and `00_modelling_helper`, regression end to end, the
docs in the same change.

**Left out, on purpose** (each with its owner): pass or fail gates (a Phase 3 question, Q632);
class weights, isotonic calibration, imputation, a confusion matrix at 0.5, "too good to be
true" warnings (settled as not built); the predefined path, BlendSearch and the trade-off chart
(Phase 3); `register`'s check of the sign-off, the HDFS transport, `promote`'s file-type list
(M2.4); the comparison report over many runs and sweeps (M4); fitting the calibrator at the true
rate and calibration curves on canonical (M3, by the oracle check); ranges and an objective
suggested from the data (M3/M4); a `cap` on the target rule (backlog); a probe at every bundle
load (Phase 3); the chunked driver scoring path (built only if the model libraries fail on the
bank's executors, A27); any change to the synthetic generator (A51: the three missing cases are
built as small constructed frames in the tests).

## 2. The major steps
| Step | Builds | What the EDS reviews at its end |
|---|---|---|
| 1 The spec and Foundations | The settled design in the owner docs, with the decision rows and the config table (Q640); then the config and the audit log, the folds and Evaluation's frames, the encoder, the families, the bundle and scoring, runs | The config table beside the template's `training` and `evaluation` sections; `model_bundle.md` beside a bundle, its manifest and `run.json` on disk; the decision rows; the encoder's codes and the fold balance on synthetic columns; one round trip per family (helper notebook) |
| 2 Training | The search, selection, fold models and calibration, the explanation charts, the per-run ledger and sign-off view, `run_training`, notebook 04 | A trained run from notebook 04: what the search did with its timings, what selection dropped and why, the calibration numbers, the sign-off view; the `dev` measurements of the ranges and budgets |
| 3 Evaluation | Scoring in Spark, metrics and intervals, baselines, strata, the drift reference, the seventeen views, the model card, `compare_runs`, `run_evaluation`, the `dev` acceptance tests, notebook 05, the stage's close | The model results report on the card config and the regression variant, with the explanation views beside EDA's lift; the metrics against the oracle and the acceptance results; the card; a comparison of two runs; notebook 05 with its closing checklist |

Regression runs through every step: each minor step builds both tasks' entries, and the
regression variant has its own trained and evaluated run in the tests.

## 3. Two chats at once
A second chat may build the next major step while the EDS reviews the current one, both on
`main` in one working tree. Little is needed to keep them apart.

1. A chat edits the files of its own major step (§5 names them per minor step). Where a later
   step adds a few lines to an earlier step's file (a stage in `run.STAGES`, a fixture in
   `conftest.py`), its minor step names them, and they go in last, when the function they wire
   passes its tests.
2. The next step builds on the shapes of §4. Its pieces marked *free* read none of them and may
   start as soon as the current step is in review; the rest start when the review-1 fixes are
   in. A shape that changes after that gets a line in `worknotes/log.md`.
3. Shared docs (`log.md`, `UPDATES.md`, `decisions.md`, `roadmap.md`, `lessons.md`) are re-read
   just before a targeted edit, and so is the next D-, T- or A-number before it is taken.
4. One memory-heavy job on the machine at a time: `pgrep -fl "pytest|SparkSubmit|synthetic"`
   before Spark or a suite, and a hard cap on every background run
   (`perl -e 'alarm shift; exec @ARGV' <seconds> <command>`; the Mac has no `timeout`).
5. A chat starts from `docs/UPDATES.md`, §4 and its own step in §5, the owner docs of its step
   and the top entry of `worknotes/log.md`. It does not read `answers.md` whole (168 KB): a
   brief points a builder at one question when the builder needs the reasoning. Then it sets
   its row in the table above.

Commits stay on the EDS's word.

## 4. The contracts between the steps
The spec (m1.1–m1.4) writes each of these into its owner doc with every column and key; this
section lists what the next step builds on.

**C1. Foundations, read by Training and Evaluation.**
- **Config:** every M2.3 field lands in m1.7, also the ones only later steps read. `features.order`;
  `decision.metric` checked against the task, `decision.baselines` in its four forms;
  `training`: `estimator_list` (four families), `max_iter`, `trials`, `time_budget_s`, `seed`,
  `folds`, `fold_repeats`, `objective`, `monotone`, `search_space` (a leaf is
  `{low, high, log, integer, start}` or `{value}`), `selection` (`cluster`, `floor_z`, the
  pruning switch), `categoricals` (`min_level_client_count`, `unordered: native | codes`),
  `calibration.method` (`platt | beta | none | mean`), `sampling`; `evaluation`: `slices`,
  `views`, `intervals`. Gone: `decision.gate_metric`, the `lifecycle` section,
  `selection.univariate_floor`, `categoricals.min_level_count`, `isotonic`.
- **Audit log:** a `run` entry of `training` (no periods, A14) and of `evaluation` (the scored
  validation period in its own field, Q626); a `sign_off` entry with the run, the feature
  signature and the final list (Q624); the loggable training and evaluation settings.
- **Frames:** `build_frames(…, "training")` returns train only, with `cv_fold` (and `cv_fold_2`,
  … under `fold_repeats`); `build_frames(…, "evaluation")` returns `rows`, one Spark frame of
  test and validation with `part`, the strata and the tag columns, collected nowhere.
- **Encoder:** `fit_encoder`, `encode_frame`; the encoder is plain data (per feature: its kind
  `numeric | ordered | unordered`, its levels and codes).
- **Families:** `FAMILIES[name]` with `fit`, `predict` (the margin, float64), `describe`, `save`,
  `load`, `contributions`, `fixed_params`; `check_monotone`.
- **Bundle and scoring:** `write_bundle`, `load_bundle`, `check_bundle`, `apply_calibration`
  (calibration as `{method, parameters, offset}` for both tasks), `score_frame` (columns
  `margin`, `score_raw`, `score`), `score_spark`.
- **Runs:** `models_dir`, `create_run`, `read_run`, `find_run`, `list_runs`, `show_run`,
  `sign_off`; `run.json`; every stage json of a run carries a flat `summary` block that
  `list_runs` and `show_run` display, so they need no edit when a later step adds numbers.

**C2. The run folder, written by Training and read by Evaluation.** Under `<use_case>/06_models/r007/`:
- `run.json` (written first, never rewritten);
- `bundle/`: the model file, `bundle.json`, `manifest.json`;
- `ledger_run.parquet` with its sidecar;
- `stage2/`: the final features' Stage 2 ledger rows, EDA's bin edges and shares per period,
  EDA's lift table (Q654);
- `training/` (written last, the commit marker):
  - `training.json`: the stamp, the identity, the `summary`, the per-family search table, the
    out-of-fold metric, the in-sample AUC (A41), the step seconds, the warnings;
  - `tables/`: `trials`, `selection`, `oof` (one row per train row as trained: keys, `cv_fold`,
    `target`, `margin`, `score_raw`, `score`), `explanation_sample` (a seeded sample of train
    rows: the raw feature values and the out-of-fold contributions), `calibration`, `signoff`;
  - FLAML's log per family, `resolved_config.yml`.
- The test fixtures `trained_card` and `trained_regression` (the `unit` preset, `lgbm`, four
  trials) are part of this contract: step 3 builds on them.

## 5. The minor steps
Every minor step: its goal, the files it owns, the functions with their signatures, its tests,
what it leaves out, and its agent (type · model · effort; §7 says why). Steps marked ∥ run in parallel on disjoint files; the others wait for what they name; a piece
marked *free* may start while the step before is in review (§3). Signatures are the plan's; a
builder may merge two tied modules but never moves a responsibility to another step.
`cfg, entity, env, spark` stand for `UseCaseConfig, str, EnvironmentConfig, SparkSession`, as
in `run_eda`.

### Major step 1: the spec and Foundations
**The spec first (m1.1–m1.6).** The design is settled; these steps write it where it lasts.
Source: `questions.md` → "For the
spec write-up" (every doc sentence that changes, by file) and the index of `answers.md`.

**m1.1 The decisions, the contracts and the config table** · main thread · Fable
- Owns: `docs/decisions.md`, `CLAUDE.md` §4.7, `docs/components/model_bundle.md` (new, through
  `new-component`), the config table inside `docs/components/config.md`.
- Does: the rows edited in place (D-088, D-094, D-049, D-098, D-054, D-037, D-100, D-106,
  D-125, D-132, D-136, D-051, D-032, D-137, as listed in `questions.md`); at most three new
  rows from D-139, after re-reading the last row (identity, runs and the bundle; the search,
  selection and calibration; Evaluation and its report), each with its sources from the
  research note; `model_bundle.md` with C1's bundle, manifest and `run.json` and C2's folder;
  the config table of Q640 rebuilt from the settled answers, every field with its default, who
  reads it and whether the audit log may set it.
- Leaves out: any code.

**m1.2 ∥ `training.md`** · `general-purpose` · Opus · high
- Owns: `docs/components/training.md` (three levels), `docs/components/feature_ledger.md` (the
  per-run part).
- Substance in the brief: the chain of m2.6, the search (Q602, Q604–Q606, Q651, Q652, A3, A45,
  T39), selection (Q611, Q612, A8–A10, A43), calibration (Q613–Q615, Q639, Q653, A42), the
  categoricals (Q609, Q610, Q657, A35), monotone constraints (Q650), the per-run ledger (Q622),
  the sign-off view (Q623, A39).

**m1.3 ∥ `evaluation.md`, `reporting.md`, `monitoring.md`** · `general-purpose` · Opus · high
- Owns: those three. Substance: the metrics per task (Q627, Q639, Q656), per period and pooled
  (Q628), slices (Q629), intervals (Q630, A47), baselines (Q631, A25, Q632), strata (Q633), the
  seventeen views with A23 and A45, the card (Q638), the chart-rule exceptions (A48), the drift
  reference (Q637, A38), `compare_runs` (Q648, Q655), the columns of the scores and metrics tables.

**m1.4 ∥ `config.md`, `dataset.md`** · `general-purpose` · Opus · high
- Owns: the rest of `config.md` (the layout, the operation table, the loggable settings, the
  identities table, the worked example with A15's correction), `dataset.md` (the folds,
  Evaluation's frames).

**m1.5 Propagation** (after m1.1–m1.4) · `general-purpose` · Sonnet · medium
- Owns: `docs/glossary.md` (A22's and A50's terms), `docs/architecture.md` (the Public API
  rows, the artifact inventory, the package layout of A54, the identities bullets),
  `lifecycle.md`, `inference.md`, `run_modes.md`, the one sentence in `eda.md`,
  `docs/README.md` and the components index, `docs/roadmap.md` (the dates of §9, OD-12 closed,
  the backlog items of A30 and Q653, depth row 3, the risk row), `notebooks/README.md`,
  `tests/README.md` (the `acceptance` marker).

**m1.6 Self-review and the format check** · main thread, plus `compat-guardian` · Opus · high
- The spec self-review (placeholders, contradictions, ambiguity, scope); `compat-guardian` on
  the config table and the artifact formats as specified; `doc-sync`.
- The config table goes to the EDS in chat when m1.1 has written it. The build does not wait
  for an answer: a veto is a small change in place (A53). The spec is reviewed with the step.

**Then Foundations (m1.7–m1.14).** m1.10 and m1.11 read settled answers only and may start
beside the spec's doc steps.

**m1.7 The config schema** · `general-purpose` · Opus · xhigh (one agent with m1.8)
- Owns: `config/schema.py`, `config/levels.py`, `conf/base/TEMPLATE.yml`, `cc_acquisition.yml`,
  `td_acquisition.yml`, `tests/conf/*.yml`, `tests/test_config_schema.py`.
- Builds: C1's config fields from the spec's table, in place (A53); `LEVEL_DEFAULTS`
  (`training.max_iter` 60 and 200); the load-time refusals: the four class-weight names in
  `search_space` (A4), `monotone_constraints_method: advanced`, `intermediate` together with
  `colsample_bynode`, `training.trials` not naming every listed family, `features.order` naming
  a non-candidate, a calibration method or a `decision.metric` the task does not allow; the
  template explains every new field in a line (when to choose `tweedie`, what `fold_repeats`
  buys, what a `start` is).
- Tests: each new field round-trips with its default; each refusal; the level defaults; the
  removed keys fail loud as unknown; the shipped examples load.
- Leaves out: the audit log (m1.8); any reader of the fields.

**m1.8 The audit log, the stage artifacts, the paths, the per-task data** (after m1.7, same agent)
- Owns: `config/audit_log.py`, `config/replay.py`, `config/__init__.py`, `artifacts.py`,
  `environment.py`, `tasks.py`, `tests/test_audit_log.py`, `tests/test_artifacts.py`,
  `tests/test_environment.py`.
- Builds: `Entry` gains `run`, `signature` and `validation_period`; a `run` entry needs
  `periods` for Feature Checks only (A14); the validation-period refusal reads Feature Checks'
  entries only (Q626); the `sign_off` entry and `signed_off(entries: list[Entry], signature:
  str) -> Entry | None` in `replay.py`; `LOGGABLE_SETTINGS` gains the training and evaluation
  leaves of the spec's table (`training.trials` and `training.monotone` among them, never
  `decision.metric`, Q656); `SETTINGS_PATHS_BY_STAGE` gains `training` and `evaluation` (A33),
  EDA's digest narrows to `decision.type` and `decision.n` (A46); one schema version per stage
  json (A17); `models_dir(env, cfg, *parts) -> str`; EDA's events warning gains the
  converting-client threshold (A46, Q600); `TASK_SPECS` gains the data entries (the objectives,
  metrics and calibration methods each task allows, with their defaults).
- Tests: a sign-off covers a later run with the same signature, not a changed list, and a
  revert undoes it; a Training entry without periods loads; an Evaluation entry naming the
  validation period blocks neither `resolve_config` nor a later move of the period; Training's
  digest ignores an evaluation setting; EDA's digest ignores a new baseline.
- Leaves out: the CLI (m1.13); the functions `TASK_SPECS` will point to (seams).

**m1.9 ∥ Folds and Evaluation's frames** · `general-purpose` · Opus · high
- Owns: `dataset/folds.py` (new), `dataset/frames.py`, `dataset/__init__.py`,
  `tests/test_folds.py`, `tests/test_frames.py`.
- Builds: `assign_folds(train: DataFrame, cfg) -> DataFrame` (per dealing: converting clients
  ordered by a salted hash of the client and dealt in turn, then the others the same way; for
  regression the hash cut into K); `fold_counts(train: DataFrame) -> pd.DataFrame` and
  `check_folds(counts: pd.DataFrame) -> None` (a fold with no positive fails loud, Q600);
  `STAGE_PARTS`: `training` gets train only (Q593), `evaluation` gets `rows`; the evaluation
  rows carry `part`, the strata and the tag columns, which never join `features`.
- Tests: no client in two folds or in both splits; the folds' converting clients differ by at
  most one; two dealings differ; a use case with fewer converting clients than folds fails loud
  (a constructed frame, A51); the strata and tags are on the evaluation rows and absent from
  the feature list; validation rows hold clients of both splits.
- The Spark tests are run by the main thread, in one batch.

**m1.10 ∥ The encoder** · `general-purpose` · Opus · xhigh
- Owns: `model/encoder.py` (new package `model/`), `tests/test_encoder.py`.
- Builds: `fit_encoder(train: pd.DataFrame, features: list[str], kinds: dict[str, str], order:
  dict[str, list[str]], min_level_client_count: int, unordered: str) -> dict`;
  `encode_frame(frame: pd.DataFrame, encoder: dict) -> tuple[pd.DataFrame, pd.DataFrame]` (the
  encoded frame in the encoder's column order, and one row per feature with the null, infinite,
  `__other__` and unseen shares). Numerics to float64, clipped to ±1e30, a null stays null
  (Q601, A1); an ordered categorical to its declared position, an unseen level to null; an
  unordered one to 0 for null, 1 to K by train frequency, K + 1 for `__other__` (rare by
  distinct train clients, and unseen), as integers when `native` and as numbers when `codes`.
- Tests: the levels are frozen from train and kept at the client count; the three codes; an
  unseen level per kind, counted; a train level missing from the declared order fails loud; the
  clip, with a null kept; a decimal column cast and an object numeric refused; the encoder
  survives a JSON round trip with identical output; `codes` gives the same integers.
- Leaves out: imputation (never, Q603).

**m1.11 ∥ The four families** · `general-purpose` · Opus · xhigh
- Owns: `model/families.py` (the `Family` dataclass, `FAMILIES`, `check_monotone`),
  `model/lgbm_family.py`, `model/xgb_family.py` (both XGBoost entries), `model/catboost_family.py`,
  `tests/test_families.py`.
- Builds, per family: `fit(X: pd.DataFrame, y: np.ndarray, params: dict, task: str) -> object`;
  `predict(booster: object, X: pd.DataFrame) -> np.ndarray`; `describe(booster) -> dict`;
  `save(booster, path: str) -> None`; `load(path: str) -> object`;
  `contributions(booster, X) -> np.ndarray`; `fixed_params(task: str, objective: str, encoder:
  dict, monotone: dict[str, str], seed: int, threads: int) -> dict` (A55: the constants the
  search and the fit must share: the objective, the declared categoricals, the constraints in
  the library's form, LightGBM's `basic` method, CatBoost's `allow_writing_files=False`).
  `check_monotone(family: str, booster: object, X: pd.DataFrame, monotone: dict[str, str],
  rows: int = 200) -> None`. The loader pins float64 in the booster's column order, XGBoost's
  tree count and CatBoost's integer categoricals; CatBoost's five run-specific metadata entries
  are deleted before saving (Q619).
- Tests, over the four families and both tasks where they apply: save, load, identical
  margins; a shuffled frame scores the same; two fits give one file hash; the contributions sum
  to the margin; an unseen code scores for every family; a constraint holds on the grid and
  `check_monotone` fails on a model that breaks it; CatBoost writes no file and scores the same
  with its metadata deleted; Tweedie's margin is on the log scale (A42); one and two threads
  agree.
- Leaves out: any search; `shap` as an import.

**m1.12 The bundle and scoring** (after m1.10, m1.11) · `general-purpose` · Opus · xhigh
- Owns: `model/bundle.py`, `model/calibration.py`, `model/scoring.py`, `model/__init__.py`,
  `tests/test_bundle.py`, `tests/test_scoring.py`.
- Builds: `Bundle` (a dataclass: the booster, the family, the task, the encoder, the
  calibration, the features, `bundle.json`'s content, `model_hash`); `write_bundle(folder: str,
  family: str, booster: object, content: dict, identity: dict) -> str`; `load_bundle(folder:
  str) -> Bundle` (the hash checked first); `check_bundle(folder: str, sample: pd.DataFrame,
  expected: pd.DataFrame) -> None` (the self-check at save, 1,000 rows); `recipe_hash(recipe:
  dict) -> str`; `feature_signature(features: list[str]) -> str`; `apply_calibration(margin:
  np.ndarray, calibration: dict, task: str) -> tuple[np.ndarray, np.ndarray]`;
  `score_frame(bundle: Bundle, frame: pd.DataFrame) -> pd.DataFrame`; `score_spark(folder: str,
  rows: DataFrame, keep: list[str]) -> DataFrame` (`mapInPandas`; the driver ships the bytes,
  the model is rebuilt once per partition, A28).
- Tests: the round trip; `model_hash` repeats over two writes and moves with one changed byte;
  a tampered file is refused at load; the self-check fails loud; no time, run or person in
  `bundle.json`; `recipe_hash` ignores the calibration numbers; each calibration method's
  arithmetic (Platt at a = 1, b = 0 equals none; the offset; the mean factor); `score_spark`
  equals `score_frame` on the same rows (Spark, run by the main thread); a missing feature
  fails loud.
- Leaves out: fitting a calibrator (m2.3).

**m1.13 ∥ Runs** · `general-purpose` · Opus · high
- Owns: `runs.py` (new), `__main__.py`, `tests/test_runs.py`.
- Builds: `next_run_id(folder: str, entries: list[Entry]) -> str` (A32); `create_run(env,
  resolved: UseCaseConfig, entity: str, stage2: dict) -> str` (A79; the folder made exclusively,
  `run.json` written once); `read_run(env, cfg, run: str) -> dict`; `find_run(env, resolved,
  entity: str, run: str | None = None) -> str` (A33); `list_runs(env, cfg, entity: str) ->
  pd.DataFrame`; `show_run(env, cfg, entity: str, run: str) -> str`; `sign_off(cfg, entity: str,
  env, run: str, reason: str) -> Entry` (A56); the CLI's `runs`, `show-run` and
  `decide --sign-off --run`.
- Tests: the next number when the folder exists; a deleted folder's number is not given again;
  a folder without `training/` lists as incomplete; `run.json` cannot be written twice;
  `find_run` takes the latest run of the same data definition and training digest and refuses
  when there is none; `sign_off` writes the run, the signature and the list.

**m1.14 The helper notebook and the step's docs** (after m1.12) · `general-purpose` · Opus · high
- Owns: `notebooks/00_modelling_helper.ipynb` (the encoder, the families, the bundle: each
  artifact's grain, columns and a few telling rows beside the function that wrote it, A26),
  `notebooks/README.md`; the Status lines of `model_bundle.md`, `dataset.md`, `config.md`.

**The step's end** (main thread): the reviews of §8; `compat-guardian` on m1.7, m1.8, m1.12 and
m1.13; the ML audit on m1.9–m1.12; one fix round; the Spark tests in one batch; the full suite;
EDA and Feature Checks rerun once on the local `dev` data (A46 makes the stored artifacts
stale); review guide 1, which lists the spec's docs first.

### Major step 2: Training
**To settle when this step starts** (found by step 1's spec self-review and reviews; each is a
signature or a few lines, none reopens the design):
- **The count check needs the population counts.** D-088 has Training recompute the per-period
  row and positive counts on every client of the window and compare them with EDA's; today
  `build_frames` computes `meta["population"]` for EDA only. m2.6 adds it to the training
  stage's frames (a few lines in `dataset/frames.py`, named here).
- **Selection's rules need train statistics.** `apply_cluster_rule` and `apply_floor` are
  written as taking the Stage 2 ledger, but the floor reads the train-split concordance and its
  SE. `select_features` computes one train-statistics table from the train frame first and
  the rules take that table beside the ledger's clusters.
- **`prune_by_importance` runs under the run's constraints,** so it takes LightGBM's fixed
  parameters (or the encoder and the constraints); `level_factor` takes the replicates.
- **A declared level without a train row is logged** (review 1): Training's log lists, per
  ordered feature, each level of `features.order` that no train row holds; it keeps its
  position and is allowed.
- **One frame per family for the search** (`training.md` → "The encoder and the families", 7):
  CatBoost's wrapper wants `category` columns, LightGBM and XGBoost the integer codes; and
  `check_order` and `check_params` run before the first trial.
- **The recipe's keys are pinned** (`model_bundle.md` → "The hashes"): m2.6 builds exactly
  those; `features.order` is passed to the encoder filtered to the features it encodes.
- `select_features(…)` and the five signatures `training.md` leaves "when built" are fixed by
  the step's orchestrator before the builders are briefed.
- **From step 1's ML audit** (each is a requirement in `training.md`):
  - `check_order` runs on every frame that is fitted, also after each selection drop; the
    pruning frame, which holds five noise columns, is checked against an encoder extended
    by them (a constraint vector shorter than the frame is refused by every family's `fit`).
  - Under `negative_downsampling` the out-of-fold rows are at the sampled rate while `score`
    is at the true rate: the out-of-fold log loss of `none`, `platt` and `beta` and the
    out-of-fold metric are taken before the offset. Fold `ap` and log loss are at the
    sampled prevalence and are never compared with test.
  - The offset is zero under `client_sample` by the method, never from the sampling
    record's two rates, which differ there by sampling noise.
  - A calibration whose fit would reverse the order (Platt `a ≤ 0`) is refused by the
    bundle: Training fails loud there and says the model is anti-predictive out of fold.
  - Training's own out-of-fold scores get the non-finite check `score_frame` has.
  - A null the model never saw in train scores as an extreme, differently per library, and
    an unseen level of an ordered feature becomes such a null: Training warns on an ordered
    feature without train nulls, and the per-run ledger's train `null_share` lets
    Evaluation flag a feature that has nulls at scoring and had none in train.
  - The recipe holds the searched and fixed parameters without the thread count, the
    calibration's method and folds only, and the client split.

**m2.0 The facts, together** (*free*: starts at step 1's review 1) · `general-purpose` · Opus · high
- Owns: nothing in the repo; one scratch script per item, every run capped; the results go to
  `worknotes/log.md` (by the main thread) and a trap to `docs/context/lessons.md`.
- Items (`questions.md` → "To check", numbers in brackets): FLAML with our splitter, declared
  categoricals, a ranged space with starts and a constraint at once, for each family (2); a
  fit through `FAMILIES` from the best configuration equals FLAML's own model, for each family,
  with CatBoost under the tree-count rule and with Tweedie (1); Poisson, the absolute error and
  Huber through the search, with the deviances as custom metrics (6); a budget of 2N trials
  repeats the N-trial run's trials first (13); scikit-learn 1.8's unpenalised logistic
  regression (9).
- Acceptance: a table of item, result and consequence. A failed item stops m2.1 until the EDS
  has seen it.

**m2.1 The search** (after m2.0 and step 1's review-1 fixes) · main thread · Fable
- Owns: `training/search_space.py` (rules as data: the bounded ranges and starts per family,
  A3's five fixed switches, the refused names), `training/search.py`, `tests/test_search.py`.
- Builds: `split_budget(cfg) -> dict[str, int]` (equal shares, the remainder to the first
  families, or `training.trials`); `build_search_space(family: str, cfg, fixed: dict) -> dict`
  (every ranged leaf with its start clipped into the range, T39); `fold_splitter(folds:
  pd.DataFrame) -> object` (yields our folds, R × K per trial); `search_metric(cfg) -> str |
  Callable`; `search_family(X: pd.DataFrame, y: np.ndarray, folds: pd.DataFrame, family: str,
  space: dict, trials: int, metric: str | Callable, seed: int, log_path: str) -> tuple[dict,
  pd.DataFrame]` (the best configuration and the trials table with every trial's seconds);
  `check_search(trials: pd.DataFrame, starts: dict) -> None` (trial 1 at the starts, the
  trials distinct, else fail loud).
- Tests (a constructed frame of a few thousand rows, `lgbm`; no Spark): the exact trial count;
  the split with a remainder, and `training.trials`; every ranged leaf reaches FLAML with a
  start; `check_search` fails on a search that did not move; the splitter's folds are ours;
  a constraint reaches the trial models; a fold metric of infinity fails loud.
- Leaves out: BlendSearch, a time budget as the default, any choice on test or validation.

**m2.2 ∥ Selection** · `general-purpose` · Opus · high
- Owns: `training/selection.py`, `tests/test_selection.py`.
- Builds: `apply_cluster_rule(ledger: pd.DataFrame, features: list[str], kept: list[str]) ->
  pd.DataFrame`; `apply_floor(ledger: pd.DataFrame, features: list[str], kept: list[str],
  floor_z: float) -> pd.DataFrame`; `prune_by_importance(X: pd.DataFrame, y: np.ndarray, folds:
  pd.DataFrame, kept: list[str], task: str, seed: int) -> pd.DataFrame` (five noise columns,
  LightGBM at the start configuration, undone when the out-of-fold loss rises, A43);
  `select_features(…) -> tuple[list[str], pd.DataFrame]` (cluster, floor, pruning, in that
  order; one row per feature and rule with its value, threshold and outcome).
- Tests: the order of the rules; a kept feature is measured and never dropped (A8); the floor
  reads the best-order concordance for a non-monotone feature (A10); pruning drops what the
  best noise column beats and is undone when the loss rises; no noise column leaves the function.

**m2.3 ∥ Fold models and calibration** · `general-purpose` · Opus · xhigh
- Owns: `statistics/calibration.py` (*free*), `training/fold_models.py`, `training/calibrate.py`,
  `tests/test_calibration.py`, `tests/test_fold_models.py`; the calibration entries of
  `TASK_SPECS` in `tasks.py`.
- Builds: `fit_platt(margin: np.ndarray, y: np.ndarray) -> dict`; `fit_beta(margin, y) -> dict`
  (refitted without a term whose coefficient is negative); `prior_shift_offset(true_rate: float,
  sampled_rate: float) -> float`; `level_factor(predicted: np.ndarray, y: np.ndarray, clients:
  np.ndarray) -> dict` (the factor, its client-bootstrap interval, the rows holding half the
  total; never winsorised, Q653); `fit_fold_models(X, y, folds, family: str, params: dict,
  task: str) -> tuple[np.ndarray, np.ndarray]` (out-of-fold margins and contributions; the
  models are discarded, A11); `calibrate(margins: np.ndarray, y: np.ndarray, clients:
  np.ndarray, cfg, rates: dict) -> dict` (the method the decision or the objective asks for,
  the out-of-fold log loss of `none`, `platt` and `beta` for every binary run, Q615).
- Tests: a fold's rows are never in the frame its model was fitted on; the offset is zero
  without sampling and the log of the keep fraction with it; Platt recovers a known pair on
  simulated margins; beta's refit; the factor and its interval, with the warning past ±5%; the
  methods refused per task.

**m2.4 ∥ The explanation charts** (*free*) · `general-purpose` · Opus · high
- Owns: `reporting/explain_charts.py`, `tests/test_explain_charts.py`; seam: `reporting/theme.py`.
- Builds, from the prototype the EDS saw (`prototype_explain_charts.py.txt` beside this file):
  `importance_bar(contributions: pd.DataFrame, compare: pd.DataFrame | None = None, top: int =
  15) -> go.Figure`; `beeswarm(contributions: pd.DataFrame, values: pd.DataFrame, top: int = 15,
  clients: int = 1500, seed: int = 0) -> go.Figure`; `waterfall(contributions: pd.Series, base:
  float, values: pd.Series, shown: int = 9) -> go.Figure`; `dependence(contributions:
  pd.Series, values: pd.Series, colour: pd.Series | None = None, lift: pd.DataFrame | None =
  None) -> go.Figure` (the mean contribution per group and EDA's lift beside it).
- Tests: each figure builds; the beeswarm draws at most 1,500 seeded clients per feature; a
  missing value is grey; the package imports no `shap`.

**m2.5 The per-run ledger, the sign-off view, Training's views** (after m2.2, m2.3) ·
`general-purpose` · Opus · high
- Owns: `training/ledger_run.py`, `training/views.py`, `tests/test_ledger_run.py`.
- Builds: `build_run_ledger(selection: pd.DataFrame, description: dict, contributions:
  pd.DataFrame, encoder_shares: pd.DataFrame, monotone: dict[str, str], stage2: pd.DataFrame)
  -> pd.DataFrame` (Q622's columns, with the constraint and whether its sign agrees with EDA's
  direction); `save_run_ledger`, `read_run_ledger`; `signoff_table(run_ledger, stage2, entries)
  -> pd.DataFrame` (Q623: the final list by out-of-fold contribution, then the held and the
  excluded features with their reasons); `search_summary(trials: pd.DataFrame) -> pd.DataFrame`
  and `search_progress_chart(trials) -> go.Figure` (A45); `selection_view`,
  `calibration_view`, `signoff_view`, each returning report blocks for notebook 04 and the
  report.
- Tests: the ledger's columns and sidecar; a constraint against EDA's direction raises the
  warning; the sign-off table lists the held and excluded features; the per-family seconds add
  up to the search's.

**m2.6 `run_training`** (after m2.1–m2.5) · main thread · Fable
- Owns: `training/run.py`, `training/__init__.py`, `tests/test_training.py`; its lines in
  `run.py` (`STAGES`, and the `autonomous` rule of Q595), `tests/conftest.py` (the fixtures
  `trained_card` and `trained_regression`) and `tests/test_run.py`.
- Builds `run_training(cfg, entity, env, spark) -> StageResult`, in this order:
  1. the resolved config; the gate (EDA and Feature Checks artifacts of the same data
     definition, §4.13; the count check, A13); the feature set in force, a held feature refused;
  2. `create_run` (the number is reserved);
  3. the train frame, the folds checked, the encoder fitted and applied; the constraint
     refusals and the wrong-sign warning;
  4. selection;
  5. one search per family with its budget, each checked; the best family and configuration by
     the fold metric;
  6. the fold models at that configuration, the calibration, the out-of-fold metric;
  7. the final fit on every train row, the in-sample AUC (A41), the bundle written, the
     self-check, then the grid check on the reloaded bundle (Q650);
  8. the per-run ledger, the `stage2/` copies, the sign-off table, the explanation sample;
  9. `training/` last (A49), then the `run` entry.
- Tests (the `unit` preset, Spark, run by the main thread): a held feature is refused; two runs
  give one `model_hash`; the frames Training asks for hold no test row; a crash before step 9
  leaves a run listed as incomplete; the entry has no periods; the fitted model equals the
  search's best model on the encoded frame; `run` at `autonomous` runs the missing upstream
  stages and `run_training` alone fails loud; and, marked `slow` on `dev`, the four families
  through the search with their round trips (§6).

**m2.7 Notebook 04 and the helper's Training section** (after m2.6, and when notebook 03's
review is closed) · `general-purpose` · Opus · high
- Owns: `notebooks/04_training.ipynb` (a guide cell before every step: the gate and the feature
  set in force, the run, what the search did, selection, calibration, the sign-off view, how to
  iterate), the helper's section, `notebooks/03_feature_checks.ipynb` (its end records the
  keeps, Q644), `notebooks/README.md`, `tests/test_code_rules.py` (the notebook joins the public-API rule);
  the Status lines of `training.md`, `feature_ledger.md`.
- The agent writes; the main thread runs the notebooks on `dev`.

**m2.8 The measurements** (after m2.6) · main thread, background, every run capped
- On `dev`: the bounded ranges against FLAML's own, judged against the oracle, with the four
  families' fold loss and seconds (3); declared categoricals against codes, one run each (5);
  the slow test (§6). On canonical: the seconds per family on the card frame, to confirm the
  budgets of 60 and 200 (4).
- The numbers go to `worknotes/log.md` and review guide 2; a default changes only on the EDS's
  word.

**The step's end:** as step 1's, with the ML audit on m2.1–m2.6 and `compat-guardian` on
`training.json` and the per-run ledger; `td_acquisition`'s EDA and Feature Checks rerun once
before its first training (A21); review guide 2.

### Major step 3: Evaluation
**To settle when this step starts** (found by step 1's spec self-review and reviews):
- **Evaluation's rows lack the baseline columns.** They carry the keys, `part`, the bundle's
  features, the strata, `target` and `split`. A `previous_model` or `historic_predicted_rate`
  column, and a single feature that selection dropped, are not among them. m3.3 lets the
  frames carry them as the strata are carried (a few lines in `dataset/frames.py`, named here).
- **The score cells:** A58 fixes the grain; the bin count and the columns are fixed by the
  step's orchestrator before m3.1 and m3.3 are briefed, with the shape of `client_weights`
  (one weight per replicate: an array column, or one column per replicate) and the
  signatures `metric_tables(…)` and `feature_table(…)`.
- **Prediction threads on an executor** (review 1): no family's `predict` sets a thread
  count. Measure what each library uses inside `score_spark` and pin it to the task's cores,
  before the first scoring at volume.
- **A part without rows fails loud** when the cells are aggregated; **the log loss clips**
  a probability of exactly 0 or 1.
- **From step 1's ML audit** (each is a requirement in `evaluation.md`):
  - `score_frame` and `score_spark` return scores only, so the unseen and null shares of
    the feature table need a pass of their own (the encoder's shares on the scored rows);
    a feature with nulls at scoring and none in train is flagged.
  - The Tweedie deviance is computed at the constant 1.5 in the metric code, never from
    `training.tweedie_variance_power`, which the audit log may set.
  - The report lists the validation periods that earlier Evaluation `run` entries scored:
    moving the validation period after one was scored is allowed, and must be visible.
  - For M2.4's `register`: a run stays listed as signed off after one of its features is
    excluded or held later, and the signature covers the names in order, not the kinds,
    the declared orders or the constraints.

**m3.1 ∥ The metrics and the client bootstrap** (*free*) · `general-purpose` · Opus · xhigh
- Owns: `statistics/metrics.py`, `statistics/bootstrap.py`, `tests/test_metrics.py`,
  `tests/test_bootstrap.py`; seam: `tasks.py`.
- Builds, on score cells (A58): `binary_metrics(cells: pd.DataFrame) -> dict[str, float]` (AUC,
  average precision, the log-loss and Brier skill against the base rate, observed to expected,
  the calibration slope and intercept); `regression_metrics(cells) -> dict[str, float]` (RMSE,
  MAE, R², the deviance, the concordance, predicted to observed); `slice_metrics(cells, slices:
  list[float], population: int) -> pd.DataFrame` (a `top_n` read as a share of the period's
  eligible population, Q629); `reliability_table(cells, groups: int = 10) -> pd.DataFrame`;
  `threshold_table(cells) -> pd.DataFrame`; `bootstrap_intervals(replicate_cells:
  pd.DataFrame, metric: Callable, level: float) -> tuple[float, float]` (the metric on each
  replicate's weighted cells, then the middle share of the values).
- Tests (constructed cells, no Spark): each metric against scikit-learn on rows, within the
  binning's tolerance; the skill scores; the slope on simulated miscalibration; a `top_n`
  above the population is not available; an interval that covers the value of a simulated
  frame; the regression metrics.
- From step 1's review: a score can be exactly 0 or 1 at an extreme margin (float64's limit),
  so the log loss clips before the logarithm; a test covers it.
- Leaves out: the replicate weights, which are drawn in Spark (m3.3).

**m3.2 ∥ The model charts** (*free*) · `general-purpose` · Sonnet · high
- Owns: `reporting/model_charts.py`, `tests/test_model_charts.py`.
- Builds, each from a table (no row-level data, `reporting.md`): `roc_chart`, `pr_chart`,
  `capture_chart`, `reliability_chart`, `score_distribution` (each class to its own scale),
  `metric_lines` (a metric by period with its interval), `predicted_vs_observed` (regression,
  20 groups). Each takes a `pd.DataFrame` and returns a `go.Figure`.

**m3.3 Scores, baselines, strata, the drift reference** (after step 2's review-1 fixes) ·
`general-purpose` · Opus · xhigh
- Owns: `evaluation/scores.py`, `evaluation/baselines.py`, `evaluation/tables.py`,
  `evaluation/drift_reference.py`, `tests/test_evaluation_tables.py`.
- Builds: `score_parts(spark, bundle_folder: str, rows: DataFrame, cfg) -> DataFrame` and
  `write_scores(scores: DataFrame, folder: str) -> None`; `client_weights(client: Column,
  replicates: int, salt: str) -> Column` (one Poisson weight per replicate from a hash of the
  client, so a client's rows move together and two runs share the weights, A47);
  `score_cells(scores: DataFrame, cfg, by: list[str]) -> pd.DataFrame` (the Spark aggregate
  the metrics read, weighted per replicate); `add_baselines(rows: DataFrame, cfg, run: dict)
  -> DataFrame` (the single feature chosen on train, the previous model's column, the historic
  rate as a number or a column, A25) and `compare_baselines(metrics: pd.DataFrame, cfg) -> pd.DataFrame` (the model against
  each baseline at the decision's metric, with intervals, no pass or fail); `metric_tables(…) ->
  dict[str, pd.DataFrame]` (per period and pooled, the slices per period, the strata with the
  list's composition, validation on test clients only); `build_drift_reference(run_folder:
  str, cells: pd.DataFrame) -> dict[str, pd.DataFrame]` (from the run's `stage2/` copy and the
  test scores, A38).
- Tests (the `unit` preset with `trained_card`; Spark, run by the main thread): a feature list
  that differs from the bundle's is refused; a part without rows fails loud when the cells
  are aggregated (step 1's review: the rows are never collected, so nothing earlier notices);
  one row per client, period and part; a client's
  rows share one weight per replicate and two scorings give a client the same weights; the
  slices are cut inside each period; the single feature is chosen without a test row; the
  drift reference is a valid input of `psi`; a stratum level below the minimum is greyed, not
  hidden.
- Also measures, once, the cells' seconds per replicate on a constructed frame of the bank's
  size (to check 8); the main thread runs it and reports it.

**m3.4 The core report and `run_evaluation`** (after m3.1–m3.3) · `report.py`:
`general-purpose` · Opus · high; `run.py`: main thread · Fable
- Owns: `evaluation/report.py`, `evaluation/run.py`, `evaluation/__init__.py`,
  `tests/test_evaluation.py`; its lines in `run.py` (`STAGES`), `__main__.py` (`run --run`),
  `conftest.py` (the fixtures `evaluated_card` and `evaluated_regression`) and `test_run.py`.
- Builds: `VIEWS: dict[str, Callable]` and `build_report(tables: dict, meta: dict, resolved:
  UseCaseConfig) -> str` with views 1–7, 12–14 and 17 and their regression forms (view 1 opens
  with the choices and the baselines comparison; views 12 and 13 call `training/views.py`);
  `run_evaluation(cfg, entity, env, spark, run: str | None = None) -> StageResult`: the run
  found, the bundle loaded and its hash checked, the rows scored in Spark, the scores written,
  the cells, the metrics with intervals, the baselines, the strata, the drift reference, the
  report, `evaluation/` written whole, then the `run` entry with the scored validation period.
- Tests: a rerun rewrites `evaluation/` and leaves `training/` and the per-run ledger untouched
  (A36); `run="r001"` evaluates an older run of the same data definition; the end-to-end test
  runs every stage on both configs within its two minutes on `unit`.

**m3.5 The acceptance tests on `dev`** (after m3.4) · written by `general-purpose` · Opus ·
high; run by the main thread
- Owns: `tests/test_modelling_acceptance.py`; the `acceptance` marker in `pyproject.toml`; the
  `dev_stage2` fixture in `conftest.py`, which `test_traps.py` reads too, so a suite pays for
  `dev`'s EDA and Feature Checks once. The four tests are in §6.

**m3.6 ∥ The explanation tables** (the functions on `score_frame` are *free*) ·
`general-purpose` · Opus · high
- Owns: `evaluation/explain.py`, `tests/test_explain.py`.
- Builds: `collect_explanation_sample(rows: DataFrame, scores: DataFrame, cfg, env) ->
  pd.DataFrame` (a seeded test sample with its features, and the three waterfall rows: the
  highest score, a row at the decision's cut, a typical row); `sample_contributions(bundle:
  Bundle, sample: pd.DataFrame) -> pd.DataFrame`; `feature_table(…) -> pd.DataFrame` (A36: the
  test contribution shares, the unseen and null shares on test and validation, a table of its
  own); `permutation_importance(bundle, sample, clusters: pd.DataFrame, metric: Callable, seed:
  int) -> pd.DataFrame` (per cluster, with the rank check against the contributions);
  `partial_dependence(bundle, sample, features: list[str]) -> pd.DataFrame`;
  `effect_features(run_ledger: pd.DataFrame, key_features: list[str]) -> list[str]` (A23).
- Tests: the contributions sum to the margin; permuting a cluster moves its members together;
  the effect features are at most twenty and hold every key feature the model uses.

**m3.7 The explanation views** (after m3.6) · `general-purpose` · Opus · high
- Owns: `evaluation/views_explain.py`; its entries in `VIEWS`, its calls in `run_evaluation`,
  and `pdp_ice_chart` in `reporting/explain_charts.py`.
- Builds views 8–11, 15 and 16: the importance bar with train out of fold beside test, the
  beeswarm, the effects with EDA's lift, the waterfalls, permutation importance, PDP and ICE.

**m3.8 ∥ The model card** · `general-purpose` · Opus · high
- Owns: `reporting/card.py`, `tests/test_card.py`; one call in `run_evaluation`.
- Builds: `build_card(run_folder: str) -> dict` (Q638's sections, a schema version, facts from
  the run folder only, no free text) and `render_card(card: dict) -> str` (tables only).

**m3.9 ∥ `compare_runs`** · `general-purpose` · Opus · xhigh
- Owns: `evaluation/compare.py`, `tests/test_compare.py`.
- Builds: `compare_runs(cfg, entity, env, spark, run_a: str, run_b: str) -> dict[str,
  pd.DataFrame]`: the metrics side by side on the rows both scored; each difference with its
  interval and the word "better" on the test split only; validation's two numbers under
  "reported, never chosen on" (Q655); the features that entered or left; the largest changes
  in importance rank; the two budgets and their seconds (A45).
- Tests: no difference is computed on validation; a run compared with itself has a zero
  interval (the shared weights); runs of two data definitions are refused.

**m3.10 Notebook 05 and the helper's last section** (after m3.7–m3.9) · `general-purpose` ·
Opus · high
- Owns: `notebooks/05_evaluation.ipynb` (a guide cell before every step: pick a run, evaluate,
  read the report section by section, the explanations, the card, a comparison, the sign-off,
  the closing checklist), the helper's Evaluation section (with a `shap.Explanation` from the
  stored contributions in three lines, Q635), `tests/test_code_rules.py` (the notebook joins
  the public-API rule); the Status lines of `evaluation.md`, `monitoring.md`, `reporting.md`.
- The agent writes; the main thread runs the notebook on `dev`.

**m3.11 The close** · main thread; the propagation by `general-purpose` · Sonnet · medium
- The reviews of §8, with the ML audit of the whole chain, Training through Evaluation (A61),
  and `compat-guardian` on the scores, the metrics table, the drift reference and the card;
  one fix round; the full suite with the acceptance and slow tests; version
  0.4.0; the secondary docs synced once (`UPDATES.md`'s status, the architecture inventory, the
  README map, the glossary's wording); `docs/guides/modelling_faq.md` with the research note
  and the stage's questions that a user would ask again (A63); the roadmap's milestone row;
  review guide 3. The stage folder is deleted on the EDS's word.

## 6. Tests: what is written, what runs, who runs it
The rule is the EDS's (Q643, and this plan's brief): light, and no test effort that costs more
tokens than the risk it covers.

1. A builder writes the tests its minor step lists in §5 and says why if it adds one.
2. Pure pandas modules are tested on constructed frames by their builder, with no Spark. Most
   of the stage is built that way on purpose.
3. A reviewer reports a missing test only for a §4 invariant, a §2 path or a public function
   with no test at all. A bug found in a review gets one regression test.
4. Spark tests are run by the main thread only, in one batch per minor step (`-k`), the output
   to a file, the tail read.
5. The full suite runs once at each major step's end. Review fixes run
   the touched modules' tests.
6. One trained and one evaluated run per task and per session (`unit`, `lgbm`, four trials):
   every Spark test of steps 2–4 reads those four fixtures.

**The `dev` tests, all of them.** Run times are estimates until the first run; the measured
time replaces each one here.

| Test | Preset, marker | What it shows | Expected | Run by, when |
|---|---|---|---|---|
| The model beats the single-feature baseline on validation | `dev`, `acceptance` | the model adds something | one shared run of the card config: `lgbm`, 15 trials, about 5 min with EDA and Feature Checks, which it shares with the trap test | main thread: when m3.5 is built, after a fix that touches Training's or Evaluation's numbers, at step 3's end |
| Validation AUC is not above the oracle's by more than two standard errors | `dev`, `acceptance` | no leak passes | same run | same |
| With a leak trap kept by a person, the oracle is beaten | `dev`, `acceptance` | the check above can fail | a second Training and Evaluation, about 3 min | same |
| Observed to expected within 10%, with and without `negative_downsampling` | `dev`, `acceptance` | the calibration level and the offset | a third Training and Evaluation, about 3 min | same |
| The four families through the search, each with its round trip | `dev`, `slow` | every family end to end | about 10 min, CatBoost most of it | main thread: once at step 2's end, once at step 3's end |

No canonical test in M2.3: canonical is used for one measurement (m2.8). The suite's test files by step (a chat's full suite may `--ignore` the files of a step
still being built): step 1 `test_config_schema`, `test_audit_log`, `test_artifacts`,
`test_environment`, `test_folds`, `test_frames`, `test_encoder`, `test_families`, `test_bundle`,
`test_scoring`, `test_runs`; step 2 `test_search`, `test_selection`, `test_calibration`,
`test_fold_models`, `test_explain_charts`, `test_ledger_run`, `test_training`; step 3
`test_metrics`, `test_bootstrap`, `test_model_charts`, `test_evaluation_tables`,
`test_evaluation`, `test_modelling_acceptance`, `test_explain`, `test_card`,
`test_compare`.

## 7. The routing table (D-072 (l): Fable at 25–30% of the stage at most)
| Piece | Agent · model · effort | Why |
|---|---|---|
| The orchestrator of each step's chat (briefs from §5, integration, the Spark batches, the review guide, the report to the EDS) | main thread · Fable | the whole picture, and the EDS's word |
| m1.1 the decisions, the contracts, the config table | main thread · Fable | design; the record the EDS reads |
| m2.1 the search | main thread · Fable | the piece with the most measured library behaviour behind it (T38, T39); a wrong answer is a search that silently does not search |
| m2.6 `run_training`, m3.4's `run_evaluation` | main thread · Fable | the two chains; they need every contract at once |
| `ml-correctness-auditor`, once per major step (three) | that agent · Fable · xhigh | the §4 paths; audits were Fable's best use in Stage 2 |
| m1.7 + m1.8 config and audit log | `general-purpose` · Opus · xhigh | the public schema and the entries (§2) |
| m1.10, m1.11, m1.12 encoder, families, bundle and scoring | Opus · xhigh | an error here scores silently wrong |
| m2.3 fold models and calibration; m3.1 metrics and bootstrap; m3.3 scores and baselines; m3.9 `compare_runs` | Opus · xhigh | §4.4, §4.7 and the statistics every number rests on |
| m1.9, m1.13, m2.0, m2.2, m2.4, m2.5, m3.4's report, m3.5, m3.6, m3.7, m3.8 | Opus · high | specified pieces on built contracts |
| m1.14, m2.7, m3.10 the notebooks | Opus · high | the guide cells are the deliverable |
| m1.2–m1.4 the component docs | Opus · high | doc content from substance in the brief |
| m3.2 the model charts | Sonnet · high | a complete brief on built primitives; not a §4 path |
| m1.5, m3.11's propagation | Sonnet · medium | text whose substance is settled |
| One combined review per minor step (`code-reviewer`, briefed with the simplicity, silent-failure and §2 lenses where they apply) | Opus · high | one fresh read instead of three |
| `compat-guardian`, once per major step on its formats (step 1's also reads the spec) | Opus · high | config, the bundle, `run.json`, the stage jsons, the scores, the card |

Every `Agent` call passes `model` and `effort`. Expected balance: Fable about a quarter, Opus
about two thirds, Sonnet the rest. The share is measured from the transcripts at each step's
end; above 30%, the next step's orchestrator moves to Opus and Fable keeps its named pieces.

**How the orchestrator stays small.** It briefs from §5 by reference (the step's bullet, the
owner doc's section, one question number), never by pasting. It reads a builder's report and
the reviewer's findings; it reads a diff in full only for the files of the xhigh rows above.
Fixes go back to the builder that holds the context (`SendMessage`), unless they are a few
lines. It never waits idle on a background job with work owed, and every measurement brief
carries a hard cap.

## 8. How a minor step is checked, and how a major step is reviewed
1. The builder runs its own files' tests and `ruff check` on them and reports the output in at
   most fifteen lines (never the full suite, never Spark).
2. The main thread reads the report, and the diff where §7 says so.
3. The combined review, spawned as each minor step lands, in parallel with the next build.
4. Once per major step: the ML audit and `compat-guardian` on the merged step, then **one fix
   round**, every finding fixed or justified.
5. The Spark batch, the full suite in the background, `doc-sync` on the step's owner docs,
   `worknotes/log.md`.
6. The review guide: what to read, in which order, what right looks like; the notebooks' guide
   cells are listed as code; at most two tests marked "read this test" per step (the EDS reads
   code, not tests).
7. **Review 1** by the EDS, then its fixes: from here the step's contracts are frozen and the
   next chat builds on them. **Review 2**, its fixes, and the step closes on the EDS's word.

## 9. Order, parallelism and time
1. Step 1: m1.1, then m1.2–m1.4 in parallel, then m1.5 and m1.6. From m1.1 on: m1.7→m1.8 (one
   agent), m1.9, m1.10, m1.11 and m1.13 in parallel; then m1.12; then m1.14.
2. Review 1 of step 1. A second chat may start m2.0, m2.4 and `statistics/calibration.py`.
3. After its fixes: m2.1 (when m2.0 is back), m2.2 and m2.3 in parallel; m2.5; m2.6; m2.7 and
   m2.8.
4. Review 1 of step 2. The next chat may start m3.1 and m3.2.
5. After its fixes: m3.3; m3.4; then m3.5, m3.6, m3.8 and m3.9 in parallel; m3.7; m3.10; m3.11.
6. The reviews of step 3; version 0.4.0.

**Time, as an estimate and not a target.** In working days of build: step 1 three (the spec
one, Foundations two), Training three, Evaluation four and a half, about 10.5 in all, plus the
EDS's reviews. With each review overlapping the next build, an approval on 11-16 ends the stage
around 12-02; with no overlap, around 12-07. **The EDS's target of about 11-20 is where step 1
is in review and step 2 has begun.** Stage 2 took nine days against a sizing of four; this
stage was sized at six and has grown by a fourth family, monotone constraints and seventeen
views. What moves with it: M2.4 (four days) then ends around 12-08 to 12-11, which leaves round
1b (12-07 to 12-11) little or nothing before the pre-release week of 12-14; the roadmap's own
fallback for that is that round 1b keeps the exit points and calibration depth moves to round
2. The roadmap rows are edited in m1.5, with the EDS's dates.

## 10. What "done" means for Stage 3
- `pytest` green with the `acceptance` tests; `pytest -m slow` green for the four families;
  `ruff check .` clean.
- `python -m core_modelling run conf/base/cc_acquisition.yml --stages training evaluation`
  writes a numbered run with its bundle, per-run ledger, report, card and drift reference; the
  same for `td_acquisition.yml`, and for the regression variant in the tests.
- The roadmap's exit: a calibrated model beats the baselines and never the oracle; the four
  families round-trip without pickle; no fold mixes a client's rows.
- Two runs of one config give one `model_hash`; a bundle scores the same in pandas and in Spark.
- Notebooks 04 and 05 run end to end on `dev`, import the public API only, and carry a guide
  cell before every step; `00_modelling_helper` shows every artifact of a run.
- A sign-off recorded from notebook 05 covers a later run with the same feature list.
- The owner docs say "built" where it is built; the decision rows are in place; the research
  note has moved to its lasting doc.

## 11. The plan's defaults (veto by number) and the risks
**Defaults this plan sets.**
- **A52.** Vetoed by the EDS on 2026-11-13: three major steps, with the spec inside step 1 and
  Evaluation in one step. (The plan had proposed five, with the spec and a second Evaluation
  step on their own.)
- **A53.** The config changes in place, with no `schema_version` bump and no migration. Q632's
  recorded outcome asked for both; that sentence overlooked D-007 (c) (no bump before user
  testing is under way; until then the shape changes in place). No config exists outside this
  repo at the old shape. A veto brings the bump: version 2, one migration for every M2.3
  removal and rename, one old-config test, in m1.7.
- **A54.** The package: `model/` (what every user of a trained model shares: the encoder, the
  families, applying a calibration, the bundle, scoring), `runs.py`, `training/`,
  `evaluation/`; statistics in `statistics/` and charts in `reporting/`, as D-137 has it
  (statistics and reporting functions are shared, the stage packages orchestrate).
- **A55.** A family has a seventh function, `fixed_params`, beside Q617's six.
- **A56.** The sign-off's public function is `sign_off(…, run, reason)` in `runs.py`, which
  reads the run and writes the entry; Q624 named it as a `record_decision` argument.
- **A57.** Every stage json of a run carries a flat `summary` block for `list_runs` and
  `show_run`.
- **A58.** Evaluation's metrics are computed from score cells aggregated in Spark, as EDA's
  are; the driver holds a row per client only for the explanation sample. The cells' grain is
  fixed in the spec; row-level formulas serve as the tests' oracle.
- **A59.** The four `dev` tests carry the marker `acceptance`: in the default suite, skippable
  in a quick loop, as `traps` is. They train `lgbm` with 15 trials, the `autonomous` share of
  one family, where Q643 said about 30.
- **A60.** Fold dealings are columns: `cv_fold`, `cv_fold_2`, ….
- **A61.** The last step's ML audit covers the whole chain; there is no separate final audit.
- **A62.** The chart prototype the EDS saw is copied beside this file
  (`prototype_explain_charts.py.txt`), because the session scratchpad does not survive a
  reboot. It goes with the folder.
- **A63.** At the close the research note moves to `docs/guides/modelling_faq.md`, with the
  stage's lasting questions, as Stage 2's did to `eda_fc_faq.md`.
- **A64.** Notebook 04 shows the sign-off view; notebook 05 guides the sign-off itself (Q642).

**Defaults the spec set (m1.1, 2026-11-13), to veto by number.** Each is in the config table
(`docs/components/config.md` → "The modelling fields (Stage 3)") or in `model_bundle.md`.
- **A65.** `decision.metric` allows `log_loss`, `roc_auc` and `ap` for a binary task, where
  the schema took any FLAML metric name: the others (`f1`, `accuracy`) judge a cut at 0.5,
  which nothing in the design uses.
- **A66.** Training's settings digest covers what Training reads: `training`,
  `features.order`, `features.kinds`, the feature decisions, `decision.type` and
  `decision.metric`, where A33 named the whole `decision`. A new baseline or a new `decision.n`
  then never orphans a trained run. Evaluation's covers `evaluation`, `decision` and `strata`.
- **A67.** The Tweedie objective's power is `training.tweedie_variance_power` (1.5 by default,
  refused with another objective). The `tweedie_deviance` metric is computed at a fixed power
  of 1.5 whatever the objective's power: the objective is loggable, the yardstick is not (the
  flaw Q656 corrected, one level down).
- **A68.** `evaluation.skip_views` (the views to leave out) replaces `evaluation.views`, since
  every view now renders by default and a person names the one to drop, not the sixteen to keep.
- **A69.** `training.selection.importance_floor` leaves the schema (nothing reads it); the
  pruning switch is `selection.prune`; `floor_z: null` switches the floor off.
- **A70.** `training.search_space` stays `{}` in a config and means the bounded ranges; the
  template prints them and `training.json` stores the space each family searched. Q605 had the
  defaults printed in every resolved config; they are rules as data of Training (m2.1), not
  config values.
- **A71.** The bundle's calibration is `{link, method, parameters, offset}`: the link (`logit`,
  `identity`, `log`) tells `apply_calibration` how the margin becomes `score_raw`, so it needs
  no knowledge of objectives. `bundle.json` holds the model library's version; the framework
  version is in the manifest, outside `model_hash`, so a patch release does not rename a model.
- **A72.** `run.json` holds what is known when the run starts (the input hashes, Training's
  digest, the Stage 2 run tokens, who and when). What the run produced (the feature signature,
  `recipe_hash`, `model_hash`, the seconds) is in `training.json`'s `summary` and the
  manifest: a file written first and never rewritten cannot hold them (Q647 listed them there).
- **A73.** `decision.metric`, `training.objective` and `training.calibration.method` are filled
  at load when null, so the resolved config states the value in force; a `set` on the
  objective refills the calibration method.
- **A74.** Folds: the converting clients are dealt in turn; every other client takes the plain
  hash fold, as Q649 has it (m1.9's bullet read "the others the same way"): dealing in turn
  needs one global order, cheap for a few thousand converting clients and a single-partition
  sort for millions of others.

- **A75.** An unordered categorical of which no level reaches the client count, or that is
  all null, is encoded and not refused: it carries only null against `__other__`, the per-run
  ledger shows its shares, Training warns and selection judges it. The encoder's reviewer
  leaned to failing loud; a run stopped by one useless column a person kept seemed the worse
  outcome.

- **A76.** Evaluation's rows carry the strata and not the modelling tags (Q633 listed both):
  every row there is eligible, so each tag is 1, which is why EDA already refuses a tag as a
  stratum. A source column named `part` or `cv_fold` is read as `source_<name>`, like `target`.

- **A77.** The single-feature baseline is chosen among the numeric features and ordered
  categoricals of the per-run ledger, by the train concordance stored there; a null takes the
  lowest score; an unordered categorical is never the single feature. The skill scores' base
  rate is the unsampled train split's rate. The scores table stores the strata columns (Q597).
  `test_contributions` (m3.6) is named `sample_contributions`: pytest would collect the old
  name.

- **A78.** Details of Training the spec fixed (`training.md`): the starts are FLAML's own
  clipped into the ranges (Q652; so 50 trees, 4 leaves, a learning rate of 0.1), and CatBoost's
  tree count, which FLAML never searches, starts at 50 too; pruning compares the decision's
  metric as a loss; `direction_model` is the sign of the rank correlation between a feature's
  values and its out-of-fold contributions; the explanation sample is 5,000 seeded train rows;
  the level factor's interval uses 200 replicates; the folds are dealt after sampling; the
  grid check runs on the reloaded bundle. The run number's form is `r` plus at least three
  digits, and an audit-log entry names it `run_id` (no second field `run`).

- **A79.** From step 1's reviews, where the built shape differs from this plan's signatures:
  `create_run(env, resolved, entity, stage2)` builds `run.json` from the resolved config
  itself and takes only the Stage 2 run tokens; `feature_signature` lives in
  `config/identities.py`, so the audit log and the runs need no model library;
  `check_bundle` lives in `model/scoring.py`; every family has `allowed_params` and `fit`
  refuses a name outside it; `fixed_params` takes the Tweedie power with no default;
  `check_order(X, encoder)` is run before every fit. Two promises narrowed: a run number that
  an audit-log entry names is never given again, while a crashed run that wrote no entry and
  whose folder was deleted may see its number reused; a sign-off covers every run of the data
  definition with the same feature list, earlier ones included.

- **A80.** `00_modelling_helper` is a dev-only code-reading aid, exempt from the notebooks'
  Public-API rule (`notebooks/README.md`): in step 1 there is no stored run to read, so it
  calls about twenty internal functions on the use case's own train rows to show what each
  returns. The alternative, making those functions public as `00_eda_fc_helper`'s readers
  were, would put them under the 1.0 compatibility promise. It defines nothing, writes only
  to a temporary folder and is committed without outputs. Whether it ships is M2.4's question.

- **A81.** From step 1's ML audit: the sampling has no seed of its own; its draw uses
  `training.seed`. `training.sampling` is loggable (Q388), so its own `seed` let a person
  pick the sample through the audit log after seeing results, which the log forbids for
  `training.seed` for that reason. Also from the audit: the client split joins Training's
  and Evaluation's digests and the recipe; names the framework owns (the objective, the
  seed, the constraints) are refused in `training.search_space`; a calibration that would
  reverse the order is refused.

Recorded with Q632 and still open to a veto with the spec: the emptied `lifecycle` config
section leaves the schema until M2.4.

**Risks and fallbacks.**
- **An item of m2.0 fails** (a family's fit does not equal FLAML's model, or the pieces do not
  work together): m2.1 waits and the EDS sees the item. The fold models give the framework its
  own out-of-fold number for the chosen configuration, so the equality is a check and not a
  dependency; a family that cannot pass is fixed in this stage, not dropped (D-037: M2 is never
  less than the crunch).
- **A review changes a contract after the next chat built on it.** A line in `log.md` (§3); the contracts are plain data shapes with one or two readers each,
  so a change is small.
- **Two chats, 8 GB.** One heavy job at a time (§3); `dev` for daily work; the canonical measurement runs alone.
- **Fable's five-hour limit stops an orchestrator.** The status table and `log.md` let an Opus
  chat take the step over; Fable's named pieces (m2.1, m2.6, m3.4's chain, the audits) wait.
- **CatBoost's seconds make 15 trials at `autonomous` slow on canonical** (m2.8): reported in
  review guide 2; the list and the budgets are the EDS's (Q651).
- **The bootstrap is slow at the bank's size** (m3.1 measures): fewer score bins, then
  `evaluation.intervals.replicates`.
- **The acceptance module is slower than estimated:** fewer trials first; it stays skippable.
- **Unverified until inside the bank** (not in this plan's path): the model libraries on an
  executor (A27), the same model on the bank's machines, plotly in JupyterLab (spike 5),
  security's view of the model files (Q621).
