# conf/base — committed configuration

Framework defaults (including the `quick` / `standard` / `thorough` profile defaults) and use-case
configs. The goal is **one file per use case**, holding every decision. Values here are **generic**:
logical source names, relative layouts, modelling settings. Physical, environment-specific values
(Hive tables, HDFS roots, Spark settings, report theme) belong in `conf/local/`, which is merged on
top at load time.

The config schema is being redesigned in Phase 2 (`docs/components/config.md`). The template lists
every option with a one-line when-to-use. The crunch-era schema and template live in
`legacy/propensity_crunch/configs/` for reference.

Rules: every config has `schema_version` and `task`; no bank identifiers or entity/domain names
beyond generic placeholders; breaking changes follow `CLAUDE.md` §2.
