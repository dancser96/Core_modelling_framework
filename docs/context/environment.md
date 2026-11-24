# Environment and bank parity

**Verdict:** we develop outside the bank on synthetic data, against pinned versions that match the
internal devcontainer. Everything environment-specific sits behind one adapter plus `conf/local/`,
so moving the code inside needs configuration, not code edits.

## Two environments

| | Outside (development) | Inside the bank (target) |
|---|---|---|
| Machines | Windows 11 PC via WSL2 (Ubuntu); MacBook (native) | Internal devcontainer (JupyterLab / VS Code) |
| Data | **Synthetic only** — generated panels that match the real schema | Real panel on Hive/HDFS |
| Spark | PySpark 3.4.3 in local mode, Java 11 | Cluster Spark (CDP-style), Hive tables, raw `hdfs://` paths |
| Storage | Local filesystem | Local workspace, plus HDFS for registered models and scores |
| LLM | Claude Code for development | Claude via API or Bedrock, limited tokens, not the newest models |

**Code flow is one-way.** To release: download a zip of the repo, then copy its contents into the
internal repo. Nothing comes back out: no data, no outputs, no code. Changes made inside are
reported back **in words** and re-applied here. Inside, the package is published through Nexus into
the base image; images are supported for a year, and the image a use case starts on sets its
default framework version, which the use case pins and may raise within the image's year (D-024).

## Pinned versions (bank parity — keep in sync with `requirements.txt`)

| Package | Version | Note |
|---|---|---|
| Python | 3.11 | Unlikely to move soon |
| numpy | 2.3.5 | Devcontainer ships 2.3.4; installing FLAML bumps it to 2.3.5 |
| pandas | 2.2.3 | |
| pyarrow | 19.0.1 | |
| pyspark | 3.4.3 | Needs Java 8/11/17; the bank uses **OpenJDK 11.0.25** |
| scikit-learn | 1.8.0 | |
| lightgbm | 4.6.0 | macOS needs `libomp` (Homebrew) |
| catboost | 1.2.8 | |
| xgboost | 3.2.0 | macOS needs `libomp` (Homebrew) |
| flaml | 2.7.0 | Installed as plain `flaml` on top of the devcontainer |
| shap | 0.50.0 | |
| scipy | 1.16.2 | Devcontainer package; pinned early because scikit-learn, LightGBM, XGBoost, CatBoost and SHAP pull it in |
| plotly | 6.3.1 | Devcontainer package; pinned early because CatBoost pulls it in. Bundles plotly.js 3.1.1 (7.x bundles plotly.js 4) |
| pydantic | 2.12.5 | v2 API only |
| pyyaml | 6.0.3 | |
| matplotlib | 3.10.8 | |

Newer devcontainer images may move packages forward. When the user reports new versions, update
this table and `requirements.txt` in the same change and re-run the tests.

**Also in the standard devcontainer (usable; pin in `requirements.txt` on first use, D-012; scipy,
plotly and jinja2 are already pinned):**

| Package | Version | Likely use |
|---|---|---|
| scipy | 1.16.2 | Synthetic data, statistics (also a scikit-learn dependency) |
| statsmodels | 0.14.5 | Statistical tests and intervals |
| seaborn | 0.13.2 | Exploration in notebooks (reports use plotly) |
| plotly | 6.3.1 | Report charts (D-036) |
| jinja2 | 3.1.6 | Required by pandas Styler for styled HTML tables (pinned 2026-11-04, the EDA report) |

**Dev-only tools** (`requirements-dev.txt`, never needed inside the bank): pytest, ruff,
ipykernel, nbformat and nbclient. plotly renders charts in a notebook only with nbformat; Jupyter
installs it inside the bank, but `ipykernel` alone doesn't locally (D-013). nbclient (0.11.0
installed) re-runs a notebook headless and in place (`jupyter execute --inplace <notebook>`; the EDS,
2026-11-10).

A package that other packages pull in must be pinned even before our code uses it: without the
pins, pip resolved scipy 1.17.1 and plotly 7.1.0 locally (2026-10-14). The package's own
`pyproject.toml` declares what `core_modelling` imports, scipy, plotly and jinja2 among them, with
ranges that hold the pins, so a wheel installed into the base image from the package index
imports the reports' modules.

**Installed on top, like FLAML:** optuna 5.0.0 (the version `pip install optuna` resolves to inside
the bank; the predefined-model tuning path, Phase 3, D-020). Its API is unverified here: check
multi-objective studies and pruning against 5.0 before relying on them.

## Known compatibility facts

- **Verified in the crunch:** PySpark 3.4.3 + numpy 2.x breaks at import of pandas-on-Spark
  (`np.NaN` was removed in numpy 2.0). FLAML imports pandas-on-Spark transitively, so
  `import flaml` crashes. **Fix:** restore the alias (`np.NaN = np.nan`) before any pyspark/flaml
  import. This is permanent until the bank moves to PySpark ≥ 3.5. The shim belongs in the
  environment adapter and is imported first by every entry point.
- **Verified in the crunch:** the HDFS paths are raw `hdfs://…` URIs, not a local mount.
  - `pathlib` collapses `hdfs://` to `hdfs:/`.
  - `pathlib.Path.read_*` and `pickle` can't read HDFS.
  - Reading or writing HDFS files outside Spark needs the `hdfs dfs` CLI (`-put`, `-get`, `-cat`),
    which is available internally.
- **Verified (2026-10-14, local):** FLAML 2.7.0 `AutoML.fit(estimator_list=["lgbm"], custom_hp=...)`
  searches one model family inside our own ranges (partial overrides of the default space work).
  `automl.config_history` keeps only improving trials; a per-trial history needs FLAML's log file
  (unverified).
- **Verified (2026-11-11, local, spike 2):** FLAML 2.7.0 fits xgboost 3.2.0 (binary and
  regression, 6,000 rows × 15 features with 5% nulls), and `automl.predict` equals the fitted
  estimator's own predictions exactly when FLAML gets a numpy array or `skip_transform=True`.
  **Given a DataFrame, FLAML fills numeric nulls with the column median first** (a
  `SimpleImputer` fitted on the whole frame in `flaml/automl/data.py`; it also drops constant
  columns and moves category columns first), so the saved booster scores raw nulls differently
  from what the search judged: up to 0.40 apart in probability on that frame (checked
  2026-11-11). Training therefore passes `skip_transform=True` on every fit (D-094, T38).
- **Verified (2026-11-11, local, spike 3):** PySpark 3.4.3 `toPandas()` with pandas 2.2.3 and
  pyarrow 19.0.1 gives the same values with Arrow on (fallback off, as the session sets it) and
  off for the synthetic mart, holdings, extract and model input. A `date` column arrives as
  Python `datetime.date` objects (object dtype), a decimal as `Decimal` objects, a nullable
  integer as float64 with NaN and a timestamp as `datetime64[us]`. An array or struct column
  differs in container type between the two paths (not inspected further; the framework
  collects none). **Never switch Arrow off:** the non-Arrow path fails on any timestamp column
  (`TypeError: Casting to unit-less dtype 'datetime64'`). Not tested: the bank's Spark build.
- **Verified in FLAML 2.7.0:** for classification, passing `groups` turns the automatic split into
  a group split; regression also needs `split_type="group"`, or its automatic split stays by rows
  (`decide_split_type` in `flaml/automl/task/generic_task.py`). Train rows repeat clients across
  periods, so a client-grouped split is needed. The framework deals its own client folds and passes them
  to FLAML as a splitter object for both tasks (D-106).
- **Verified (2026-11-11, local, spike 1)** on 76,000 panel rows of 19,650 clients (3.9 rows
  each), `lgbm`, groups = the client:
  - classification with `groups`: holdout and 5-fold CV both put no client on both sides (0 over
    all 50 folds); `eval_method="auto"` chose a 10% holdout at this size;
  - regression: `groups` alone leaves the holdout split by rows (6,498 clients on both sides);
    with `split_type="group"` holdout and CV are disjoint; classification without groups leaks
    the same way (6,476), so the check does detect it;
  - `sample=True` trains its early trials on the first rows of the training frame in the order it
    was given, not on a random sample of rows or clients (FLAML shuffles only for the non-group
    split types): the first 10,000 rows were 10,000 clients' first period when the frame was
    sorted by period, and 2,544 whole clients when sorted by client. It runs only for a holdout
    above 40,000 rows; under CV, and below that size, every trial uses all rows, and the final
    refit always does. The framework's search always cross-validates on its own folds and keeps
    `sample` off, so the row order plays no part (D-106);
  - read in the source, not run: a class under 20 rows makes FLAML duplicate rows without their
    groups (`auto_augment`); it would fail loud on the length check.
  No sample weights in Phase 2 (D-117); the fallback stays in `docs/components/training.md`.
- **Assumed:** a source period never changes after it has been loaded (no late-arriving rows or
  restatements). Reproducibility from the resolved config + hashes depends on it (`CLAUDE.md`
  §4.10); the data-definition hash describes the data, it doesn't fingerprint it. Upstream data
  facts are the data owners' and the platform's responsibility, not the framework's (D-079): whether
  source periods are restated, when the monthly mart lands, and how storage permissions differ per
  entity. The framework states its assumption, reads tables and paths from `conf/local/`, and
  training's count check against the EDA artifact catches a restatement in between (D-088).
- **Verified (2026-11-11, local, spike 2):** non-pickle round trips of FLAML-fitted models
  (binary and regression, a numeric frame with 5% nulls), predictions compared with the fitted
  model's after reload:
  - `lgbm`: the text model (`booster_.save_model`) is bit-identical; the JSON dump
    (`dump_model`) cannot be loaded back (`LightGBMError`);
  - `xgboost`: JSON and UBJSON, into a fresh sklearn wrapper or a `Booster`, are bit-identical;
  - `catboost`: `.cbm` is bit-identical; its JSON loads back but differs by up to 2e-16 (binary)
    and 1e-13 (regression, values in the hundreds);
  - scikit-learn forests have none (D-051).
- **Verified (2026-11, local, the audit):** the same round trips hold with categorical features,
  which the framework encodes to codes before any library sees them, and for models fitted by
  Training's own function: a bundle written and loaded back scores a frame exactly as the fitted
  model does, for every family on a binary target and for `lgbm` on a regression target
  (`tests/test_bundle.py`).
- **Assumed, unverified:** no internet access from the bank's notebooks, so reports embed plotly.js
  instead of loading it from a CDN (~4–6 MB per report, not optimised in Phase 2, D-036; the model
  results report measured 5.9 MB for a binary run and 5.6 MB for a regression run). Plotly
  rendering and report opening time inside the bank's JupyterLab are also unverified; the EDS's
  JupyterLab test inside the bank shows both.
- **Assumed, unverified (Evaluation, M2.3 step 3):** to check or time inside the bank
  ([evaluation](../components/evaluation.md#open-questions)):
  - Evaluation scores inside Spark through `mapInPandas`, rebuilding the model once per
    partition and setting `threads` from the task's CPUs (`spark.task.cpus`); verified locally
    only;
  - `score_edges` runs two `approxQuantile` passes per binary scorer: time it on a large scores
    table;
  - `frames.rows` is computed about six times per Evaluation run;
  - the cells collected to the driver grow with the periods and the replicates: per replicate,
    at 1M rows over 12 periods, about 6,900 per-period cells and 700 pooled.

## Change requests

Every production change goes through a change request (`docs/components/lifecycle.md`). The first
one is very slow; later, iterative ones are quicker (the LDS, 2026-10-21). No durations are
known yet. A long change freeze around the year end (dates unknown) shapes the first one: it is
release 1.0 and carries only the framework, no model; a model's first deploy is a later, quicker
change request (D-021).

## Environment adapter (the seam)

All of the following live in one place (the `environment` component) and are driven by the
environment file `conf/local/environment.yml` (D-130):
- Spark session creation and settings (including Arrow)
- The compat shim
- The read/write transport (filesystem vs `hdfs dfs`)
- Root paths for data, models, registry and outputs (per entity where needed, OD-06)
- Source resolution: logical source → Hive table or path (the synthetic dataset on a laptop), or the
  feature store (OD-26)
- The report theme file (not built: the environment file's `theme` must stay null; the theme
  file is release 1.0's reporting depth, roadmap → Depth per component; the corporate look after
  internalisation)

The framework code never branches on "am I inside the bank". It calls the adapter, and the config
decides.

## Runtime notes (from the crunch)

- Marts usually hold 24 months of history. A use case starts from 100–300 candidate features,
  often pre-filtered from thousands (especially with the feature store), so the framework's
  candidate lists and patterns are a second filter, not the first (the EDS, 2026-10-20).
- Threads: the environment file's optional `threads` sets the model libraries' threads in
  Training; null means every core of the machine, which on a shared node or in a container may
  be more than the run is given, so there it is set to the cores the run has
  ([environment adapter](../components/environment.md), which also says when a shared
  environment file may set it). Training records the thread count and the versions of the
  libraries it ran with in `training.json`
  ([training](../components/training.md#the-search), item 12). Measured on the development
  machine: the models were byte-identical at 1 to 8 threads for every family (LightGBM 4.6.0,
  XGBoost 3.2.0, CatBoost 1.2.8); not checked with declared categoricals or on the bank's
  hardware.
- Retail scale is ~2M rows per period × ~50 columns per model (ceiling ~5M × 400).
  Single-node pandas and FLAML are fine **if** columns and rows are pruned in Spark first. With
  multi-period observation windows this becomes e.g. ~24M unit-periods for 12 periods, beyond the row
  budget. Sampling happens only when the config declares it (D-117); when the estimate exceeds the
  budget, the collect prints a callout naming the rows, the estimate, the budget and the two
  sampling options, and proceeds (D-133; `docs/components/dataset.md`).
- `toPandas()` of the full width is the main OOM risk. Downsampling after collection won't prevent
  an OOM, so declared sampling runs in Spark before collecting (whichever sampling option,
  `docs/components/dataset.md`).
- In the crunch, FLAML was time-budgeted (Phase 2 runs on a trial budget plus seeds by default,
  D-094). At 2M rows, LightGBM tends to consume most of the budget, and other learners may barely
  run. Read `automl.config_history` / `best_config_per_estimator` to see what was actually tried.
