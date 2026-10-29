# LLM-assisted modelling
**Status:** designing (Phase 3, D-021) · **Legacy:** none
**Related:** [run modes](run_modes.md) (experiment sweeps) · [dataset](dataset.md) (window ablation) ·
[config](config.md) · [target factory](target_factory.md) (config mode) · [feature checks](feature_checks.md)
(the human gate) · D-017, D-021, D-031, D-083 · OD-19

## Purpose
The assisted-modelling sponsor's branch: an LLM loop that drafts configs from a business intake and
explores a **bounded** axis (initially the target/observation window) through the existing pipeline.
It reads the pipeline's own evaluation output, and a human inspects every step. It drives the
pipeline; it never replaces its checks. No LLM is used in the first release (D-021); the CDS is keen
on this branch for Phase 3.

## Phase 2 requirements (design only, no build)
1. The framework's config + CLI/API must be drivable by a program. Config validation catches malformed
   or unsafe requests.
2. Phase 2 builds the things the loop will call anyway:
   - experiment sweeps (one config field varied, compared on a fixed validation set:
     [dataset](dataset.md));
   - the Target Factory's config mode (targets built straight from the spec, without a saved table).
3. Iterating over feature aggregations is a later axis, so its spec shape is kept in mind only
   (OD-19).
4. Provider-agnostic interface. The bank will call Claude via API or Bedrock with limited tokens and
   older models, so prompts must be small and structured, and outputs validated against the config
   schema.
5. Gate: the loop starts only when the pipeline is a clean config-in / artifacts-out job, with the
   invariants enforced and tests green. It picks variants the way every sweep does: on train and
   test metrics, never on the validation period (D-083).

## Design constraints
- Nothing in the core package depends on an LLM.
- An LLM never passes a check or a human gate; in particular, a person signs off every feature
  (D-031).
- Early automation on a bounded axis only. An automated search won't get suspicious of a leaking
  feature the way a person would.

## Open questions
- Which models and token budgets are available internally (the user will confirm at build time).
