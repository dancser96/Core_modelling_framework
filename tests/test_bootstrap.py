"""The client bootstrap's intervals on replicate cells (statistics/bootstrap.py): the interval
covers the value, is wider than a row bootstrap when a client's rows move together, and an
undefined replicate gives no interval instead of a narrower one."""

from functools import partial

import numpy as np
import pandas as pd
import pytest
from scipy.special import expit

from core_modelling.statistics.bootstrap import bootstrap_intervals, replicate_values
from core_modelling.statistics.metrics import binary_metrics
from core_modelling.statistics.score_cells import bin_quantiles, cells_from_rows

REPLICATES = 200


def _clustered_rows(clients: int = 2_000, periods: int = 6) -> pd.DataFrame:
    """Every client in every period with one propensity and mostly the same label, as a
    converting client is positive in up to `w` periods: rows far from independent."""
    rng = np.random.default_rng(11)
    margin = rng.normal(-2.5, 1.0, clients)
    label = (rng.random(clients) < expit(margin)).astype(float)
    client = np.repeat(np.arange(clients), periods)
    flipped = rng.random(client.size) < 0.05
    y = np.where(flipped, 1 - label[client], label[client])
    score = expit(margin[client] + rng.normal(0, 0.3, client.size))
    edges = np.quantile(score, bin_quantiles("binary"))
    period = np.tile(np.arange(periods), clients).astype(str)
    return pd.DataFrame({
        "part": "test", "period": period, "client": client,
        "score_bin": np.searchsorted(edges, score, side="right"), "target_bin": y.astype(int),
        "target": y, "score": score, "weight": 1,
    })  # fmt: skip


def _replicates(rows: pd.DataFrame, unit: np.ndarray) -> pd.DataFrame:
    """The long frame of replicates 1 … `REPLICATES`: one Poisson(1) weight per `unit` (the
    client, or the row for a row bootstrap), so a unit's rows move together."""
    rng = np.random.default_rng(5)
    _, at = np.unique(unit, return_inverse=True)
    frames = [
        cells_from_rows(rows.assign(weight=rng.poisson(1.0, at.max() + 1)[at]), [], "log_loss")
        .assign(replicate=r)
        for r in range(1, REPLICATES + 1)
    ]  # fmt: skip
    return pd.concat(frames, ignore_index=True)


def test_the_client_interval_covers_the_value_and_is_wider_than_a_row_bootstrap() -> None:
    """With six periods per client and labels that persist, the client bootstrap's interval of
    the base rate is about √6 times a row bootstrap's (measured 2.1) and the AUC's wider too
    (1.45): a row count is too narrow."""
    rows = _clustered_rows()
    metric = partial(binary_metrics, base=0.1)
    value = metric(cells_from_rows(rows, [], "log_loss"))
    by_client = bootstrap_intervals(_replicates(rows, rows["client"]), metric, 0.95, REPLICATES)
    by_row = bootstrap_intervals(_replicates(rows, rows.index), metric, 0.95, REPLICATES)
    for name in ("base_rate", "roc_auc", "ap", "log_loss_skill", "calibration_slope"):
        low, high = by_client[name]
        assert low < value[name] < high, name
    for name, ratio in (("base_rate", 1.8), ("roc_auc", 1.2)):
        client_width, row_width = (np.subtract(*reversed(by[name])) for by in (by_client, by_row))
        assert client_width > ratio * row_width, name


def _three_cells() -> pd.DataFrame:
    """Three binary cells of one part and period, one of them the only event."""
    return pd.DataFrame({
        "part": "test", "period": "p", "score_bin": [0, 1, 1], "target_bin": [0, 0, 1],
        "rows": [5.0, 4.0, 1.0], "target_sum": [0.0, 0.0, 1.0], "score_sum": [0.5, 0.8, 0.3],
        "sq_error_sum": 0.1, "abs_error_sum": 0.1, "loss_sum": 0.5,
        "target_sq_sum": [0.0, 0.0, 1.0], "link_sum": [-11.0, -6.0, -1.5],
    })  # fmt: skip


def test_an_undefined_replicate_gives_no_interval() -> None:
    """A replicate that drew no event leaves AUC undefined there, so AUC gets no interval while
    the rows keep theirs; a replicate without any cell leaves every metric without one; replicate
    0 is the value, refused as a replicate."""
    cells = _three_cells()
    no_event = cells.iloc[:2]
    replicate_cells = pd.concat(
        [cells.assign(replicate=1), no_event.assign(replicate=2), cells.assign(replicate=3)]
    )
    metric = partial(binary_metrics, base=0.1)
    intervals = bootstrap_intervals(replicate_cells, metric, 0.9, 3)
    assert np.isnan(intervals["roc_auc"]).all() and np.isfinite(intervals["rows"]).all()
    missing = bootstrap_intervals(
        replicate_cells.loc[replicate_cells["replicate"] != 3], metric, 0.9, 3
    )
    assert all(np.isnan(pair).all() for pair in missing.values())
    with pytest.raises(ValueError, match="replicate 0"):
        bootstrap_intervals(cells.assign(replicate=0), metric, 0.9, 3)


def test_the_value_is_replicate_zeros_and_the_interval_the_others() -> None:
    """`replicate_values` reads the value on replicate 0 alone and the interval on 1 … R alone,
    as `bootstrap_intervals` gives it; cells without replicate 0 are refused."""
    cells = _three_cells()
    doubled = cells.assign(rows=2 * cells["rows"])
    others = pd.concat([cells.assign(replicate=1), doubled.assign(replicate=2)])
    metric = partial(binary_metrics, base=0.1)
    values, bounds = replicate_values(
        pd.concat([doubled.assign(replicate=0), others]), metric, 0.9, 2
    )
    # `equals` holds a NaN equal to a NaN in the same place: an undefined metric stays undefined
    assert pd.Series(values).equals(pd.Series(metric(doubled)))
    assert pd.DataFrame(bounds).equals(pd.DataFrame(bootstrap_intervals(others, metric, 0.9, 2)))
    with pytest.raises(ValueError, match="no replicate-0 cells"):
        replicate_values(others, metric, 0.9, 2)
