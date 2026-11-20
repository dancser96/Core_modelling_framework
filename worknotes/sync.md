# Sync page
_For the EDS and the LDS · last updated: 2026-11-20 (the modelling stage as built; the Chief DS joins the repo) · last sync: not recorded since 2026-11-03_

**In short (11-12 to 11-20):** The modelling stage is built: one command trains a calibrated
model and evaluates it, for a binary and a regression target; the EDS's review of both is open,
so expect rough edges. FLAML only searches, one model family at a time on client folds, and the
framework itself fits every model it keeps; nothing is imputed and calibration is fitted out of
fold. Evaluation scores the test clients and the validation period inside Spark, reads every
metric from binned scores with client-bootstrap intervals, and shows the model against the
declared baselines with no pass or fail line. A run is a numbered folder complete in itself; a
model is saved without pickle under one hash. The Chief DS has joined the repo as a collaborator
and has a one-page status.

Detail behind each item: `worknotes/log.md`. How this page is written: `worknotes/README.md`.

## For the LDS: to review (most important first, then newest)
**Your view wanted on: the short-term open decisions** in `docs/roadmap.md` → Open decisions (OD-06, OD-08, OD-18, OD-23)
- [ ] **Decision: FLAML only searches; the framework fits what is kept** — D-140;
      `docs/components/training.md` → Level 1, then "The search", "Selection" and "Fold models
      and calibration" — feedback wanted: is one trial-budgeted search per family the comparison
      you'd trust, and would you miss anything on the "Deliberately not built" list (class
      weights, imputation, isotonic)?
- [ ] **Decision: metrics from score cells with client-bootstrap intervals; baselines, no gates**
      — D-141; `docs/components/evaluation.md` → Level 1, then "Metrics", "Intervals: the client
      bootstrap", "Baselines" and "What the report states" — feedback wanted: are these the
      metrics and baselines you'd judge a propensity model on, and is leaving the verdict to the
      person right?
- [ ] **Decision: a numbered run complete in itself; the bundle without pickle under one hash**
      — D-139; `docs/components/model_bundle.md` → Level 1, then "The run folder" and "The
      hashes" — feedback wanted: are three names for a person (data definition, run, model
      version) enough to find and compare models?
- [ ] **Training, as built** — `training/selection.py` → `apply_cluster_rule`, `apply_floor`,
      `prune_by_importance`; `training/search.py` → `fit_parameters`, `check_search`,
      `check_judged_model`; `training/fold_models.py` → `fit_fold_models`;
      `statistics/calibration.py` → `fit_platt`, `fit_beta`, `prior_shift_offset` — feedback
      wanted: does anything fitted or selected here see test or validation rows, and are the
      three selection rules the ones you'd apply?
- [ ] **Evaluation, as built** — `statistics/score_cells.py` → `quantile_passes`, `pool_cells`;
      `statistics/bootstrap.py` → `bootstrap_intervals`; `statistics/metrics.py` →
      `binary_metrics`, `slice_metrics`; `evaluation/baselines.py` → `choose_single_feature`,
      `compare_baselines`; `evaluation/compare.py` → `compare_runs` — feedback wanted: are the
      binned metrics and the client bootstrap right for rare targets, and does any read of the
      validation period feed a choice?
- [ ] **Decision: an open flag holds the feature out of training at both levels** — D-134;
      `docs/components/feature_checks.md` → Level 1, then "Flags act: the hold-out" and "The two
      automation levels and the review"; `docs/components/feature_ledger.md` → Level 1 and the
      "Example rows" table — feedback wanted: is holding out at autonomous right for you, and is
      the flag / note split the right line?
- [ ] **Decision: the checks and their thresholds** — `docs/components/feature_checks.md` →
      "The finding table" (per step: each finding, flag or note, its default and why) and the
      "Trap acceptance test" table — feedback wanted: would any flag hold out a feature you'd
      keep on a card or deposit model, and is a check you'd expect missing?
- [ ] **Decision: no sampling; the window as a Spark counts table, the snapshot whole** — D-135;
      `docs/components/eda.md` → Level 1, then "The counts table", the table in "The statistics"
      and the list in "The views" — feedback wanted: are these the views you'd want first, and
      is concordance the ranking scale you'd read?
- [ ] **Decision: artifacts under root → use case → layer; no format version bumps in 0.x** —
      D-136; `data/README.md` — feedback wanted: does that layout work for how use cases share a
      data area?
- [ ] **Stage 1 (M2.1 Foundation), as built** — the design: D-129–D-133;
      `docs/components/dataset.md` → Purpose, "Time model" and "Model input";
      `docs/components/config.md` → "Layout" and the "Worked example"; the ML logic:
      `target_factory.py` → `build_targets`, `dataset/eligibility.py` → `apply_eligibility`,
      `dataset/panel.py` → `prepare_panel`, `dataset/split.py` → `assign_split`, `sample_train`,
      `dataset/frames.py` → `build_frames`, `dataset/contract.py` → `check_contract` — feedback
      wanted: do the target rule, the two eligibility lists, the frames and one model input for
      several use cases match how you'd define and model card and deposit acquisition?

## Questions for the LDS
None open.

## Open questions for both of us

| Question | Context | Current leaning | Needs |
|---|---|---|---|
| Is MLflow available inside the bank (OD-08)? | Its shape is settled (D-111): the framework's own records map one-to-one onto it | Ask the platform / MLOps team | EDS + LDS, with the platform / MLOps team |
| Who builds the registry and the deployment path (OD-23)? | Downstream questions go to the platform / MLOps team (D-079); register, promote and deploy stay thin but real until then | Agree whether that team builds or advises | EDS + LDS, with the platform / MLOps team |
| How are the registered and production folders laid out per entity × domain (OD-06)? | The sandpit root is settled (D-136); permissions are the platform's | The same shape as the sandpit root | EDS + LDS |
| Do manifests sit beside the score files or apart (OD-18)? | Manifests beside the score files break a Hive table over the scores | Apart | EDS + LDS |

## Last 2 working days (11-19 to 11-20)
- **The Chief DS joins the repo (11-20).** He asked to be a collaborator: he reads everything
  and may raise pull requests. A one-page status was written for him: what is built beside what
  it replaced in the crunch, the code's size, the key features and the decisions behind them. —
  look at: `worknotes/cds_pulse_check.md`
- **Training and Evaluation are on `main` (11-20).** Both run from the notebooks and the CLI,
  and the run guide has the steps. The EDS's joint review of the two is open, and a contract it
  changes is fixed in both. — look at: `worknotes/lds_run_guide.md`;
  `worknotes/m2_3_modelling/review_guide.md` and `review_guide_3.md`

## To try
- Training and Evaluation — `worknotes/lds_run_guide.md`, steps 8–9
  (`notebooks/04_training.ipynb`, then `notebooks/05_evaluation.ipynb`) · the sign-off table
  (could you defend every feature?), the search view (how close the four families land), the
  model against each baseline in the report's summary, the metrics per period with the
  validation period beside them, the reliability view.
- EDA and Feature Checks — the same guide, steps 1–7 · the held list: the planted traps (`trap`
  in the name) should be there, and few honest features.

## Last 7 working days (11-12 to 11-18)
- 11-17 — **Evaluation built**: scoring inside Spark, metric tables with client-bootstrap
  intervals, the seventeen-view report, the model card, `compare_runs`. The ML audit found
  average precision reading low from coarse score bins at rare base rates; binary now has 380
  bins, dense at the top — D-141, `docs/components/evaluation.md`
- 11-16 — **Training built**: the gate, three selection rules on train statistics, one FLAML
  search per family, the fold models, calibration, the bundle, the sign-off table. The reviews
  closed three findings: the search could judge another LightGBM constraint method than the
  kept model used; under a time budget the judged and the kept model can differ; the floor read
  a mark that had seen test labels — D-140, `docs/components/training.md`
- 11-14 → 11-16 — **Stage 3 foundations built and reviewed by the EDS**: the modelling config
  fields, client folds, the encoder, four model families with non-pickle round trips, the
  bundle, numbered runs — D-139, `docs/components/model_bundle.md`
- 11-12 → 11-13 — **Stage 3 design closed**: four families in the default list, 60 trials at
  `autonomous`, monotone constraints in, no gates; FLAML median-imputes numeric nulls unless
  its transformer is switched off, so the framework encodes the data itself — D-094, D-140
