# Reporting and model card
**Status:** legacy-only · **Legacy:** `src/card.py`, `src/analysis.py` plotting helpers
**Related:** [EDA](eda.md) · [feature checks](feature_checks.md) · [evaluation](evaluation.md) ·
[monitoring](monitoring.md) · [lifecycle](lifecycle.md) · [environment](environment.md) (theme) · D-031, D-036, D-052, D-083 · OD-12

## Purpose
One shared writer that turns structured results from any stage into a self-contained HTML report,
plus the versioned model card. Reports are generated from frozen configs, never hand-assembled in
notebooks, and the same objects display in notebooks.

**Reports:** EDA · Feature Checks (+ ledger) · model performance (evaluation) · model comparison ·
model card · monitoring. EDA and Feature Checks together form a data-analysis report in its own
right, a product within the product, not notebook output next to artifacts. Target Factory,
Training, Inference and the lifecycle steps write artifacts, not reports.

## Phase 2 requirements
1. **Self-contained HTML:** styled tables (pandas Styler) and interactive plotly charts, with plotly.js
   embedded once per file so reports open offline inside the bank (no CDN). That makes each report
   about 4–5 MB, and the size isn't optimised in Phase 2: reports regenerate from frozen configs,
   and retraining in production regenerates them anyway (D-036).
2. **Every report has the same structure:**
   1. A one-page summary for business and governance readers. It opens with a **choices block**:
      what was chosen (profile, decision, metric, sampling, modelling path), the alternatives, and
      rule-based warnings (e.g. few positive events, pooled AUC far above within-segment AUC, a
      choice among variants made on test metrics, D-083).
   2. Core views.
   3. Extended views, or "not available: reason".
   4. A technical appendix.
3. **Theme:** neutral in the repo. A theme file in `conf/local/` (palette, fonts, logo path) is
   the Phase 2 mechanism; the corporate look it applies inside the bank comes after
   internalisation (Phase 3).
4. **Model card = structured facts only**, with a versioned schema (§2). It covers:
   - config summary, data definition and lineage, dates, eligibility;
   - sampling, calibration (prior shift and any calibration step);
   - modelling path and best config;
   - metrics vs baselines (overall and stratified), importance;
   - unresolved flags, human decisions and the feature sign-off (D-031);
   - for a refit: the parent run and its evaluation metrics (D-052).

   It is designed so a later generator can map it onto the internal model documentation standard
   (Phase 3).

## Chart rules (a living rule set — extend it whenever a chart is reviewed)
1. **Axes follow the data.** For rates use `(0, 1.25 × max plotted value)`. Zoom reliability curves to
   the score range, with the diagonal clipped to it. Never use a fixed (0, 1) range at low prevalence
   (T16).
2. **Where absolute rates are tiny, show lift vs base rate,** always with positive counts and
   intervals.
3. **Suppress or grey out** bins and cells with too few positives, and say so.
4. **Quantile bins** for numeric features; **log axes** for heavy tails.
5. **No chart whose bars are all near zero.** Switch to lift, a log axis or a table.
6. **One colour per segment / model** across a whole report; comparisons overlay on shared axes.

## Design constraints
- No templating framework beyond what pandas Styler needs (jinja2): string building + plotly.
- One charting library (plotly) for reports. Revisit if it disappoints (D-036).

## Open questions
- The mandatory core views (OD-12).
- Unverified: how fast a report opens and whether plotly renders in the bank's JupyterLab. Both
  show in the SDS's JupyterLab test inside the bank (D-036).
