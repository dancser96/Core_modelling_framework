# Environment and bank parity

**Verdict:** we develop outside the bank on synthetic data, against pinned versions that match the
internal devcontainer. Everything environment-specific sits behind one adapter plus `conf/local/`,
so moving the code inside needs configuration, not code edits.

## Two environments

| | Outside (development) | Inside the bank (target) |
|---|---|---|
| Machines | Windows 11 PC via WSL2 (Ubuntu); MacBook (native) | Internal devcontainer (JupyterLab / VS Code) |
| Data | **Synthetic only** — generated panels that match the real schema | Real monthly panel on Hive/HDFS |
| Spark | PySpark 3.4.3 in local mode, Java 11 | Cluster Spark (CDP-style), Hive tables, raw `hdfs://` paths |
| Storage | Local filesystem | Local workspace, plus HDFS for registered models and scores |
| LLM | Claude Code for development | Claude via API or Bedrock, limited tokens, not the newest models |

**Code flow is one-way.** To release: download a zip of the repo, then copy its contents into the
internal repo. Nothing comes back out: no data, no outputs, no code. Changes made inside are
reported back **in words** and re-applied here. Inside, the package is published through Nexus into
the base image; images are supported for a year, and the image a use case starts on pins its
framework version (D-074).

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

**Also in the standard devcontainer (usable; pin in `requirements.txt` on first use, D-042; scipy
and plotly are already pinned above):**

| Package | Version | Likely use |
|---|---|---|
| scipy | 1.16.2 | Synthetic data, statistics (also a scikit-learn dependency) |
| statsmodels | 0.14.5 | Statistical tests and intervals |
| seaborn | 0.13.2 | Exploration in notebooks (reports use plotly) |
| plotly | 6.3.1 | Report charts (D-036) |
| jinja2 | 3.1.6 | Required by pandas Styler for styled HTML tables |

**Dev-only tools** (`requirements-dev.txt`, never needed inside the bank): pytest, ruff, ipykernel
and nbformat. plotly renders charts in a notebook only with nbformat; Jupyter installs it inside the
bank, but `ipykernel` alone doesn't locally (D-063).

A package that other packages pull in must be pinned even before our code uses it: without the
pins, pip resolved scipy 1.17.1 and plotly 7.1.0 locally (2026-10-14).

**Installed on top, like FLAML:** optuna 5.0.0 (the version `pip install optuna` resolves to inside
the bank; the predefined-model tuning path, Phase 3, D-080). Its API is unverified here: check
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
- **Unverified:** FLAML 2.7.0 with xgboost 3.2.0. XGBoost 3.x changed parts of its API. Check with
  a small FLAML run that includes `xgboost` in `estimator_list` before relying on it.
- **Unverified:** PySpark 3.4.3 `toPandas()` with pandas 2.2.3 and Arrow for all column types
  (datetime columns in particular). Test on the synthetic panel with Arrow on and off.
- **Unverified:** FLAML 2.7 grouped CV (`split_type="group"` with `groups`), needed because train
  rows repeat clients across months (`docs/components/dataset.md`).
- **Assumed, unverified:** a source month never changes after it has been loaded (no late-arriving
  rows or restatements). Reproducibility from frozen config + hashes depends on it (`CLAUDE.md`
  §4.10); the data-definition hash describes the data, it doesn't fingerprint it.
- **Unverified:** a lossless non-pickle format per model family on the pinned versions (XGBoost
  JSON, LightGBM text, CatBoost JSON; scikit-learn forests have none), each proven by a round trip
  giving identical predictions (D-078; list in `docs/components/training.md`).
- **Assumed, unverified:** no internet access from the bank's notebooks, so reports embed plotly.js
  instead of loading it from a CDN (~4–5 MB per report). Plotly rendering inside the bank's
  JupyterLab is also unverified.

## Environment adapter (the seam)

All of the following live in one place (the `environment` component) and are driven by
`conf/local/`:
- Spark session creation and settings (including Arrow)
- The compat shim
- The read/write transport (filesystem vs `hdfs dfs`)
- Root paths for data, models, registry and outputs (per entity where needed, OD-06)
- Source resolution: logical source → Hive table or path (the synthetic dataset on a laptop), or the
  feature store (OD-26)
- The report theme file (the mechanism in Phase 2; the corporate look after internalisation)

The framework code never branches on "am I inside the bank". It calls the adapter, and the config
decides.

## Runtime notes (from the crunch)

- Marts usually hold 24 months of history. A use case starts from 100–300 candidate features,
  often pre-filtered from thousands (especially with the feature store), so the framework's
  candidate lists and patterns are a second filter, not the first (the SDS, 2026-10-20).
- Retail scale is ~2M rows per month × ~50 columns per model (ceiling ~5M × 400).
  Single-node pandas and FLAML are fine **if** columns and rows are pruned in Spark first. With
  multi-month observation windows this becomes e.g. ~24M unit-months for 12 months, so Spark-side
  sampling against a row budget is the normal case (`docs/components/dataset.md`).
- `toPandas()` of the full width is the main OOM risk. Downsampling after collection won't prevent
  an OOM, so sample in Spark before collecting (whichever sampling option,
  `docs/components/dataset.md`).
- FLAML is time-budgeted. At 2M rows, LightGBM tends to consume most of the budget, and other
  learners may barely run. Read `automl.config_history` / `best_config_per_estimator` to see what
  was actually tried.
