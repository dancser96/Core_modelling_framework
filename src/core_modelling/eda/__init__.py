"""EDA: the population, the target and the features that matter, from the counts table (D-135).

The stage collects one period whole (the snapshot) and reads every statistic from the cells the
counts passes aggregate over the compared periods (`dataset/counts.py`, `statistics/`). The
modules here compute tables only: `ranking.py` (the per-feature statistics, the ranking and the
key features), `population.py` (the headline, the funnel, the target per period and by stratum,
the reference groups), `deep_dives.py` (the key features' group tables, quartiles and per-period
concordance, the strata pivots), `slices.py` (the key features at the decision's slices) and
`profile.py` (the value profile). `report.py` turns the tables into the views and the
report, `run.py` orchestrates the stage and `explore.py` holds the functions a reader calls on
its result (`docs/components/eda.md`). Public API: `run_eda`, `pivot_target`, `lift_by_group`,
`compare_sides` and `rate_by_period`.
"""

from core_modelling.eda.explore import compare_sides, lift_by_group, pivot_target, rate_by_period
from core_modelling.eda.run import run_eda

__all__ = ["compare_sides", "lift_by_group", "pivot_target", "rate_by_period", "run_eda"]
