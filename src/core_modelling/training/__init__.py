"""Training: one model fitted on the train split of the observation window, written as a
numbered run (D-139, D-140; docs/components/training.md).

`search_space.py` holds the bounded ranges, the starts and FLAML's fixed switches as plain
data and `search.py` runs one search per family on the dataset's client folds. `gate.py` is the
gate: no model without data knowledge. `train_statistics.py` computes the train-split
statistics the selection rules read, `selection.py` applies the three rules and `train_data.py`
gives the train rows after them. `fold_models.py` gives every out-of-fold number and
`calibrate.py` the calibration fitted on them. `ledger_run.py` builds the per-run ledger and
the sign-off table, `tables.py` Training's other tables and `views.py` their report blocks.
`run.py` is the stage, which orchestrates only. FLAML only searches: every model that is kept
is fitted through `model.FAMILIES`.
"""

from core_modelling.training.run import run_training

__all__ = ["run_training"]
