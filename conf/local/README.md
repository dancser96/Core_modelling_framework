# conf/local — environment-specific configuration (gitignored)

Everything in this folder except this README is ignored by git. It holds one file, the
**environment file** `environment.yml` (D-130; the example with placeholders is
`conf/base/environment.example.yml`), with its own schema:
- Spark settings;
- the roots: the data folder, and inside the bank the `hdfs://` roots of the registered and
  production tiers (per entity where the layout needs it, OD-06);
- the physical table or path of each logical source, per entity;
- the collect budget (D-133);
- the report theme file (after internalisation).

On a laptop it points the logical sources at the synthetic dataset in `data/01_raw/` and the data
root at `data/`. The framework finds it by a path argument or the `CORE_MODELLING_ENVIRONMENT`
variable, never from the working directory. It is loaded beside the use-case config, never merged
over it, and the hashes exclude it (`docs/components/environment.md`). Nothing here ever enters the
repo, and nothing inside the bank ever leaves it.
