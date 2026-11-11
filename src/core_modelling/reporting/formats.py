"""How numbers read in a report's tables: one format per known column, shared by every report.

`format_of` is the one place a column name gets its format, and `column_formats` gives
`style_table` the format of each column it knows by name: counts with
thousands separators, the estimate as the task prints it (`TASK_SPECS[task]["estimate_format"]`),
shares as percentages, concordances, PSI and R² to three decimals, lifts and differences to two,
a p-value through `p_value` and a finding's value and threshold through `plain_number`, which
never falls into scientific notation. The column lists are the statistics' shared vocabulary (the
ledger's and the stages' tables), so a column keeps its format in every report that shows it.
"""

from collections.abc import Callable

import numpy as np
import pandas as pd

from core_modelling.tasks import TASK_SPECS


def plain_number(x: float) -> str:
    """A value as an amount reads, never in scientific notation: `69,310` from |x| ≥ 999.5, four
    significant digits below (`0.3315`, `0.00001234`)."""
    if abs(x) >= 999.5:  # .4g would round 999.95 to "1000" without the separator
        return f"{x:,.0f}"
    plain = np.format_float_positional
    return plain(x + 0.0, precision=4, unique=False, fractional=False, trim="-")


def p_value(x: float) -> str:
    """A p-value: "< 0.0001" below 0.0001, where more digits say nothing, else `plain_number`."""
    return "< 0.0001" if x < 0.0001 else plain_number(x)


COUNT, SHARE = "{:,.0f}", "{:.1%}"
CONCORDANCES = ["concordance", "concordance_plain", "concordance_se", "concordance_best_order",
                "concordance_window", "null_concordance", "null_concordance_window",
                "se", "lagged_concordance", "concordance_range",
                "association_with_best"]  # fmt: skip
SHARES = ["missing_share", "missing_share_window", "zero_share", "zero_share_window",
          "dominant_share", "dominant_share_window", "nonzero_share", "nonzero_low",
          "nonzero_high", "eligible_share", "capture", "inf_share", "signal_kept",
          "constant_share", "new_level_share"]  # fmt: skip
THREE_DECIMALS = ["psi", "psi_window", "psi_latest", "explained_by_others", "association",
                  "association_min", "explained_by_others_max"]  # fmt: skip
PLAIN = ["value", "threshold"]  # a finding's numeric columns only: a share, a ratio or a p
P_VALUES = ["heterogeneity_p"]
ESTIMATES = ["estimate", "low", "high", "median", "nonzero_mean", "nonzero_median", "q1", "q3",
             "lower_whisker", "upper_whisker"]  # fmt: skip
PREFIXES = {"rows_": COUNT, "share_": SHARE, "median_": plain_number, "p10_": plain_number,
            "p90_": plain_number}  # fmt: skip


def format_of(name: str, task: str) -> str | Callable[[float], str] | None:
    """A column's format by its name: counts with separators, the estimate as the task prints
    it, shares as percentages, concordances, PSI and R² to three decimals, lift and differences
    to two, a p-value as `p_value` gives it and a finding's value and threshold as plain
    numbers; a known prefix's format otherwise, None for any other."""
    rules = {
        **dict.fromkeys(["rows", "support", "positive_rows", "levels", "rank", "n", "size"], COUNT),
        **dict.fromkeys(ESTIMATES, TASK_SPECS[task]["estimate_format"]),
        **dict.fromkeys(SHARES, SHARE),
        **dict.fromkeys([*CONCORDANCES, *THREE_DECIMALS], "{:.3f}"),
        **dict.fromkeys(["lift", "smd", "skew"], "{:.2f}"),
        **dict.fromkeys(PLAIN, plain_number),
        **dict.fromkeys(P_VALUES, p_value),
    }
    if name in rules:
        return rules[name]
    prefixed = [f for prefix, f in PREFIXES.items() if name.startswith(prefix)]
    return prefixed[-1] if prefixed else None


def column_formats(df: pd.DataFrame, task: str) -> dict[str, str | Callable[[float], str]]:
    """Each column's format that `format_of` knows by its name."""
    formats = {column: format_of(str(column), task) for column in df.columns}
    return {column: f for column, f in formats.items() if f is not None}
