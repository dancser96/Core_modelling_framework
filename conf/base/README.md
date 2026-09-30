# conf/base — committed configuration

Framework defaults and use-case configs. Values here are **generic**: logical table names,
relative layouts, modelling settings. Physical, environment-specific values (Hive tables, HDFS
roots, Spark settings) belong in `conf/local/`, which is merged on top at load time.

The config schema is being redesigned in Phase 2 (`docs/components/config.md`). The crunch-era
schema and template live in `legacy/propensity_crunch/configs/` for reference.

Rules: every config has `schema_version` and `task`; no bank identifiers; breaking changes follow
`CLAUDE.md` §2.
