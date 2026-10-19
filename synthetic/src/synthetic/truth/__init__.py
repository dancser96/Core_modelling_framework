"""The hidden truth of a generated dataset: what no model could know, kept for checking.

`oracle` gives the standard targets, their realised values and the true window probabilities, and
the oracle's metrics (AUC per target and window, sizing); `regression` simulates the true
distribution of next-3-month card spend; `truth_file` builds `truth.json`.
"""
