"""The 95% intervals every rate and mean in the reports carries (D-050, T16).

`wilson_interval` is the interval of a share `k / n`: the binary group summaries' rate, the
regression summaries' non-zero share, the deep dives' bins. It is the closed form, vectorised:
it agrees with `scipy.stats.binomtest(k, n).proportion_ci(method="wilson")` to 2e-16 and is
about 20,000 times faster, which matters for a hundred bins times every feature (the Stage 2
facts spike). `t_interval` is the interval of a mean, for the regression summaries. Both take
numbers or numpy arrays and return the same shape; both refuse inputs that have no interval
instead of returning NaN.
"""

import numpy as np
from scipy import stats

Z_95 = float(stats.norm.ppf(0.975))  # 1.95996…, the quantile scipy's intervals use


def wilson_interval(
    k: float | np.ndarray, n: float | np.ndarray, z: float = Z_95
) -> tuple[float | np.ndarray, float | np.ndarray]:
    """The Wilson score interval of the share `k / n`, clipped to [0, 1]."""
    k, n = np.asarray(k, dtype=float), np.asarray(n, dtype=float)
    if (n <= 0).any() or (k < 0).any() or (k > n).any():
        raise ValueError("wilson_interval: needs 0 <= k <= n and n > 0 for every share")
    centre = (k + z**2 / 2) / (n + z**2)
    half = z * np.sqrt(k * (n - k) / n + z**2 / 4) / (n + z**2)
    return _plain(np.clip(centre - half, 0.0, 1.0)), _plain(np.clip(centre + half, 0.0, 1.0))


def t_interval(
    mean: float | np.ndarray, sd: float | np.ndarray, n: float | np.ndarray
) -> tuple[float | np.ndarray, float | np.ndarray]:
    """The 95% Student t interval of a mean from its sample standard deviation and `n` rows."""
    mean, sd, n = (np.asarray(x, dtype=float) for x in (mean, sd, n))
    if (n < 2).any() or (sd < 0).any():
        raise ValueError("t_interval: needs at least two rows and a non-negative sd")
    half = stats.t.ppf(0.975, n - 1) * sd / np.sqrt(n)
    return _plain(mean - half), _plain(mean + half)


def _plain(values: np.ndarray) -> float | np.ndarray:
    """A 0-d array as a float, so scalar inputs give scalar outputs."""
    return float(values) if values.ndim == 0 else values
