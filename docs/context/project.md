# Project context

**Verdict:** `core_modelling` is how the unit will build, ship and maintain models. It is a
versioned, config-driven library that takes a use case from data to a monitored production model in
days to weeks, not months. It sets one standard for every stage of the data science lifecycle:
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
| **Speed** | 2–4 months per use case; "modelling takes months" is taken for granted | ~3 days on the hands-off `quick` profile to ~3 weeks on `thorough`; a first model within days |
| **Structure** | A bespoke pipeline per use case; notebooks copied and hand-edited per product; logic inside notebooks | One versioned library; a use case is a config; custom code only at named extension points |
| **Decisions** | Features, windows and eligibility live in code or in someone's head | Every decision in one config; the frozen config plus hashes reproduce any run |
| **Targets and leakage** | Targets built ad hoc, next to the raw forward columns they came from; leakage caught by memory, if at all | Target Factory records lineage and excludes those columns automatically; time separation is enforced at the boundary |
| **Data understanding** | EDA is ad hoc, slow or skipped; charts show nothing at low prevalence | EDA worth running first: population, target, key features and segment comparisons, built for rare targets, plus pivot tools for exploring |
| **Feature decisions** | Afterwards, nobody can say which features were dropped, by what, or why | A feature ledger records every candidate, every check, every human and automated decision, and what the model used |
| **Splits and evaluation** | A single training month; random splits; feature selection on the full data; pooled AUC taken as quality | Observation windows; train/test split by client; out-of-time validation; metrics per segment against declared baselines |
| **Modelling** | AutoML as a black box where one learner eats the budget; no guard against overfitting; metric picked ad hoc | AutoML and predefined models with efficient tuning: bounded search spaces, a guard on the train–test gap, and a metric derived from how the scores will be used |
| **Explainability** | Explainers that error out and get switched off | Views chosen per model family from a compatibility table; anything that should work does work |
| **Registry and deployment** | Models copied by hand and promoted as a side effect of scoring; unclear what is in production | register → promote → deploy, gated and signed off; tables showing every registered and production model |
| **Scoring** | Outputs overwritten; scores not traceable to a model or config | Batch-scoped outputs with manifests; every score traces to its model, config and code version |
| **Monitoring** | Rare and manual; performance seldom checked after go-live | Operational health and drift from day one; realised performance and impact as soon as outcomes exist |
| **Knowledge** | Inconsistent vocabulary; no overview of live models; little learning across the team | A shared glossary, a model inventory, and guided notebooks that show how things work under the hood |
| **Environment** | Laptop code breaks inside the bank (paths, versions, HDFS) | An environment adapter and bank-parity pins: moving inside is configuration, not code |

## Goals

1. **Speed with rigour.** Profiles trade depth for speed (`quick` ≈ 3 days, `thorough` ≈ 3 weeks).
   Correctness checks are never what gets skipped: the hands-off mode skips human effort, not the
   checks themselves.
2. **One standard for the whole lifecycle:** target creation, data understanding, feature checks,
   training, evaluation, registration, deployment, scoring and monitoring.
3. **Reproducibility.** Frozen config, config hash, data-definition hash, feature signature, model
   hash and code version. Every number and every score traces back.
4. **Maintainability** of 50–100 live models: tiers, registry tables, versioned artifacts, and use
   cases that upgrade at their own pace without breaking (D-047, `CLAUDE.md` §2).
5. **Generality.** Any domain, entity and source, through configuration. Task families are kept
   open, and a second working task type proves extensibility.
6. **Guidance and learning.** Every non-trivial choice comes with options and when-to-use guidance.
   Notebooks are guided. Users can see and debug what happens under the hood (a library, not a
   black-box service).
7. **Overview.** Registry tables, a model inventory and a cross-model monitoring view show the whole
   estate.
8. **Ready for assisted modelling.** The config-in / artifacts-out runs and bounded experiment
   sweeps are what an LLM loop will drive after internalisation (token-frugal, and it never replaces
   the checks).

## Scope

**Eventual (the design must leave room for all of it):**
- **Panel tasks:** one row per unit (client, account, card, merchant…) per period. This covers
  binary (propensity, churn, default…), multiclass (e.g. next product), regression (amounts) and
  time-to-event.
- **Series tasks:** aggregate time series (forecasting). They need their own data contract, rolling
  validation and metrics, and share the lifecycle, registry, reporting and monitoring.
- **Nearby problems** (uplift, recommendation, segmentation, anomaly detection…) are not excluded,
  and the shapes must not block them. The eventual list is a Chief DS meeting topic (OD-21).
- **Every domain** (retail, SME, corporate) and **every entity**.

**Phase 2:**

| | Phase 2 | Later |
|---|---|---|
| Task types | Binary plus at least one more panel task type, end to end (which one: OD-15) | Other panel tasks; series tasks |
| Domains / entities | Any, through configuration (synthetic data outside the bank) | — |
| Modelling paths | AutoML (FLAML) and predefined model + Optuna | Spark-native engines, only if ever needed |
| Training data | Multi-month observation windows | — |
| Lifecycle | local → registered → production; register / promote / deploy; registry tables | Sign-off log; shadow challengers; MLflow (if adopted) |
| Monitoring | Operational and drift: deep. Realised performance and impact: thin | Alerting; retrain automation |
| Run modes | Library + CLI + Python API + guided notebooks | No service layer planned |
| LLM-assisted modelling | Interface kept in mind only | After internalisation |

**Phase 2 is done when** a DS can take a new use case, for whichever entities it applies to, from
data to scores from a production model using only a config and the guided notebooks. Every component
exists at least as a thin version (depth per component: OD-01), and only the LLM branch is missing.
The production step is met outside the bank when `deploy` runs against a production-tier path on
synthetic data, and inside the bank when the first change request runs it (D-055). Target: move into the bank around December 2026 (in early October 2026 this was put as "within 1–2
months"; there is no hard deadline). Build order and milestones: `docs/roadmap.md`.

## Entities, domains and sources

- **Two entities (subsidiaries).** Most use cases exist in both, with separate models: data can't be
  merged, and the populations and product catalogues differ (one entity runs a different banking
  model). Some use cases apply to one entity only, so instances are never created automatically, and
  cross-entity comparison is not a default (D-034).
- **Domains** (retail, SME, corporate) come with different schemas, use cases, requirements and data
  timing, and they won't all be touched at the same time.
- **Sources are not one per domain.** An FX use case and a loan use case may read different schemas.
- Folder layout per entity/domain and per-entity permissions are open (OD-06).

## People and rhythm

Short forms in notes and meeting material: **SDS** (the builder), **LDS** (the Lead DS), **CDS** (the
Chief DS).

- **The framework's builder** (a senior DS) does the work and owns every design decision; all
  decisions flow through them.
- **The Lead DS** reviews in a daily ~1-hour sync (design, reviews, ideas). Each sync is prepared with
  `/brief` from `worknotes/sync.md`.
- **The Chief DS** sets direction. A design meeting is on 2026-10-15 (topics: `docs/roadmap.md`).
- **Platform / MLE colleagues** own the production paths and the change-request process. Who builds
  the registry and deployment (an MLE/MLOps colleague?) and when they join: OD-23.
- **Users** are the unit's data scientists. **Consumers** are the business and the strategy team
  (via reports and monitoring).

## Distribution

The framework is a versioned Python library with a config-driven CLI and Python API; there is no
service (D-024). A service would mean running a platform, and users learn more when they can see
under the hood. Each use case pins the framework version it runs with, upgrades at its own pace, and
scores its models with that version. Use cases are not folders in one shared repo (D-047). Still
open: the channel (e.g. an internal package repository with version pins, or git clone), the release
path, where use cases live, and where their extension code lives (OD-02, OD-04, OD-05). These are a
Chief DS meeting topic. Forward compatibility stays a first-class constraint either way, because
many versions write to the same shared tables (`CLAUDE.md` §2).

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
   (D-020 to D-043).

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
- **Testing:** light now; full per-function coverage and internal CI/Sonar before migration.

Vocabulary: [`docs/glossary.md`](../glossary.md).
