# conf/local — environment-specific configuration (gitignored)

Everything in this folder except this README is ignored by git. Inside the bank it holds physical
table names, `hdfs://` roots for the registered/production tiers and outputs, Spark settings, and
any credentials references. On a laptop it points at local folders and synthetic data.

It is merged over `conf/base/` at load time. Nothing here ever enters the repo, and nothing inside
the bank ever leaves it.
