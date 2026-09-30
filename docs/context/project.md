# Project context

**Verdict:** `core_modelling` is the unit's standard way to deliver low- and medium-value models.
It is a config-driven, governed framework that turns a 3–4 month bespoke project into a 3–4 week
configuration exercise. Phase 2 turns the crunch prototype into a standalone, maintainable product.

## Why this exists

- **The problem.** Use cases take 2–4 months each and end up as bespoke pipelines, many of them
  anti-patterns. Across a unit of up to ~100 people running 50–100 live models, this makes the
  estate unmaintainable. Current deployment and registry practice is inconsistent.
- **The goal.** Every low- and medium-value use case is *required* to go through this framework:
  straightforward, config-driven, delivered in ~3–4 weeks. Bespoke, high-value, continuously
  developed work (e.g. AML) stays outside.
- **The standard.** Beyond delivery, the framework sets the new standard for how models are
  trained, registered, promoted, deployed, scored and tracked.

## Scope

| | Now (Phase 2) | Later (the design must leave room) |
|---|---|---|
| Segments | Retail | SME, Corporate |
| Task types | Binary classification (propensity) | Regression, multiclass, time-to-event, time-series forecasting |
| Run modes | Notebook-driven (manual) and CLI / Python API (automated) | Service-style integration (HTTP/scheduler), not built now |
| LLM-assisted modelling | Not built; only the interface is kept in mind | After the product is internalised in the bank |

**Distribution is undecided.** It will be either a service or a template repo that use cases fork
(e.g. a "sample use case" repo). Either way, the framework pushes updates into every use case
under it, so **forward compatibility** and **room for future structure** are first-class
constraints (see `CLAUDE.md` §2).

## History

1. **Original plan** (`docs/reference/`): a phased roadmap built on a spine
   (feature/target contract → population/eligibility → feature checks → model production →
   OOT evaluation → model card → batch scoring). Three shared agreements (config shape, component
   interface, card shape) are checked automatically. Two sponsors: one for retail model delivery,
   one for an LLM-assisted modelling loop, which grows as a branch off the stable backbone.
2. **The crunch** (2–3 weeks, politically urgent): basic activation-propensity scores for ~10 retail
   products on a single training month, built in notebooks + YAML configs with FLAML. It worked:
   models were built, promoted and scored end-to-end. The code is in `legacy/propensity_crunch/`.
   Lessons: `docs/context/lessons.md`.
3. **Phase 2 (now):** back to the drawing board with the crunch takeaways. Build the standalone
   product, get "a version of everything" done before the codebase moves inside the bank, and set
   up for later small-block collaboration.

**Crunch results — read carefully.** Most models reached 0.85–0.95 OOT AUC. This is very likely
inflated by pooling a heterogeneous client base: segments with near-zero propensity make ranking
easy without much within-segment skill. Phase 2 evaluation must report segment-stratified metrics
before treating AUC as model quality. Precision is **not** the Phase 2 priority.

## Phase 2 goals, in priority order

1. **A standalone product.** Installable package, `.py` production path, thin notebooks, a clean
   config spine with `schema_version`, and an environment adapter so bank specifics are config only.
2. **Usability and runtime.** Faster end-to-end runs (Spark-side pruning and sampling, fewer wasted
   minutes like the 30–40 min MI computation), sensible defaults, clear reports.
3. **Rethink every component**, most heavily:
   - **EDA:** a standalone unit producing analyst-grade outputs and reports.
   - **Feature Checks:** a standalone unit with stepwise, traceable filtering decisions.

   Data Creation gets a lighter touch while upstream integration is still TBD.
4. **Lifecycle:** three tiers (local → registered → production); promotion and deployment separated
   from inference; artifacts designed for maintaining 50–100 live models.
5. **Baselining and tracking:** automatic baselines and simple impact tracking.
   - *Business reporting:* against the population base rate.
   - *Internal metrics:* also against previous model scores and historically predicted rates.
6. **Generalisation:** handle very different population sizes and positive rates (0.04%–10%+); keep
   every shape task-agnostic.
7. **LLM-assisted modelling:** after internalisation. It runs inside the bank on Claude via API or
   Bedrock, with limited tokens and not the newest models, so it must be token-frugal.

## Hard constraints

- **Code-light, reviewable, no slop** (`CLAUDE.md` §1) — every line is human-reviewed.
- **One-way code flow:** code goes into the bank only (download zip → copy into the internal repo).
  No data, results or code ever come out. All development happens outside, on synthetic data.
- **Bank parity:** pinned versions matching the internal devcontainer (`docs/context/environment.md`).
- **General identifiers only:** no bank, people, path or table names in the repo.
- **Testing:** light now; full per-function coverage and internal CI/Sonar before migration.

## Glossary

- **Use case:** one modelling problem (e.g. one product's activation propensity), defined by configs.
- **Observation month (`obs_date`):** features are as-of this month. **OOT month:** a later month
  used for evaluation. **Inference month:** the month being scored.
- **Eligibility:** the population a use case models and scores.
- **Candidates / features:** the pre-screening feature list vs the final model inputs.
- **Local / registered / production:** the three model tiers. **Promotion:** local → registered.
  **Deployment:** registered → production.
- **Run / run_id:** one training run. **Scoring batch / scoring_run_id:** one inference run.
  **Manifest:** links a scoring batch to the models that produced it.
- **Model card:** a generated record binding config, lineage and results.
- **Frozen config:** the fully resolved config saved with an artifact, used for reports and
  reproduction.
- **Bank parity:** matching the internal environment's versions and behaviour.
- **STUB / BUILD / MIN:** depth markers from the spine reference (interface-only / correct and
  general / minimal).
