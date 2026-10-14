# core_modelling: design update and first release
_CDS design meeting, 2026-10-15 · session 1, part 2 · draft_

## 1. Where we are

The crunch delivered the first retail propensity models end to end. Phase 2 turns that into the
unit's standard way to build, ship and maintain models. The design baseline is done, and building
has started on synthetic data.

| | Today | Target |
|---|---|---|
| **Speed** | 2–4 months per use case | A first model in about 3 days hands-off; about 3 weeks on the thorough path |
| **Structure** | A bespoke pipeline per use case; logic in copied notebooks | One versioned library; a use case is a config file |
| **Traceability** | Nobody can say which features were dropped, or why; scores can't be traced to a model | Any run can be reproduced from its frozen config; a feature ledger; every score traces to its model and config |
| **Evaluation** | One training month, random splits, pooled AUC | Several training months, a split by client, an out-of-time validation month, metrics per segment against baselines |
| **Lifecycle** | Models copied by hand; unclear what is in production | register → promote → deploy as gated steps; tables of registered and production models |
| **Monitoring** | Rare and manual | Health and drift from day one; performance once outcomes exist |

**A caution from the crunch:** most models showed 0.85–0.95 out-of-time AUC. That is very likely
inflated by pooling very different segments, so per-segment metrics are now mandatory.

## 2. What it is

- **A library, not a service.** A use case is one config file plus its own copies of the guided
  notebooks. It runs through those notebooks, a CLI or a Python API, and pins the framework version
  it uses. Users can see what happens under the hood and debug locally.
- **Standalone stages.** Each one runs on its own from the config and writes its own artifacts and
  HTML report.

| Modelling half: designed, our proposal | Downstream: to design together |
|---|---|
| Target Factory (optional) → EDA → Feature Checks → Training → Evaluation | register → promote → deploy → Inference → Monitoring |

- **Guided, not guessed.** Profiles set the defaults, from hands-off `quick` (≈ 3 days) to
  `thorough` (≈ 3 weeks). The config states the business decision (a top-N list, a threshold, a
  ranking or a probability), and the framework derives the metric and the gates from it. Every
  report opens with what was chosen.
- **Modelling:** FLAML AutoML, plus a predefined model family tuned with Optuna, behind one
  interface. Which of these the first release includes is a question for session 2.
- **Any domain, entity or source, through configuration.** Data is never merged across entities.
- **Three tiers: local → registered → production.** A data scientist's session never writes to
  production; deployment goes through the change-request process.

## 3. Principles that shape everything

- **One standard for every model.** Every model is built, evaluated, registered and monitored the
  same way, so it can be compared, handed over and audited.
- **Speed comes from skipping human effort, never checks.** The hands-off profile runs the same
  checks. No model is trained without EDA and Feature Checks on the same data.
- **Traceable end to end.** Every score traces back to its model, frozen config, data definition and
  code version. A feature ledger shows each feature's path: checks, human decisions, automated
  selection, use in the model.
- **Leakage is handled by the framework, not by memory.** Columns the target was built from are
  excluded automatically. Suspicious features are flagged for a person to decide on, never dropped
  silently.
- **Decisions come before results.** The business decision, metric and baseline are fixed in the
  config before any result is seen.
- **Upgrades never break a live model.** Each use case pins its version. Config and artifact
  formats are general from the start and versioned with migrations, because many versions write to
  the same shared tables.
- **Readable, not clever.** The code is small enough for a reviewer to follow, and custom code goes
  in only at named extension points. What we want to avoid is a big generated pipeline that nobody
  understands.
- **Nothing bank-specific in the code.** We build on synthetic data; inside the bank, only
  configuration changes.

## 4. First release: before the end of the year

**Done when** a data scientist can take a new use case from data to production scores using only a
config and the guided notebooks. Every component exists, at least in a thin version. Only the
LLM-assisted branch is missing. The detailed plan comes after this meeting.

| Step | Content | Status |
|---|---|---|
| Design baseline | Scope, rules, decisions, component designs | Done |
| Synthetic data + local Spark | ~100k clients × 24 months with planted traps and a known ground truth; shared by tests and notebooks | In progress |
| Walking skeleton | Every stage thin and working end to end on a binary task | Next |
| Deepening (2–3 rounds) | EDA that is worth running, history windows and sampling, modelling paths, per-segment reporting, health and drift monitoring | — |
| Move into the bank | Tests, CI readiness, the first internal run | — |

- **Modelling half:** deep where it matters most (EDA, data splits, training, evaluation).
- **Downstream:** thin but real. register, promote and deploy work as commands, and scores come with
  manifests. Health and drift monitoring are deep; realised performance and business impact are
  thin.

**Open for the first release (session 2):** binary only, or binary plus regression? FLAML only, or
both modelling paths?

## 5. What we'd like from you

| | Modelling half | Downstream |
|---|---|---|
| **Where we are** | A worked-out design, rules and decisions | Proposals to start from, and open questions |
| **What we'd like** | Agreement on the stage structure and the direction. Occasional check-ins; the few open points come up in session 2 | Design it with us, and help bring in the MLE/MLOps and platform colleagues. Questions you can't answer yet we still raise, so they stay visible |

## 6. Longer term (likely to change)

- More task types (multiclass, time-to-event), then forecasting.
- A model inventory and a cross-model monitoring view of the whole estate.
- A sign-off log, shadow challengers, retraining automation, and MLflow if it is adopted.
- LLM-assisted modelling after the move into the bank. It drives the same config-in, reports-out
  runs and never replaces the checks.
