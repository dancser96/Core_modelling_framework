# Core Modelling Framework — Initial Roadmap (Draft v0)

*Status: first-iteration proposal for alignment. Timelines are indicative ranges, not commitments. The intent is to agree direction and sequencing before any date is firmed up.*

---

## 1. Purpose and framing

This initiative has two sponsoring priorities that, on the surface, pull in different directions:

- **Retail model delivery** — a deployed propensity model for each of the nine retail products, as quickly as is responsibly possible: FX Activation, FX Reactivation, Credit Cards, Current Account, Savings Account, Fixed Deposits, Personal Loans, Home Loans, Auto Loans.
- **Assisted (LLM) modelling** — a demonstrable LLM-driven modelling loop, running and visible early, explicitly **not** in production.

The plan does not treat these as two parallel projects. It treats retail model delivery as the **backbone**, and the LLM capability as a **branch that grows off the backbone once the backbone is stable enough to support it safely**. This is deliberate: the only way to deliver nine models with the available capacity is to build the first product as a reusable template and produce the rest as configuration on top of it. That templating mechanism *is* the framework, and it is also the surface the LLM loop later drives. One backbone serves both sponsors.

The organising principle throughout: **build the mechanism once, correctly; fill it with one product; then extend by configuration, not by rewriting.**

---

## 2. The build skeleton (spine)

Every product — and later, every assisted-modelling experiment — runs through the same ordered sequence. This order is the invariant; the pieces behind each step start hardcoded to the first product and are generalised only when a later product proves the abstraction is needed.

1. **Feature/target contract** — an enforced agreement on the input features and the label, including the strict time-separation rule between them (features as-of a date; label measured only in the window after that date). This is the primary defence against leakage and it is checked at the boundary, not left to discipline.
2. **Population & eligibility** — who is in scope for this product and who is excluded.
3. **Feature checks** — correctness screening (leakage, redundancy) and relevance selection, performed inside the evaluation loop so that reported results are not optimistic.
4. **Model production** — the automated modelling engine, wired in as one named, swappable option behind a stable interface (so that a hand-built model can be added later as an alternative without re-architecting).
5. **Out-of-time evaluation** — the model is judged on a later time period than it was trained on, against a declared baseline and a metric agreed before results are seen.
6. **Model card** — a generated record binding configuration, data lineage, and results into one hand-over artifact.
7. **Batch scoring** — scored output delivered to an agreed table.

Three of these are the parts that must be *correct* from the very first product, because getting them wrong makes every downstream number untrustworthy: the **feature/target contract**, the **feature checks done inside the evaluation loop**, and the **out-of-time evaluation**. The rest can be minimal and product-specific at first.

---

## 3. Integrability — how the parts stay reusable under delivery pressure

Modularity that is only *aspired to* does not survive a deadline. It has to be *enforced*. The plan holds the whole system together with three stable agreements that every workstream must consume:

- a single agreed shape for the **configuration** that drives a run,
- a single **component interface** by which interchangeable parts (modelling engine, population logic, feature selectors, evaluation scheme) are referenced by name rather than written inline,
- a single agreed shape for the **model card / hand-over artifact**.

These three are checked automatically. Any workstream — retail models, the LLM branch, the scoring/deployment path, or the platform demo surface — must pass that check to be accepted. If a piece of work does not consume the shared agreements, it does not integrate, and this is caught mechanically rather than discovered late.

This same mechanism is what keeps the modelling engine swappable: because it is referenced as one named option from the start, adding a hand-built alternative later is a configuration change, not a redesign. It is also what lets the platform demo work stay loosely coupled where it should be and integrate cleanly where it must.

A deliberate deferral: the choice of overarching orchestration/pipelining tooling, and the target environment a model is *deployed* into, are **not** settled in this plan. The unit of work is a model run that executes cleanly and reproducibly on its own, with full provenance logged. Whether and how that run is later wrapped and scheduled is a downstream decision that does not block delivery. Note the distinction the plan maintains throughout: **"runs reliably and reproducibly on demand"** is not the same as **"deployed and scheduled in a target environment"** — the former is in scope early; the latter is sequenced later and depends on the tooling decision.

---

## 4. Phases (delivery milestones)

Phases are milestones, not fixed-length sprints. Lengths differ by what each milestone actually requires. Ranges are indicative.

### Phase 0 — First product, end to end (indicative: ~5–7 weeks)

**Milestone:** one retail product (FX Activation) delivered through the full spine — scored output in an agreed table, a model card, and a one-time out-of-time sign-off — with performance at parity with a competent bespoke build.

**What gets done:**
- The full spine runs for one product as a clean, reproducible, command-line-runnable job with provenance logged.
- The three correctness-critical parts are built properly: the feature/target contract with its time-separation rule; feature checks inside the evaluation loop; out-of-time evaluation against a declared baseline.
- The three shared agreements (configuration shape, component interface, card shape) are established in their first version.
- The automated modelling engine is wired in as the single named modelling option behind the swappable interface.
- Everything else in the spine is intentionally product-specific and minimal, behind clean interfaces, to be generalised only when later products justify it.

**Why this first:** this product is the template. Every hour spent here is repaid across the remaining products. Until it is right, extending would only multiply mistakes.

### Phase 1 — Prove it templates (indicative: ~5–7 weeks)

**Milestone:** two to three further products delivered, produced predominantly through configuration rather than new code — demonstrating that a new product can be stood up quickly and consistently.

**What gets done:**
- FX Reactivation plus one or two topology-clean products (an account/deposit product) delivered end to end.
- Population/eligibility logic and target-window definition move from hardcoded to configuration-driven values.
- The shared agreements are hardened against a second and third product; wherever the first product's assumptions leaked into the "reusable" parts, those seams are corrected now — while the cost of correction is small.
- The integrability check now runs across several products at once.

**Why this matters:** the honest test of a framework is whether the *second* product is dramatically cheaper than the first. If it is not, the abstraction is wrong, and this is the point to find out and fix it — at three products, not at nine.

### Phase 2 — Fan-out, and the assisted-modelling branch begins (indicative: ~8 weeks)

**Milestone (delivery):** the remaining products progressed through the pipeline, sequenced by data readiness. Topology-clean products delivered; the more complex products (notably the loan products, whose eligibility and target definitions diverge most) progressed as far as their underlying data readiness allows.

**Milestone (assisted modelling):** a visible, inspectable LLM loop running on one already-working product — **not in production**. Delivered in two steps:
- **First step:** an LLM drafts a run configuration from a business intake; the human reviews it; the pipeline runs it. The configuration is validated automatically, so a malformed or unsafe request cannot silently proceed.
- **Second step:** an LLM outer loop proposes variations along a *bounded* axis (initially the target/observation window), runs each through the existing pipeline, reads the pipeline's own evaluation output, and selects the best — with every step open to human inspection.

**Why the branch starts only here:** the LLM loop drives the pipeline; it can only be allowed to do so once the pipeline is stable, reproducible, and enforcing its own correctness checks. Starting the loop on a bounded, safe axis (rather than open-ended feature generation) is what keeps early automation from producing confident-but-wrong models. The prerequisites for starting are concrete: the run is a clean configuration-in, artifacts-out job; the correctness checks are enforced around the modelling engine rather than delegated to it; and the integrability check is green.

### Phase 3 — Reproducible across the set, and lifecycle hardening (indicative: ~6–8 weeks)

**Milestone:** a reproducible way to stand up a new product's model with enough governance to trust the result, plus the operational groundwork that makes delivered models maintainable.

**What gets done:**
- Remaining products brought to a consistent, reproducible state.
- Input-drift monitoring in place; performance monitoring designed but necessarily deferred, since propensity outcomes only mature over time and cannot be measured immediately.
- Score-and-outcome logging matured so that models can later be evaluated against realised results.
- Retraining and retirement handled as agreed policy, recorded now, with the machinery to follow.
- The assisted-modelling loop extended to reason over more of the lifecycle (within hard limits, human-gated, still not in production).
- The shared agreements consolidated to a stable version.

---

## 5. Responsibilities across phases

Roles are deliberately arranged so that no one is idle waiting on another workstream — in particular, the engineering work that unlocks the assisted-modelling branch is the same work needed for delivery, so it is never "waiting."

| Lane | Phase 0 | Phase 1 | Phase 2 | Phase 3 |
|---|---|---|---|---|
| **Data science (lead + additional DS resource)** | Build the first product's spine; get the three correctness-critical parts right; establish shared agreements. Lead carries correctness quality and transfers the pattern by pairing. | Prove templating on 2–3 products; move eligibility and target-window to configuration; correct the seams that break under a second product. | Fan-out under review; author the assisted-modelling loop's first and second steps on one product. | Bring the full set to reproducible state; extend the loop across more of the lifecycle; consolidate the shared agreements. |
| **ML engineering (part-time)** | Build the provenance/logging harness and a minimal on-demand batch run; register models and their parameters/metrics. | Parametrised multi-product batch running; the clean run-harness that the LLM loop will later call is built here as delivery work. | Wire the loop's execution surface (the same run-harness); take ownership of reining in the platform workstream's integration. | Scheduling/deployment path; drift alerting; retraining triggers. |
| **Platform workstream** | Self-contained, off the critical path: a fast feature-promotion / searchable-feature demo surface, reading shared artifacts only. | Feature-promotion demo matured into an early visible demonstration; boundary policed by ML engineering. | Front-end/orchestration surface for the assisted-modelling loop, integrated under ML-engineering supervision and passing the integrability check. | Demo hardening; conversational feature/configuration surface. |
| **Data engineering** | First product's features and target materialised to the contract, with the time-separation boundary enforced. | Account/deposit features and targets; feature availability/timing metadata captured. | Loan products' targets and eligibility (the most likely bottleneck); retail feature build-out. | Metadata completeness; feature source reaching steady state. |

The efficiency at the centre of this: the engineering harness built for delivery in Phases 0–1 is simultaneously the deployment path for the retail models **and** the execution surface the assisted-modelling loop calls in Phase 2. It is built once and serves both sponsors, so the engineering effort is never blocked behind the assisted-modelling prerequisite — it is what produces that prerequisite.

---

## 6. Breakage points and delivery risks

This section is deliberately prominent. The plan is credible only if these are stated plainly up front rather than discovered later.

**Nine products in this horizon, at this capacity, is not a safe commitment.** The realistic outcome is: the reproducible machine is delivered, the topology-clean products (the FX pair and the account/deposit products) are delivered solidly, and the more complex products — particularly the loan products, whose eligibility and target logic diverge most — are in progress rather than complete by the end of the window. The honest target to commit to is *"a reproducible delivery mechanism, the clean products done, the complex products in flight"* — not *"nine finished models."* Committing to nine finished within the horizon carries high delivery risk and should not be offered in a first proposal.

**Upstream data readiness is the most likely thing to move the timeline, and it is largely outside this team's control.** The plan assumes at least partial feature and target readiness across all nine products. Where that assumption does not hold — most plausibly for the loan products' targets and eligibility — those products will slip regardless of how good the template is, because no amount of modelling framework compensates for a label or an eligible population that does not yet exist. This is the single dependency most able to break Phase 2 and Phase 3. It is also the area where additional resourcing would have the clearest, most immediate effect: if this risk begins to materialise, adding data-engineering capacity is the highest-leverage response, and it should be flagged early rather than absorbed silently.

**Correctness quality rests heavily on one experienced person.** The parts that are unforgiving — leakage control and out-of-time discipline — depend on experienced judgement. Additional data-science capacity contributes real throughput, but a meaningful share of that throughput is consumed by the review needed to keep quality high on exactly those unforgiving parts. The plan should not be read as having two fully independent senior modelling contributors; it has one carrying correctness, and review time is a real, budgeted cost against delivery.

**The assisted-modelling branch is gated, and the gate is a genuine dependency, not a formality.** If the branch is allowed to start before the pipeline is stable and enforcing its own checks, it will produce confident, wrong results — an automated search does not get suspicious of a leaking feature the way a person does. The sequencing that starts the loop only after the pipeline is ready, and only on a bounded axis, is a safety requirement. Pressure to demonstrate the loop earlier, or on a flashier open-ended axis, should be resisted or explicitly accepted as risk.

**"Runs reliably" and "deployed" are different, and the gap depends on an unmade tooling decision.** Delivering models that run cleanly and reproducibly on demand is in scope early. Having them deployed and scheduled in a target environment depends on the orchestration/tooling decision that this plan deliberately leaves open. That decision cannot remain open indefinitely: it does not block early delivery, but it does gate the "scheduled and deployed" end-state, and it should be taken by the end of the templating phase.

**Capacity is genuinely shared, and context-switching is a real cost.** The same small group carries retail delivery, the assisted-modelling branch, and the enabling engineering. "Both ends at once" is achievable only because the backbone is shared; it is not achievable as two fully independent efforts, and the plan should not be read as though it were.

---

## 7. Open points for this iteration

- **Per-product data readiness** is the input that would most sharpen the fan-out sequencing and the honesty of the product-count commitment. The plan currently assumes at least partial readiness across all nine and calls out the consequences if that proves untrue.
- **The first axis for the assisted-modelling loop** is proposed as the target/observation window — bounded, safe, and already a configuration value. This is a good training-wheel for the loop; it is open to change based on feedback, with the note that a more open-ended first axis raises the risk profile and moves the readiness gate.
- **The orchestration/tooling and deployment-target decision** is deferred but not indefinitely; end of the templating phase is the point at which it should be taken.
