"""Synthetic retail feature mart with known ground truth, for developing core_modelling.

Dev-only and never shipped into the bank. It plays the upstream data owner: it writes the kind of
monthly feature mart that use cases read inside the bank, plus the hidden truth (oracle) that
tests and demos check the framework against. `generate.generate_mart` builds it, `presets` holds
the spec, `checks_<step>` prove each build step. Spec: docs/components/test_harness.md.
"""

__version__ = "0.3.0"
