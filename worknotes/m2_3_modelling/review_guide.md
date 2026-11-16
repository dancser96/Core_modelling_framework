# Stage 3 major step 1 (the spec and Foundations): review guide
_Written 2026-11-14 for the EDS · review 1 · the plan: `plan.md` beside this file · this file
holds the current review only and is replaced by the next step's guide_

**In short.** The settled design is in the owner docs, and everything Training and Evaluation
will stand on is built, reviewed and tested: the config fields, the client folds and
Evaluation's rows, the encoder, four model families, the bundle with one scoring path, and
numbered runs with the sign-off. Nothing trains or evaluates a model yet. The step's ML audit
found three gaps that would have let a wrong number through silently; all three are closed.
Seventeen defaults (A65–A81) and four questions (Q658–Q661) are yours to veto or answer; none
blocks step 2.

## 1. What to read, in this order
1. **The config table:** `docs/components/config.md` → "The modelling fields (Stage 3)", beside
   the `decision`, `features`, `training` and `evaluation` sections of `conf/base/TEMPLATE.yml`.
   Right looks like: every field you would set is there with a default you accept, and no
   field a user sets is silently ignored.
2. **`docs/components/model_bundle.md`,** Levels 1 and 2 (the first hundred lines), then the
   three tables `run.json`, `bundle.json`, `manifest.json`.
3. **The decision rows:** D-139 (runs, identity, the bundle), D-140 (the search, selection, the
   fits), D-141 (Evaluation and its report). Fourteen rows were edited in place: D-032, D-037,
   D-049, D-051, D-054, D-088, D-094, D-098, D-100, D-106, D-125, D-132, D-136, D-137.
4. **The helper notebook:** run `notebooks/00_modelling_helper.ipynb` (it needs `02_eda` and
   `03_feature_checks` run for the card config, which is done on this machine as of 11-14). Its
   guide cells say what right looks like per section. On the card config it shows the folds'
   converting clients differing by at most one, the four families reloading to identical
   margins, the bundle's hashes recomputing to the manifest's, scoring inside Spark equal to
   pandas, a changed byte refused, and two runs numbered `r001` and `r002`.
5. **The code,** in this order (lines):
   - `model/encoder.py` (269);
   - `model/family_inputs.py` (151) and `model/families.py` (124), then `model/lgbm_family.py`
     (177) in full; `xgb_family.py` (186) and `catboost_family.py` (187) for what differs;
   - `model/calibration.py` (124), `model/bundle.py` (297), `model/scoring.py` (137);
   - `dataset/folds.py` (125), and in `dataset/frames.py` the functions `_training_frame`,
     `_evaluation_rows` and `check_level_orders`;
   - `runs.py` (429: over the guideline; its functions belong together);
   - `config/schema.py`: `TASK_CHOICES`, the `Training` models, `_fill_task_defaults`, the
     search-space refusals; `config/replay.py`: `Entry`'s new fields and checks,
     `LOGGABLE_SETTINGS`, `signed_off`; `artifacts.py`: `SETTINGS_PATHS_BY_STAGE` and the
     stage versions.
6. **The specs of the next two steps,** Levels 1 and 2 only: `docs/components/training.md`,
   `docs/components/evaluation.md`. Each holds the audit's requirements for its step; the
   plan's steps 2 and 3 open with what must be settled when they start.
7. **Two tests worth reading:**
   `tests/test_scoring.py::test_score_spark_equals_score_frame_on_the_same_rows` (one scoring
   path) and `tests/test_folds.py::test_converting_clients_are_dealt_evenly_and_a_client_sits_in_one_fold`.

## 2. Defaults to veto, by number
Each is explained in `plan.md` §11.

| # | Default |
|---|---|
| A65 | `decision.metric` for binary allows `log_loss`, `roc_auc`, `ap` only |
| A66 | Training's digest covers what Training reads, not the whole `decision`; with A81, the client split too |
| A67 | The Tweedie deviance as a metric is always computed at a power of 1.5; `training.tweedie_variance_power` is the objective's |
| A68 | `evaluation.skip_views` replaces `evaluation.views` |
| A69 | `selection.importance_floor` removed; the switch is `selection.prune`; `floor_z: null` turns the floor off |
| A70 | `training.search_space: {}` means the bounded ranges; the template prints them |
| A71 | The bundle's calibration is `{link, method, parameters, offset}`; the framework version is in the manifest, outside `model_hash` |
| A72 | `run.json` holds what is known at the run's start; what the run produced is in `training.json` and the manifest |
| A73 | `decision.metric`, `training.objective`, `calibration.method` are filled at load when null |
| A74 | Converting clients are dealt in turn; every other client takes the plain hash fold |
| A75 | An unordered categorical with no level at the client count is encoded, not refused |
| A76 | Evaluation's rows carry the strata, not the modelling tags (each tag is 1 on an eligible row) |
| A77 | The single-feature baseline is chosen among numeric and ordered features by the stored train concordance; a null scores lowest |
| A78 | The search starts at FLAML's own start clipped into the ranges; CatBoost's tree count starts at 50 |
| A79 | Signatures that changed in review: `create_run(env, resolved, entity, stage2)`, a family's `load` takes bytes, `feature_signature` and `recipe_hash` live in `config/identities.py`; a crashed run that wrote no entry may see its number reused; a sign-off covers every run with the same feature list |
| A80 | `00_modelling_helper` is dev only and exempt from the notebooks' Public-API rule |
| A81 | The sampling has no seed of its own: its draw uses `training.seed`, which the audit log can never set |

## 3. Questions
- **Q658. The roadmap's dates.** The M2.3 row (11-16 to 11-24, six days), its risk trigger
  and "a spike fails before 11-16" are stale. The plan estimates the stage ends around 12-02
  with reviews overlapping the next build. *Default:* M2.3 as 11-13 to 12-02 and M2.4 as 12-03
  to 12-10; M3 and the pre-release week unchanged, with the roadmap's existing fallback (round
  1b keeps the exit points; M3's calibration checks move to round 2).
- **Q659. Split `config/schema.py`?** It is 924 lines. A reviewer suggests moving the `training`
  section's models into their own module. *Default:* keep one file: it is the one place a
  reader looks for every field.
- **Q660. Stricter type coercion in the config?** `folds: "5"` loads as 5, in every section, as
  before this stage. *Default:* leave as is; a separate decision for the whole schema.
- **Q661. `conf/local/cc_acquisition.yml`.** A gitignored copy from 11-11 that nothing in the
  repo reads; it uses six removed fields and no longer loads. *Default:* delete it. I have not
  touched it.

## 4. What the reviews found, and what was done
Every minor step had one combined review; the step ended with an ML audit, a compatibility
check and a spec self-review. Every finding was fixed or is recorded where the next step
starts.

| Piece | Found | Done |
|---|---|---|
| Encoder | A value's level text depended on which equal value came first; an empty train frame, duplicate columns and an encoder read from disk were not checked | Fixed; the level-text rule now lives once, in `statistics/distributions.py`, for EDA and the encoder |
| Families | A frame in another column order trained with the constraint on the wrong feature; a misspelt parameter trained on the defaults; binary ignored `objective` | `check_order` before every fit, an allowed-parameter set per family, the objective refused; `load` takes the verified bytes |
| Folds and frames | A stale test; an empty test or validation part no longer caught | Fixed; the empty-part check is an Evaluation requirement |
| Config, audit log | CatBoost's `class_weights` and mixed-case names passed the class-weight refusal; EDA's report showed a metric its digest no longer tracks | Fixed; the metric row left EDA's choices |
| Bundle, scoring | The calibration and the recipe were not validated before writing; `model_hash` was a plain concatenation; a non-finite score passed | Fixed; the hash covers each file's name and length; the model is built from the bytes that were verified, so an executor writes no file |
| Runs | A sign-off could record a signature that did not match its list; `create_run` could loop forever on a case-insensitive file system | Fixed; the signature is recomputed from the list |
| **ML audit** | **F1** the client split was in no identity a run is found by, so an edited split would score a run on its own train clients; **F2** a constant in `training.search_space` could override the objective, the seed or the constraints; **F3** the calibration accepted numbers that reverse the ranking | All three fixed. Eight further points are requirements in `training.md`, `evaluation.md` and `lifecycle.md` |
| Compatibility | No silent break of a stored artifact. `hash_version` was stored but never checked; a `run` entry with a null `run_id` was refused | Fixed. For the 1.0 freeze: a removed loggable setting makes an old log unreplayable; the stage digests cover whole sections, so a new defaulted field orphans stored runs |

Three things the builders measured that Training's step needs are in `training.md` → "The
encoder and the families": what reaches FLAML as a constant and what only as a fit argument,
and that the search needs one frame per family. One new trap, T40 (`docs/context/lessons.md`):
PySpark starts its local Python workers with `python3` from the PATH; the environment adapter
now points them at the driver's interpreter.

## 5. Verified
- **The full suite, once, at the step's end:** 936 passed, 1 failed, 11 deselected, in 11 min
  36 s. The failure was a test in `tests/test_eda.py` that still built `Frames` with its old
  fields; the test was corrected and passes on its own rerun, with the split, folds and Spark
  scoring tests (15 passed). The whole suite was not repeated for that one-line test fix.
- **`ruff check .`** clean.
- **EDA and Feature Checks** rerun for the card config on the local data (2 min 46 s): the
  stored artifacts are on the current stage version. `td_acquisition`'s are stale and are
  rerun before its first training (step 2's end).
- **The helper notebook** runs end to end on the card config with every check true, twice; the
  four saved model files had the same hashes in both runs.
- The version is `0.4.0.dev0` during the build.

## 6. Not verified, and known limits
- Inside the bank: the model libraries on a Spark executor, the same model scoring the same on
  the bank's machines, plotly in JupyterLab (all on spike 5's trip).
- The first EDA rerun failed with "No buffer space available" while three agents ran tests: the
  machine's memory, not the code. A Jupyter kernel from 11-11 still holds a Spark JVM of about
  2 GB; closing it makes the heavy runs of step 2 safer.
- Nothing trains a model yet, so the folds, the bundle and the runs are exercised by the tests
  and the helper notebook only.

## 7. What step 2 starts from
`docs/UPDATES.md`, the plan's §4 and "Major step 2" (which opens with what to settle first),
`docs/components/training.md`, and the top entry of `worknotes/log.md`. The pieces marked
*free* (m2.0, m2.4, `statistics/calibration.py`) can start now; the rest after this review's
fixes.
