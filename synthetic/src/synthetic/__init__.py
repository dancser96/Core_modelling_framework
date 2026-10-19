"""Synthetic retail feature mart with known ground truth, for developing core_modelling.

Dev-only and never shipped into the bank. It plays the upstream data owner: it writes the kind of
monthly feature mart that use cases read inside the bank, plus the hidden truth (oracle) that
tests and demos check the framework against. Layout: `spec/` holds the rules as plain data,
`mechanisms/` the functions that simulate them, `generate` the month loop, `output` writing and
reading a dataset, `truth/` the oracle and `truth.json`, `checks/` the checks written from the
spec. Spec and code map: docs/components/test_harness.md.
"""

__version__ = "0.4.0"
