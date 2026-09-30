# data — local data folders (gitignored)

Kedro-style numbered layers, used as a naming convention only (no Kedro dependency):

| Folder | Holds |
|---|---|
| `01_raw` | Synthetic raw monthly panels (outside the bank only synthetic data exists) |
| `02_intermediate` | Cleaned / typed panels |
| `03_primary` | Enriched panel from Data Creation (targets, rollups, eligibility flags) |
| `04_feature` | Feature-level artifacts (screening outputs) |
| `05_model_input` | Materialised training / OOT frames when needed |
| `06_models` | **Local tier** training runs (`<use_case>/<run_id>/`) |
| `07_model_output` | Scoring batches (`<scoring_batch_id>/{scores, manifest}`) |
| `08_reporting` | EDA / feature-check / evaluation reports, model cards |

Inside the bank, the registered and production tiers (and possibly outputs) live on HDFS. Their
roots come from `conf/local/`, and the layout may still change (`docs/components/lifecycle.md`).
Code never hardcodes these paths; the environment adapter resolves them.
