# Stage 2 (M2.2 Understanding): the review guide for the SDS
_Written for the SDS's review at the end of each major step (D-003, D-072 (i)); it holds the
current review only (worknotes are current-only). What to read, in which order, and what "right"
looks like. Tests appear only where reading one matters, marked **read this test** (at most two
per major step). Decisions the build made without the SDS are numbered in `plan.md` §9: silence
confirms them._

## Major step 2: EDA — review 2 applied, ready for review 3 (2026-11-05)
**Built** from `review2_spec.md` (the SDS's remarks R10–R28 and answers Q494–Q522), then the
stage-3 comprehensive review of the whole major step 2 code:
- the report reorganised: how to read up front, a three-column choices table, a lean ranking
  ordered and barred on one value, deep dives as rows of two-panel figures with the key features
  against the strata and their pivots, the correlation overview on the key features;
- the look: short centred titles, axis titles, nothing clipped, translucent table colours,
  range labels on merged bins (`[374, 419)`, `= 13`, `≥ 900`);
- `lift_by_group`, `compare_sides`, `rate_by_period` beside `pivot_target` (`eda/explore.py`);
- the cells' `sum_y2` (a regression mean's interval per period), the collect sorted in Spark,
  the strata check folded, `encoding_prior_rows`;
- notebooks 01 and 02 rewritten (02: 4,009 → 2,046 words; 01: 796 → 581) and run on the
  100k dataset; two simplicity passes (`report.py` + `charts.py` −15%);
- the stage-3 review: seven reviewers (code ×4, ML audit, silent failures, compatibility), every
  finding checked by a second reader, one fix round, then a review of the fixes. The biggest
  find: a regression concordance's standard error ignored the target's ties (V47).

**Measured:** full suite 510 passed, 9 slow deselected, about 9 minutes; `ruff check .` clean
(2026-11-05). On the 100k data (this laptop): notebook 01 about 2 minutes of cells; `run_eda`
132 s (1.2 GB peak); the report 5.6 MB, 34 figures; notebook 02 end to end with no cell error.

**Reading order (about 90 minutes; what you will see first, then the code behind it):**
1. `notebooks/02_eda.ipynb` on the canonical preset (step E pointed `conf/local/` at it): run it
   top to bottom. Right looks like: nine steps, each saying what to look at and what to decide,
   no decision references; step 7 answers four questions with one call each (holders vs
   non-holders is `compare_sides(result, "income", "non_holders")`).
2. `report.html` in a browser (the path prints in step 8): the summary, the ranking (one order,
   one bar), the `income` deep dive (lift | segment, then onboarding_channel alone, then boxes
   | concordance per period, then two pivots), `onboarding_channel`'s deep dive (a stratum
   itself: no chart against itself), the correlation overview.
3. `src/core_modelling/eda/report.py`: `build_views`, `_deep_dive`, `_concordance_row`,
   `_ranking_views` (`RANKING_VIEW`, `concordance_plain`), `_correlation_view`. Right looks like:
   tables in, Stylers and figures out, every group read from a stored table.
4. `src/core_modelling/eda/explore.py`: the four functions; right looks like: the report's
   groups, base and greying, a ValueError naming the valid choices for anything else.
5. `src/core_modelling/reporting/charts.py`: `_apply_theme`, `grouped_lines`, `side_by_side`.
6. `src/core_modelling/statistics/concordance.py` `kendall_null_se` (the tie factor, V47) and
   `statistics/distributions.py` `range_label`.
7. `src/core_modelling/eda/run.py` `_write`: the report is rendered before anything is removed
   and committed with `eda.json` in one rename (V49).

**Read this test (two):**
- `tests/test_statistics.py::test_kendall_se_matches_a_null_numerics_spread_on_a_zero_inflated_target`:
  the corrected SE against a simulated null spread (70% zeros, 2,000 units: 0.01195 against an
  empirical 0.01193; the old SE was 0.0075).
- `tests/test_eda.py::test_the_exploration_functions_cut_the_deep_dives_groups`: the notebook's
  functions show the report's groups, so a reader never compares two different cuts.

**Decisions made without you, to veto by number (`plan.md` §9):** V29–V46 from the build (the
one label rule and no thousands separators V29–V32, the two-panel rules V33–V34, the how-to-read
wording V35, the explore rules V37–V38 and V44, short titles V39, the stratum-as-itself skip V41,
the simplicity passes V46), V47–V54 from the stage-3 fix round (the tie-corrected SE, labels
falling back on reversed order, the report committed with the stage, axes below zero, one colour
per thing, the per-period concordance with no window direction, per-task summary columns, a tag
refused as a stratum). V20, V22, V26 and V27 were rewritten to the new state.

**Questions for you (defaults in brackets; `questions.md`):** Q523 percentage rate axes [yes,
in major step 3's first minor step]; Q524 thin stratum levels setting a strata chart's axis
[the axis follows the supported points].

**Open risks:**
- A preset switch writes to the same folder: the data-definition hash ignores physical paths,
  so the 100k run replaced the dev run's `eda/` (by design, but surprising on a laptop).
- The report is checked by headless-browser screenshots here, not yet in the bank's JupyterLab.
- A double column declared categorical names a level `1` in the snapshot's tables and `1.0` in
  the cells (`rate_by_period`), known since review 1.
- `rate_by_period` and the per-period concordance draw no interval (greying only; Q505's
  lean-tables rule).
- `lift_by_group` with a high-cardinality `by` and a raised `strata.max_levels` is slow (many
  group × level cells).
- `report.py` (~480 lines) and `charts.py` (~430) are the largest modules: tied views and
  primitives, kept whole.
