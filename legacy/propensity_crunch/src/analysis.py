"""Post-fit analysis for the modelling notebook. All helpers are MODEL-AGNOSTIC
(they only call `model.predict_proba(DataFrame)`), so they work on any FLAML
estimator and on models loaded back from disk, with raw-string categoricals.

Grouped by what they answer:
  importance        -> importance_bar, native_importance, importance_crosscheck
  directionality    -> pdp_ice (numeric), categorical_direction (levels)
  campaign shape    -> gains_chart, score_distribution
  probability trust -> calibration_plot
  optional/slow     -> shap_beeswarm (SHAP over predict_proba)
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import matplotlib.pyplot as plt


def _proba(model, X, features):
    return np.asarray(model.predict_proba(X[features]))[:, 1]


# ----------------------------------------------------------------- importance
def importance_bar(imp_df, top=20, ax=None):
    """Bar plot of permutation importance (feature, importance)."""
    d = imp_df.head(top).iloc[::-1]
    if ax is None:
        _, ax = plt.subplots(figsize=(6, max(3, 0.35 * len(d))))
    ax.barh(d["feature"], d["importance"])
    if "std" in d:
        ax.errorbar(d["importance"], range(len(d)), xerr=d["std"], fmt="none",
                    ecolor="k", elinewidth=0.6, capsize=2)
    ax.set_xlabel("OOT AUC drop when shuffled")
    ax.set_title("Permutation importance")
    return ax


def native_importance(model, features):
    """Best-effort native importance as a Series aligned to `features`, or None.
    With raw-string categoricals FLAML encodes internally, so native importances
    are often at the ENCODED level and won't align — then this returns None and
    the cross-check is skipped."""
    for obj in (model, getattr(model, "model", None), getattr(getattr(model, "model", None), "estimator", None)):
        fi = getattr(obj, "feature_importances_", None)
        if fi is not None and len(fi) == len(features):
            return pd.Series(np.asarray(fi, dtype=float), index=features, name="native")
    return None


def importance_crosscheck(perm_df, other, other_name="shap", rank_gap=5):
    """Merge permutation importance with another importance (native or mean|SHAP|)
    and flag features whose ranks disagree by more than `rank_gap` — often a sign
    of collinearity or leakage."""
    a = perm_df.set_index("feature")["importance"].rank(ascending=False)
    b = pd.Series(other).rank(ascending=False)
    t = pd.DataFrame({"perm_rank": a, f"{other_name}_rank": b})
    t["rank_gap"] = (t["perm_rank"] - t[f"{other_name}_rank"]).abs()
    t["disagree"] = t["rank_gap"] > rank_gap
    return t.sort_values("rank_gap", ascending=False)


# ----------------------------------------------------------------- directionality
def pdp_ice(model, X, features, feature, grid=20, ice_n=40, sample=2000, ax=None):
    """Partial-dependence (mean, bold) + ICE (per-row, light) for a NUMERIC
    feature: how the predicted score moves as the feature varies, holding the
    rest at their real values. Directionality without SHAP."""
    if not pd.api.types.is_numeric_dtype(X[feature]):
        raise ValueError(f"{feature} is not numeric; use categorical_direction")
    xs = X[feature].dropna()
    gv = np.unique(np.quantile(xs, np.linspace(0.02, 0.98, grid)))
    base = X[features].sample(min(sample, len(X)), random_state=0)
    if ax is None:
        _, ax = plt.subplots(figsize=(6, 4))
    ice_rows = base.sample(min(ice_n, len(base)), random_state=1)
    for _, r in ice_rows.iterrows():
        tmp = pd.DataFrame([r.to_dict()] * len(gv)); tmp[feature] = gv
        ax.plot(gv, _proba(model, tmp, features), color="0.8", lw=0.6)
    pdp = [_proba(model, base.assign(**{feature: v}), features).mean() for v in gv]
    ax.plot(gv, pdp, color="C0", lw=2.2, label="PDP")
    ax.set_xlabel(feature); ax.set_ylabel("predicted score")
    ax.set_title(f"PDP / ICE — {feature}"); ax.legend()
    return ax


def categorical_direction(model, X, y, features, col):
    """Per-level table for a categorical feature: count, mean predicted score,
    observed target rate, lift vs base, and direction (↑/↓ vs overall mean
    score). Shows which levels drive the score and which way. Also draws a bar
    of mean score per level with the base-rate reference."""
    s = _proba(model, X, features)
    d = pd.DataFrame({col: X[col].astype("object"), "score": s, "y": np.asarray(y)})
    base_score, base_y = float(d["score"].mean()), float(d["y"].mean())
    g = d.groupby(col, dropna=False).agg(
        count=("y", "size"), mean_score=("score", "mean"), target_rate=("y", "mean"))
    g["lift"] = g["target_rate"] / base_y if base_y > 0 else np.nan
    g["direction"] = np.where(g["mean_score"] >= base_score, "up", "down")
    g = g.sort_values("mean_score", ascending=False)

    ax = g["mean_score"].plot.bar(figsize=(min(10, 1 + 0.5 * len(g)), 4))
    ax.axhline(base_score, ls="--", lw=1, color="k")
    ax.set_ylabel("mean predicted score"); ax.set_title(f"Score by level — {col}")
    return g


# ----------------------------------------------------------------- campaign shape
def gains_chart(y, scores, ax=None):
    """Cumulative gains: share of all positives captured vs share of population
    contacted, ranked by score. The diagonal is random; the gap is your lift."""
    order = np.argsort(np.asarray(scores))[::-1]
    yy = np.asarray(y)[order]
    frac_pop = np.arange(1, len(yy) + 1) / len(yy)
    cum_pos = np.cumsum(yy) / yy.sum()
    if ax is None:
        _, ax = plt.subplots(figsize=(5, 5))
    ax.plot(frac_pop, cum_pos, label="model")
    ax.plot([0, 1], [0, 1], ls="--", color="k", label="random")
    ax.set_xlabel("population contacted"); ax.set_ylabel("positives captured")
    ax.set_title("Cumulative gains"); ax.legend()
    return ax


def score_distribution(scores, y=None, bins=40, ax=None):
    s = pd.Series(np.asarray(scores))
    if ax is None:
        _, ax = plt.subplots(figsize=(6, 4))
    if y is None:
        ax.hist(s, bins=bins)
    else:
        yy = np.asarray(y)
        for v in (0, 1):
            ax.hist(s[yy == v], bins=bins, alpha=0.5, density=True, label=f"target={v}")
        ax.legend()
    ax.set_xlabel("score"); ax.set_title("Score distribution")
    return ax


# ----------------------------------------------------------------- calibration
def calibration_plot(y, scores, bins=10, ax=None):
    """Reliability diagram on OOT: mean predicted score vs observed target rate
    per quantile bin. On the diagonal = well calibrated. Directly validates the
    downsampling->prior-shift calibration."""
    from sklearn.calibration import calibration_curve
    prob_true, prob_pred = calibration_curve(
        np.asarray(y), np.asarray(scores), n_bins=bins, strategy="quantile")
    if ax is None:
        _, ax = plt.subplots(figsize=(5, 5))
    ax.plot(prob_pred, prob_true, "o-", label="model")
    ax.plot([0, 1], [0, 1], ls="--", color="k", label="perfect")
    ax.set_xlabel("mean predicted"); ax.set_ylabel("observed rate")
    ax.set_title("Calibration (OOT)"); ax.legend()
    return ax


# ----------------------------------------------------------------- optional SHAP
def shap_beeswarm(model, X, features, sample=800, seed=0, max_display=15):
    """Optional, slow. Model-agnostic SHAP (Permutation explainer over
    predict_proba) + beeswarm for directionality. Returns mean|SHAP| per feature
    (for the cross-check). Categorical (string) features show spread but no
    colour gradient. Wrapped defensively — falls back to a mean|SHAP| bar."""
    import shap
    rng = np.random.default_rng(seed)
    idx = rng.choice(len(X), size=min(sample, len(X)), replace=False)
    Xs = X[features].iloc[idx].reset_index(drop=True)
    bg = Xs.iloc[: min(100, len(Xs))]
    f = lambda D: _proba(model, pd.DataFrame(D, columns=features), features)
    expl = shap.PermutationExplainer(f, bg)
    sv = expl(Xs, max_evals=2 * len(features) + 1)
    try:
        shap.plots.beeswarm(sv, max_display=max_display, show=True)
    except Exception:
        plt.figure(figsize=(6, 5))
        order = np.argsort(np.abs(sv.values).mean(0))[::-1][:max_display][::-1]
        plt.barh([features[i] for i in order], np.abs(sv.values).mean(0)[order])
        plt.title("mean |SHAP| (beeswarm unavailable)"); plt.tight_layout()
    return pd.Series(np.abs(sv.values).mean(0), index=features, name="shap")
