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
reported back **in words** and re-applied here.

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
| pydantic | 2.12.5 | v2 API only |
| pyyaml | 6.0.3 | |
| matplotlib | 3.10.8 | |

Newer devcontainer images may move packages forward. When the user reports new versions, update
this table and `requirements.txt` in the same change and re-run the tests.

**Also in the standard devcontainer (usable; pin in `requirements.txt` on first use, D-042):**

| Package | Version | Likely use |
|---|---|---|
| scipy | 1.16.2 | Synthetic data, statistics (also a scikit-learn dependency) |
| statsmodels | 0.14.5 | Statistical tests and intervals |
| seaborn | 0.13.2 | Exploration in notebooks (reports use plotly) |
| plotly | 6.3.1 | Report charts (D-036) |
| jinja2 | 3.1.6 | Required by pandas Styler for styled HTML tables |

**Installed on top, like FLAML:** optuna 5.0.0 (the version `pip install optuna` resolves to inside
the bank; the predefined-model tuning path, D-037). Its API is unverified here: check
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
- **Unverified:** FLAML 2.7.0 with xgboost 3.2.0. XGBoost 3.x changed parts of its API. Check with
  a small FLAML run that includes `xgboost` in `estimator_list` before relying on it.
- **Unverified:** PySpark 3.4.3 `toPandas()` with pandas 2.2.3 and Arrow for all column types
  (datetime columns in particular). Test on the synthetic panel with Arrow on and off.
- **Unverified:** FLAML 2.7 grouped CV (`split_type="group"` with `groups`), needed because train
  rows repeat clients across months (`docs/components/dataset.md`).
- **Assumed, unverified:** a source month never changes after it has been loaded (no late-arriving
  rows or restatements). Reproducibility from frozen config + hashes depends on it (`CLAUDE.md`
  §4.10); the data-definition hash describes the data, it doesn't fingerprint it.
- **Unverified:** which engine-native model formats (LightGBM text, XGBoost JSON, CatBoost binary)
  can be extracted from FLAML 2.7's fitted models on the pinned versions (D-051).
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
- Source resolution: logical source → Hive table or path (the synthetic dataset on a laptop)
- The report theme file (after internalisation)

The framework code never branches on "am I inside the bank". It calls the adapter, and the config
decides.

## Runtime notes (from the crunch)

- Retail scale is ~2M rows per month × ~50 columns per model (ceiling ~5M × 400).
  Single-node pandas and FLAML are fine **if** columns and rows are pruned in Spark first. With
  multi-month observation windows this becomes e.g. ~24M unit-months for 12 months, so Spark-side
  sampling against a row budget is the normal case (`docs/components/dataset.md`).
- `toPandas()` of the full width is the main OOM risk. Downsampling after collection won't prevent
  an OOM, so sample negatives in Spark before collecting.
- FLAML is time-budgeted. At 2M rows, LightGBM tends to consume most of the budget, and other
  learners may barely run. Read `automl.config_history` / `best_config_per_estimator` to see what
  was actually tried.
