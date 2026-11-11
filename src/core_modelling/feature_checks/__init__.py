"""Feature Checks: the correctness and data-quality gate between the candidates and the model
inputs (D-028, D-134), judged on EDA's artifacts alone (docs/components/feature_checks.md).

`findings.py` holds the finding table as plain data and the finding-row builders, `inputs.py`
EDA's artifacts gathered and checked into what every step reads, `measures.py` the numbers
Feature Checks reads from EDA's cells that EDA does not store (the lagged concordance, PSI
between two periods, the per-period table), `steps.py` the five steps in their fixed order,
`decisions.py` the `flag` entries a run writes and the proposed decisions a person reviews,
`report.py` the views and the report, and `run.py` the stage, which writes the audit log's
entries, the ledger's columns and `feature_checks/`. Public API: `run_feature_checks`.
"""

from core_modelling.feature_checks.run import run_feature_checks

__all__ = ["run_feature_checks"]
