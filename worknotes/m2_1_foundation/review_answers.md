# Stage 1, major steps 2 and 3: for the SDS's review
_Written 2026-10-27 · step 2: what changed after your review of Target Factory, per remark ·
step 3: the questions the dataset build raised · the earlier rounds' outcomes are in `docs/` and
`worknotes/log.md`; this file holds the current review only and is deleted with the folder_

## Step 2: your four remarks, applied
**Nothing is outstanding.** Read `review_guide.md` → Major steps 2 and 3 in its reading order.

| Your remark | What changed |
|---|---|
| Nulls in the window: coverage strict, the rule relaxed | `_check_months_covered` stays (every month from `train_months.first` to `v + w`). Null values follow SQL: a null never counts as an event, the target is null only when nothing can be compared (the value at t, or every forward value, null). The summary shows `null_value_share`. `data.target.null_as` (Q393 A) gives the value a null stands for, e.g. `0` for a holdings flag left null for non-holders; built targets only. The dataset's contract adds the callout: nulls in the window without `null_as` may hide negatives |
| Holders by eligibility, not by nulling; EDA keeps the current clients | The "flag at t must be 0" precondition is gone: a holder at t gets 0. Eligibility filters have two kinds (D-129): `before: eda` drops rows; `before: model` tags them (a 0/1 column named after the step) and drops them before modelling, so EDA compares holders with non-holders. `cc_acquisition.yml` shows one of each. The dataset builds it: the window frame keeps the holders tagged `non_holders = 0`, the modelling frames take `eligible = 1` |
| The two table rows: compare t with any forward month | The rule is `max(forward values) > value at t`: `[0, null, 1, 1]` → 1, `[1, 0, 1, 1]` → 0, `[0, 0, 1, 1]` → 1, `[1, 1, 1, 1]` → 0; tested row by row |
| `flag_goes_up`; counts and amounts separate | Renamed; the rule takes a 0/1 column only (a 2 is refused). `count_goes_up` and the amount rules are separate rules for M4 (D-091), named in `target_factory.md` and D-029 (c) |

The oracle comparison holds on the non-holders at t (the oracle's own eligibility for
`cc_acquire`); the oracle nulls holders, the rule gives them 0.

## Step 3: questions from the dataset build
Each with my default; the deviations from the plan are listed in `review_guide.md`.

- **Q395. `month` in the pandas frames.** It arrives as `datetime.date` objects (Spark's
  `DateType` through Arrow), the same in the in-memory and the model-input paths. Default: leave
  it; EDA (M2.2) decides whether it wants `datetime64` (`dataset.md` → Open questions).
- **Q396. Persisting the panel.** The panel is a lazy plan, so every action (the join log, each
  filter's counts, each contract check, each collect) recomputes the joins and the target's
  window function: about ten seconds per stage on the unit preset, unknown inside the bank.
  Default: no `persist` in Stage 1; decide at M2.4 when a real source is read, with the numbers.
- **Q397. The sampling record's rates for regression.** `true_rate` and `sampled_rate` are the
  target's mean before and after sampling (for binary the positive rates of D-049; for
  regression the mean spend). Default: keep one record shape for both tasks, named as D-049
  names them, the doc saying what they are for regression.
- **Q398. One column set for every frame.** The window frame carries `split` too, and the
  modelling frames carry the tags and `eligible` (all 1 there), so every frame and the model
  input have the same columns in the same order. Default: keep; a stage drops what it doesn't
  use.
- **Q399. Labels only in the window and at the validation month.** The ML audit's hardening:
  the panel and the saved model input carry a null `target` for the gap months between the
  window and the validation month and for the months after it, so Feature Checks' label-free
  reads of those months are label-free by construction, not by discipline (§4.4; Target
  Factory's summary already shows no label rate there). The cost: a DS exploring the model
  input in a notebook copy can't look at later months' labels; the targets of a scored month
  come from Target Factory's labels for monitoring (M4). Default: keep it (taken; D-131 and the
  glossary say so).
