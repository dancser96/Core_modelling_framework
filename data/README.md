# data — local data folders (gitignored)

Kedro-style numbered layers, used as a naming convention only (no Kedro dependency). The root is
`roots.data` in the environment file (`conf/local/environment.yml`, D-130): one path, and one
entity's area. The environment adapter builds every path under it, and code never hardcodes them.

Under the root, the use case comes first and the layer second, with no entity segment (D-136): two
entities under one laptop root are kept apart by the data-definition hash (`<ddh>`, its 12-character
short form, D-088), which contains the entity. Reports live beside their artifacts.

| Path under the root | Holds |
|---|---|
| `<use_case>/04_feature/<ddh>/` | Per data definition: `decisions/` (the audit log, `<seq>.json`), `eda/`, `feature_checks/`, `ledger.parquet` and `_ledger.json` (the feature ledger) |
| `<use_case>/06_models/<run_id>/` | **Local tier** training runs (M2.3; the bank-side layout per entity × domain is OD-06) |
| `<use_case>/07_model_output/` | Scoring batches (M2.4; layout of scores vs manifests under review, OD-18) |

The inputs are the environment file's `sources`, mapped by logical name wherever they physically
are. On a laptop they sit beside the use-case folders:

| Folder | Holds |
|---|---|
| `01_raw` | Synthetic raw panels from `synthetic/` (outside the bank only synthetic data exists), e.g. `synthetic_dev/` (daily work) and `synthetic_canonical/` (panel parquet + `truth.json`) |
| `02_intermediate` | Cleaned / typed panels, when a source needs one |
| `05_model_input` | The **model input** (D-131): the saved table every stage after Target Factory reads, with its `_model_input.json`; its exact path is the environment file's source entry for `data.model_input`, since several use cases may share one table |

`03_primary` is unused: the model input carries the target, so there is no separate targets table
(D-131); where labels for scored periods (M4) go is set when they are built.

Inside the bank the inputs are Hive tables or HDFS paths, and every artifact stays on a local path
(the DS's workspace) until the M2.4 transport moves them all at once (Q487). The registered and
production tiers get their own roots (`roots.registered`, `roots.production`) with the same shape
when M2.4 builds them; the layout may still change (`docs/components/lifecycle.md`).
