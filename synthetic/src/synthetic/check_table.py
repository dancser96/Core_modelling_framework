"""The check table shared by every build step: one row per check, and how a row passes.

A row compares a realised value with the value the spec expects: shares against their binomial
standard error (`share_row`), rules that must always hold as a share of violating rows
(`violations_row`), anything else with an explicit tolerance (`row`). `pytest` asserts every row
passes; the checking notebook shows the same table.
"""

import numpy as np
import pandas as pd

# Tolerance in standard errors: a family-wise false-failure rate of about 0.1% over a step's
# ~150–250 rows at the canonical size, which the tests use (in the 5k preset many strata are too
# small to show anything). Shares measured after months of turnover carry extra noise, so their
# effective tolerance is closer to 3.5–4 standard errors. With the tests' fixed seed, a failing row
# is investigated as a generator bug, never fixed by widening a tolerance.
Z_TOL = 4.5


def row(
    check: str, stratum: str, n: int, expected: float, realised: float, tolerance: float
) -> dict:
    """One row of the check table; it passes when |realised − expected| ≤ tolerance."""
    return dict(
        check=check,
        stratum=stratum,
        n=int(n),
        expected=expected,
        realised=realised,
        tolerance=tolerance,
        passed=bool(abs(realised - expected) <= tolerance),
    )


def share_row(check: str, stratum: str, expected: float, hits: int, n: int) -> dict:
    """A share checked against its binomial standard error."""
    tolerance = Z_TOL * np.sqrt(expected * (1 - expected) / n)
    return row(check, stratum, n, expected, hits / n, tolerance)


def violations_row(check: str, bad: pd.Series) -> dict:
    """Share of rows breaking a rule that must always hold."""
    return row(check, "all", len(bad), 0, float(bad.mean()), 0)


def profile_of(spec: dict, df: pd.DataFrame) -> pd.Series:
    """Each row's profile, looked up from its subsegment."""
    return df["subsegment"].map(lambda s: spec["subsegments"][s]["profile"])
