# conf/local — environment-specific configuration (gitignored)

Everything in this folder except this README is ignored by git. Inside the bank it holds:
- physical table names for each logical source;
- `hdfs://` roots for the registered/production tiers and outputs (per entity where the layout needs
  it);
- Spark settings;
- the report theme file (after internalisation);
- any credentials references.

On a laptop it points the logical sources at the synthetic dataset in `data/01_raw/`, and the roots
at local folders.

It is merged over `conf/base/` at load time. Nothing here ever enters the repo, and nothing inside the
bank ever leaves it.
