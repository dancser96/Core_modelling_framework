# Sync page
_For the builder and the Lead DS · last updated: 2026-10-13 · last briefed: —_

The detail behind each item is in `worknotes/log.md`. Decisions live in `docs/decisions.md`; open
decisions (OD-nn) in `docs/roadmap.md`. Nothing is committed yet: the whole design baseline below is
one uncommitted change, ready for review.

## For the Lead DS: to review
- [ ] **Where we start → where we want to reach**, goals and scope — `docs/context/project.md`.
      Feedback wanted: anything missing from the anti-patterns, or goals you'd frame differently?
- [ ] **Reading order and stage → component map** — `docs/README.md`. Feedback wanted: is it the
      right way into the docs for a newcomer?
- [ ] **Roadmap**: milestones M0–M5 and the open-decision table — `docs/roadmap.md`. Feedback wanted:
      milestone order, and which open decisions you want to own or take to the Chief DS.
- [ ] **Rule changes from the holistic review** — `CLAUDE.md` §2 and §4.4, §4.7, §4.10;
      `docs/decisions.md` D-047–D-055. Feedback wanted: do the reworded invariants (label checks on
      train-split clients; calibration) match how you'd audit a model?
- [ ] **Lifecycle**: register → promote → deploy, change-request path, registry tables —
      `docs/components/lifecycle.md` (D-033). Feedback wanted: does it match how production changes
      actually run, and the two-table "registered / production" idea?
- [ ] **Observation windows and splits** — `docs/components/dataset.md`, including the design
      analysis on pandas training, downsampling with correlated clients, and the window ablation.
      Feedback wanted: the default sampling option (OD-17).
- [ ] **Feature ledger sketch** — `docs/components/feature_ledger.md` (OD-11). Feedback wanted: does
      it give enough oversight of initial vs selected features? Two keying issues are listed there.
- [ ] **Inference output** — `docs/components/inference.md` open questions (OD-18). Needed from you:
      the extra columns for the campaign system and the score/manifest path layout.

## Questions for the Lead DS
- **Trade-off chart (OD-22):** may the overfitting chart pick a trial using the test metric, or only
  client-grouped CV inside train? Leaning: CV only, with test reported but never chosen on, so the
  test-vs-validation gap still separates overfitting from decay (`docs/components/training.md`).
- **Example notebooks:** beyond the framework working both as a pipeline (`python -m core_modelling
  run …`) and through notebooks, do you want anything more from the release examples?
  (`docs/components/run_modes.md`)
- **Model documentation:** what did you mean by "checks that the necessary inputs exist"?
  (`docs/roadmap.md` Phase 3 backlog)
- **Monitoring in Phase 2:** you suggested Phase 3; the builder's view is a stub of every major
  component in Phase 2, with operational and drift monitoring deep (D-040). Agree? (OD-01)
- **Production paths:** confirm the move from sandpit paths to production paths, with deployment as
  a copy job (`docs/components/lifecycle.md`).

## Open questions for both of us

| Question | Context | Current leaning | Needs |
|---|---|---|---|
| Chief DS meeting prep (topics a–f) | Meeting this week; topics mapped to open decisions in `docs/roadmap.md` | Build a pre-read from the OD table | Builder + Lead DS |
| Definition of done, production step (D-055, soft) | Deploying inside the bank depends on the change-request calendar | Outside: `deploy` to a production-tier path on synthetic data; inside: the first CR | Chief DS meeting (e) |
| High-level lifecycle, deployment and registry design (OD-06–OD-09) | Both agree it must be drawn up soon | — | Builder + Lead DS, then platform colleagues / Chief DS |
| Per-entity storage permissions and folder layout (OD-06) | Decides whether entities need physically separate registries | — | Lead DS + platform colleagues |
| Model versions, one production version per key, shadow challengers (OD-07) | Above the builder's remit | Proposal in `lifecycle.md` | Lead DS / Chief DS |
| What "registered" means (OD-09) | Any kept run vs a gated production candidate | — | Chief DS meeting |
| Registry storage and MLflow (OD-08, OD-13) | Quick tables now; MLflow later? | Append-only records shaped like MLflow's | Platform/MLE + Chief DS |
| Depth per component (OD-01) | full / deep / thin / stub; wording proposed, to review | — | Builder + Lead DS |
| Second task type (OD-15) | Proves extensibility; its shapes must be known before EDA and Feature Checks are built | Chosen by the end of M1 (D-050) | Builder |
| Config lifecycle for feature decisions (OD-10) | Includes the case where resolving a flag after training would force an identical retrain | Open | Builder |

## What the design baseline contains (uncommitted)

**Scope and plan**
- Domain- and entity-agnostic. Binary plus one more panel task type end to end; extensibility is
  proven when the second task only fills its per-task spec (D-020, D-050).
- Done when a DS takes a new use case to production scores with only a config and the guided
  notebooks; every component at least thin; only the LLM branch missing. Move into the bank
  ≈ December 2026, no hard deadline (D-021, D-055).
- Walking skeleton first (M2), then at most 2–3 deepening rounds; depth levels full / deep / thin /
  stub (D-022, OD-01). Next milestone: M1, synthetic data + local Spark harness.
- Profiles `quick` (≈ 3 days, hands-off) / `standard` / `thorough` (≈ 3 weeks) set every stage's
  defaults (D-023).
- A library with a CLI and Python API, no service (D-024). Each use case pins its framework version
  and upgrades at its own pace; use cases are not folders in one shared repo (D-047).

**Stages and data**
- Target Factory (optional) → EDA → Feature Checks → Training → Evaluation → register → promote →
  deploy → Inference → Monitoring. Renamed: Data Creation → Target Factory, Tracking → Monitoring
  (D-028, to verify with the Chief DS).
- Target Factory builds targets only, with lineage so their source columns are excluded
  automatically; features come from upstream (D-029).
- Training uses a multi-month observation window; train/test split by client; one out-of-time
  validation month whose target window doesn't overlap training's (D-030). Label-using checks see
  train-split clients only; label-free drift checks never use the validation month (D-048).
- No model without EDA and Feature Checks for the same data definition (D-031).
- Domains and entities are configuration; data is never merged across entities (D-034).
- Feature ledger: every candidate's path through checks, human keep / exclude decisions,
  automated selection and use in the model (D-043).
- Synthetic data: a dev-only `synthetic/` package, ~100k clients × 24 months, sticky holdings,
  planted traps and an oracle ground truth (D-041).

**Modelling, evaluation, reporting**
- The config declares the business decision (top-N, threshold, ranking, probability); it drives the
  metric, the gates and the report emphasis, and every report opens with a choices block (D-032).
- Two modelling paths behind one interface: FLAML AutoML, and a predefined family tuned with Optuna;
  categoricals encoded by the framework; an overfitting trade-off chart (D-037, OD-22).
- Calibration: prior shift whenever sampling happened, plus a general calibration step built in
  Phase 2 (D-049). Optional refit on all clients or an extended window (D-052). The model bundle is
  a versioned artifact (D-051).
- Stratified metrics are mandatory: the crunch's 0.85–0.95 pooled AUC is likely inflated by
  segment mix (D-038).
- Fail loud; only views declared incompatible up front show "not available: reason" (D-035).
- Self-contained HTML reports with plotly embedded for offline use (D-036). A sweep that picks a
  variant labels the winner's validation result as optimistic (D-053).

**Lifecycle and monitoring**
- register → promote (the approved PR is the sign-off) → deploy (run by the change-request
  process). A DS session never writes to production. Model key = (entity, domain, use case, split)
  (D-033).
- Monitoring: operational health and drift deep, realised performance and impact thin (D-040).
  Training saves the drift reference on the true population; Target Factory builds labels for
  scored months (D-054).

**Ways of working**
- Code-light rules; small classes allowed where state and behaviour travel together (D-025). Major
  steps start with research, critique and a holistic review (D-026).
- New invariants: client-grouped split, sampling independent of outcomes unless weighted, no model
  without data knowledge (`CLAUDE.md` §4.11–13).
- Doc rules (one owner per fact, update triggers) in `CLAUDE.md` §8; `docs/README.md` as the front
  door (D-045); a glossary; worknotes shared with the Lead DS (D-044).
- Usable libraries: scipy, statsmodels, seaborn, plotly, jinja2; Optuna on top (D-042). No
  per-source column catalogue for now (D-046).

## Recent developments (newest first)
- 2026-10-13 — **Holistic review settled**: nine decisions (D-047–D-055) and reworded invariants
  §4.4, §4.7 and §4.10. Main points:
  - use cases pin their framework version (OD-03 settled);
  - label checks on train-split clients only;
  - one calibration rule plus a calibration step;
  - per-task spec; versioned model bundle; optional refit;
  - the drift reference and labels for monitoring.

  Parked as open questions: the identity hashes, ledger keying and the scores format. Look at:
  `docs/decisions.md` D-047–D-055, `CLAUDE.md` §4. Status: done.
- 2026-10-12 — **Holistic review of the baseline**: the docs are consistent with each other; the
  review found four places where test or validation data could inform a choice, plus shape risks.
  Status: answered 2026-10-13 (above).
- 2026-10-12 — **Review pass before compacting**: inputs that weren't yet recorded are now in the
  docs (questions for the Lead DS above, lifecycle urgency and sandpit-path note, D-046 no column
  catalogue, aggregation starting list, OD-15 quantile-loss idea). Status: done.
- 2026-10-12 — **Worknotes are now shared and committed**, and there is a new reading guide
  (`docs/README.md`) with the stage → component map. Status: done.
- 2026-10-12 — **Design baseline (milestone M0)**: every doc rebuilt from three review rounds and
  the Lead DS notes; contents summarised above. Status: done.

## Demo next
- No code yet. Walk through `docs/README.md` (reading order + map), then the `docs/context/project.md`
  from → to table and the `docs/roadmap.md` milestones.
