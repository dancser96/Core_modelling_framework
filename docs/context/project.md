# Project context

**Verdict:** `core_modelling` is how the unit will build, ship and maintain models. It is a
versioned, config-driven library that takes a use case from data to a registered candidate in days
to a few weeks of DS effort, not months; production follows through the change-request calendar
(D-023). It sets one standard for every stage of the data science lifecycle:
correct, reproducible, maintainable and explainable. Phase 2 turns the crunch prototype into that
product: a first usable version of every part, built on synthetic data and then moved into the
bank.

Related: [glossary](../glossary.md) · [roadmap](../roadmap.md) · [architecture](../architecture.md) ·
[decisions](../decisions.md) · [lessons](lessons.md).

## Why this exists

The unit has up to ~100 people and runs 50–100 live models, and it delivers each use case as a
bespoke project of 2–4 months. The results are an estate nobody can maintain, inconsistent
deployment and registry practice, and a widespread belief that a model *should* take months. The
framework exists to prove the opposite and make it the norm: a credible first model in days, with
every model built, evaluated, deployed and monitored the same way.

Every low- and medium-value use case is expected to go through the framework. Bespoke, high-value,
continuously developed work (e.g. AML) stays outside, but should still follow the lifecycle
standard where it can.

## Where we start from → where we want to reach

| Area | Today | Target |
|---|---|---|
| **Speed** | 2–4 months per use case; "modelling takes months" is taken for granted | A registered candidate in days to a few weeks of DS effort, depending on the automation level; production follows through the change-request calendar (D-023) |
| **Structure** | A bespoke pipeline per use case; notebooks copied and hand-edited per product; logic inside notebooks | One versioned library; a use case is a config and its decision audit log (D-006); custom code only at named extension points |
| **Decisions** | Features, windows and eligibility live in code or in someone's head | The intent in one config and every later decision in its decision audit log (D-125); the resolved config plus hashes reproduce any run |
| **Targets and leakage** | Targets built ad hoc, next to the raw forward columns they came from; leakage caught by memory, if at all | Target Factory records lineage and excludes those columns automatically; time separation is enforced at the boundary |
| **Data understanding** | EDA is ad hoc, slow or skipped; charts show nothing at low prevalence | EDA worth running first: population, target, key features and segment comparisons, built for rare targets, plus pivot tools for exploring |
| **Feature decisions** | Afterwards, nobody can say which features were dropped, by what, or why | A feature ledger records every candidate, every check, every human and automated decision, and what the model used |
| **Splits and evaluation** | A single training month; random splits; feature selection on the full data; pooled AUC taken as quality | Observation windows; train/test split by client; out-of-time validation; metrics per segment against declared baselines |
| **Modelling** | AutoML as a black box where one learner eats the budget; no guard against overfitting; metric picked ad hoc | AutoML and, from Phase 3, predefined models (D-020) with efficient tuning: bounded search spaces, a guard on the train–test gap, and a metric derived from how the scores will be used |
| **Explainability** | Explainers that error out and get switched off | Views chosen per model family from a compatibility table; anything that should work does work |
| **Registry and deployment** | Models copied by hand and promoted as a side effect of scoring; unclear what is in production | register → promote → deploy, gated and signed off; tables showing every registered and production model |
| **Scoring** | Outputs overwritten; scores not traceable to a model or config | Batch-scoped outputs with manifests; every score traces to its model, config and code version |
| **Monitoring** | Rare and manual; performance seldom checked after go-live | Operational health and drift from day one, connected to the data observability framework; realised performance and impact as soon as outcomes exist |
| **Knowledge** | Inconsistent vocabulary; no overview of live models; little learning across the team | A shared glossary, a model inventory, and guided notebooks that show how things work under the hood |
| **Environment** | Laptop code breaks inside the bank (paths, versions, HDFS) | An environment adapter and bank-parity pins: moving inside is configuration, not code |

## Goals

1. **Speed with rigour.** A registered candidate takes days to a few weeks of DS effort (D-023).
   Automation levels (D-023) run the same checks at every level; the difference is human
   time, and a higher-value use case brings more people and inputs that shape its choices.
   Correctness checks are never what gets skipped, and a person always signs off the features
   before a model is registered (D-031). Production follows through the change-request calendar.
2. **One standard for the whole lifecycle:** target creation, data understanding, feature checks,
   training, evaluation, registration, promotion, deployment, scoring and monitoring.
3. **Reproducibility.** Resolved config, config hash, data-definition hash, feature signature, model
   hash and code version. Every number and every score traces back.
4. **Maintainability** of 50–100 live models: tiers, registry tables, versioned artifacts, and use
   cases that upgrade at their own pace without breaking (D-047, `CLAUDE.md` §2).
5. **Generality.** Any domain, entity and source, through configuration, including the feature
   store alone or with other sources (D-021). Task families are kept open, and a second working task
   type proves extensibility.
6. **Guidance and learning.** Every non-trivial choice comes with options and when-to-use guidance.
   Notebooks are guided. Users can see and debug what happens under the hood (a library, not a
   black-box service).
7. **Overview.** Registry tables and a model inventory, which owns the cross-model view (OD-14),
   show the whole estate.
8. **Ready for assisted modelling.** From Phase 3, an LLM loop drives the config-in / artifacts-out runs and bounded experiment sweeps
   (token-frugal, and it never replaces the checks or the human feature sign-off).

## Scope

**Eventual (the design must leave room for all of it):**
- **Panel tasks:** one row per unit (client, account, card, merchant…) per period. This covers
  binary (propensity, churn, default…), multiclass (e.g. next product), regression (amounts) and
  time-to-event.
- **Series tasks:** aggregate time series (forecasting). They need their own data contract, rolling
  validation and metrics, and share the lifecycle, registry, reporting and monitoring.
- **Nearby problems** (uplift, recommendation, segmentation, anomaly detection…) are not excluded,
  and the shapes must not block them. The working order is D-081.
- **Every domain** (retail, SME, corporate) and **every entity**.

**Phase 2:**

| | Phase 2 | Later |
|---|---|---|
| Task types | Binary and regression, end to end (D-020) | Other panel tasks; series tasks |
| Domains / entities | Any, through configuration (synthetic data outside the bank) | — |
| Modelling paths | AutoML (FLAML) only (D-020) | Predefined model + Optuna (Phase 3); Spark-native engines, only if ever needed |
| Training data | Multi-month observation windows | — |
| Automation | Two automation levels, `autonomous` and `assisted`, with the same checks at both (D-023; D-132) | `manual` |
| Upstream | Feature store integration, limited to Stage 1 (M2.1 Foundation), where a use case's data comes in (no later stage knows about it): one use case config in three source settings (the feature store, other sources, both); outside the bank only the other-sources setting runs, on synthetic data, and the two feature-store settings ship commented out (D-021, OD-26) | Feedback mechanisms into the feature store (Phase 3 wishlist) |
| Lifecycle | local → registered → production; register / promote / deploy; one production version per model key; own records (append-only registry events, `production.json`) that map one-to-one onto MLflow concepts, with MLflow added beside them in M4 once confirmed available (D-111, OD-08); retraining in production on the same data definition as the default deploy path (only the inference month moves; a check against the evaluated parent before it scores), deploying the fitted model also allowed (D-033, D-052; operations researched with the platform team in M4, OD-27); no log of who signs off or approves a model (approvals stay in the PR and the change request, D-033) | Which source of people logs to build in; shadow challengers; retraining on moved or extended data (later months, all clients, a longer window) (Phase 3 wishlist in `docs/roadmap.md`) |
| Monitoring | The frame built properly: all four layers present (health, drift, realised performance, impact), with versioned tables, flags and the seam to the data observability framework, whose needs shape the tables only once we have seen it in use (D-021, OD-13). The content light: a few health and drift measures, realised performance thin, impact a stub (D-040) | Richer content; alerting outputs (acting on them: the platform / MLOps team, D-079); retrain automation |
| Run modes | Library + CLI + Python API + guided notebooks | No service layer planned |
| LLM-assisted modelling | Interface kept in mind only | Phase 3 (D-021) |

**Phase 2 is done when** a DS can take a new use case, for whichever entities it applies to, from
data to scores from a production model using only a config and the guided notebooks. Every component
exists at least as a thin version (depth per component: OD-01), including the feature store and data
observability integrations (thin); LLM-assisted modelling comes in Phase 3 (D-021).
The production step is met outside the bank when `deploy` runs against a production-tier path on
synthetic data (D-021). Inside the bank, a long change freeze around the year end makes the first
change request release 1.0, which carries only the framework, no model; a model's first deploy is
a later, quicker change request (D-021). This definition of done is met at **release 1.0**;
December 2026 is a pre-release that moves the code into the bank's internal repo, committed and
demonstrated, not into production (D-021). Its content and dates are being agreed with the LDS
(D-022; proposal in `worknotes/timeline_proposal.md`). In early
October 2026 the target was put as "within 1–2 months"; there is no hard deadline. Build order and
milestones: `docs/roadmap.md`.

## Entities, domains and sources

- **Two entities (subsidiaries).** Most use cases exist in both, with separate models: data can't be
  merged, and the populations and product catalogues differ (one entity runs a different banking
  model). Some use cases apply to one entity only, so instances are never created automatically, and
  cross-entity comparison is not a default (D-034).
- **Domains** (retail, SME, corporate) come with different schemas, use cases, requirements and data
  timing, and they won't all be touched at the same time.
- **Sources are not one per domain.** An FX use case and a loan use case may read different schemas.
- The output layout per entity × domain is open (OD-06); per-entity permissions are the platform's
  (D-079).

## People and rhythm

Short forms in notes and meeting material: **SDS** (the builder), **LDS** (the Lead DS), **CDS** (the
Chief DS).

- **The framework's builder** (a senior DS) does the work and owns every design decision; all
  decisions flow through them.
- **The Lead DS** reviews in a daily ~1-hour sync (design, reviews, ideas). Each sync is prepared with
  `/brief` from `worknotes/sync.md`.
- **The Chief DS** sets direction and leaves the design to the SDS and LDS (D-073). Topics for him
  are collected in `docs/roadmap.md` → Chief DS topics and raised at check-ins.
- **The platform / MLOps team** owns the production paths and the change-request process, and
  handles the downstream operation questions: who acts on monitoring flags, who owns a live model
  after its builder moves on, monitoring tooling and dashboards (D-079). Who builds the registry and
  deployment, and when: OD-23.
- **The feature store and data observability teams** own the frameworks the first release
  integrates with (D-021).
- **Users** are the unit's data scientists. **Consumers** are the business and the strategy team
  (via reports and monitoring).

## Distribution

The framework is a versioned Python library with a config-driven CLI and Python API; there is no
service (D-024). A service would mean running a platform, and users learn more when they can see
under the hood. The package ships in the base image through Nexus; images are supported for a year,
so the image a use case starts on sets its default framework version, which the use case pins and
may raise within the image's year (D-024). Each use case upgrades at its own pace and scores its
models with its pinned version. Use cases are not folders in one shared repo (D-047). Still open:
where use cases live (OD-02; leaning one repo per entity × domain, with use cases branching off as
they grow) and the release mechanics (OD-04). A repo may hold several similar use cases, each with
its own config and audit log; extension code lives in the repo that holds the use case, never in the
framework (D-006). Forward compatibility stays a first-class constraint either way, because many
versions write to the same shared tables (`CLAUDE.md` §2).

## History

1. **Original plan** (`docs/reference/`): a phased roadmap built on a spine (feature/target contract
   → population/eligibility → feature checks → model production → OOT evaluation → model card →
   batch scoring), with three shared agreements (config shape, component interface, card shape)
   checked automatically. It was reviewed with the Chief DS around August 2026. It had two sponsors: retail model delivery, and an LLM-assisted modelling
   loop growing as a branch off the stable backbone.
2. **The crunch** (2–3 weeks, politically urgent): basic activation-propensity scores for ~10 retail
   products on a single training month, built in notebooks + YAML configs with FLAML. It worked:
   models were built, promoted and scored end to end. Code: `legacy/propensity_crunch/`. Lessons:
   `docs/context/lessons.md`.
3. **Phase 2 (now):** back to the drawing board with the crunch takeaways. In October 2026, three
   review rounds with the builder and notes from the Lead DS reshaped the scope: domain- and
   entity-agnostic, observation windows, two modelling paths, a full lifecycle, guided usage
   (D-020 to D-043). On 2026-10-15 the Chief DS reviewed the design and left it to the SDS and LDS,
   adding feature store and data observability integration to the first release (D-021, D-023, D-024, D-031, D-051, D-073, D-079).

**Crunch results — read carefully.** Most models reached 0.85–0.95 OOT AUC. That is very likely
inflated by pooling a heterogeneous client base: segments with near-zero propensity make ranking easy
without much within-segment skill. Metrics per segment are therefore mandatory (D-038), and AUC is
not treated as model quality until they are seen. Precision is **not** the Phase 2 priority.

## Hard constraints

- **Code-light, reviewable, no slop** (`CLAUDE.md` §1): every line is human-reviewed.
- **One-way code flow:** code goes into the bank only (download zip → copy into the internal repo).
  No data, results or code ever come out. All development happens outside, on synthetic data.
- **Bank parity:** pinned versions matching the internal devcontainer
  (`docs/context/environment.md`).
- **General identifiers only:** no bank, people, path or table names in the repo (roles only).
- **Testing:** light tests now and at the December pre-release; every function tested and internal
  CI/Sonar by release 1.0 (D-014).

Vocabulary: [`docs/glossary.md`](../glossary.md).
