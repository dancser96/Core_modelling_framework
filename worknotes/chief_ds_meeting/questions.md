# Questions for the CDS
_CDS design meeting · session 1 held 2026-10-15 · status after session 1 · draft_

**How to read this.**
- **Confirm** items are things we plan to do; we take them as agreed unless someone objects.
  **Discuss** items need an answer, or at least need raising so they stay visible.
- *Proposal:* our answer, agreed between the SDS and the LDS · ★ = ask even if time is short ·
  small grey codes = where the answer gets recorded.
- Questions answered in session 1 are in "Settled questions" at the end.

**Order:** (a) → (b) → (d) → (e) → (f). The downstream lifecycle design gets its own session
(below).

| Topic | Question |
|---|---|
| **(a) Scope** | a1. ★ In what order should task families come after the first release? *Proposal: binary → regression → multiclass → time-to-event → forecasting → nearby problems (uplift, recommendation, segmentation).* And should regulated models (e.g. credit risk) ever run through it? That would raise the bar for validation and documentation. <sub>OD-21</sub> |
| | a2. ★ The LLM component is to be part of the first release, coming in at the end. Which jobs must it do there: write model documentation in the current structure, act as the feature-check gate in automated runs, or both? What does "least interference" mean for how it plugs into the framework? <sub>D-017, llm_assist.md</sub> |
| | a3. First release: binary only, or binary plus one more task type; and FLAML AutoML only, or also a predefined model family tuned with Optuna? *Proposal: binary, possibly with regression as a second task; FLAML only.* Either way, we design regression's shapes now, so shared outputs don't assume binary; and FLAML can be limited to one model family with our own search ranges, so a predefined family stays possible. <sub>OD-15</sub> |
| **(b) Consumption** | b1. ★ Where does a use case live (a repo per use case, per domain, or something else), and how do users get the guided notebooks? *Proposal: one repo per entity × domain (2 × 3). Caveat: this needs standardised upstream data per entity and domain.* <sub>OD-02</sub> |
| **(d) Structure** | d1. ★ The feature store should be the source in all cases. For the first release: feature store only, or also show how the feature store and other sources are used together? <sub>OD-19, test_harness.md</sub> |
| | d2. ★ Do we keep the current folder structure that mirrors the permission barriers (separate parent folders per entity × domain)? Are storage permissions actually separate per entity? <sub>OD-06</sub> |
| | d3. Targets in the feature store: should Target Factory's targets be enrolled into the feature store, and how do we split that work with the feature store team? <sub>D-029, target_factory.md</sub> |
| | d4. Human gate: a person must be able to defend every feature in the model, so feature checks use low thresholds and a stage gate. In automated (hands-off) runs, may an LLM review pass that gate, or must a person always sign off before a model is registered? <sub>D-031, D-023</sub> |
| | d5. The stage structure: Target Factory (optional) → EDA → Feature Checks → Training → Evaluation → register → promote → deploy → Inference → Monitoring. Each stage runs alone from the config and writes its own report. Is anything missing, merged or in the wrong place? <sub>D-028</sub> |
| **(e) Promotion, deployment** | e1. ★ The original plan had a part-time ML engineering lane for registration, the deployment path and drift alerting. Is that capacity still there, who would it be, and when could they join? If this becomes the unit's new registry type, we don't want to design it alone. <sub>OD-23</sub> |
| **(f) Monitoring** | f1. ★ Who acts on a monitoring flag, and who owns a live model once the person who built it moves on? *Proposal: a central team monitors the live models.* <sub>monitoring.md</sub> |
| | f2. Model inventory: what should an overview of every live model show, and who uses it? <sub>OD-14</sub> |
| | f3. *Confirm:* first release: health (did scoring run, row counts, score distribution) and drift are deep; realised performance and business impact are thin, but must work as soon as outcomes arrive. <sub>D-040</sub> |
| | f4. Tooling: our view is that MLflow suits the registry and experiment tracking, not tracking decay over time. What should monitoring use, what is shown, and where do the dashboards live? Is there something in the existing data observability framework we could reuse, or should monitoring be built separately? <sub>OD-13</sub> |

## To be covered in a separate session: the downstream lifecycle, from a blank slate

> **Separate session.** We want the CDS to come up with ideas from a blank slate here. The current
> stages (register → promote → deploy) and the questions below are our starting points, not
> constraints. We may end up with something quite different.

| Topic | Starting question |
|---|---|
| **Lifecycle design** | s1. The lifecycle steps today: **register** (local → registered), **promote** (choose the version for production; the approved PR is the sign-off), **deploy** (the change-request process copies it to production). A data scientist's session never writes to production. Is this the right shape, and what should "registered" mean: any run someone wants to keep, or a gated candidate for production? <sub>D-033, OD-09</sub> |
| | s2. Versions: how many per model, exactly one in production at a time, and do we want shadow challengers (a new version scoring next to production before it takes over)? <sub>OD-07</sub> |
| | s3. Registry storage: our own append-only records with tables on top (shaped like MLflow's, so a later move is a mapping), or MLflow itself? <sub>OD-08</sub> |
| | s4. Deployment copies the model to production paths, rather than pointing production at sandpit paths. Is that right? <sub>lifecycle.md</sub> |

## Settled questions

| Topic | Question | Answer |
|---|---|---|
| **Consumption** | A versioned Python library used through guided notebooks, a CLI and a Python API, with no service. Is that the right model for the unit, rather than a central service or platform? <sub>D-024</sub> | Yes, implicitly: the package ships in the base image |
| **Consumption** | Once the code sits in an internal repo, how do use cases get it: from an internal package repository where each use case pins a version, or by git clone? *Proposal: distribution as a package through Nexus.* <sub>OD-04</sub> | The package goes into the base image, i.e. through Nexus. Images are supported for a year, so starting on an image pins the version |
| **Documentation** | Which model documentation standard should the model card follow, so documentation can be generated from it later? *Proposal: the current group model validation framework, already built into our Kedro project template.* <sub>Phase 3 backlog</sub> | The LLM writes documentation following our current documentation structure |
