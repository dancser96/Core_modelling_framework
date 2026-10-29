# Sync page
_For the SDS and the LDS · last updated: 2026-10-29 (questions answered; the use case name freed; two example use cases in one model input; worknotes cleaned up) · last sync: 2026-10-26_

**In short (10-28 to 10-29):** Stage 1 is complete and reviewed by the SDS; your one to-do is
to start reviewing it. Yesterday's addendum made the unit of analysis (month, week or day) a
parameter and let one saved model input serve several use cases. Today that is visible: the
Target Factory notebook builds a credit card and a term deposit use case into one table and
reads it back for each. The SDS's questions were answered; a source column that shares a name
with one the framework adds is now kept under a prefixed name instead of refused, and a use
case's name is free of the old naming rule. The working notes now hold only what is current.

Detail behind each item: `worknotes/log.md`. How this page is written: `worknotes/README.md`.

## For the LDS: to review (most important first, then newest)
**Your one to-do: start reviewing Stage 1.** Nothing else is waiting on you.
- [ ] **Stage 1 (M2.1 Foundation), as built** — the design: D-129–D-133, `docs/components/dataset.md`
      → Model input, `docs/components/config.md` → the layout; the ML logic:
      `target_factory.py` → `build_targets`, `dataset/eligibility.py` → `apply_eligibility`,
      `dataset/panel.py` → `prepare_panel`, `dataset/split.py` → `assign_split`, `sample_train`,
      `dataset/frames.py` → `build_frames`, `dataset/contract.py` → `check_contract` — feedback
      wanted: do the target rule, the two eligibility lists, the frames and one model input for
      several use cases match how you'd define and model card and deposit acquisition?

## Questions for the LDS
- **Example notebooks:** beyond running as a pipeline and through notebooks, anything more you want
  from the release examples? (`docs/components/run_modes.md`)
- **Model documentation (Phase 3):** what did you mean by "checks that the necessary inputs exist"?

## Open questions for both of us

| Question | Context | Current leaning | Needs |
|---|---|---|---|
| Is MLflow available inside the bank (OD-08)? | MLflow in Phase 2 is the goal; its shape is settled (D-111): M2.4's records map onto it, it goes in with the integrations in M4 | Ask at the platform learn session, by 11-06 | SDS + LDS, with the platform / MLOps team |

## Last 2 working days (10-28 to 10-29)
- **Two example use cases in one model input; the SDS's questions answered (10-29).** A
  second example, `td_acquisition` (term deposit), shares `retail_acquisition_input` with
  `cc_acquisition`: the notebook saves both targets in one table and reads it back per use
  case, each with its own eligibility (the card's income filter applies to the card only). A
  source column named like one the framework adds (`unit_id`, `period`, `target`, `split`,
  `eligible`) is read as `source_<name>` instead of refused, and a use case's own upstream label
  is dropped on the read side, so no eligibility condition can name it; reviewed by three
  fresh-context reviewers, findings fixed. The use case's name is letters, digits, `_` and `-`
  in any case, compared ignoring case (D-128 replaced). Missing periods are a Phase 3 wish. The stage folder now holds
  the review guide alone. Full suite 286 passed; the notebook runs on the dev data in 34 s. —
  look at: `notebooks/01_target_factory.ipynb`;
  D-128, D-129; `docs/components/dataset.md` → Model input
- **The Stage 1 addendum, built and reviewed (10-28).** From the SDS's second and third
  rounds: the unit of analysis is `time.period` (month, week or day; the key column `period`,
  the `time` fields `observation_window`, `target_window`, `validation_period`; one dict of
  period arithmetic in `periods.py`, never a bare `add_months`); the model input is the sources
  joined plus one target column per use case (`target_<use_case>`), saved for one config or a
  list, with eligibility, candidates, contract and split derived on read from the reader's
  config (a changed eligibility no longer forces a rebuild; sidecar schema 3; the freeze point
  narrows to the data part); `revert` in the audit log; the id cast to string at load so the
  split's draw survives an upstream type change (T22). Built by five agents on disjoint files
  from one spec; four reviews (code, silent failures, compatibility, ML audit) found no
  invariant broken and tightened refusals: `task` in the hashes, a feature source matching
  nothing, a reserved column name, a validation period outrunning the saved target source, a
  `revert` laundering a rule's exclude. Full suite 252 passed, 9 deselected, 4 min 56 s; the notebook runs on the dev
  data in 30 s; two configs save one table with two target columns. — look at:
  `worknotes/m2_1_foundation/review_guide.md`; D-088, D-125, D-129, D-131
- **The SDS's review of steps 2 and 3, applied (10-28).** Labels kept in every period Target
  Factory can build (an upstream target would look the same; the framework does not police a
  DS); the two config knobs for source data quality went (`null_as`, `leavers`): a null never
  counts as an event and the contract's callout points upstream; eligibility is two ordered
  lists, `analysis` filters dropping rows before EDA and `modelling` filters tagging them until
  Feature Checks, which runs on the eligible rows; the split and the sampling as one salted hash
  draw in [0, 1); one coverage check for the spine and the target source; the template's comment
  rule. — look at: D-029, D-030, D-129, D-131
## To try
- `notebooks/01_target_factory.ipynb` on the synthetic dev data, or
  `python -m core_modelling run conf/base/cc_acquisition.yml conf/base/td_acquisition.yml --stages
  target_factory --env conf/local/environment.yml` — look at the two target summaries, the one
  table with `target_cc_acquisition` and `target_td_acquisition`, and how each use case's read
  drops the other's target and applies its own eligibility.
- The audit log's worked example, `pytest tests/test_audit_log.py -q`, with `revert` — look at
  how entries become the resolved config.

## Last 7 working days (10-21 to 10-27)
- 10-26 → 10-27 — **Stage 1 (M2.1 Foundation) built end to end, version 0.2.0**: the config
  spine, Target Factory, the dataset, `run` and the first guided notebook; traps T20, T21 —
  D-129–D-133, `docs/components/dataset.md`
- 10-23 → 10-25 — **Inconsistency sweep answered and closed**: 21 decision rows extended; EDA and
  Feature Checks use all clients and the client split comes after them (D-030, `CLAUDE.md` §4.4);
  production retrains the recipe by default, checked against its parent (D-033, D-052); one
  sign-off gate (D-031); sampling only when declared (D-117); the validation month in the config
  (D-088) — the rows changed on 10-23 in `docs/decisions.md`
- 10-25 — **Your synthetic to-dos built as ten trap columns** (0.5.0), on in every preset; the
  package goes into the bank as code, tests generate their data from a seed (D-041, D-064) —
  `docs/components/test_harness.md` → Trap summary
- 10-23 → 10-26 — **Stage 1 designed and planned**: the config layout, the environment file, the
  model input, the automation-level mapping, the collect printout (D-129–D-133; OD-25 closed) —
  `docs/decisions.md`
- 10-22 — **Decision log compacted; inconsistency sweep; LDS reading list**: 128 rows → 58 in a
  high-impact and a low-impact table, so IDs may have moved (mapping in `worknotes/log.md`) —
  `docs/decisions.md`
- 10-22 — **Planning thread closed**: plan as working assumption, audit log in `config.md`;
  D-022, D-024, D-052, D-125, D-128 — `worknotes/timeline_proposal.md`, `docs/components/config.md`
- 10-22 — **Fourth answers; plan adjusted**: registry records (D-111), monitoring frame (D-040),
  sampling kept simple (D-117), the Phase 3 wishlist — `docs/roadmap.md`
- 10-21 — **Third answers; plan reshaped; synthetic data accepted by the LDS**: the master layer
  (D-016), calibration a release requirement (D-049), outputs-only compatibility (D-007) —
  `worknotes/timeline_proposal.md`
- 10-21 — **No pickle only at promotion**: D-051 — `docs/components/lifecycle.md` → Open questions
- 10-21 — **Holistic review, second answers**: per-month evaluation (D-098), trial budgets (D-094),
  M2 engineering shape (D-100); doc-hygiene pass — `docs/decisions.md`
