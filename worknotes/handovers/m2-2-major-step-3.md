# Handover: m2-2-major-step-3
_Written: 2026-11-06 11:40 · branch: main · last commit: db76225 (EDA mid-review state; EDA's
reviews 3 and 4 are uncommitted on top of it)_

## Goal
Build Stage 2's major step 3, **Feature Checks**: m3.1 the five steps, m3.2 the decisions and
the stage, m3.3 the trap acceptance test, m3.4 notebook 03, m3.5 the docs, version 0.3.0 and the
review guide. The binding list of files, functions and tests is
`worknotes/m2_2_understanding/plan.md` §2 "Major step 3"; the spec is
`docs/components/feature_checks.md` (settled 2026-11-02, D-134). The SDS's intent: "Based on
[the LDS's] feedback, we might make changes for EDA but in the meantime I want to get Feature
checks started in another chat." So EDA is under the LDS's review in its own chat while this one
builds; every formatting rule the SDS set during EDA's four reviews applies to Feature Checks'
report and notebook 03 from the first draft (listed below).

## State
- **Done:** major step 1 (foundations); major step 2 (EDA) through the SDS's reviews 1–4. The
  full suite last ran at 533 passed, 9 slow deselected (2026-11-06, before review 4's small
  changes, whose own tests ran after them).
- **In review:** EDA with the LDS (`worknotes/m2_2_understanding/review_guide.md`). Changes from
  that feedback are made in the EDA chat, not here.
- **Not started:** m3.1–m3.5. No `src/core_modelling/feature_checks/` yet; `run.py`'s `STAGES`
  holds `target_factory` and `eda`.
- **Uncommitted:** about 55 files (EDA's reviews 3–4, the gaps spec, the docs). The SDS may
  commit them before this chat starts: check `git status`.

## Decisions in that chat (all recorded; where)
- The gaps spec: D-138 (decision slices, value profile, sources, Target Factory occurrences);
  D-030 amended (Target Factory's labels and occurrences); D-136 clarified (an artifact reader
  bumps its schema version). The build's choices: plan §9 V55–V73.
- Review 4: a line chart's top is min(every point, twice the highest supported point)
  (`reporting.md` chart rule 1, V72); text only in notebook markdown cells (`notebooks/README.md`);
  `eda/report.py` is not split (Q531, maybe revisited after the LDS's feedback).
- The routing: plan §3 (Opus main thread and builders; Fable only for the whole-stage ML audit
  at the end of this step). The verbatim record of every round: `answers.md` beside the plan.

## The formatting rules (the SDS's, from EDA's reviews)
Owner docs: `docs/components/reporting.md` "Chart rules" 1–10 and "The chart primitives";
`notebooks/README.md`. The ones easiest to miss:
- **Numbers in tables:** thousands separators from 999.5 (`69,310`), four significant digits
  below (`0.3315`), never scientific notation (`_value` in `eda/report.py`); an amount
  `{:,.2f}`; a rate per `TASK_SPECS[task]["estimate_format"]`. `_value` and `_formats` are
  private to `eda/report.py`: Feature Checks is their second use, so move them to `reporting/`
  (see Open questions) rather than copy them.
- **Tables:** `style_table` (no matplotlib); coloured by lift; greyed below the support rule,
  never hidden; the caption names what colours and greys, with the threshold's name and value
  (`MIN_BIN_SUPPORT = 20`, `strata.min_events`).
- **Axes:** an estimate's axis and hover take `TASK_SPECS[task]["axis_format"]` (binary
  percent); lift and concordance axes stay plain; from zero at 1.25 × the data; a line chart's
  values capped at twice its highest supported point (headroom on top); a greyed bar keeps its
  height.
- **Labels:** a numeric shown by level reads `0, 1, 2` (no `=`); ranges `[374, 419)`; `= 0`
  only for a mass point among ranges; `null` always last, in its own colour; a stratum's levels
  keep their order and colours on every chart and pivot.
- **Layouts:** two related charts in one figure (`side_by_side`, legend right); a heatmap
  through the `heatmap` primitive (square cells, labels fit, at least 560 wide); a share-of-rows
  curve on a linear 0–100% axis with any reference line dashed and muted.
- **"Not available: reason"** is decided before drawing, never by catching an error (D-035).
- **Names:** never a function named like a library one (`pivot_table` became `_stratum_pivot`).
- **Notebooks:** a guide markdown cell before every step (what it does, what to look at, how to
  read each number, what to decide and how to record it, at both levels; no D-, T- or worknotes
  references). Text lives in markdown cells only: a code cell displays tables, charts and at most
  a Markdown heading per item, never a paragraph as an HTML output (R33, R39, R40). No
  machine-specific numbers (budgets, run times); the snapshot's size is fine. Public API only, no
  definitions, outputs cleared; rewrite in place, never keep a copy of the old outputs (R38).
  Notebook 03 says in words that a held feature acts, for Training, as an excluded feature
  without a final decision (V1).
- **Wording:** in-sample views are context, never a baseline (`decision.baselines` is the
  baseline); people's feature decisions here have seen test labels (D-030), which the report says.
- **Process:** no line-count or word-count targets for simplicity passes (R29): write lean the
  first time.

## Open questions (with the SDS's latest leaning)
- None from the SDS on Feature Checks; the spec is settled.
- **Shared files with the EDA chat** (both may write while the LDS's feedback lands):
  - numbering: re-read the last D-row (D-138 now), the highest Q (Q531) and the last V (V73)
    right before numbering anything;
  - this chat's questions go in `worknotes/m2_2_understanding/feature_checks_questions.md` and
    its review guide in `feature_checks_review_guide.md` there; `review_guide.md` is the LDS's
    EDA guide; don't touch it;
  - moving `_value` and `_formats` out of `eda/report.py` touches an EDA file: tell the SDS
    when you do it (default: at m3.2's start, into `reporting/html.py`, a mechanical move).
- Whether EDA's artifacts change after the LDS's review is open; Feature Checks reads only
  `eda.json`, the ledger and `tables/{cells,client_constant,correlation}`.

## Next steps
1. **Reconcile the spec with what EDA writes now:** `feature_checks.md` "Inputs: what EDA
   provides" and plan §2's m3.x bullets against `eda/run.py` and the saved artifacts under
   `data/cc_acquisition/04_feature/28f8bc322919/` (ledger schema 2 with `source`; ranking's
   `raw_sign`; the regression concordance's tie-corrected SE (V47); the client-fold
   cross-fitting; `CROSS_FIT_SE_INFLATION`). Ask the SDS numbered questions with defaults only
   where a real choice appears.
2. **Brief and spawn m3.1 ∥ m3.2's `decisions.py`** (plan §5 step 6, §3's models and efforts),
   with the common brief of `worknotes/handovers/m2-2-major-step-2.md` (still valid) and the
   formatting rules above in every report or notebook brief.
3. Then m3.2's stage, m3.3 ∥ m3.4, m3.5; one combined review per minor step, the ML audit on
   m3.1 + m3.2, the whole-stage audit (Fable, xhigh), the full suite, the review guide.

## Gotchas
- **Memory:** one Spark job at a time on the 8 GB Mac. The SDS's own Jupyter kernels often
  hold Spark JVMs of 2 GB each (`pgrep -fl ipykernel`): never kill them. `run_eda` on the 100k
  data took 200 s with two of them alive.
- **Never wait with `while pgrep -f …`:** the loop matches its own command line and never ends.
  Run long jobs in the background and wait for the notification.
- **The full suite** (about 9 min) runs only on the main thread, in the background, at a
  major step's end; subagents run their own tests only.
- **Checking views without Spark:** rebuild them from saved artifacts (`read_resolved_config`
  on `eda/resolved_config.yml`, the `tables/*.parquet`, `eda.json` as meta, `ledger.parquet`,
  then `build_views`). There is no nbconvert or nbclient in the venv: run a notebook's code cells
  as a script; check the look with headless Chrome screenshots.
- **Shell:** zsh treats `echo ====` as an error; use quoted heredocs (`<<'EOF'`); ruff's line
  limit is 100 and docstrings are rewrapped by hand.
- **Panel data:** a window statistic with an SE uses effective clients; a fitted order is
  cross-fitted by client fold, never by period (EDA's two ML-audit catches).

## Read first
1. `docs/UPDATES.md`; plan §2 "Major step 3", §3, §5, §6 and §9 (skim V1–V73).
2. `docs/components/feature_checks.md` (whole), `feature_ledger.md`, `docs/decisions.md` D-134,
   D-137, D-138.
3. `docs/components/reporting.md` (chart rules, primitives), `notebooks/README.md`, and
   `notebooks/02_eda.ipynb` as the guide-cell model.
4. `src/core_modelling/eda/run.py` (the stage shape, `_write`), `eda/report.py` (`build_views`,
   `report_sections`, `_formats`), `artifacts.py`, `ledger.py`, `config/audit_log.py`
   (`record_decision`), `tasks.py`, `run.py`.
5. `worknotes/handovers/m2-2-major-step-2.md`: "Common brief for builders" and "Gotchas".
