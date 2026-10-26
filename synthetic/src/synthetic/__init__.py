"""Synthetic retail feature mart with known ground truth, for developing core_modelling.

Dev-only, not part of core_modelling. It goes into the bank as code, with the tests, which generate
their data from a seed; its data never does (D-041). It plays the upstream data owner: it writes
the kind of monthly feature mart that use cases read inside the bank, plus the hidden truth
(oracle) that tests and demos check the framework against. Layout: `spec/` holds the rules as plain
data, `mechanisms/` the functions that simulate them, `generate` the month loop, `output` writing
and reading a dataset, `truth/` the oracle and `truth.json`, `checks/` the checks written from the
spec. Spec and code map: docs/components/test_harness.md.
"""

__version__ = "0.5.2"
