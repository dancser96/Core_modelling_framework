# Lifecycle: promotion, registry, deployment
**Status:** designing · **Legacy:** `src/inference.py` (`promote_model`, `verify_model`, manifests) — promotion was coupled to inference in the crunch

## Purpose
Set the unit's new standard for keeping 50–100 live models maintainable. There are three tiers with
explicit, recorded transitions:
- **local:** experiments
- **registered:** immutable, hashed, on HDFS inside the bank
- **production:** a per-use-case pointer to one registered model

## Phase 2 requirements
1. **Promotion** (local → registered) is its own step with gates:
   - complete, valid model card
   - OOT result vs the declared baseline meets the configured bar
   - contract checks passed

   It copies the minimal reproducible bundle (model, frozen config, card) and records `model_hash`.
2. **Registry records:** a simple, versioned record per registered model (use case, `run_id`,
   `model_hash`, dates, metrics summary, status). Plain files first; no database until needed.
3. **Deployment** (registered → production) is explicit, recorded and reversible (points back to
   the previous model).
4. **Retirement** is recorded, not deleted.
5. Integrity: every load from the registry verifies the content hash.

## Design constraints
- Registered models are immutable; a new version means a new `run_id`.
- Path construction goes through the environment adapter, because the bank layout is still
  evolving.

## Lessons from the crunch
Promote-on-inference coupling; hash verification; manifest reproduction; T2–T4 for HDFS handling.

## Open questions
- The bank-side layout and naming of the registered/production tiers.
- Who can deploy (governance), and whether deployment needs a sign-off record.
