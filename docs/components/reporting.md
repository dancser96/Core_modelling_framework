# Reporting and model card
**Status:** legacy-only · **Legacy:** `src/card.py`, `src/analysis.py` plotting helpers

## Purpose
One small shared writer that turns structured results (tables, figures, short text blocks) from any
stage into a report artifact. It is used by EDA, Feature Checks, Evaluation and the model card.
Reports are generated from frozen configs, never hand-assembled in notebooks.

## Phase 2 requirements
1. A single simple format first (markdown or self-contained HTML — to decide), with embedded
   figures.
2. **Model card = structured facts only:**
   - config summary, data lineage, dates, eligibility
   - sampling, calibration
   - selected model and `best_config`
   - metrics vs baselines, importance
   - no hardcoded prose caveats
3. Versioned card schema (`CLAUDE.md` §2), because promotion gates and registries read it.

## Design constraints
- No templating framework unless genuinely needed. String building and matplotlib are enough to
  start.

## Open questions
- Report format and styling expectations for analyst-grade EDA output.
