# Stage 1, major steps 2 and 3: the SDS's review of 10-28, applied
_Written 2026-10-28, second round added the same day · per remark: what changed, or the
explanation asked for · your answers to Q400–Q404 and the hash follow-up · Q400 reworked ·
the third round's answers (Q405, Q406, everything built) · this file holds the current
round only; the
earlier rounds' outcomes are in `docs/` and `worknotes/log.md`, and the folder is deleted when
the stage is done_

## Your remarks, one by one

| Remark | Outcome |
|---|---|
| Q395–Q398: the defaults | Applied as they were: `month` stays `datetime.date` in pandas, no `persist` until M2.4, one sampling record shape for both tasks, one column set for every frame. |
| Q399: no, labels for the whole panel | **Reverted.** `build_panel` no longer nulls `target` outside the window and the validation month. The panel and the saved model input carry the label of every month whose forward window is complete; null only at the panel edge, for leavers and across gaps, exactly what an upstream target would give. The modelling frames still take the window plus the validation month. The summary's display rule is unchanged: Q404. D-131, the glossary and `dataset.md` say so; the test checks the labelled months are every month but the last w. |
| Target Factory on a list of configs | **Q400**, reworked in the second round around your simpler shape (below). |
| The template says sources are ordered; duplicate keys fail loud | The template's `sources.features` comment now says ORDERED, the first the governing spine, and that a duplicate key in any source fails. The check already existed: `read_keyed_source` runs `_check_unique_keys` on every source (the spine, every joined source, the target source), after the month move, so a source carrying a first-day and a last-day row for one client-month fails too, naming the source and a few keys (`test_duplicate_keys_fail_naming_the_source_and_key`). Nothing to add in code. |
| `null_as` and `leavers` | **Both removed.** I agree: `leavers` was a placeholder (`negative` only ever raised "not implemented"), and `null_as` solved a data-quality problem at the wrong end. One more argument against it: the case it was meant for, a holdings table with rows for holders only, gives *missing rows* for non-holders, not null values, so `null_as` would not even have helped; the row has to exist upstream. What stays: nulls follow SQL semantics (never an event; a null target when nothing can be compared), the summary shows `null_value_share`, and the contract's callout now fires whenever that share is above 0 and says to fill such nulls upstream. The target spec is `rule` + `column`, or `column` + optional `lineage`. The golden digests were re-pinned (the target spec's canonical form changed; `HASH_VERSION` stays 1 until the December pre-release). |
| Two functions doing the same thing (`_check_spine_months`, `_check_months_covered`) | **Merged** into one, `sources.check_months_covered(log, first, last, role, until)`. The two callers differ only in the range: the spine must cover `train_months.first … validation_month` (a gap would drop a month of rows quietly; the validation month must exist to be scored), the target source `train_months.first … validation_month + w` (a gap nulls the w targets before it; a source ending earlier leaves the validation labels immature). `month_from_number` (the inverse of `month_number`) computes v + w without `add_months` (T19). |
| Explain the bucketing in `split.py` | **Rewritten to read plainly**, explanation below. |
| Eligibility as two lists; the second before Feature Checks | **Done**, both parts: `data.eligibility.analysis` and `data.eligibility.modelling`; the `before:` field is gone; Feature Checks gets the eligible rows. The names `analysis` / `modelling` are kept (Q402, second round). |
| The month anchoring | **Q401**, approved in the second round as proposed: to do, after Q400. |
| Univariate AUC on the modelling population: both frames in memory? | No; explanation below. |
| Audit log: branches, and changing one earlier decision | Explanations below; the `revert` operation (Q403) is approved for M2.2. |
| `TEMPLATE.yml` comments | **Done.** The rule, written into the template's reading key: a short comment sits on the line it explains; a longer one sits right above its key; a level line always names both levels' values on its own line (the template test needs them there). Every line is now under 100 characters; the long inline comments moved above their keys (`decision.type`, `evaluation.slices`, `eligibility`, `target.rule`). |

## The explanations you asked for

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
- **Per row or per client.** `negative_downsampling` draws on `(unit_id, month)`, since it keeps
  rows; `client_sample` draws on `unit_id`, since it keeps whole clients.

### The split's hash on structured ids (your follow-up, second round)
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
differently (hence the two columns above). The third is the one thing to fix: `read_keyed_source`
renames the id column and leaves its type, so an upstream change of the id column's type (int to
string, say) would move every client's split. One line, `unit_id` cast to string at load: on
the to-do list below. The check script is in the session's scratchpad, not the repo.

### Univariate AUC on the modelling population
One frame. The window frame carries the modelling tags and `eligible` as columns, so the
modelling population is a row filter of the same pandas frame (`window[window.eligible == 1]`):
EDA computes the univariate ranking and every label statistic that feeds a choice (the top-N key
features) on that subset, and the reference-group views (holders vs non-holders) on every row.
No second collect; the filtered copy is at most the frame's size again, transiently. Feature
Checks now receives the eligible rows only (`build_frames(stage="feature_checks")`), so it
never sees the other group. `eda.md` and `feature_checks.md` say so.

### Audit log, usability 1: two paths (A, then back to step 8, then B)
Today's log is append-only and linear: entries are never deleted or edited, so nothing is ever
lost, but "reset to 8" is not an operation. Path B is written as reversal entries: an `include`
for the features an `exclude` after entry 8 dropped, a `set` back to the earlier value, and then
B's own entries. Both paths are in the log (A is entries 1–13, B is 14 on), and
`resolve_config(upto=13)` reproduces A exactly. What is missing is a one-entry way to say "back
to the state after 8": **Q403** proposes it.

### Audit log, usability 2: changing decision 5 and keeping 6–8
No reset needed. Entries are independent: a later entry supersedes only what it names. An
`exclude` is reversed feature by feature with an `include`; a `set` is overwritten by a later
`set` on the same path, which stores the value it replaced. So "change 5" is one new entry
(9), and 6–8 stay as they are. The resolved config's header names the entry behind each value,
and `show_decisions` shows 5 and 9 in order. Two caveats: evidence that cites `#5` stays as
written (evidence is text), and an entry that cites a superseded one is flagged at replay but
not blocked (`config.md` → Open questions).

## Your answers of the second round (10-28)

| Question | Your answer | Outcome |
|---|---|---|
| Q400 one model input for several use cases | Simpler: loop over the configs, add every target to the merged frame, filter nothing, save one table every config refers to | Reworked below around your shape; two questions remain (Q405, Q406) |
| Q401 the unit of analysis as a parameter | Agreed, as proposed | To do, after Q400 |
| Q402 the list names | The default | Kept: `analysis` / `modelling` |
| Q403 `revert` in the audit log | Build it, with scepticism about use | To do in M2.2, as defaulted |
| Q404 the summary's label columns | The default | Kept: the window's months only |
| Follow-up: the hash on structured ids | | Answered above, with the check |

## Q400, reworked around your shape
You are right, and what made my version heavy was keeping eligibility and the split *in* the
table: take them out and the per-use-case column blocks, the rename on read and the
per-use-case sidecar blocks all disappear. The shape I'd now build, which is yours:

- **Target Factory builds the data, nothing else.** `run_target_factory` and
  `save_model_input` take one config or a list. The panel is loaded once: the spine from the
  earliest `train_months.first` to the spine's last month, the feature sources joined on the
  keys, every column kept (no candidate selection, no lineage drop). Each config's target is
  built from its own target source with its own w and left-joined as one column, labelled in
  every month it can be. The table holds the keys, every feature column and one target column
  per use case. No eligibility, no `eligible`, no split, no tags.
- **Everything after that is read-side, from the reader's config.** `build_frames(cfg, …)`
  reads the table, keeps its own target as `target` and drops the other use cases' target
  columns (forward-looking: never a candidate, by construction, with a test), then does what
  `build_panel` does today after the join: the eligibility lists, the candidates (lineage
  excluded), the contract checks, the split. The in-memory path (`model_input: null`) is the
  same function on a freshly built one-config panel. One code path either way; nothing a
  reader needs is stored, because all of it is SQL filters and a hash draw, recomputed exactly.
- **The sidecar** (schema 3): the shared `sources` and `keys` as data, the table's months, the
  join log and the column list; per use case its `target_spec_hash`, lineage, the window it was
  built for and its target log; `framework_version`, `built_at`. Reading checks the schema and
  hash versions, that the reader's `sources` and `keys` equal the saved ones, that its use case
  is there with the same `target_spec_hash`, and that the table's months cover
  `train_months.first … validation_month`; else refused naming `save_model_input`. The
  data-definition hash leaves the sidecar: it keys the EDA → Training artifacts (D-088) and
  includes eligibility, the window and the candidates, which the table no longer embodies. The
  audit log's feature-decision check (`saved_candidates`) resolves the candidates from the
  sidecar's column list instead, no Spark needed.
- **Rules for a list.** Every config in the list declares the same
  `entities.<entity>.sources.features`, the same `data.keys` and the same `data.model_input`;
  otherwise fail naming the config and the field. The target source, `data.target`, `time` and
  everything from `eligibility` on may differ. A target column that collides with a feature
  column fails at save. The CLI: `run --stages target_factory a.yml b.yml`.
- **What it changes that you reviewed.** (1) A changed eligibility, window, split or candidate
  list no longer forces a rebuild of the model input; only the EDA → Training artifacts go
  stale (their data-definition hash changes). D-125's freeze point becomes the data part of the
  config, frozen when the table is saved: sources, keys, target spec, w. D-131's column list
  changes accordingly. (2) The contract's null callout reads a `null_in_window` column today,
  which `build_panel` drops after the check; without it in the table, the callout takes its
  share from the sidecar's target summary (Target Factory already computes `null_value_share`
  per month), the same message from one source. (3) The eligibility and contract logs are
  produced at read and travel in the frames' log, which EDA's artifacts record from M2.2; the
  sidecar holds the join and target logs only.
- **Size and order.** Less code than the first proposal: `panel.py` splits `build_panel` into
  the load (a list of configs) and the read-side preparation; `target_factory.py` names the
  target column; `model_input.py` writes and checks the per-use-case part of the sidecar;
  `frames.py` prepares after the read; `run.py` takes several config paths; tests, docs
  (`dataset.md`, `target_factory.md`, `config.md`, D-088, D-125, D-131, the glossary) and the
  notebook. About a day with subagents. Schema 3 refuses today's tables by name; none exists
  inside the bank. Order: Q400 first (it reshapes the panel and the frames), then Q401's rename
  sweep over the settled code, then Q403 with M2.2.

## Your answers of the third round (10-28): everything accepted, then built
| Item | Your answer | Outcome |
|---|---|---|
| The split's hash on structured ids | Understood and accepted | Nothing to change; the id cast (below) is the one finding |
| Q400 one model input for several use cases | Accepted as reworked | Built: `addendum_spec.md` section B |
| Q405 the target column's name | `target_<use_case>` | Built |
| Q406 one shape for the single-config path | Yes | Built: a single config is the one-element list |
| Q401 the unit of analysis as a parameter | Agreed on 10-28 | Built: `addendum_spec.md` section A |
| Q403 `revert` in the audit log | Build it | Built now rather than in M2.2: `addendum_spec.md` section C |
| The id's type at load | (found by the hash check) | Built: `unit_id` cast to string in `read_keyed_source` (T22) |

The full proposals for Q401 and Q403 are in `addendum_spec.md` (the spec every builder
followed), kept there until the stage folder is deleted at sign-off; the lesson that a to-do
keeps its proposal is recorded. What was built, how it was reviewed and where to read it:
`review_guide.md`. No question is open.
