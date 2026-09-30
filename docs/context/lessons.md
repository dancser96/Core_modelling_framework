# Lessons from the crunch and known traps

**Verdict:** the crunch proved the spine works end-to-end. The bugs that hurt were almost all
**environment and boundary bugs** (paths, versions, write modes, HDFS) that stubbed tests couldn't
catch, plus a few **silent statistical traps**. Phase 2 answers these with a real local-Spark test
harness, an environment adapter and explicit invariants. Legacy file references are to
`legacy/propensity_crunch/`.

## Known traps (check before writing related code)

| # | Trap | What happened | Rule now |
|---|---|---|---|
| T1 | numpy 2 vs PySpark 3.4 | `import flaml` → pandas-on-Spark → `np.NaN` → crash | Compat shim before any pyspark/flaml import (`src/_compat.py`) |
| T2 | `pathlib` on `hdfs://` | `Path("hdfs://x")/"y"` → `hdfs:/x/y`; `_is_hdfs` silently false | HDFS paths are strings joined with `/`; only local paths become `Path` |
| T3 | Reading HDFS in Python | `pickle` / `read_bytes` can't read HDFS | Fetch to a local temp dir via `hdfs dfs -get`, then load |
| T4 | `str / str` TypeError | A temp dir (str) was passed into a function using `/` | Local-I/O functions coerce `Path(x)` at their boundary |
| T5 | cwd-relative roots | `Path("artifacts")` resolved to the notebook's cwd; logs were read from the wrong place | All roots come from config; never cwd-relative |
| T6 | Overwrite inside a loop | Per-product `mode("overwrite")` kept only the last product's scores | Collect → union → write once; assert every "ok" product landed on disk |
| T7 | Overwrite-first-then-append across runs | Run 2 wiped run 1's batch | Batch-scoped outputs (`<root>/<batch_id>/…`) |
| T8 | Backward rollup off-by-one | `rangeBetween(-m, -1)` excluded the current month | Backward includes current: `(-(m-1), 0)`; forward excludes: `(1, m)` |
| T9 | FLAML metric names | `average_precision` isn't a FLAML metric | Use FLAML's own names (`roc_auc`, `ap`, `log_loss`, …) |
| T10 | PSI on categoricals | `np.quantile` on strings crashed | Numeric-only PSI; categoricals need their own stability measure |
| T11 | Eligibility × feature | Under `is_fx_active = 0`, FX-activity features were constant 0 | A feature built from the eligibility-defining activity is dead; flag automatically |
| T12 | Target-signal leakage | The raw forward column the target was built from sat next to it in the panel | Target lineage columns are auto-excluded, not remembered |
| T13 | Hardcoded window literals | The panel-edge guard hardcoded `3` | Windows come from config only |
| T14 | FLAML trial counting | Reading the search log gave wrong counts (path issue) | Use `automl.config_history` and `best_config_per_estimator` |
| T15 | Stubs hide environment bugs | The smoke test passed while T1–T7 were live | Real local Spark on a synthetic panel for the e2e test |

## Statistical lessons

- **Mutual information is useless at very low prevalence.** At 0.04–0.2% positives, the kNN MI
  estimator returned near-identical values across different targets and took 30–40 min.
  Rank features with univariate AUC (base-rate agnostic) and read direction from target-rate
  deciles. Don't compute MI on downsampled data: it silently changes the joint distribution.
- **Univariate AUC floor.** Direction-agnostic AUC < ~0.515 is a drop candidate. Treat this mainly
  as a speed lever (more FLAML trials per budget). Its standard error is ≈ `0.5/sqrt(n_positives)`,
  so with ~800 positives the third decimal is noise.
- **Downsampling.** Keep all positives; the negative:positive ratio is mostly a compute lever that
  barely moves ranking. The positive *count* is the real ceiling (e.g. ~800 for a 0.04% product
  is low-confidence at any ratio). Set the ratio per use case. Stratified negative sampling is the
  upgrade if negatives prove heterogeneous.
- **Calibration (`prior_shift`).** A log-odds offset `logit(true_rate) − logit(sampled_rate)`.
  Apply it only after downsampling. Rank metrics are unchanged. It does **not** fix a model that is
  miscalibrated in itself — check the reliability curve.
- **Contract checks before downsampling.** A base-rate floor produced false alarms on legitimately
  rare products. The real "degenerate target" guard is `nunique > 1`; the band only catches
  implausible *high* rates.
- **PR-AUC is not comparable across products.** Its floor is the base rate. Compare products on
  ROC-AUC and top-k lift.
- **Pooled AUC is inflated.** 0.85–0.95 on a heterogeneous base is not within-segment skill. Report
  segment-stratified metrics.
- **Single training month** bakes in that month's seasonality. Record it in the model card.
- **Importance.** Permutation importance splits credit across correlated features. Native
  importance doesn't align with raw-string categoricals (FLAML encodes them internally). SHAP via
  `PermutationExplainer` works for any model but is slow — sample it. Per-level categorical tables
  are the reliable categorical view.
- **FLAML search.** It is time-budgeted and cost-frugal. With large data, the cheapest improving
  learner (LightGBM) eats the budget. For a fair comparison, run learners in isolation or raise the
  budget. `sample=True` means early trials run on subsamples.

## Design lessons (kept for Phase 2)

- **Two feature views of one config.** Exploration reads the candidates; the model reads the
  survivors (candidates − exclusions). One file, and excluded features stay inspectable.
- **Config-driven top-k metrics:** percentile slices plus absolute-count slices (a count larger than
  the population is skipped). Full-population stats are always reported.
- **Frozen config + hashes** (config hash, feature signature, model content hash) made every score
  traceable. The manifest linked scoring batches to the exact models; verify the hash before
  reproducing.
- **Per-use-case run pinning** as a dict `{use_case: run_id}`, never a positional list.
- **Reinference** from registered models + manifest (a new month or table with the same schema)
  worked without the local scratch runs. This is the value of a registry tier.
- **Promote-on-inference was a crunch shortcut.** Phase 2 separates promotion from inference.
- **The model card holds structured facts only** (calibration, downsampling, selected model,
  `best_config`) — no hardcoded prose caveats.
- **Notebooks as interface worked.** One notebook per stage; switch the product and rerun.

## Legacy map (where to look)

| Concern | Legacy file(s) |
|---|---|
| Config schema, validation, two feature views | `configs/_schema.py`, `configs/_TEMPLATE.yaml` |
| Rollups / target building | `src/rollups.py`, `notebooks/Data_Creation.ipynb` |
| Spark IO, labelled frames, downsampling | `src/io.py`, `src/dataset.py` |
| Contract checks, leakage screen | `src/contract.py`, `src/leakage.py` |
| EDA / feature statistics / plots | `src/feature_stats.py`, `src/plots.py`, `notebooks/EDA.ipynb` |
| Training orchestration | `src/run.py` |
| Calibration | `src/calibration.py` |
| OOT metrics | `src/evaluate.py` |
| Importance and analysis suite | `src/importance.py`, `src/analysis.py` |
| Model card | `src/card.py` |
| Inference, promotion, manifest, HDFS transport | `src/inference.py`, `notebooks/Inference.ipynb` |
| Compat shim | `src/_compat.py` |
| Offline smoke test (stub-based) | `tests/smoke_test.py` |
