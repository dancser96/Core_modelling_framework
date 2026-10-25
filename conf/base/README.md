# conf/base — committed configuration

Framework defaults (including the `autonomous` / `assisted` level defaults) and use-case configs.
A use case is **one config file** (unless it bloats) and its decision audit log (D-006, D-043). The
config holds the intent: the candidates, the rules and the settings. People's keep / exclude
decisions are audit-log entries the run replays, never config content (D-125,
`docs/components/config.md`). Values here are **generic**: logical source names, relative layouts,
modelling settings. Physical, environment-specific values (Hive tables, HDFS roots, Spark settings,
report theme) belong in `conf/local/`, which is merged on top at load time.

The config schema is being redesigned in Phase 2 (`docs/components/config.md`). The template lists
every option with a one-line when-to-use. The crunch-era schema and template live in
`legacy/propensity_crunch/configs/` for reference.

Rules: every config has `schema_version` and `task`; no bank identifiers or entity/domain names
beyond generic placeholders; breaking changes follow `CLAUDE.md` §2.
