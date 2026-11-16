# Model bundle, manifest and run record
**Status:** built in M2.3 major step 1 (2026-11-13/14), for the EDS's review · **Legacy:** none
ported: the crunch pickled the whole `AutoML` object and named runs by a long manifest
**Related:** [training](training.md) (writes a run) · [evaluation](evaluation.md) (reads one) ·
[config](config.md) (the identities, the audit log's `run` and `sign_off` entries) ·
[feature ledger](feature_ledger.md) (the per-run part) · [inference](inference.md) and
[lifecycle](lifecycle.md) (the bundle's later readers) · [monitoring](monitoring.md) (the drift
reference) · D-037, D-051, D-052, D-088, D-094, D-136, D-139

Read it in three levels: Level 1 gives the essentials, Level 2 how the parts connect, Level 3
every detail.

## Level 1: Summary
A **run** is one Training call and its Evaluation. It lives in one numbered folder,
`<use_case>/06_models/r007/`, and is complete in itself: everything a later reader needs is
inside it. The **bundle** is the trained model as plain data, three files and never a pickle:
the model library's native file, `bundle.json` (the encoder, the calibration, the recipe) and
`manifest.json`.

- **Three names for people:** the data definition (its 12-character hash), the run (`r007`) and,
  from M2.4, a model version. Every other identifier is bookkeeping, kept in `run.json`,
  `training.json` and the manifest.
- **One hash names the model.** `model_hash` is one SHA-256 over the model file and
  `bundle.json`. Every loader recomputes it first, refuses a difference and builds the model
  from the very bytes it verified; two runs of one resolved config give the same hash in every
  family.
- **One scoring path.** `score_frame` turns a frame of raw feature values into `margin`,
  `score_raw` and `score`, in pandas and, through `score_spark`, inside Spark. Training's
  self-check, Evaluation and later Inference all use it.
- **Who writes and reads.** Training writes the run folder and the bundle; Evaluation,
  `list_runs`, `show_run`, `compare_runs` and the sign-off read them; `register` (M2.4) will
  copy the bundle unchanged.

## Level 2: How it fits together

### What depends on what
- The **encoder** (plain data, fitted on train) fixes the model's column order and every code.
  The model file is meaningless without it, so both are under one hash.
- The **calibration** (plain numbers) turns the model's margin into the score. It is fitted by
  Training and applied by `apply_calibration`, the same code at every scoring.
- The **recipe** is everything a retrain needs to repeat the model on new data: it is inside
  `bundle.json` and has its own `recipe_hash`, which leaves the fitted numbers out.
- `run.json` is written **first** and never again: it reserves the run number and records what
  the run was built from. What the run produced is in `training.json` and the manifest.

### The run folder
`<use_case>/06_models/r007/`, the runs of every data definition of a use case side by side:
- `run.json`: the identity record, written first, never rewritten;
- `bundle/`
  - the model file (`model.txt`, `model.json` or `model.cbm`),
  - `bundle.json`,
  - `manifest.json`;
- `ledger_run.parquet` with its sidecar: the per-run feature ledger ([feature ledger](feature_ledger.md));
- `stage2/`: the run's own copy of what it needs from Stage 2 (the final features' ledger rows,
  EDA's bin edges and shares per period, EDA's lift table);
- `training/`: written last, the commit marker of a trained run ([training](training.md));
- `evaluation/`: written whole by each Evaluation ([evaluation](evaluation.md)).

A folder without `training/` is a crashed run: it is listed as incomplete, and its number
stays taken while the folder exists.

### How one bundle is written, loaded and scored
1. `create_run` takes the next number, creates the folder exclusively and writes `run.json`.
2. Training fits the encoder, selects, searches, fits the final model and the calibration.
3. `write_bundle` checks the encoder, the calibration and the recipe before anything is on
   disk, saves the model through the family's `save`, writes `bundle.json`, computes
   `model_hash` over the two files and writes `manifest.json`.
4. `check_bundle` reloads the bundle from disk and scores a fixed sample of 1,000 train rows; any
   difference from the scores of the model in memory fails loud (the self-check at save).
5. `load_bundle` reads the files as bytes, recomputes `model_hash`, refuses a difference from
   the manifest, and returns a `Bundle` built from those bytes: the booster, the encoder, the
   calibration and the feature list.
6. `score_frame(bundle, frame)` encodes the frame, predicts the margin through the family's
   `predict` and applies the calibration. `score_spark` runs the same function per partition
   with `mapInPandas`: the driver ships the bundle's bytes and each partition rebuilds the model
   once, in memory, verifying the hash again; an executor writes no file, and one whose model
   library differs in version from the driver's fails loud.

### The functions in brief
- `model/encoder.py`: `fit_encoder`, `encode_frame`.
- `model/families.py` and one module per library: `FAMILIES` (`fit`, `predict`, `describe`,
  `save`, `load`, `contributions`, `fixed_params`, `file_name`, `allowed_params`),
  `check_params`, `check_monotone`; `model/family_inputs.py`: the checks the families share,
  `check_order` among them.
- `model/calibration.py`: `apply_calibration`.
- `model/bundle.py`: `write_bundle`, `read_bundle_files`, `load_bundle`.
- `model/scoring.py`: `score_frame`, `check_bundle`, `score_spark`.
- `config/identities.py`: `feature_signature` and `recipe_hash`, beside the config's hashes,
  so the audit log and the runs read them without loading a model library.
- `runs.py`: `create_run`, `read_run`, `find_run`, `list_runs`, `show_run`, `sign_off`.

### How it is checked
- Per family and task: save, load, identical margins; a shuffled frame scores the same; two
  fits give one file hash.
- The bundle: `model_hash` repeats over two writes and moves with one changed byte; a tampered
  file is refused at load; the self-check fails loud; no time, run or person in `bundle.json`.
- Scoring: `score_spark` equals `score_frame` on the same rows; a missing feature fails loud.
- Runs: the next number when the folder exists and after a deletion; `run.json` cannot be
  written twice; a folder without `training/` lists as incomplete.

## Level 3: Details

### Requirements and design constraints
1. **Plain data, never pickle** (D-051): the model in its library's lossless native format,
   everything else JSON. The formats: LightGBM text (`model.txt`), XGBoost JSON (`model.json`,
   both XGBoost families), CatBoost `.cbm` (`model.cbm`).
2. **`bundle.json` holds no time, run or person**, so the same model always has the same
   `model_hash`. The manifest and the resolved config carry those and sit outside the hash.
3. **A loader verifies before it reads:** `model_hash` is recomputed from the two files'
   bytes and compared with the manifest; a difference is refused, naming the folder. The model
   is then built from those same bytes (a family's `load` takes bytes, not a path), so what
   was verified is what scores.
4. **The loader pins what the libraries leave open:** the frame is put in the encoder's column
   order (LightGBM accepts a wrong order silently), numerics are float64, XGBoost predicts with
   its explicit tree range, CatBoost's declared categoricals are integers. A feature missing
   from the frame fails loud.
5. **One `model_hash` per model in every family, on every machine:** CatBoost's five
   run-specific metadata entries are deleted before saving and LightGBM's text model is saved
   without its thread-count line; the models score the same without them.
6. **`run.json` is written once.** The folder is created exclusively, so two people training at
   once get two numbers. The next number is one above the highest among the existing folders
   and the runs any audit log of the use case names, so a number that an entry names is never
   given again, also after its folder is deleted. A crashed run that wrote no entry and whose
   folder was deleted by hand leaves no trace, so its number may be given again. Inside the
   bank one data root is one entity, so the numbers run per use case and entity.
7. **Versioned** (`CLAUDE.md` §2): `bundle_schema_version`, `manifest_schema_version`,
   `run_schema_version` and the encoder's `schema_version`, each 1. A reader refuses another
   version and names the fix.
8. **Task-agnostic shapes:** the output columns are `margin`, `score_raw` and `score` for both
   tasks; the calibration has one shape for both.
9. **Local paths only in M2.3;** the HDFS transport arrives in M2.4 for every artifact at once
   (D-136). `score_spark` ships bytes, never a path, so it does not depend on it.

### `run.json`
| Key | Holds |
|---|---|
| `run_schema_version` | `1` |
| `run_id` | the run number, `r007` |
| `use_case`, `entity` | whose run it is |
| `started_at`, `started_by` | UTC time and the person, as the audit log names one |
| `config_hash`, `data_definition_hash`, `resolved_input_hash`, `replayed_to`, `hash_version` | the resolved config's identity, the same keys every stage json carries |
| `training_settings_digest`, `training_settings` | the digest of the settings Training reads and their values ([config](config.md#the-modelling-fields-stage-3)); Evaluation finds its run by this and the data-definition hash |
| `stage2` | the run tokens of the EDA and Feature Checks runs it was trained against |
| `sources_digest` | where the data physically was, as in every stage json (D-137) |
| `framework_version` | the version that trained |

What the run produced is not here, because the file is written before anything is trained: the
feature signature, `recipe_hash`, `model_hash`, the family, the counts and the seconds are in
`training.json`'s `summary` and in the manifest. Whether a run is evaluated or signed off is
read from its folder and the audit log when runs are listed.

### `bundle.json`
| Key | Holds |
|---|---|
| `bundle_schema_version` | `1` |
| `task` | `binary` or `regression` |
| `family` | `lgbm`, `xgboost`, `xgb_limitdepth` or `catboost` |
| `model_file` | the model file's name |
| `features` | the final features, in the model's column order |
| `encoder` | the encoder, below |
| `calibration` | `{link, method, parameters, offset}`, below |
| `output_columns` | `[margin, score_raw, score]` |
| `recipe` | the recipe, below; exactly its listed keys, so nothing run-specific can enter a hash |
| `library_version` | the model library and its version; a loader running another version warns, naming both, and loads (a native model file is built to load across versions) |

### `manifest.json`
| Key | Holds |
|---|---|
| `manifest_schema_version` | `1` |
| `files` | the two hashed file names, in name order |
| `model_hash` | one SHA-256 over those files in name order, each as its name, its length and its bytes, so bytes moved between the two files cannot give the same hash |
| `hash_version` | the version of the canonical form behind `recipe_hash` and the feature signature, as beside every hash the package stores |
| `recipe_hash`, `feature_signature` | below |
| `run_id`, `data_definition_hash`, `config_hash`, `resolved_input_hash` | the run the bundle belongs to |
| `framework_version`, `written_at` | provenance |

### The encoder
Fitted on the train frame only (`CLAUDE.md` §4.4), plain data, `schema_version` 1:

```json
{"schema_version": 1, "unordered": "native", "min_level_client_count": 50,
 "features": [
   {"name": "income",  "kind": "numeric"},
   {"name": "rating",  "kind": "ordered",   "levels": ["C", "B", "A"]},
   {"name": "channel", "kind": "unordered", "levels": ["branch", "online"], "pooled": ["fax"]}]}
```

| Kind | Code | Null | Unseen level |
|---|---|---|---|
| `numeric` | float64, clipped to ±1e30 (so ±inf stays apart from null) | stays null | — |
| `ordered` (a categorical named in `features.order`) | its position in the declared list, as float64 | stays null | null, counted |
| `unordered` (every other categorical) | 1 … K for the kept levels, most frequent in train first; K + 1 for `__other__` | 0 | K + 1, counted |

- A level is kept when at least `min_level_client_count` distinct train clients have it; the
  others are listed under `pooled` and share the `__other__` code.
- Levels are compared as text, by EDA's rule (`level_text` in `statistics/distributions.py`: a
  boolean in lower case, an integral number without `.0`), so an integer column that arrives as
  float in one frame and as integer in another gives the same levels.
- With `unordered: native` the codes are integers and the family declares the column
  categorical to its library; with `codes` the same values are passed as numbers.
- The text rule is part of `schema_version` 1: changing it changes every code's meaning. It
  differs from Spark's own string cast for a float (`3`, where Spark writes `3.0`), so a
  declared order is written in the encoder's form; a level written otherwise fails loud at fit.
- An unordered feature of which no level reaches the client count, or that is all null, is
  still encoded: it carries only null against `__other__`, and the per-run ledger's shares show
  it.
- A train level missing from a declared order fails loud at fit: the list is a contract.
- Nothing is imputed, and no statistic other than the levels is fitted.
- `encode_frame` also returns one row per feature with the null, infinite, `__other__` and
  unseen shares of the frame it encoded.

### The calibration and the output columns
`calibration` is `{link, method, parameters, offset}`. The link comes from the objective:
`logit` for binary, `log` for the Tweedie and Poisson objectives, `identity` for the other
regression objectives. With `m` the margin:

| Link | `score_raw` | `score` |
|---|---|---|
| `logit` | `sigmoid(m)` | `none`: `sigmoid(m + offset)`; `platt`: `sigmoid(a · m + b + offset)`; `beta`: `sigmoid(a · ln(p) − b · ln(1 − p) + c + offset)` with `p = sigmoid(m)` |
| `identity` | `m` | `m × factor` |
| `log` | `exp(m)` | `exp(m) × factor` |

- `parameters` holds `{a, b}` for `platt`, `{a, b, c}` for `beta`, `{factor}` for `mean`, and
  nothing for `none` (the factor is then 1).
- A calibration that would reverse or flatten the model's order is refused, at save and at
  load: Platt needs `a > 0`, beta `a ≥ 0` and `b ≥ 0` with one of them positive, the factor
  `> 0`. Every calibration map is then increasing, so rank metrics are the same on `score` and
  on `score_raw`.
- `score_raw` leaves out both the calibration and the offset. Under `negative_downsampling` it
  is a probability at the sampled rate: its order is usable, its level is not.
- `offset` is the prior-shift offset, `logit(true rate) − logit(sampled rate)`: zero without
  sampling and under `client_sample`, and always zero for regression (`CLAUDE.md` §4.7).
- The evidence behind the numbers (the two rates, the out-of-fold log loss of each method, the
  factor's interval) is in Training's `calibration` table, not in the bundle.
- A score is never NaN or infinite: `score_frame` refuses one, naming the column and the
  count. A probability of exactly 0 or 1 can occur at an extreme margin (float64's limit), so
  a log loss clips before it takes a logarithm.

### The hashes
| Hash | Covers | Changes when |
|---|---|---|
| `model_hash` | the model file and `bundle.json` | the trees, the encoder, the calibration numbers or the recipe change: every retrain |
| `recipe_hash` | the recipe, exactly the keys `task`, `family`, `parameters` (with the tree count and the seed), `features` (the final ones, in order), `encoder` (with its frozen levels), `monotone`, `calibration` (the spec: exactly the method and the folds), `split` (the client split), `sampling`, `data_definition_hash`; its task, family, features and encoder must equal the bundle's own, and its parameters hold no thread count, which would give one model two hashes on two machines | the recipe changes; a production retrain keeps it and recomputes the calibration numbers (D-052) |
| feature signature | the final feature list, in order | a feature enters or leaves; a sign-off covers every run of the same data definition with the same signature, earlier ones included |

A retrain keeps the encoder's levels, so a level new in production data maps to `__other__` and
a code never changes meaning under a live model.

### Code map
- `model/encoder.py`, `model/families.py`, `model/family_inputs.py`, `model/lgbm_family.py`, `model/xgb_family.py`,
  `model/catboost_family.py`, `model/calibration.py`, `model/bundle.py`, `model/scoring.py`:
  what every user of a trained model shares.
- `runs.py`: the run folder, `run.json`, listing and showing runs, the sign-off.
- `environment.py`: `models_dir(env, cfg, *parts)`, the path of `06_models/` and what is under it.

### Interface
```python
fit_encoder(train, features, kinds, order, min_level_client_count, unordered) -> dict
encode_frame(frame, encoder) -> tuple[pd.DataFrame, pd.DataFrame]

FAMILIES[name].fit(X, y, params, task) -> object
FAMILIES[name].predict(booster, X) -> np.ndarray                 # the margin, float64
FAMILIES[name].describe(booster) -> dict
FAMILIES[name].save(booster, path) -> None
FAMILIES[name].load(data) -> object                              # the model file's bytes
FAMILIES[name].contributions(booster, X) -> np.ndarray           # n × (features + 1)
FAMILIES[name].fixed_params(task, objective, encoder, monotone, seed, threads,
                            tweedie_variance_power) -> dict
check_monotone(family, booster, X, monotone, rows=200) -> None

write_bundle(folder, family, booster, content, identity) -> str  # the model_hash
load_bundle(folder) -> Bundle                                    # public
read_bundle_files(folder) -> dict[str, bytes]
check_bundle(folder, sample, expected) -> None                   # model/scoring.py
recipe_hash(recipe) -> str                                       # config/identities.py
feature_signature(features) -> str                               # config/identities.py
check_order(X, encoder) -> None                                  # model/family_inputs.py; before every fit
check_params(family, params) -> None                             # before the first trial
apply_calibration(margin, calibration, task) -> tuple[np.ndarray, np.ndarray]
score_frame(bundle, frame) -> pd.DataFrame                       # public: margin, score_raw, score
score_spark(folder, rows, keep) -> DataFrame

models_dir(env, cfg, *parts) -> str
create_run(env, resolved, entity, stage2) -> str                 # stage2: the EDA and Feature Checks run tokens
read_run(env, cfg, run) -> dict
find_run(env, resolved, entity, run=None) -> str
list_runs(env, cfg, entity) -> pd.DataFrame                      # public
show_run(env, cfg, entity, run) -> str                           # public
sign_off(cfg, entity, env, run, reason) -> Entry                 # public
```

### Open questions
- Inside the bank, unverified: the model libraries on a Spark executor; the same model scoring
  identically on the bank's machines; security's view of `.cbm` and LightGBM's text model.
- XGBoost's JSON writer under another locale (its docs warn of locale-dependent floats).
- A probe that scores a fixed table at every load, to catch a library upgrade that changes the
  scores: Phase 3 wishlist (D-051).
