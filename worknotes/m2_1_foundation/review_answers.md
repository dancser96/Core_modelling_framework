# Stage 1, major step 2: for the SDS's second review
_Written 2026-10-27 · what changed after your review of Target Factory, per remark · the earlier
rounds' outcomes are in `docs/` and `worknotes/log.md`; this file holds the current review only
and is deleted with the folder_

**Nothing is outstanding.** Your four remarks are applied; read `review_guide.md` → Major step 2
in its reading order.

| Your remark | What changed |
|---|---|
| Nulls in the window: coverage strict, the rule relaxed | `_check_months_covered` stays (every month from `train_months.first` to `v + w`). Null values follow SQL: a null never counts as an event, the target is null only when nothing can be compared (the value at t, or every forward value, null). The summary shows `null_value_share`. `data.target.null_as` (Q393 A) gives the value a null stands for, e.g. `0` for a holdings flag left null for non-holders; built targets only |
| Holders by eligibility, not by nulling; EDA keeps the current clients | The "flag at t must be 0" precondition is gone: a holder at t gets 0. Eligibility filters have two kinds (D-129): `before: eda` drops rows; `before: model` tags them (a 0/1 column named after the step) and drops them before modelling, so EDA compares holders with non-holders. `cc_acquisition.yml` shows one of each. The dataset (step 3) builds it; `dataset.md`, `eda.md`, the glossary and D-131 say so |
| The two table rows: compare t with any forward month | The rule is `max(forward values) > value at t`: `[0, null, 1, 1]` → 1, `[1, 0, 1, 1]` → 0, `[0, 0, 1, 1]` → 1, `[1, 1, 1, 1]` → 0; tested row by row |
| `flag_goes_up`; counts and amounts separate | Renamed; the rule takes a 0/1 column only (a 2 is refused). `count_goes_up` and the amount rules are separate rules for M4 (D-091), named in `target_factory.md` and D-029 (c) |

The oracle comparison holds on the non-holders at t (the oracle's own eligibility for
`cc_acquire`); the oracle nulls holders, the rule gives them 0.
