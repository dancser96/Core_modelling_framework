"""Evaluation: one trained run judged on clients and a period it never saw (evaluation.md).

`scores.py` scores the evaluation rows inside Spark and writes the scores table; `cells.py`
sums it into score cells with the client-bootstrap weights; `tables.py` turns one scorer's
cells into the metric tables with intervals; `baselines.py` chooses and scores the baselines
and compares them with the model; `drift_reference.py` builds Monitoring's yardstick;
`explain.py` the explanation tables; `views.py` and `views_explain.py` the report's views and
`report.py` the page. `run.py` is the stage, which orchestrates only and writes the model card
(`reporting/card.py`) with the report; `compare.py` sets two evaluated runs side by side.
"""

from core_modelling.evaluation.compare import compare_runs
from core_modelling.evaluation.run import run_evaluation

__all__ = ["compare_runs", "run_evaluation"]
