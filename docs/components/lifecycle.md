# Lifecycle: register, promote, deploy
**Status:** designing · **Legacy:** `src/inference.py` (`promote_model`, `verify_model`, manifests) — promotion was coupled to inference in the crunch
**Related:** [inference](inference.md) · [monitoring](monitoring.md) · [reporting](reporting.md) (model card) ·
[environment](environment.md) · D-016, D-021, D-031, D-033, D-034, D-047, D-051, D-052, D-073, D-079, D-111, D-125 · OD-06, OD-08, OD-14,
OD-23, OD-27

## Purpose
The unit's new standard for keeping 50–100 live models maintainable: three tiers with explicit,
recorded transitions, and a clear view of what is registered and what is in production.

## Tiers and steps

Three tiers in order, each with the step(s) that move a model on to the next:

1. **LOCAL**: experiments; cheap, disposable.
   - `register`: one gate, the human feature sign-off (D-031). A registered model is any
     model a person has defended and wants to keep (D-033). It packs the run's slice of the
     decision audit log (the entries up to its run marker, any later validation-month entry its
     Evaluation was scored with, plus the sign-off) into one file inside
     the registered bundle, since a folder of entries can't be registered or promoted as is
     (D-125; [config](config.md#decision-audit-log-d-125)). It always writes the lossless
     plain-data model too (any other format may sit beside it), so every registered version stays
     promotable without unpickling (D-051). That copy is trusted on its family's verified round
     trip; re-scoring each model's copy is a Phase 3 wishlist question.
2. **REGISTERED**: immutable, content-hashed, versioned per model key.
   - `promote`: picks the production candidate among the registered versions (D-033); the approved
     PR is the sign-off. Builds a verified bundle (model, resolved config, the audit-log slice read
     from the registered version, card, drift reference, checksums, framework version) from the
     plain-data model, never pickle (D-051). The bundle carries the recipe (`recipe_hash`,
     D-052), so production can retrain from it.
   - `deploy`: the change-request process moves the promoted bundle to production paths and
     records it. By default production then retrains the recipe on the same data definition
     (neither more clients nor a longer window) before it scores; deploying the fitted model
     without a retrain is also allowed (D-033, D-052). A Phase 2 production retrain keeps the
     window and the clients; only the inference month moves, since inference always runs on the
     latest month (D-052, D-088). Before it scores, it passes the **production retrain check**
     against its evaluated parent: label-free agreement on the inference month; its own test-split
     AUC and calibration per window month; per-month rows and positive events against the parent's
     EDA artifact; each within tolerances declared in the config, never on the validation month.
     Failing keeps whatever production model is current and is recorded; at a first deploy the
     deploy fails loud (D-052).
3. **PRODUCTION**: one version per model key in Phase 2 (D-111); shadow challengers are on the
   Phase 3 wishlist.

- **A DS session never writes to production.** Production changes go through change requests (CR),
  which need pre-agreed windows and platform and security approval (how long they take: see
  [environment](../context/environment.md) → Change requests). `deploy` is the framework command
  the CR process runs; it verifies checksums before copying. The first CR (release 1.0) carries
  only the framework; a model's first deploy inside the bank is a later, quicker CR (D-021).
- **Production paths are separate from the sandpit** (D-033, D-051). The sandpit is the local and
  registered (HDFS) tiers; anything saved there may be in any format, pickle included. What moves
  from the sandpit to production is never pickle. The folder layout per entity × domain is OD-06.
- **Sign-offs, kept apart:** the **feature sign-off** (D-031) gates `register` and is
  recorded with the run; the **promotion sign-off** is the approved PR (code review by the project
  owner/lead) behind `promote`; the CR process approves and runs `deploy`. Phase 2 builds no log
  of who signs off or approves a model: the PR and CR approvals stay in the PR and the change
  request, outside the framework. Which source of people logs the framework should build in is a
  Phase 3 wishlist question (D-033). The feature sign-off stays an audit-log entry that `register`
  checks (D-031, D-125).
- **Model key** = (entity, domain, use case, split). split = `all` in Phase 2; it is reserved for
  per-segment models later.

## Phase 2 requirements
1. register, promote and deploy are separate commands with recorded outcomes. None of them happens as
   a side effect of inference.
2. Registered models are immutable. A retrain in the sandpit is a new version of the same model
   key. A production retrain links to its evaluated parent run by `parent_run_id` (D-052); what it
   records in the registry is open (OD-27).
3. **Integrity:** every load verifies the content hash.
4. **Visibility: two tables people can query.**
   - Registered models: run id, model key, version, code version (framework version + use-case repo
     commit), status, path, dates, headline metrics.
   - Production models: the same, for deployed versions only.

   Both are derived from append-only registry events (registered, promoted, deployed, retired,
   rolled back), each carrying a UUID, model key, version, hashes and framework version. A small
   `production.json` per model key, at a path the adapter resolves, is the one record every
   pinned framework version reads to find the production model (D-111). Metrics are stored as long
   rows keyed by metric name (D-016). MLflow integration in Phase 2 is the goal (D-111, OD-08):
   M2.4 writes these own records so that each maps one-to-one onto an MLflow concept (run,
   parameters, metrics, registered model version), and MLflow goes in with the other integrations
   in M4 once the platform / MLOps team confirms it is available. For the whole of major version 1,
   `production.json` stays the pointer every pinned version reads; MLflow is a store added beside
   the own records, never a replacement.
5. **Model inventory** (an overview of every model across use cases and entities) is in scope; its
   design is open (OD-14).
6. Retirement and rollback are recorded, not deleted.

## Design constraints
- Paths go through the environment adapter. The bank-side folder layout per entity × domain is
  open (OD-06); per-entity storage permissions are the platform's (D-079).
- Registry records are versioned artifacts (`CLAUDE.md` §2).

## Lessons from the crunch
Promote-on-inference coupling; hash verification; manifest reproduction; T2–T4 for HDFS handling.

## Open questions
- The lifecycle evolves as it is built; the CDS doesn't want a blank-slate redesign (D-073).
  OD-06 and OD-08 are the open pieces; D-111 sets the Phase 2 records, which MLflow joins beside
  rather than replaces. Downstream operation questions are the platform / MLOps team's
  (D-079); the SDS won't design the registry and deployment alone if they are to become the unit's
  new registry type. The proposals below are straw men. Who builds them, and when: OD-23.
- The exact CR steps (who runs what, windows, approvals) are not known in detail yet; the current
  design assumes the CR process runs the framework's `deploy` command. Confirm with the platform
  / MLOps team.
- OD-06: folder layout per entity × domain. Keep the current folder structure that emulates the
  permission barriers? Whether storage permissions differ per entity is the platform's (D-079).
- OD-08: whether MLflow is available in the bank, and when it goes in (M4, with the other
  integrations). The own records (append-only events, `production.json`, D-111) map one-to-one onto
  MLflow concepts, and `production.json` stays the pointer for the whole of major version 1.
- OD-14: model inventory design.
- OD-27: retraining in production. The shape is settled (D-052): the bundle carries the recipe,
  and production retrains it and passes the production retrain check against the parent before
  it scores (see `deploy` above); `model_hash` and `parent_run_id` identify what scored. In Phase 2 a production retrain
  on the same data definition (neither more clients nor a longer window) is the default deploy path: the
  parameters differ only because production data differs from sandpit data, and only the inference
  month moves. There is no refit command in the sandpit. Retraining on moved or extended data
  (later months, all clients, a longer window) is on the Phase 3 wishlist (D-052). Still open with the platform
  / MLOps team (M4): whether production has the data and compute to train, determinism, and what
  "deployed" then records.
- Not to solve now: the code version of a run made from uncommitted code, and which repo's PR is
  the sign-off (depends on OD-02; extension code lives in the use case's repo, D-006).
