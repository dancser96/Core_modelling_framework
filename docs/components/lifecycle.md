# Lifecycle: register, promote, deploy
**Status:** designing · **Legacy:** `src/inference.py` (`promote_model`, `verify_model`, manifests) — promotion was coupled to inference in the crunch
**Related:** [inference](inference.md) · [monitoring](monitoring.md) · [reporting](reporting.md) (model card) ·
[environment](environment.md) · D-033, D-034, D-047, D-051, D-052, D-073, D-076, D-078, D-079, D-095, D-096 · OD-06, OD-07, OD-08, OD-14,
OD-23, OD-27

## Purpose
The unit's new standard for keeping 50–100 live models maintainable: three tiers with explicit,
recorded transitions, and a clear view of what is registered and what is in production.

## Tiers and steps

Three tiers in order, each with the step(s) that move a model on to the next:

1. **LOCAL**: experiments; cheap, disposable.
   - `register`: gates, including the human feature sign-off (D-076). A registered model is any
     model a person has defended and wants to keep (D-095).
2. **REGISTERED**: immutable, content-hashed, versioned per model key.
   - `promote`: picks the production candidate among the registered versions (D-095); the approved
     PR is the sign-off. Builds a verified bundle (model, frozen config, card, drift reference,
     checksums, framework version). The bundle carries the recipe (`recipe_hash`, D-096), so with
     retraining in production (OD-27) production runs the refit from it instead of copying the
     fitted model.
   - `deploy`: the change-request process copies the bundle to production paths and records it.
3. **PRODUCTION**: one version per model key in Phase 2 (OD-07).

- **A DS session never writes to production.** Production changes go through change requests (CR),
  which need pre-agreed windows and platform and security approval. `deploy` is the framework command
  the CR process runs; it verifies checksums before copying.
- **Production paths, not sandpit paths.** The way currently proposed inside the bank points
  production at the registered (sandpit) paths. The Lead DS's view is that the model should be moved
  to production paths, so deployment may simply be a job that copies the selected model there. To be
  confirmed with the platform / MLOps team (OD-06, OD-08).
- **Sign-offs, kept apart:** the **feature sign-off** (D-076, D-092) gates `register` and is
  recorded with the run; the **promotion sign-off** is the approved PR (code review by the project
  owner/lead) behind `promote`; the CR process approves and runs `deploy`. The PR and CR approvals
  are external in Phase 2; Phase 3 adds a sign-off log in the registry that pulls the PR approvers.
- **Model key** = (entity, domain, use case, split). split = `all` in Phase 2; it is reserved for
  per-segment models later.

## Phase 2 requirements
1. register, promote and deploy are separate commands with recorded outcomes. None of them happens as
   a side effect of inference.
2. Registered models are immutable. A retrain is a new version of the same model key, linked to the
   previous one (OD-07). A refit carries a link to its evaluated parent run (D-052).
3. **Integrity:** every load verifies the content hash.
4. **Visibility: two tables people can query.**
   - Registered models: run id, model key, version, code version (framework version + use-case repo
     commit), status, path, dates, headline metrics.
   - Production models: the same, for deployed versions only.

   Storage design: OD-08. MLflow later, if adopted (OD-13).
5. **Model inventory** (an overview of every model across use cases and entities) is in scope; its
   design is open (OD-14).
6. Retirement and rollback are recorded, not deleted.

## Design constraints
- Paths go through the environment adapter. The bank-side layout (entity × domain folders,
  permissions) is open (OD-06).
- Registry records are versioned artifacts (`CLAUDE.md` §2).

## Lessons from the crunch
Promote-on-inference coupling; hash verification; manifest reproduction; T2–T4 for HDFS handling.

## Open questions
- The lifecycle evolves as it is built; the CDS doesn't want a blank-slate redesign (D-073).
  OD-06 to OD-08 are the pieces. Downstream operation questions are the platform / MLOps team's
  (D-079); the SDS won't design the registry and deployment alone if they are to become the unit's
  new registry type. The proposals below are straw men. Who builds them, and when: OD-23.
- The exact CR steps (who runs what, windows, approvals) are not known in detail yet; the current
  design assumes the CR process runs the framework's `deploy` command. Confirm with the platform
  / MLOps team.
- OD-06: folder layout per entity × domain. Keep the current folder structure that emulates the
  permission barriers? Are storage permissions actually separate per entity?
- OD-07: model versions per key, one production version per key, shadow challengers.
- OD-08: registry storage. Proposal (not agreed):
  - append-only event records (registered, promoted, deployed, retired, rolled back) on HDFS, with
    tables on top;
  - "current production" as a view;
  - records shaped like MLflow's concepts (experiment, run, params, metrics, artifacts, registered
    model, version), so a later move is a mapping, not a redesign.
- OD-14: model inventory design.
- OD-27: retraining in production. The shape is settled (D-096): the bundle carries the recipe,
  production runs the refit (D-052) with a label-free agreement check against the parent before
  it scores; `model_hash` and `parent_run_id` identify what scored. Still open with the platform
  / MLOps team (M4): whether production has the data and compute to train, determinism, and what
  "deployed" then records.
- Not to solve now: the code version of a run made from uncommitted code, and which repo's PR is
  the sign-off (depends on OD-02; extension code lives in the use case's repo, D-090).
