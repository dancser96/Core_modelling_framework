"""Evaluation: one trained run judged on clients and a period it never saw (evaluation.md).

`scores.py` scores the evaluation rows inside Spark and writes the scores table; `cells.py`
sums it into score cells with the client-bootstrap weights; `tables.py` turns one scorer's
cells into the metric tables with intervals, and `slices.py` the slices and the strata's list
composition; `baselines.py` chooses and scores the baselines and compares them with the model;
`explain.py` collects the explanation tables, with `permutation.py` the permutation importance
and `effects.py` the effect features and the effects table; `drift_reference.py` builds
Monitoring's yardstick. `views.py`, `views_explain.py` and `views_summary.py` are the report's
views and `report.py` the page. `card.py` builds the model card's facts (`reporting/card.py`
renders them). `run.py` is the stage, which orchestrates only, and `meta.py` assembles its
`evaluation.json` and stage result; `compare.py` sets two evaluated runs side by side.
"""

from core_modelling.evaluation.compare import compare_runs
from core_modelling.evaluation.run import run_evaluation

__all__ = ["compare_runs", "run_evaluation"]
