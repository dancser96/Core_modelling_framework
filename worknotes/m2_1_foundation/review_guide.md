# Stage 1 (M2.1 Foundation): review guide
_For the SDS (D-072 (i): the LDS reads the design and the functions the sync page names, and
tries the notebook) · one continuous guide to Stage 1 as it stands · the design is D-129–D-133
in `docs/decisions.md` and the owner docs named below; the build's trail is
`worknotes/log.md` · this guide stands alone: the stage's questions, plan and specs were
deleted on 10-29, their outcomes being in `docs/`_

**Status.** Built end to end and reviewed by the SDS three times (10-26 the config spine and
the environment adapter; 10-27 Target Factory; 10-28 Target Factory and the dataset together,
then the second round whose answers became the addendum, built the same day; 10-29 questions
answered, two changes made, the second example use case added). Every remark is applied.
What remains for Stage 1: the LDS's read of the data code and the deletion of this folder at
sign-off. Version 0.2.0 is Stage 1's label until then.

**What Stage 1 is.** One config file per use case, validated at load with the automation
level's defaults, hashed (D-088) and frozen in its data part once the model input is saved
(D-125); the environment adapter (the Spark session, the sources, the paths); Target Factory,
which labels every unit-period it can from the target source; the dataset, which joins the
sources into one panel, saves it as the model input and, on read, applies a config's
eligibility, candidates, contract checks and client split to give each stage its frames; the
decision audit log, which records every later decision as an entry and replays them into the
resolved config; `run` and the CLI; the Target Factory notebook.

## Read in this order
Docs first, then the configs, then the tests (they say what the code promises), then the code.
1. [Explanations](#explanations) at the end of this guide: why the split is a hash, and why
   it can be trusted on structured client ids.
2. `notebooks/01_target_factory.ipynb`, run on the dev data: two use cases, `cc_acquisition`
   and `td_acquisition`, saved as one model input and read back each with its own config.
   It is the shortest way to see what the code below does.
3. `docs/components/config.md`: the layout (`data.keys` with `period`, `time` with `period`,
   `observation_window`, `target_window`, `validation_period`), the load, the identities, the
   audit log with `revert`, the level mapping. What "right" looks like: every field of
   `conf/base/cc_acquisition.yml` is explained there; nothing in the doc describes code that
   doesn't exist without saying "planned".
4. `docs/components/target_factory.md` → Interface, then `docs/components/dataset.md` → Purpose,
   Time model, Frames, Sources and joins, Model input, requirements 1, 3, 6, 8 and 9, Interface.
   What "right" looks like: every refusal and every printout named there exists.
5. `docs/components/environment.md`: the environment file and the public session function.
6. `conf/base/cc_acquisition.yml` (the two eligibility lists, `flag_goes_up`, `model_input`,
   `period: month`), then `conf/base/TEMPLATE.yml` for the when-to-use of each option and the
   reading key (how a comment is placed). Readable as a DS's first contact with the framework.
7. `src/core_modelling/periods.py`: the one dict. Per period (month, week, day): the index
   (consecutive periods are consecutive integers), its inverse, the start and the end, the same
   in Spark, the label and the typo rule. Everything else that steps or compares periods goes
   through it; nothing adds months or days.
8. `src/core_modelling/config/schema.py`: flat models, one validator per rule; `Time` moves the
   three dates to their period's end and checks `v ≥ tk + w` by index. Then
   `config/identities.py` and `tests/test_identities.py`: what changes which hash (D-088).
9. `src/core_modelling/sources.py`: one reader for every source (keys renamed to `unit_id` as a
   string and `period` at the period's end, the refusals, the duplicate-key check after the
   move) and the one coverage check the spine and the target source go through.
10. `src/core_modelling/tasks.py` (one dict by task, D-050: the two rules, the two column checks,
    the summary, the contract checks), then `src/core_modelling/target_factory.py`:
    `build_targets` (the forward window over the period index, the one place §4.1 lives;
    `null_in_window` null where the window is incomplete), the checks `load_targets` runs before
    building, `run_target_factory`.
11. `src/core_modelling/dataset/panel.py`, top down: `load_panel` for a list of configs (the
    shared-definition check, the sources joined once, each config's target joined as
    `target_<use_case>`, the one rollup behind the join log and the null shares), then
    `prepare_panel` (the read side: the own target kept, the other use cases' targets and
    upstream columns dropped, eligibility, candidates, contract, split) and `build_panel`
    (the in-memory one-config path). Then `dataset/eligibility.py`: `apply_eligibility` (the
    two lists as one order; `_condition` resolves a step's SQL against the sources' columns
    and earlier defines only) and `resolve_candidates`.
12. `src/core_modelling/dataset/split.py` (one hash draw in [0, 1), salted, T20), `contract.py`
    (the shared checks and the null callout, fed by the saved share, around the task's),
    `frames.py` (`build_frames` top down: the window for EDA, its eligible rows for Feature
    Checks, the modelling frames; `collect_frame`), `model_input.py` (`save_model_input` for one
    config or a list, the sidecar at schema 3, `read_model_input_metadata`'s refusal order,
    `read_model_input` returning the prepared panel, `saved_candidates` without Spark).
13. `src/core_modelling/config/replay.py` and `audit_log.py`: the entry model, `replay` with
    `revert` restarting from the slice, `resolve_config(upto=…)`, `record_decision`,
    `show_decisions`; the worked example in `tests/test_audit_log.py`.
14. `src/core_modelling/run.py` and `__main__.py` (parsing only; `run` takes one or several
    config paths), then `notebooks/01_target_factory.ipynb`: thin, the guide cell written as
    instructions.
15. The tests, in this order: `tests/test_config_schema.py` (one test per rule; a failing
    config's message says how to fix it), `test_sources.py` (the id cast, the week and day
    moves, the index round trips), `test_target_factory.py` (the six monthly series side by
    side, the weekly and daily windows, then the oracle), `test_dataset.py` (the join for two
    configs, every eligibility rule, the other use case's target never a candidate),
    `test_split.py` (T20 is `test_client_sample_keeps_whole_clients_whatever_the_split_seed`),
    `test_contract.py`, `test_frames.py` (end to end on the unit preset: the window, the
    eligible window, the modelling frames, the model input round trip for two configs, what is
    refused and what is not), `test_run.py`, `test_audit_log.py` (the revert example).
16. `synthetic/src/synthetic/output.py::_holdings_frame`: the holdings tag the last day, the mart
    the first, so every run converts one of them (0.5.2).

## What "right" looks like
The config and the identities:
- Every field has one owner model and one validator per rule; an unknown or retired key
  (`train_months`, `keys.month`) fails naming it; the level fills the `null` fields.
- A month is written as its first or its last day, a week as any of its days, a day as itself;
  all three dates are held as the period's end; the validation period is at least w periods
  after the window's last, counted by the period index.
- The data-definition hash covers what EDA depends on (entity, sources, keys, eligibility,
  target, period, window, w, candidates); the target-spec hash what one label column depends on;
  the golden digests pin both.

Target Factory:
- The rule compares the observation period with the forward periods t+1 … t+w by period index,
  on month, week or day data alike: 1 when some forward flag exceeds the flag at t, else 0. A
  holder at t gets 0; who is in the population is eligibility's business, never the rule's.
- A missing forward row (a leaver, a gap) gives a null target; a null value follows SQL: never
  an event; the target is null only when nothing can be compared. `null_in_window` is null
  where the window is incomplete, so its average is the share among complete windows, shown in
  the summary and stored per use case in the model input's sidecar for the contract's callout.
- Every row of the source gets its label wherever the forward window is complete: the gap
  periods and the periods after the validation period included. The summary shows label rates
  for the observation window only.
- The built targets equal the oracle's on every non-holder row of the `unit` preset, nulls
  included.
- A source tagged on the first day and one tagged on the last key alike; an integer id reads
  back as a string; a bad period, key, column type or value, a duplicate key, a short source
  and an upstream target with values in its last w periods all fail loud, naming the source.
- A source column named like one the framework adds is never refused: a non-key `unit_id` or
  `period` is read as `source_<name>` at the reader; on the read side the use case's own
  upstream target column is dropped (its values are `target`'s, so `data.target.column:
  target` works and no eligibility condition can name the label), and any other `target`,
  `split` or `eligible` column is read as `source_<name>`, printed and logged; a built
  target's own column stays excluded under its read name.

The dataset:
- The saved model input is the sources joined plus one target column per use case, nothing
  else; a single config is the one-element list. A reader keeps its own target as `target` and
  drops the others; another use case's target is never a candidate, even with `include: ["*"]`.
- Configs sharing a table declare the same feature sources, keys, model input and period, else
  the two use cases and the field are named; a target column that collides with a source column
  fails at save.
- A reader is refused, naming `save_model_input`, on another schema or hash version, other
  sources, keys or period, a use case the table lacks, another target spec, periods that
  don't cover its window and validation period, or a validation period whose target window
  outruns the saved target source. A changed eligibility, window, split or candidate list is
  not refused: the new frames are derived on read. A joined feature source that matches no
  spine row fails naming both id types.
- Eligibility is two ordered lists run as one order, analysis first: an analysis filter drops
  rows before EDA; a modelling filter keeps them, tagged 0/1 by its name, and `eligible` is the
  AND of the tags. A define in either list serves the steps after it. A condition that names
  the target, a key, the split, `eligible` or another filter's tag, or a non-deterministic
  function, fails naming the step; a null condition counts as false.
- The window frame (EDA) holds every client of the window after the analysis filters, the
  holders present with `non_holders = 0` and `eligible = 0`; Feature Checks' frame is its
  eligible rows; the lineage column `cc_flag` is gone; the tag and the helper columns are not
  candidates.
- The modelling frames hold eligible rows with a known target only, from the window and the
  validation period; no client is in both train and test; every frame has the same columns.
- The log's order is the invariants' order: join, eligibility (analysis then modelling),
  contract (on the eligible window before the split and any sampling), null-target, sampling
  (only when declared), collect.
- The frames read from the saved model input equal the frames built in memory.
- The split and the sample are two independent hash draws: a client is in test when its draw is
  below `test_share`; a sample keeps the rows or clients whose draw is below the fraction asked,
  whatever the split seed. The draw on structured ids is as uniform as a random number's
  ([Explanations](#explanations)).
- The collect printout appears on every collect; above the budget it becomes the callout and the
  collect still proceeds.

The audit log:
- Entries are independent and append-only; a later entry supersedes only what it names;
  `resolve_config(upto=n)` reproduces the state after entry n. A `revert` restarts the state
  from the config with entries 1 … `to_seq` and continues after it; the undone entries stay as
  the trail; a revert to the current state, or to a later entry, is refused.
- A feature decision checks its names against the saved model input's candidates, resolved
  from the sidecar without Spark.

`run`, the CLI and the notebook:
- `run` and the CLI only call the stage functions; several config paths save one model input
  with one target column per use case; the notebook imports the Public API only.

## What the reviews changed
Every major step and the addendum were reviewed by fresh-context reviewers (code review,
silent-failure audit, compatibility review, ML audit at the highest effort) before the SDS saw
them; every finding was fixed on the main thread and re-tested. The full lists are in
`worknotes/log.md` (10-26, 10-27, 10-28). What matters for a reader of the code:
- **The addendum (10-28):** four reviews on the merged state (code review, silent-failure
  audit, compatibility review, ML audit at the highest effort): no invariant violated, no
  blocking code finding. Taken: `task` in both hashes (an upstream column read as binary
  and as regression no longer shares a hash); a feature source that matches no spine row is
  refused naming both raw id types (was printed; the string cast would turn a type mismatch
  into an all-null feature block); a source column named like a key or a helper column
  (`target`, `split`, `eligible`) was refused at read, a rename since 10-29; a reader whose
  validation period plus
  target window outruns the saved target source is refused (the sidecar records
  `target_last`); another use case's upstream target column is dropped on read like its
  `target_` column; the audit log's `include` is judged over the effective entries, so a
  `revert` or a no-op person's exclude cannot launder a rule's exclude; `save_model_input([])`
  and `run([])` refused, and `run` refuses configs whose entity lists differ; the null
  callout names its population (target-source rows in the window with a complete target
  window, before eligibility); eligibility moved to its own module and the join's 4-tuples
  became a small frozen dataclass; one `label_by_period` helper behind every per-period
  dict; weekly end-to-end frames and the second config's own window tested. Justified, not
  taken: a monthly config over a source tagged on other days is logged, not refused (the
  duplicate-key check after the move catches a finer source; the framework doesn't police);
  the target source read twice by `run` (the summary before the save; one comment).
- **The 10-28 remarks:** the model input's sidecar refuses an older schema by name, naming the
  framework version when it differs; the modelling rows restrict themselves to the window and
  the validation period, so the labels the panel carries elsewhere cannot reach a fit by
  accident; a non-deterministic function is refused in eligibility SQL; the upstream tail check
  finds the period before the tail by index; the pinned hash draw and the boundary agreement
  test; a labelled gap-period row in the contract test.
- **Step 3 (10-27):** the model input's folder is rewritten whole (a dynamic partition overwrite
  left periods of an earlier definition on disk); a missing model-input mapping fails loud; a
  step named `split` or `eligible` is refused; a star in a call, a subquery and a window function
  are refused in eligibility SQL; a period without eligible rows is refused by the contract;
  null conditions are counted per period; `period` is cast on read.
- **Step 2 (10-26):** a string flag, a flag of 2 and a string amount are refused before
  building; a timestamp period not at midnight in the session time zone is refused (it shifts a
  period); a source with a missing period or ending before `v + w` is refused; an upstream
  target with values in the source's last w periods, or none in the period before them, is
  refused; replay refuses a `set` on a path that isn't loggable.
- **Step 1 (10-26):** entries carry `hash_version`, a `set` may write null, a write clash fails
  rather than retrying, a level move re-fills the level-filled fields, a config file carrying
  replay-written fields is refused.
- **Justified, not taken:** the notebook finds the repo's config from the editable install (a
  use-case repo writes its own absolute path); `Frames` keeps positional fields; a per-row test
  for `negative_downsampling` (a test idea, not a bug).
- **Deferred, with a row:** a migration hook for the model input's sidecar (roadmap backlog);
  the `definition.json` question for the audit log's folder (`config.md` → Open questions); a
  `label_free_periods` helper for Feature Checks (`feature_checks.md` → Open questions, M2.2).

## The SDS's rounds, in short
- **10-26 (step 1):** Q388–Q390 applied: the loggable settings widened, the pre-release
  carve-out for recipe changes, the golden-hash test.
- **10-27 (step 2):** the rule compares t with the forward periods (`flag_goes_up`; a holder at
  t gets 0); nulls follow SQL semantics with `null_value_share` shown; eligibility in two kinds,
  so EDA keeps the current holders as a reference group.
- **10-28 (steps 2 and 3):** labels kept in every period Target Factory can build (Q399
  reverted); `null_as` and `leavers` removed; the two coverage checks merged into one; the split
  rewritten around one plain hash draw; eligibility as two lists (`analysis`, `modelling`), the
  modelling filter applied before Feature Checks; the template's comment rule and the
  ordered-sources note.
- **10-28, second round (the addendum):** the hash draw trusted on structured ids after a check
  with numbers; the model input reshaped to the SDS's picture (the sources joined plus one
  target column per use case, everything else derived on read; `target_<use_case>`; one shape
  for one or several configs); the unit of analysis as `time.period` with the renamed fields;
  `revert` built now rather than in M2.2; the id cast found by the hash check.
- **10-29:** seven questions answered in chat and in `worknotes/log.md`; a source column
  named like the framework's own is renamed `source_<name>` instead of refused, and the own
  upstream target column is dropped on the read side, which also closes an eligibility
  condition naming the label; missing periods as a Phase 3 wish; the use case's name freed
  to letters, digits, `_` and `-` in any case, compared ignoring case, its lower-case form
  naming folders and columns (Q407, D-128 replaced); a second example use
  case, `td_acquisition`, sharing `retail_acquisition_input` with `cc_acquisition`, shown in
  the notebook.

## Deviations from the design, for your judgement
- **Steps 2 and 3 were built on the main thread, not by parallel agents**, since the pieces
  depend on each other; the addendum, by contrast, was built by five agents on disjoint files
  from one written spec, with the reviews in parallel after the merge.
- **Two traps found and ruled** (`docs/context/lessons.md`): T20, the sampling draw salted apart
  from the split's; T21, the metadata file is `_model_input.json`, since Spark reads a
  `_metadata*` file as a parquet summary; T22, the hash draw depends on the id column's bytes,
  hence the cast.
- **The spine must cover `first … v`** without a gap, the target source `first … v + w`: one
  check, two ranges; with several configs the spine covers the earliest first to the latest v.
- **The model input's folder is rewritten whole** (the design said dynamic partition overwrite):
  a rerun must never leave periods of an earlier definition behind; per-period incremental
  builds are M4's requirement 7 and will revisit this.
- **The split is not in the sidecar any more** (it was, to refuse a reseeded config): the split
  is derived on read, so a reseeded config simply gets its own split.
- **`null_in_window` reaches no frame and not the model input**: the contract's callout takes
  the share from the sidecar (saved) or the fresh target log (in memory).
- **The contract takes the whole panel** and first checks that every window period and the
  validation period has eligible rows; its task checks run on the window's rows.
- **`negative_downsampling` is refused for regression at config load** (a schema validator).
- **`record_decision` checks feature names against the saved model input's candidates**,
  falling back to the patterns, saying so, when the config names no model input or none
  is saved yet; a stale model input fails loud.
- **Signatures:** `estimate_collect(frame, name)` takes no `spark`; `collect_frame` returns the
  frame with its log entry; `check_contract(panel, cfg, null_in_window_share)`;
  `apply_eligibility(panel, eligibility, spec)` takes the config's `Eligibility` and the period
  spec; `load_panel(cfgs, …)` takes a list; `prepare_panel(panel, cfg, entity, targets)` is the
  read side; the model input lives in `dataset/model_input.py` (the design said `frames.py`);
  `run_target_factory` stays per config while `save_model_input` takes a list.
- **Each step prints its own line** (join, eligibility, contract, null-target, sampling,
  collect) and the log entries are plain data, so a notebook and a `run` show the same lines.

## Explanations
### `split.py`: why a hash, and what the buckets were
- **Why a hash and not `rand()`.** The split must be the same on every machine, on every
  rerun and in every Spark partition, and all of a client's months must land on the same side.
  A random number gives none of that. A hash of the client id is a deterministic pseudo-random
  number: the same client always gets the same one.
- **How it is a number in [0, 1).** `xxhash64(salt, unit_id, seed)` is a 64-bit integer that
  looks random. `pmod(…, 1_000_000)` folds it into one of a million equal buckets, 0 to
  999,999, evenly spread; dividing by a million gives a number in [0, 1) that behaves like a
  uniform draw. A client is in test when its number is below `test_share`. That is all the
  "bucketing" was: the old code compared the bucket with `share × buckets`, the same test
  written less readably, with two different bucket counts (1,000 for the split, 1,000,000 for
  the sample). Now there is one function, `_hash_uniform(columns, salt, seed)`, and one
  constant, `RESOLUTION`.
- **Why the salt (T20).** The split and the sample would otherwise use the same draw of the
  same key with the same default seed 42. Every train client then has a draw of 0.3 or more, so
  "keep the clients with a draw below 0.5" keeps those in [0.3, 0.5): 29% of the train clients,
  not the 50% asked, and always the same slice of the split. The salt (`'split'`, `'sample'`)
  makes the two draws independent.
- **Why the seed.** Another seed gives another split or sample; both are recorded.
- **Per row or per client.** `negative_downsampling` draws on `(unit_id, period)`, since it keeps
  rows; `client_sample` draws on `unit_id`, since it keeps whole clients.

### The split's hash on structured ids
Yes, it can be trusted. A hash is built for exactly this: `xxhash64` passes the SMHasher
avalanche and keyset tests (sequential, sparse and common-prefix keys), which is what Spark
relies on when it partitions a shuffle by key. Changing one digit of the id changes about half
the bits of the hash, so segment digits, age digits and a counter give draws unrelated to each
other and to their neighbours. Checked on 100,000 ids of the shape you describe (two segment
digits, three for a relationship-age block, three for a counter within it, nothing random),
with `_hash_uniform` as it stands in `split.py` and `test_share` 0.3:

| What | string ids | long ids | a random draw would give |
|---|---|---|---|
| test share overall | 0.301 | 0.300 | 0.3 |
| worst segment of 5, deviation in standard deviations | 1.6 | 0.7 | about 1.5 |
| worst age block of 20, deviation in standard deviations | 2.2 | 1.8 | about 2 |
| lag-1 autocorrelation along the counter | −0.001 | −0.000 | 0 ± 0.03 |
| chi-square of the draw over 100 equal bins | 94 | 102 | 99 ± 14 |

So every downstream assumption of a random client split holds: each segment's test share is the
one asked up to binomial noise, and neighbouring ids are independent. Three things the hash
does not do, and a random number would not do either: it does not stratify, so a small
segment's share wobbles as any random split's would (500 clients: 30% ± 4 pp); it does not know
about dependent clients (a household with two ids), which needs the household as `unit_id`; and
its draw depends on the id's bytes, so the same digits stored as a string and as a long draw
differently (hence the two columns above). The third was the one thing to fix: the reader
now casts `unit_id` to string, so an upstream change of the id column's type (int to string)
no longer moves every client's split (T22; a double or decimal id still would, `12345.0`).
