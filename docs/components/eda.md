# EDA
**Status:** legacy-only (major rethink) · **Legacy:** `src/feature_stats.py`, `src/plots.py`, `notebooks/EDA.ipynb`

## Purpose
A standalone unit whose output is partly what a data analyst would deliver: a readable,
reproducible profile and report of a use case's population, target and candidate features,
generated from a frozen config. It informs decisions; it never changes data.

## Phase 2 requirements
1. Runs alone from a config and produces a report artifact (tables + plots + short generated
   narrative sections) through the shared reporting component.
2. Population view: size, eligibility funnel (from stepwise eligibility logs), target base rate
   over several months (checks representativeness and seasonality of the training month),
   segment mix.
3. Feature view on the candidates:
   - univariate summary (nulls, quantiles)
   - distributions by target
   - target-rate deciles
   - event rate per categorical level
   - correlation and VIF
4. Relevance ranking by univariate AUC, which works at any prevalence. MI only above a prevalence
   threshold, or not at all (lessons: MI at low prevalence).
5. Must stay fast at 2M+ rows: compute in Spark or on samples, with sampling declared in config and
   stated in the report.

## Design constraints
- Report content comes from functions; notebooks only display it.
- Every number in the report is reproducible from the frozen config.

## Lessons from the crunch
MI uselessness at 0.04–0.2% prevalence; the 30–40 min runtime; notebooks copied per product (don't).

## Interface
*(fill when built)*

## Open questions
- Detailed report contents and format (HTML vs markdown). **The user will provide more input.**
