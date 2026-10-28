# data — local data folders (gitignored)

Kedro-style numbered layers, used as a naming convention only (no Kedro dependency). The root is
`roots.data` in the environment file (`conf/local/environment.yml`, D-130); the environment adapter
builds every path under it, and code never hardcodes them.

| Folder | Holds |
|---|---|
| `01_raw` | Synthetic raw panels from `synthetic/` (outside the bank only synthetic data exists), e.g. `synthetic_dev/` (daily work) and `synthetic_canonical/` (panel parquet + `truth.json`) |
| `02_intermediate` | Cleaned / typed panels |
| `03_primary` | Unused for now: the model input carries the target, so there is no separate targets table (D-131); where labels for scored months (M4) go is set when they are built |
| `04_feature` | Per instance and data definition, `<use_case>/<entity>/<data_definition_hash>/`: the decision audit log (`decisions/<seq>.json`) and, from M2.2, the EDA and Feature Checks artifacts and the feature ledger |
| `05_model_input` | The **model input** (D-131): the saved table every stage after Target Factory reads, with its `_model_input.json`; its exact path is the environment file's source entry for `data.model_input`, e.g. `<use_case>/<entity>` |
| `06_models` | **Local tier** training runs (`<use_case>/<entity>/<run_id>/`; the bank-side layout per entity × domain is OD-06) |
| `07_model_output` | Scoring batches (`<scoring_batch_id>/…`; layout of scores vs manifests under review, OD-18) |
| `08_reporting` | HTML reports (EDA, feature checks, model performance, comparison, monitoring), model cards |

On a laptop, the environment file maps the logical source names to `01_raw/` and the model input
to `05_model_input/`. Inside the bank, the registered and production tiers (and possibly outputs)
live on HDFS; their roots come from the environment file (`roots.registered`, `roots.production`,
set when M2.4 builds them), and the layout may still change (`docs/components/lifecycle.md`).
