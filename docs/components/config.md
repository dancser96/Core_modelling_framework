# Config spine
**Status:** legacy-only · **Legacy:** `configs/_schema.py`, `configs/_TEMPLATE.yaml`

## Purpose
The whole definition of a use case, validated at load. This is the framework's most important
contract with its users, and the thing central updates must never break.

## Phase 2 requirements
1. Every config has `schema_version` and `task` (`binary` implemented; others defined but not
   implemented).
2. Load = `conf/base` → `conf/local` merge → Pydantic v2 validation → **frozen config** saved with
   every artifact.
3. Sections per stage (data, eligibility, eda, feature_checks, training, evaluation, lifecycle,
   inference, tracking), each usable alone.
4. **Stepwise sections:** ordered, named filter/selection steps (eligibility, feature screening),
   each producing a log entry (rows/cols in → out, reason).
5. Two feature views: `candidates` for exploration, and `features` = candidates − exclusions for
   modelling.
6. Temporal validation at load:
   - obs < oot < inference
   - the OOT gap is at least the target window
7. Metric and baselines are declared up front. Metric names are validated against the engine's
   names (T9).
8. Metric slices: `top_pct` and `top_n` lists; either may be empty.
9. Migrations: small functions `migrate_vN_to_vN+1(dict) -> dict`, applied automatically with a
   deprecation warning.

## Design constraints
- No bank identifiers; physical names only in `conf/local/`.
- Pydantic models stay flat and readable. No clever validators; one validator per rule, with a
  clear message.
- Adding optional fields with defaults is non-breaking. Renaming or removing fields is breaking
  (`CLAUDE.md` §2).

## Lessons from the crunch
T9, T13. The two feature views and the validated temporal ordering were the crunch's best ideas.

## Interface
*(fill when built)*

## Open questions
- Exact section layout, and how a use-case extension function is referenced by name.
- The detailed design for stepwise configs is pending more input from the user.
