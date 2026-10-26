# Stage 1, major step 1: answers to the SDS's review
_Written 2026-10-26 for the SDS · your six remarks on major step 1, answered in the order you gave
them · the three questions they raised (Q388–Q390) were answered the same day, and the sections
below give the outcomes · deleted with the folder when the stage is done_

**In short.**
- **Changed already:** the template now shows every default, and a test keeps it in step with the
  schema (remark 4).
- **Found while answering, fixed:** a level move overwrote a person's `set` on a level-filled
  setting (remark 2, last part).
- **Explained:** the `include` rule (remark 1), what `HASH_VERSION` does (remark 5) and where the
  log lives (remark 6).
- **Decided by you, applied:** the loggable settings widened, with the exclusions as proposed
  (Q388); months held as their last day (Q389); `HASH_VERSION` kept as a label (Q390).

Verified: the full suite passed (111, 9 slow tests deselected, 2 min 52 s) before the code
review's small follow-ups. The config, identity, audit-log and code-rule tests passed again after
them (59), and `ruff check .` is clean. A fresh-context code review approved the changes with
nothing blocking, and all eleven of its suggestions are taken (sections 2 and 4).

---

## 1. Config: "`include` reverses a person's `exclude` only"
**It works feature by feature, and the rule is about who dropped the feature. It has nothing to do
with flags.**

- An `include` names features, and each one is checked on its own. It must be excluded right now,
  and the entry that last excluded it must be a person's. If entry #6 excluded 10 features, one
  `include` may name 1, 3 or all 10 of them. It never has to mirror the earlier entry. Like every
  entry it carries one reason, so bringing back 3 of the 10 is one entry with one reason.
- "A person's only" rules out the two other kinds of drop:

| The feature is out because… | Undone by |
|---|---|
| a person excluded it | `include` |
| a rule's threshold excluded it (Feature Checks' quality filters, e.g. all null) | a `set` on `feature_checks.steps` with another threshold, then the step reruns |
| it built the target (lineage) | never (`CLAUDE.md` §4.6) |
| automated selection in Training dropped it (a run output) | `keep_despite_flag` before the next run, which shields it from pruning |

- Why `include` and `keep_despite_flag` differ: `include` brings back a feature that is out.
  `keep_despite_flag` acts on a feature that is still in but was flagged: it settles the flag and
  shields the feature from automated pruning. A flag never drops anything (§4.6), so a flagged
  feature is never "out" and there is nothing to `include`.
- Why a rule's exclude can't be undone by `include`: the config would say "drop all-null columns"
  while the resolved input still had one. Rerunning the rule on the same data would then disagree
  with the input. Changing the threshold keeps the rule and its outcome in step.

Two gaps this shows, both for Feature Checks' design in M2.2. I've added them to `config.md` →
Open questions:
- **How a rerun with a new threshold replaces the step's old `exclude` entry.** Replay applies
  entries in order. As built, the old rule entry would still apply after the rerun, so the rerun
  must write a rule `include`, or a step's latest outcome must replace its earlier one. Replay
  already accepts an `include` from a rule. Nothing writes rule entries until M2.2.
- **A person overruling a quality rule for one feature.** An example is a rare flag that is 99.9%
  zeros and still predictive. Today the only way is to change the threshold for every feature.

The doc's wording now says "feature by feature" (`config.md` → Allowed decisions).

## 2. Loggable settings: why these, and why not split, eligibility, the window, strata, the rest of training and evaluation?
**Three tests, in order. The first two are hard lines. The third is where I was too cautious.**

1. **Does it change the data?** The data definition is the entity, sources, keys, eligibility,
   target, observation window, `w` and candidates. A change means other rows, labels or columns,
   so every EDA and Feature Checks result and every decision in the log describes data that no
   longer exists. The log is also stored under the data-definition hash (remark 6). A `set` on
   eligibility would have to move its own log to another folder. **So this needs a new config:**
   edit the file, Target Factory rebuilds the model input, and EDA and Feature Checks start again
   with an empty log. The old log stays readable under the old hash.
2. **Was it declared before any result, so that the results stay honest?** That covers the
   decision type, metric, gate metric and baselines (§4.3). Changing one after seeing a result is
   choosing the metric that looks best. Never loggable.
3. **Otherwise it is an iteration choice, and the log is the place for it.** I listed only what
   the worked example and the level mapping (D-132: the four points where the two automation
   levels differ) needed. The reason to start narrow was compatibility: adding a path later
   leaves old logs replaying unchanged, while removing one breaks every log that used it
   (`CLAUDE.md` §2). Still, that was too narrow for training and reporting, so the list is now
   widened (Q388).

Your list, setting by setting:

| Setting | Loggable? | Why |
|---|---|---|
| `data.eligibility` | never: a new config | test 1: another population |
| `time.train_months` (the training window), `time.target_window_months` | never: a new config | test 1: other rows, other labels. `time_budget_s`, the training *time* budget, is loggable already |
| `data.split` (share, seed) | never (my call) | not in the data-definition hash, since EDA and Feature Checks see every client (D-030: the client split comes after Feature Checks). Two reasons to keep it out: redrawing the test clients after seeing a test score lets the test number pick its own sample, and every run in one log is compared on the same test clients (D-083: choices weigh train and test metrics). A split change would make runs before and after it incomparable inside one log |
| `training.seed` | never (my call) | the same reason: a seed changed after a result picks noise as if it were signal |
| `strata` | loggable since Q388 | reporting only; reruns from EDA |
| `training.estimator_list`, `search_space`, `selection`, `categoricals` | loggable since Q388 | the modelling choices you iterate on, weighed on train and test |
| `evaluation.slices`, `evaluation.views`, `eda.chart_sample_share` | loggable since Q388 | they change what is reported, not the model |
| `lifecycle`, `inference`, `monitoring` | decided with M2.4 and M4 | they act after registration, and the log's slice is packed into the bundle at `register`. How a later entry reaches a registered model is those milestones' design. `promotion_gate.min` will be never, by test 2 |
| `training.path` | no | it has one value in Phase 2 |

**The bug this turned up.** `training.max_iter` is both loggable and filled by the level. A
person's `set` of 200 → 300, followed by a level move to `autonomous`, came back as 50, because
the move refilled every path the level had filled at load. That contradicts D-132 ("explicit
values stay"). It's fixed: a `set` on a level-filled path takes it off
`housekeeping.level_filled`, so a later level move keeps the person's value
(`levels.py::unmark_level_filled`, called from `replay.py::_apply_set`). The new test is
`test_level_move_keeps_a_persons_set`.

**How the widened list is written.** The paths are leaves wherever a section holds independent
settings, e.g. `training.selection.univariate_floor`, `strata.min_events`,
`eda.key_features.top_n` and `eda.key_features.include` (the last two used to be the one section
`eda.key_features`). A `set` then changes one value without restating the others. That also
removes a surprise the code review found: changing `include` through the old section path also
fixed `top_n`, so a later level move no longer refilled it.

## 3. schema.py: monthly data tagged on the first or the last day of the month
**You're right, and today it would break quietly.** The config accepts only first-of-month dates.
The data side, reading the sources' month column, comes in major step 3 and doesn't handle tags
yet. I checked these on local Spark 3.4.3:
- `add_months(date'2024-02-29', 1)` gives 2024-03-29, and `add_months(date'2024-04-30', 1)` gives
  2024-05-30. Spark 3 keeps the day number instead of moving to the month's end, so month
  arithmetic on last-day dates drifts and month equality stops matching.
- `date'2024-06-30' BETWEEN date'2024-01-01' AND date'2024-06-01'` is false. A last-day source
  filtered by a first-day window silently loses the window's last month.
- Two sources with different tags never match on the month key, so every column of the left-joined
  source comes back null.

**Settled (Q389, 10-26): one internal convention, the last day of the month, reached at the two
places where months come in.** You asked for the end of the month, the more common tag. For the
config and the data to agree, both hold the last day (D-129).
1. **Config (done):** a month may be written as its first or its last day and is stored as its
   last. A mid-month day still fails, since it is more likely a typo than a convention. The
   resolved config shows the last day. The example's data-definition hash moved with it; the
   golden digest is re-pinned and `HASH_VERSION` stays at 1, since nothing is kept inside the bank
   before the December pre-release (`config.md` → Identities now says so).
2. **Data (major step 2):** one reader, `read_keyed_source`, used by Target Factory now and by the
   dataset and Inference later. It renames the keys and moves each source's month column to its
   month's last day (`last_day`). This happens before the duplicate-key check, so a source
   carrying both tags for one client and month fails it by name. Its log says how each source
   tagged its months. A month column that is not a date or timestamp (a `2024-06` string, a
   `202406` integer) fails loud naming its type; a format setting comes when a real source needs
   one.
3. **Synthetic data (major step 2):** the holdings table tags its months on the last day (0.5.2),
   while the mart keeps the first, so the skeleton's two sources carry both tags on every run.

One trap comes with the last day: Spark's `add_months` keeps the day number, so month arithmetic
uses a month index (`year × 12 + month`), never a bare `add_months`. It is trap T19 in
`docs/context/lessons.md`.

Outputs such as the scores' month column follow the internal convention. Whether a downstream
consumer wants last-day dates is decided with the scores schema.

## 4. schema.py: "when an omitted value defaults to something, show it in the template"
**Done, and a test now enforces it.**
- `conf/base/TEMPLATE.yml` opens with a key for reading each line:

| A line shows | It means |
|---|---|
| `# required` | no default: the line must stay; you fill the angle brackets, and a plain value is the usual choice |
| a plain value | the default: deleting the line gives exactly this value |
| `null · level: autonomous … · assisted …` | the automation level fills it, and both values are named, e.g. `max_iter`: autonomous 50 · assisted 200 |
| any other `null` | off, or derived as the comment says |
| a commented-out line | an alternative to the line above it |

- What changed to make the key hold:
  - The level-filled fields now name their numbers. Before, they said only "null".
  - Examples that weren't defaults became commented alternatives under the default line: the
    eligibility step, `rule: flag_in_window`, a `targets:` source, a `model_input` name and
    `top_n: [10000]`.
  - `lineage: []` is written out.
- The new test is `test_template_shows_every_field_with_its_default`. It walks the schema against
  the template and checks four things:
  - every field is present;
  - every optional value equals the schema default, so an uncommented alternative fails;
  - every level field is null, with both values named on its own line;
  - every required line the level doesn't fill, sections included, says `# required`.

  I planted eight kinds of drift and it caught each one.
- The code review's follow-ups on the template:
  - option lists moved to a comment line above their key, so lines stay readable (the slices line
    stays at 118 characters, since it must name both level values);
  - the level marker in one form;
  - the `search_space` example dropped, since it showed a syntax nothing defines yet.
- Found on the way: `training.calibration` was a required section although its one field
  (`method`, default `platt`) has a default. A config with no `training:` section failed for that
  reason alone. It now defaults. This only loosens the schema: existing configs load and hash the
  same.
- `conf/base/cc_acquisition.yml`, the skeleton's config, is unchanged. It sets the
  `flag_in_window` rule, the holdings source and the model input explicitly.

## 5. identities.py: what does `HASH_VERSION = 1` do?
**Today, nothing in the code reads it. You're right that it has no effect yet.** It's a label
written beside every hash, on each audit-log entry and in the resolved config's housekeeping. It
names the recipe that computed the hash. Its job starts at the first change to that recipe.
- **What counts as a recipe change.** Any change to the JSON form of a hashed section changes the
  digests of every existing config even though no data changed. That includes a field added,
  renamed or retyped, and even a new optional field with a default, since the form then carries it.
  For the data-definition hash, the hashed sections are `entities.*.sources`, `data.keys`,
  `data.eligibility`, `data.target`, the window, `w` and `features.candidates`.
- **Why a label is needed.** A later version that compares a stored hash with a fresh one sees a
  mismatch and can't tell "your data changed" from "our recipe changed". With the label it can
  say: "written under recipe 1, this version computes 2: a schema change, not a data change. Rerun
  EDA or accept the old artifacts" (D-088: every hash is stored with a `hash_version`).
- **Who will compare.** The model input's hash check (major step 3), Training's check that EDA and
  Feature Checks artifacts exist for the same data definition (M2.2, D-031), and the registry
  records (M2.4). I've added `hash_version` to the model input's `metadata.json` in `dataset.md`,
  where only the hashes were listed.
- **What enforces it now.** `test_golden_hashes_of_the_example` pins the example's digests, so a
  recipe change fails that test, and its message says to bump `HASH_VERSION`.
- **Known gap.** The log folder is named by the short hash. After a recipe change, a reader looks
  in a new folder and finds no log: a warning today, an error once the model input exists. The fix,
  a `definition.json` in each folder carrying the full hash and its version, is an open question
  in `config.md`.
- **A consequence to plan for.** We'll add fields to hashed sections often during Phase 2, e.g. a
  parameter for each new target rule. Before 1.0 that costs nothing, since nothing is kept inside
  the bank. From the December pre-release on, each such addition orphans every use case's EDA and
  Feature Checks artifacts and its log. One remedy is to hash only the values that differ from the
  schema default, so an added optional field leaves every hash alone. The price: a changed default
  would then have to bump `HASH_VERSION` by rule, with its own pinned test, or old artifacts would
  be reused silently. Decided (Q390, option A): `HASH_VERSION` stays a label, and both this and
  the log folder's `definition.json` are decided before the December pre-release.

## 6. audit_log.py: where does it write, and where is the mutable table?
**There is no mutable table.** Three things are involved, and only one is stored:

| What | Where | Changes? |
|---|---|---|
| the entries, one JSON file each | `<roots.data>/04_feature/<use_case>/<entity>/<data-definition hash, 12 characters>/decisions/0001.json`, `0002.json`, …; on your laptop under `data/04_feature/cc_acquisition/entity_a/…`, since `roots.data` comes from `conf/local/environment.yml`; inside the bank, `roots.data` on HDFS | never: each file is created once and never overwritten; a reversal is a new entry |
| the resolved config, the current state | built in memory by `resolve_config` on every call; written as one YAML file only where `save_to` says; from M2.2 every stage saves it beside its artifacts | a view, rebuilt on demand and never edited back |
| the table `show_decisions` prints | a pandas DataFrame built from the entries on every call | not stored |

The path is built by `audit_log_dir` in [environment.py](../../src/core_modelling/environment.py)
and used by `_log_dir` in `audit_log.py`.

Why files rather than a table:
- An append-only log needs neither HDFS append, which may be off in the bank (unverified), nor a
  table writer.
- Create-if-absent makes two simultaneous writers safe: the second one fails and re-runs its
  decision.
- A use case has tens of entries, not thousands.
- Storing the log under the data-definition hash means a changed data definition starts a fresh
  log while the old one stays readable.

A shared, queryable table may come with the registry tables in M4. It would follow D-007 (shared
tables only grow within a major version).

**Inside the bank, until M2.4.** The `hdfs dfs` transport arrives with M2.4. Until then, an
`hdfs://` data root is refused wherever the log is read or written, so inside the bank the log
needs a local path or M2.4.
