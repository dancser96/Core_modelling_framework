"""External OOT evaluation. Full-population stats (AUC + base rate) are always
reported. On top, precision/recall/lift are computed at configurable top score
slices: `top_pct` (percentiles) and `top_n` (absolute counts) — the operational
numbers for a large retail base where you contact only a slice. Baseline is the
population base rate (lift reference 1.0). Run OUTSIDE the engine.

All metrics are rank-based, so they are unaffected by score calibration."""
from __future__ import annotations

import numpy as np
from sklearn.metrics import roc_auc_score


def oot_evaluate(y_true, scores, metric, top_pct=(0.01, 0.10), top_n=(10000,)) -> dict:
    y = np.asarray(y_true)
    s = np.asarray(scores)
    base = float(y.mean())
    n = len(y)
    return {
        "metric": metric,
        "oot_auc": float(roc_auc_score(y, s)),
        "baseline_base_rate": base,
        "n_oot": int(n),
        "top_pct": {f"top_{p * 100:g}pct": _at_k(y, s, max(1, int(p * n)), base)
                    for p in (top_pct or [])},
        # an absolute slice larger than the population is meaningless -> skipped
        "top_n": {f"top_{k}": _at_k(y, s, int(k), base)
                  for k in (top_n or []) if k <= n},
    }


def _at_k(y, s, m, base) -> dict:
    idx = np.argsort(s)[::-1][:m]                 # top-m by score
    tp = float(y[idx].sum())
    pos = float(y.sum())
    precision = tp / m
    return {
        "n": int(m),
        "precision": float(precision),
        "recall": float(tp / pos) if pos > 0 else float("nan"),
        "lift": float(precision / base) if base > 0 else float("nan"),
    }
