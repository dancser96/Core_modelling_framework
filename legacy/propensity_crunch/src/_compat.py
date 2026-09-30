"""Compatibility shims, applied by importing this module before any heavy
third-party import that needs them.

`import flaml` transitively imports pyspark's pandas-on-Spark
(flaml.fabric.mlflow -> flaml.automl.spark -> pyspark.pandas). Older pyspark
still references the numpy alias `np.NaN`, which NumPy 2.0 removed, so the
import fails at module load with:
    AttributeError: `np.NaN` was removed in the NumPy 2.0 release.
`np.NaN` was always identical to `np.nan`, so restoring the alias is safe and
lets pyspark.pandas import cleanly. The proper fix is a compatible
pyspark/numpy pairing (pyspark >= 3.5.2 / 4.0, or numpy < 2); this unblocks
meanwhile without touching the cluster.
"""
import numpy as np

if not hasattr(np, "NaN"):
    np.NaN = np.nan
