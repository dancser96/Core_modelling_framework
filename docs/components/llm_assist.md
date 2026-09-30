# LLM-assisted modelling
**Status:** designing (deferred until after internalisation) · **Legacy:** none

## Purpose
The assisted-modelling sponsor's branch: an LLM loop that drafts configs from a business intake and
explores a **bounded** axis (initially the target/observation window) through the existing
pipeline. It reads the pipeline's own evaluation output, and a human inspects every step. It
drives the pipeline; it never replaces its checks.

## Phase 2 requirements (design only, no build)
1. The framework's config + CLI/API must be drivable by a program: config validation catches
   malformed or unsafe requests.
2. Provider-agnostic interface. The bank will call Claude via API or Bedrock with limited tokens
   and older models, so prompts must be small and structured, and outputs validated against the
   config schema.
3. Gate: starts only when the pipeline is a clean config-in / artifacts-out job with invariants
   enforced and tests green.

## Design constraints
- Nothing in the core package depends on an LLM.
- Early automation on a bounded axis only. An automated search won't get suspicious of a leaking
  feature the way a person would.

## Open questions
- Which models and token budgets are available internally (the user will confirm at build time).
