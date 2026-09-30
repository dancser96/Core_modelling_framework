# Core Modelling Framework — Spine & Governance Reference

*Internal context note. Captures the build spine, the governance checks each role owns, and how each one is scoped over time. Not a delivery plan — a reference for what gets stubbed first and built properly later, and in what priority order.*

---

## Depth legend

- **BUILD** — must be correct and reasonably general from the first product. The seam is load-bearing; getting it wrong makes downstream numbers untrustworthy.
- **STUB** — clean interface now, body hardcoded to the first product, replaced with a general implementation once a later product proves the abstraction. The *interface* is the deliverable; the body is throwaway.
- **MIN** — minimal; do the least that works and revisit only when a product forces it.

## Priority legend

- **P0** — correctness-critical at the first product. Wrong here and every result downstream lies. No second chance.
- **P1** — must exist at the first product (either a load-bearing seam or near-free to add), even if the body is minimal.
- **P2** — minimal at first, built out later.
- **P3** — deferred by nature (label-gated, tooling-gated, or only meaningful at scale); stubbed/designed now, built later.

---

## The spine (build order — the invariant)

Every product, and later every assisted-modelling run, goes through the same ordered sequence. The order is fixed; the pieces behind each step start product-specific and generalise only when a later product justifies it.

1. **Feature/target contract** — enforced agreement on features and label, including the strict time-separation rule (features as-of a date; label measured only after). Primary leakage defence, checked at the boundary.
2. **Population & eligibility** — who is in scope, who is excluded.
3. **Feature checks** — correctness (leakage, redundancy) and relevance selection, run *inside* the evaluation loop.
4. **Model production** — the automated engine, wired as one named, swappable option behind a stable interface.
5. **Out-of-time evaluation** — judged on a later period than trained on, against a declared baseline and a pre-agreed metric.
6. **Model card** — generated record binding configuration, lineage, and results.
7. **Batch scoring** — scored output to an agreed table.

---

## The three non-negotiables at the first product

Everything else can be stubbed or minimal. These three must be built properly from day one:

1. **The configuration spine** — typed, validated config + the named component interface. Blocks everything else and is what makes products 2–9 "just configuration."
2. **Feature checks done inside the evaluation loop** — leakage screening and relevance selection, never as a pre-step on the full data.
3. **Out-of-time evaluation** — the only split that reflects production and the empirical backstop for time-based leakage.

---

## Data science — components, depth, priority

| Component | First product | Eventually | Priority | Note |
|---|---|---|---|---|
| Configuration spine + component interface | BUILD (mechanism; content product-specific) | BUILD (general) | **P0** | Blocks all else. Interface is the framework; bodies are swappable. |
| Feature/target contract | BUILD | BUILD | **P0** | Time-separation enforced at the boundary, not left to discipline. DS owns target *definition*; upstream owns *materialisation*. |
| Feature checks — leakage (correctness) | BUILD (first-order screen) | BUILD (+ standing human-review process) | **P0** | First-order flags for human review, never auto-drop. Second-order/temporal leakage has no reliable automated screen — controlled by review + out-of-time backstop. |
| Feature checks — relevance | BUILD (inside CV) | BUILD (+ stability/null-importance at scale) | **P0** | Runs inside the evaluation split. Pre-selection on full data inflates every number. |
| Evaluation protocol (out-of-time) | BUILD | BUILD | **P0** | Baseline + promotion metric declared *before* results are seen. |
| Model production (engine behind the interface) | STUB (one named entry) | BUILD (multiple entries; hand-built alternative addable) | **P0 (seam) / P2 (body)** | The seam is critical so a manual model can be added later as configuration. The engine body itself is not where the risk sits. |
| Pre-processing / EDA gate checks | STUB (product-specific transforms) + MIN (checks) | BUILD | **P1** | Fitted transforms fit on the training fold only — fit-on-all is leakage. Checks *gate*, not just report. |
| Population & eligibility | STUB (one product's rules) | BUILD (reusable rule set) | **P1 (seam) / P2 (engine)** | The main lift when fanning out across products; do not try to generalise from one product. |
| Promotion / sign-off gate | MIN (informal review of the card) | BUILD (governed) | **P1** | Exists as a *named seam* now so governance bolts on later without re-plumbing. |
| Model card / documentation | STUB (template with product values) | BUILD (config + lineage + results bound) | **P2** | This is the "substantiation next to results" artifact, not docs-for-docs. |
| Feature intake (candidate features) | MIN (manual curated list) | BUILD (metadata-filtered; assisted later) | **P2** | Manual restriction is the correct first regime. Full-universe intake is a distinct capability with an external metadata dependency. |
| Feature checks — redundancy | MIN (correlation/VIF drop) | MIN → BUILD | **P2** | Cheap; mainly aids interpretability and card stability, not correctness. |

---

## ML engineering — components, depth, priority

| Component | First product | Eventually | Priority | Note |
|---|---|---|---|---|
| Score / outcome logging | BUILD (log score + config-hash + feature-snapshot) | BUILD (+ realised-label join) | **P0** | Near-free now, impossible to retrofit. The triplet is what makes a prediction reproducible and what performance monitoring later joins against. |
| Clean run-harness (config-in, artifacts-out, callable) | BUILD | BUILD | **P1** | Built as delivery work; doubles as the execution surface the assisted-modelling loop later calls. The single most leveraged MLE deliverable. |
| Model registry / versioning | BUILD (log model + params + metrics + config-hash) | BUILD (governed promotion stages) | **P1** | Near-free given existing tooling; the spine everything else hangs off. |
| Batch inference | STUB/MIN (product scoring, terminal- or cron-runnable) | BUILD (multi-model, parametrised) | **P2** | "Runs cleanly on demand" ≠ "deployed and scheduled." Former is early; latter is gated on the tooling decision. |
| Data-drift monitoring | STUB (hooks + baseline stats captured) | BUILD (alerting) | **P2** | Input drift is measurable immediately; design the hook early. |
| Orchestration / scheduling | STUB (manual/triggered) | BUILD | **P3** | Deferred pending the orchestration-tooling decision; must be taken by end of the templating phase. |
| Retrain / refresh | Policy recorded, not built | BUILD (triggered/scheduled) | **P3** | The *policy* (what triggers a retrain) is a cheap decision to record now; the machinery follows. |
| Performance monitoring | — (label-gated; cannot exist yet) | BUILD (metric-vs-label once labels mature) | **P3** | Propensity outcomes mature over time — there is nothing to measure against at first. Absence here is correct, not a gap. |
| Retirement | — | BUILD (governed) | **P3** | Documented process later. |

---

## Cross-cutting correctness invariants

These hold regardless of a component's depth. They are the actual governance content — the rules that keep an automated pipeline from producing confident, wrong results. Priority **P0** across the board.

1. **Time separation (point-in-time correctness)** — features as-of a date, label strictly after; enforced at the contract boundary so a leaking join fails rather than trains.
2. **Selection inside the evaluation loop** — leakage and relevance screening run inside cross-validation folds, never as a pre-step on the full dataset.
3. **Fit on training data only** — any fitted transform (imputation values, encoders, scalers) is fit on the training fold, never the full set.
4. **The checks wrap the engine from outside** — the modelling engine receives a pre-vetted, cap-applied feature set and does not see the raw feature universe; the out-of-time evaluation is run externally, not delegated to whatever the engine did internally. The engine does not grade its own homework.
5. **Leakage screen flags, never auto-drops** — a legitimately strong feature and a leaking one look identical to the screen; a human decides.
6. **Baseline and metric declared before results** — the benchmark-to-beat and the promotion metric are fixed before any result is seen.

---

## Sequencing dependencies (non-obvious)

- The **configuration spine** blocks everything — it is built first.
- The **evaluation protocol** must be decided *before* any relevance/selection work, because selection has to run inside the evaluation split. Deciding it late means rebuilding selection.
- The **assisted-modelling branch** may only start once the pipeline is a clean config-in/artifacts-out job with the correctness checks enforced around the engine and the integrability check green. Until then the branch is design/scaffold only.
