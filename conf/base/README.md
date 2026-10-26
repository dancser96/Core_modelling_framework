# conf/base — committed configuration

The use-case configs and the examples a new use case starts from:
- `cc_acquisition.yml`: the walking skeleton's use case, card acquisition on entity A;
- `TEMPLATE.yml`: every option with a one-line when-to-use;
- `environment.example.yml`: the environment file's example with placeholder paths; copy it to
  `conf/local/environment.yml` and fill it in (`docs/components/environment.md`, D-130).

A use case is **one config file** (unless it bloats) and its decision audit log (D-006, D-043). The
config holds the intent: the entities and their logical sources, the data definition, the
candidates, the rules and the settings; the level defaults fill what it leaves out
(`docs/components/config.md`, D-129). People's keep / exclude decisions are audit-log entries the
run replays, never config content (D-125). Nothing in `conf/base/` is physical: sources are logical
names, and the physical tables, paths, Spark settings, collect budget and report theme live only
in the environment file, which is loaded beside the config and never merged into it (D-130).

Rules: every config has `schema_version` and `task`; no bank identifiers, and no entity or domain
names beyond generic placeholders; an unknown key fails loud at load; breaking changes follow
`CLAUDE.md` §2. The crunch-era schema and template live in `legacy/propensity_crunch/configs/` for
reference.
