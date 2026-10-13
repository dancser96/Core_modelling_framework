# data — local data folders (gitignored)

Kedro-style numbered layers, used as a naming convention only (no Kedro dependency):

| Folder | Holds |
|---|---|
| `01_raw` | Synthetic raw panels from `synthetic/` (outside the bank only synthetic data exists), e.g. `synthetic_canonical/` (panel parquet + `truth.json`) |
| `02_intermediate` | Cleaned / typed panels |
| `03_primary` | Targets from Target Factory (notebook mode), partitioned by source, entity and month |
| `04_feature` | Feature-level artifacts: EDA and Feature Checks outputs, the feature ledger |
| `05_model_input` | Materialised train / test / validation frames when needed |
| `06_models` | **Local tier** training runs (`<use_case>/<run_id>/`; per-entity layout open, OD-06) |
| `07_model_output` | Scoring batches (`<scoring_batch_id>/…`; layout of scores vs manifests under review, OD-18) |
| `08_reporting` | HTML reports (EDA, feature checks, model performance, comparison, monitoring), model cards |

On a laptop, `conf/local/` maps the logical source names to `01_raw/`. Inside the bank, the
registered and production tiers (and possibly outputs) live on HDFS. Their roots come from
`conf/local/`, and the layout may still change (`docs/components/lifecycle.md`). Code never hardcodes
these paths; the environment adapter resolves them.
