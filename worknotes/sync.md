# Sync page
_For the SDS and the LDS · last updated: 2026-11-03 (Stage 2's key decisions: flags that act, no sampling, one statistics engine) · last sync: 2026-11-03_

**In short (11-02 to 11-03):** The SDS settled how Stage 2 (EDA, Feature Checks, the feature
ledger and the reports) behaves; nothing of it is coded yet. A flag now has teeth: a flagged
feature is held out of training at every automation level, including autonomous, until a person
keeps or excludes it; signals that are only worth a look (drift, near-duplicate features, odd
null patterns) are notes and hold nothing out. Nothing is sampled: the statistics over the whole
observation window are computed in Spark as one table of counts, and the latest snapshot is
analysed on every client. One statistics engine serves both tasks, with concordance (AUC for
binary, its generalisation for regression) as the single ranking scale. Leakage in time is
caught by checking whether a feature keeps its signal when lagged by one period. Columns full of
zeros or a few repeated values get those values as their own bins, so no feature collapses into
one bucket. No config format versions are bumped while the framework is pre-release.

Detail behind each item: `worknotes/log.md`. How this page is written: `worknotes/README.md`.

## For the LDS: to review (most important first, then newest)
**Decisions needed from you: the short-term open decisions** in `docs/roadmap.md` → Open decisions (OD-01, OD-06, OD-08, OD-12, OD-18, OD-23)
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
| Is MLflow available inside the bank (OD-08)? | MLflow in Phase 2 is the goal; its shape is settled (D-111): M2.4's records map onto it, it goes in with the integrations in M4 | Ask at the platform learn session | SDS + LDS, with the platform / MLOps team |
| Has the Phase 2 plan been agreed with stakeholders (OD-01)? | Stages and depth per component are a working assumption; nothing in the repo records the buy-in | Confirm, then move the plan into the roadmap | SDS + LDS, then stakeholders |

## Last 2 working days (11-02 to 11-03)
- **Flags act; notes inform (11-02 → 11-03).** An open flag holds the feature out of training at
  both levels until a `keep` or `exclude` entry; the held set is written into the resolved
  config, so two runs with different held features never share a hash. For Training, a held
  feature acts as an excluded one without a final decision. Flags: quality (all null, constant,
  ≥ 95% null, ≥ 99% one value, over 50 levels), leakage (too strong, nulls that predict the target, a rare value
  with a large lift), time alignment, unstable signal across periods. Notes: drift (PSI), near-
  duplicate pairs, null patterns. Drift is a note because a flag would hold every trending
  legitimate feature out of an autonomous model. — look at: D-134; `feature_checks.md` (summary)
- **No sampled analysis; one statistics engine (11-02 → 11-03).** EDA and Feature Checks use
  every client: the window and the later periods as one Spark counts table (feature, period,
  bin, target bin, lagged, n, sum of target), the snapshot collected whole for the pairwise
  matrix and the row-level views. Every statistic is read from counts: concordance, the
  best-order concordance (the signal of a non-monotone feature like an inverted-U age), shares,
  Wilson intervals, PSI between named periods (window start to end; window end to the latest
  period). 100 bins by default, switchable off for small populations; a value holding a large
  share gets its own bin (T25). No chart draws individual clients. — look at: D-135; `eda.md`
  (summary)
- **Time alignment as a lag check; a look-ahead finding (11-02).** A feature that loses more
  than half its signal when lagged by one period is flagged (it may be stamped after the fact);
  a feature constant per client yet predictive is flagged as possible look-ahead (the
  feature-store stand-in's trap). This replaces the earlier backward-label check, which
  degenerates under a precondition eligibility. — look at: D-029, D-134; `feature_checks.md`
- **Layout and compatibility while pre-release (11-02).** Artifacts under root (the entity's
  area) → use case → layer; config and log formats change in place, no version bumps or
  migrations until user testing starts. — look at: D-136
- **What Stage 2 ships (11-03).** EDA and Feature Checks with their reports, the feature ledger
  (one wide row per candidate), notebooks 02 and 03 whose guide text is a main deliverable,
  regression handled for real on a variant config, the synthetic traps as an acceptance test.
  The plan waits for the SDS's approval. — look at: D-137; `worknotes/m2_2_understanding/plan.md` §1

## To try
- Nothing of Stage 2 runs yet. Walk through the summary level of `docs/components/eda.md` and
  `docs/components/feature_checks.md` · the list of checks and views, the flag thresholds, what a
  flag does at the autonomous level.
- `notebooks/01_target_factory.ipynb` on the synthetic dev data, or
  `python -m core_modelling run conf/base/cc_acquisition.yml conf/base/td_acquisition.yml --stages
  target_factory --env conf/local/environment.yml` · the two target summaries, the one table with
  both target columns, each use case's own eligibility on read, and the feature-store stand-in
  joined as a source with its own key names.
- `pytest tests/test_source_mistakes.py -q` · one test per planted source mistake (padded ids,
  periods dated on the 15th, a column shared with the mart, another id system…); read the
  messages a DS would see.

## Last 7 working days (10-26 to 10-30)
- 10-30 — **Integrations narrowed**: data observability only gets a production model's source
  tables at deploy; the feature store leans towards an extract joined like any other source;
  built: per-source key names, a feature-store stand-in with a look-ahead trap, mistake tests
  for every source guardrail — D-021, D-129, OD-26
- 10-30 — **Stage 2 scope**: between thin and deep with every key component in; the AUC
  standard-error rule in the lessons was 1.7× too conservative — `docs/context/lessons.md`
- 10-29 — **Two example use cases in one model input**; a source column named like a framework
  column read as `source_<name>`; the use case name rule freed — D-128, D-129
- 10-29 — **Working rules**: the LDS reads the important code and tries the notebooks; stage
  notes are written for the SDS — D-072 (i)
- 10-28 — **Stage 1 addendum**: the unit of analysis as `time.period` (month, week, day); the
  model input as sources plus one target per use case, eligibility and split derived on read;
  `revert` in the audit log — D-129, D-131, `worknotes/m2_1_foundation/review_guide.md`
- 10-28 — **Stage 1 review applied**: two eligibility lists, the null-handling knobs removed, the
  split and sampling as one hash draw — D-029, D-030, D-131
- 10-26 → 10-27 — **Stage 1 (M2.1 Foundation) built end to end, version 0.2.0** — D-129–D-133,
  `docs/components/dataset.md`
