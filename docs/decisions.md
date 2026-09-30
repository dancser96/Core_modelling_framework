# Decision log

Short entries, newest last. **Status:** `decided` | `soft` (expected, revisit if needed) | `superseded`.
Add a new entry rather than rewriting an old one; mark superseded entries.

| ID | Decision | Why | Status |
|---|---|---|---|
| D-001 | Plain Python package under `src/core_modelling/`; repo `retail.core_modelling` (name may change) | Installable, testable, production `.py` path; segment-neutral package name | decided |
| D-002 | **No Kedro.** The numbered data-folder convention may be kept | Avoid framework weight; the layer naming still makes sense | decided |
| D-003 | Code-light rules (`CLAUDE.md` §1) govern all code; forward compatibility (§2) is the only override | Every line is human-reviewed; the framework pushes updates to use cases | decided |
| D-004 | Crunch code kept in `legacy/propensity_crunch/` as reference, not a constraint | Keep proven logic accessible without anchoring the redesign | decided |
| D-005 | Only binary classification is built; configs, contracts and outputs are task-agnostic (`task` field, dispatch dicts) | Regression, multiclass, time-to-event and forecasting will follow | decided |
| D-006 | A use case = configs; custom code only at named extension points (mostly Data Creation) | Keeps delivery at weeks and use cases updatable | decided |
| D-007 | Every config and artifact format carries `schema_version`, with migrations + deprecation; semver for the package | Forward compatibility across use cases | decided |
| D-008 | Lifecycle tiers local → registered → production; promotion and deployment are separate steps from inference | Maintainability of 50–100 live models; the crunch coupled them | decided |
| D-009 | Baselines: population base rate for business reporting; previous-model and historic-predicted-rate baselines for internal metrics | Matches how use cases are measured now | decided |
| D-010 | Run modes: notebooks (manual) + CLI `python -m core_modelling run <config>` + Python API; service layer later | Both manual and automated use from one set of functions | decided |
| D-011 | Environment adapter + gitignored `conf/local/` hold every bank-specific detail; no bank identifiers in the repo | One-way code flow; the port is configuration, not code | decided |
| D-012 | Bank-parity pins in `requirements.txt`; compatible ranges in `pyproject.toml` | Pins for environments, ranges for package consumers | decided |
| D-013 | Dev setup: WSL2 (Windows 11) + native macOS, plain `venv` + `pip`; `ruff` + `pytest`; no pre-commit/CI yet | Simplest setup; CI/Sonar come before migration | decided |
| D-014 | Tests: light (invariants, migrations, one real local-Spark e2e) now; full coverage + CI/Sonar before migration | Build speed now, compliance later | decided |
| D-015 | Notebooks are interface only: no function definitions, no per-use-case copies; reports from frozen configs | Reproducibility and zero notebook drift | decided |
| D-016 | Scoring outputs are batch-scoped (`<outputs>/<scoring_batch_id>/{scores, manifest}`), written once per batch | Crunch lessons T6/T7 | decided |
| D-017 | LLM-assisted modelling comes after internalisation; provider-agnostic interface (Anthropic API / Bedrock), token-frugal | Limited tokens and older models inside the bank | soft |
| D-018 | Distribution (service vs forkable template repo) is undecided; the design must support both | Governance decision outside this repo | soft |
