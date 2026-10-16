"""The ground truth of a generated dataset, as it goes into `truth.json`.

`build_truth` collects what the generator knows and the mart doesn't show: seed, preset, size, the
generator and library versions (the seed-to-data mapping depends on them), the spec, the
calibrated intercepts and leaving chances, and turnover per month and profile. Values are made
JSON-safe (numpy numbers as Python numbers, tuples as lists, dict keys as strings, NaN as null)
and round-tripped through JSON, so the truth in memory is exactly what `output.load_truth` reads
back. Keys become `str(key)`: the spec's `{True: 0.7}` reads back as `{"True": 0.7}`, so readers
look levels up by their string form. Build stage E adds the column schema, oracle metrics,
relevance and traps.
"""

import json

import numpy as np
import pandas as pd
import pyarrow as pa
import scipy

from synthetic import __version__


def build_truth(sim: dict) -> dict:
    """The truth of a simulation (see the module docstring), JSON-safe."""
    truth = {
        "generator_version": __version__,
        "versions": {
            "numpy": np.__version__,
            "scipy": scipy.__version__,
            "pandas": pd.__version__,
            "pyarrow": pa.__version__,
        },
        "seed": sim["seed"],
        "preset": sim["preset"],
        "n_clients": sim["n_clients"],
        "n_months": sim["n_months"],
        "first_month": str(sim["first_month"]),
        "spec": sim["spec"],
        "calibration": sim["calibration"],
        "turnover": sim["turnover"],
    }
    # The round trip also copies the spec, so editing the truth never changes the preset.
    return json.loads(json.dumps(_json_safe(truth), allow_nan=False))


def _json_safe(value: object) -> object:
    """`value` with numpy numbers as Python numbers, tuples as lists, keys as strings, NaN as None.

    Anything else JSON can't hold is left as it is, so `json.dumps` fails loud on it.
    """
    if isinstance(value, dict):
        return {str(key): _json_safe(item) for key, item in value.items()}
    if isinstance(value, list | tuple | np.ndarray):
        return [_json_safe(item) for item in value]
    if isinstance(value, np.generic):
        value = value.item()
    if isinstance(value, float) and not np.isfinite(value):
        return None  # e.g. the intercept of a profile without clients
    return value
