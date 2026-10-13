# LLM-assisted modelling
**Status:** designing (deferred until after internalisation) · **Legacy:** none
**Related:** [run modes](run_modes.md) (experiment sweeps) · [dataset](dataset.md) (window ablation) ·
[config](config.md) · [target factory](target_factory.md) (config mode) · D-017, D-053 · OD-19

## Purpose
The assisted-modelling sponsor's branch: an LLM loop that drafts configs from a business intake and
explores a **bounded** axis (initially the target/observation window) through the existing pipeline.
It reads the pipeline's own evaluation output, and a human inspects every step. It drives the
pipeline; it never replaces its checks.

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
   invariants enforced and tests green. Before it picks variants, a selection month must exist:
   choose on one out-of-time month, report on a later one (D-053).

## Design constraints
- Nothing in the core package depends on an LLM.
- Early automation on a bounded axis only. An automated search won't get suspicious of a leaking
  feature the way a person would.

## Open questions
- Which models and token budgets are available internally (the user will confirm at build time).
