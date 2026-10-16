"""Compatibility shims, applied on package import before anything imports pyspark or flaml (T1).

`import flaml` pulls in `pyspark.pandas`, which on PySpark 3.4 still uses `np.NaN`, removed in
NumPy 2.0. `np.NaN` was always `np.nan`, so restoring the alias is safe. The proper fix is a newer
PySpark inside the bank.
"""

import numpy as np

if not hasattr(np, "NaN"):
    np.NaN = np.nan
