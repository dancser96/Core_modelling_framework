# Pulse check for the Chief DS
_2026-11-20 · version 0.4.0_

**In short.** `core_modelling` is the crunch rebuilt as a versioned library: a use case is one
YAML config, and every lifecycle stage runs from it through a CLI, a Python API or a guided
notebook. Five of the ten stages are built and run end to end on synthetic data, for a binary
and a regression target: one command takes a config from source tables to a calibrated model
with its evaluation report and model card. Register, promote, deploy, batch scoring and
monitoring are designed and not built, and nothing has run on real data yet.

## What is built, and what it replaced

The crunch got about ten products scored in two to three weeks. Most of the time since went
into the shortcuts it took: each row is now a component, designed in writing, built, audited for
ML correctness and reviewed line by line (review is about 40% of build time). Before the stages:
the design baseline (10-12) and a synthetic dataset of 100k clients over 24 months with planted
traps and known true probabilities (10-21).

| Stage | In the crunch | In the framework |
|---|---|---|
| **Target Factory (was Data Creation), dataset** (built 10-27) | One training month, its seasonality baked in. A target's source columns kept out of the features by memory. | Target rules declared in config, on monthly, weekly or daily periods. Eligibility as ordered steps that log what they removed. Client split and sampling from one salted hash, so reruns agree. One saved table serves several use cases. |
| **EDA** (built 11-04) | Charts that showed nothing at 0.04–0.2% positives. Mutual information ran 30–40 minutes and could not tell targets apart. | One Spark counts table (feature × period × bin × target) feeds every multi-period statistic. Ranking by concordance, with standard errors counted in converting clients (the crunch's rule overstated them 1.7 times). Nulls and mass points get their own bins. |
| **Feature Checks, feature ledger** (built 11-07) | Statistics after median imputation, so missingness leaked into the signal. A feature decision that read the out-of-time labels. Thresholds as literals in notebooks. | Five steps on EDA's stored tables: quality, leakage, time alignment, stability, redundancy. Time alignment is a lag test: a feature that keeps less than half its signal when lagged one period was probably stamped after the fact. Every threshold is a config field, and every finding has a planted trap it must catch and a near-threshold control it must not. |
| **Training, model bundle** (built 11-16, in review) | FLAML on a time budget, most of it taken by LightGBM. The whole AutoML object pickled. Prior shift as the only calibration. | A trial budget per family, so a run repeats. An encoder with levels frozen from train and nothing imputed. Monotone constraints. Platt or beta calibration. The model is its native file plus JSON under one hash, loaded without pickle. No training without EDA and Feature Checks results for the same data. |
| **Evaluation, report, model card** (built 11-17, in review) | Pooled metrics only: an out-of-time AUC of 0.85–0.95, very likely segment mix more than skill. | Scoring inside Spark. Metrics from binned scores, the bins dense at the top because coarser ones read average precision up to 61% low at a 0.05% base rate. Seventeen report views chosen per model family from a compatibility table, so a view is produced or declared unavailable up front. A model card of generated facts and a two-run comparison. |
| **Register, promote, deploy, batch scoring, monitoring** | Promotion happened as a side effect of scoring. | Designed, not built. |

- **Code.** 1,166 functions in 105 modules: about 14,200 lines of function code (12 per
  function), 1,900 of declarative data (config schema, per-task dictionaries, thresholds,
  constants) and 5,400 of docstrings and comments, and its corresponding tests. The crunch: 76
  functions and about 900 lines of code, notebook cells included.
- **One run on the 100k-client data** (card acquisition, 257k training rows): flags hold 47
  features out, 123 enter Training, 38 survive selection. The four model families finish within
  0.0004 fold log loss of each other; out-of-fold concordance is 0.806 against 0.818 in sample.
  Source tables to calibrated model: 11 minutes on a laptop at 15 trials per family.

## Key features and the decisions behind them

- **A use case is data, not code.** The config declares the intent, the decision metric and the
  baselines before any result; an append-only log replays every human decision; hashes identify
  every artifact.
- **Time and splits are enforced by structure.** A multi-period window, train and test split by
  client, and one out-of-time period that no selection, tuning or calibration ever sees. Columns
  the target was built from are excluded by lineage.
- **Flags act.** EDA and Feature Checks use every client, unsampled. A feature flagged for
  leakage, time misalignment, instability or quality stays out of training until a person
  decides, and a person signs off the final feature list.
- **FLAML searches, the framework fits.** One search per family (LightGBM, two XGBoost variants,
  CatBoost) on client-grouped folds; the framework encodes the data itself (FLAML would
  median-impute nulls), refits what is kept and calibrates out of fold.
- **Evaluation informs, people judge.** Metrics per period and per segment with client-bootstrap
  intervals, against the declared baselines; no pass or fail gate. Two automation levels run
  identical checks.
- **Outputs are the compatibility contract.** Each use case pins its framework version, so
  several versions will write the same tables: the shared formats (scores table, model bundle,
  registry records, monitoring tables) only grow, and internals stay free. Tiers are explicit:
  a data scientist's session never writes to production.
