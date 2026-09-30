"""Offline smoke test.

Runs the real pipeline code end-to-end without a cluster. pyspark, flaml and
pyarrow are not installed in this sandbox, so this script injects *faithful,
minimal* stubs:
  - a pandas-backed fake Spark (filter / select / toPandas + eligibility query),
  - a fake flaml.AutoML wrapping a real sklearn GradientBoosting model,
  - a pandas.to_parquet capture (no parquet engine here),
  - a duck-typed config mirroring RunConfig's fields/properties.
Everything else is the real code from src/. Run: python tests/smoke_test.py
"""
import sys, json, pickle, hashlib, pathlib, tempfile
from types import ModuleType
from datetime import date
import numpy as np
import pandas as pd

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

# ---------------------------------------------------------------- capture parquet
PARQUET = {}
def _to_parquet(self, path, *a, **k): PARQUET[str(path)] = self.copy()
pd.DataFrame.to_parquet = _to_parquet

# ---------------------------------------------------------------- fake flaml
class AutoML:
    def fit(self, X_train, y_train, **kw):
        from sklearn.ensemble import GradientBoostingClassifier
        self._m = GradientBoostingClassifier(random_state=0, n_estimators=60).fit(
            np.asarray(X_train), np.asarray(y_train))
        self.best_estimator = "gbm_stub"
        self.best_config = {"n_estimators": 60, "learning_rate": 0.1}
        self.best_loss = 0.2
    def predict_proba(self, X):
        return self._m.predict_proba(np.asarray(X))
_flaml = ModuleType("flaml"); _flaml.AutoML = AutoML; sys.modules["flaml"] = _flaml

# ---------------------------------------------------------------- fake pyspark
class _Col:
    def __init__(self, n): self.n = n
    def __eq__(self, o): return ("==", self.n, o)
class _F:
    @staticmethod
    def col(n): return _Col(n)
class _DF:
    def __init__(self, pdf): self.pdf = pdf
    @property
    def columns(self): return list(self.pdf.columns)
    def filter(self, cond):
        if isinstance(cond, tuple) and cond[0] == "==":
            _, n, v = cond
            return _DF(self.pdf[self.pdf[n].astype(str) == str(v)])
        if isinstance(cond, str):
            q = cond.replace(" = ", " == ").replace(" AND ", " and ").replace(" OR ", " or ")
            return _DF(self.pdf.query(q))
        raise ValueError(cond)
    def select(self, *cols): return _DF(self.pdf[list(cols)].copy())
    def toPandas(self): return self.pdf.reset_index(drop=True).copy()
class _Reader:
    def __init__(self, reg): self.reg = reg
    def parquet(self, ref): return _DF(self.reg[ref])
class _Spark:
    def __init__(self, reg): self.reg = reg; self.read = _Reader(reg)
    def table(self, name): return _DF(self.reg[name])
_ps = ModuleType("pyspark"); _sql = ModuleType("pyspark.sql")
_sql.functions = _F; _sql.SparkSession = object; _sql.Window = object
_ps.sql = _sql; sys.modules["pyspark"] = _ps; sys.modules["pyspark.sql"] = _sql

# ---------------------------------------------------------------- fake pydantic
# Enough for configs/_schema.py to IMPORT (real validation is not exercised here).
class _BaseModel:
    def __init__(self, **kw):
        for k, v in kw.items(): setattr(self, k, v)
def _Field(*a, **k): return a[0] if a else None
def _passthrough(*a, **k): return lambda f: f
_pyd = ModuleType("pydantic")
_pyd.BaseModel = _BaseModel; _pyd.Field = _Field
_pyd.field_validator = _passthrough; _pyd.model_validator = _passthrough
sys.modules["pydantic"] = _pyd

# ---------------------------------------------------------------- duck-typed config
class M:
    time_budget, estimator_list = 30, ["lgbm"]
    eval_method, n_splits = "cv", 3
    ensemble, sample, early_stop, n_jobs, seed = False, True, True, 1, 42
    def model_dump(self): return {k: getattr(self, k) for k in
        ["time_budget", "estimator_list", "eval_method", "n_splits",
         "ensemble", "sample", "early_stop", "n_jobs", "seed"]}
class DS:
    def __init__(self, n): self.neg_per_pos, self.seed = n, 42
    def model_dump(self): return {"neg_per_pos": self.neg_per_pos, "seed": self.seed}
class Cfg:
    def __init__(self, downsample=None):
        self.product = "fx_activation"
        self.table = "hdfs:///retail/snapshots/modelling_panel"
        self.id_col, self.month_col = "cif", "snapshot_month"
        self.obs_date, self.oot_date, self.infer_date = date(2026,3,1), date(2026,6,1), date(2026,8,1)
        self.features_include = [f"f{i}" for i in range(8)]
        self.features_exclude = []
        self.eligibility_expr = "eligible_segment = 1 AND is_fx_active = 0"
        self.target_col, self.window_months = "target", 3
        self.model, self.downsample, self.calibration = M(), downsample, "prior_shift"
        self.metric, self.baseline = "roc_auc", "population_base_rate"
        self.min_base_rate, self.max_base_rate = 0.001, 0.90
        self.top_pct, self.top_n = [0.01, 0.10], [10000]
    @property
    def candidates(self): return list(self.features_include)
    @property
    def features(self): return [f for f in self.features_include if f not in self.features_exclude]
    def model_dump(self, mode=None):
        return {"product": self.product, "table": self.table, "id_col": self.id_col,
                "month_col": self.month_col, "obs_date": str(self.obs_date),
                "oot_date": str(self.oot_date), "infer_date": str(self.infer_date),
                "features_include": self.features_include, "features_exclude": self.features_exclude,
                "eligibility_expr": self.eligibility_expr, "target_col": self.target_col,
                "window_months": self.window_months, "model": self.model.model_dump(),
                "downsample": self.downsample.model_dump() if self.downsample else None,
                "calibration": self.calibration, "metric": self.metric, "baseline": self.baseline,
                "min_base_rate": self.min_base_rate, "max_base_rate": self.max_base_rate,
                "top_pct": self.top_pct, "top_n": self.top_n}

# ---------------------------------------------------------------- synthetic panel
def build_panel(n_cif=2000):
    from sklearn.datasets import make_classification
    rng = np.random.default_rng(0)
    months = [f"2026-{m:02d}-01" for m in range(1, 10)]
    frames = []
    for mi, mon in enumerate(months):
        Xm, ym = make_classification(n_samples=n_cif, n_features=8, n_informative=5,
                                     weights=[0.8], random_state=mi)
        d = pd.DataFrame(Xm, columns=[f"f{i}" for i in range(8)])
        d["cif"] = np.arange(n_cif)
        d["snapshot_month"] = mon
        d["target"] = ym
        d["eligible_segment"] = rng.integers(0, 2, n_cif)
        d["is_fx_active"] = rng.integers(0, 2, n_cif)
        frames.append(d)
    return pd.concat(frames, ignore_index=True)


def section(t): print("\n" + "=" * 8, t)


def test_pure_helpers():
    section("PURE HELPERS on sklearn breast_cancer")
    from sklearn.datasets import load_breast_cancer
    from sklearn.ensemble import RandomForestClassifier
    from src.leakage import leakage_report
    from src.feature_stats import (vif, mutual_info, univariate_summary,
                                    event_rate_by_category, signal_persistence)
    from src.evaluate import oot_evaluate
    from src.calibration import prior_shift, from_offset
    from src.importance import permutation_importance
    from src.contract import assert_training_contract
    from src.dataset import downsample_train

    bc = load_breast_cancer(as_frame=True)
    X = bc.data.copy(); X.columns = [c.replace(" ", "_") for c in X.columns]
    y = bc.target
    feats = X.columns.tolist()

    rep = leakage_report(X, y, feats)
    assert set(rep.columns) >= {"feature", "univariate_auc", "suspected_leak"}
    print("leakage_report rows:", len(rep), "| top auc:", round(rep['univariate_auc'].max(), 3))

    print("vif top:", round(vif(X, feats).iloc[0], 1))
    print("mutual_info top feature:", mutual_info(X, y, feats).index[0])
    us = univariate_summary(X, feats)
    assert set(us.columns) == {"pct_null", "min", "p1", "median", "p99", "max"}
    print("univariate_summary shape:", us.shape)

    Xc = X.assign(size_band=pd.qcut(X["mean_area"], 4, labels=list("ABCD")))
    er = event_rate_by_category(Xc, y, "size_band")
    assert {"count", "target_rate"} <= set(er.columns)
    print("event_rate_by_category:\n", er.round(3).to_string())

    rngd = np.random.default_rng(1)
    X_oot = X.copy()
    for c in feats[:5]:
        X_oot[c] = X_oot[c] + rngd.normal(0, X_oot[c].std(), len(X_oot))  # induce drift
    sp = signal_persistence(X, y, X_oot, y, feats)
    assert "psi" in sp and sp["flag"].any()
    print("signal_persistence flagged:", int(sp['flag'].sum()), "of", len(sp))

    model = RandomForestClassifier(n_estimators=60, random_state=0).fit(X.values, y.values)
    class W:  # wrap to expose predict_proba on a DataFrame
        def predict_proba(self, D): return model.predict_proba(np.asarray(D))
    s = W().predict_proba(X)[:, 1]
    m = oot_evaluate(y, s, "roc_auc", top_pct=[0.01, 0.10], top_n=[10000, 50])
    assert 0.5 <= m["oot_auc"] <= 1.0 and m["top_pct"]["top_1pct"]["lift"] >= 1.0
    assert "top_50" in m["top_n"] and "top_10000" not in m["top_n"]      # 10000 > n_oot -> skipped
    assert oot_evaluate(y, s, "roc_auc", [], [])["top_pct"] == {}        # empty lists accepted
    print("oot_evaluate: auc", round(m["oot_auc"], 3),
          "| top1%", {k: round(v, 3) for k, v in m["top_pct"]["top_1pct"].items()},
          "| top50", {k: round(v, 3) for k, v in m["top_n"]["top_50"].items()})

    imp = permutation_importance(W(), X, y, feats, n_repeats=2)
    assert imp["importance"].iloc[0] >= imp["importance"].iloc[-1]
    print("permutation_importance top:", imp.iloc[0]["feature"], round(imp.iloc[0]["importance"], 4))

    cal = prior_shift(0.05, 0.4); cal2 = from_offset(cal.offset)
    assert np.allclose(cal(s), cal2(s)) and cal.offset < 0
    print("calibration offset:", round(cal.offset, 3), "(deflates as expected)")

    ns = type("NS", (), {"id_col": "cif", "min_base_rate": 0.0, "max_base_rate": 1.0})()
    Xk = X.assign(cif=np.arange(len(X)))
    assert_training_contract(Xk, y, ns)
    yimb = pd.Series((np.arange(len(X)) % 5 == 0).astype(int))   # rare positives (~20%)
    Xd, yd = downsample_train(Xk, yimb, DS(1))
    assert yd.mean() > yimb.mean()
    print("downsample: base", round(float(yimb.mean()), 3), "->", round(float(yd.mean()), 3), "| rows", len(Xd))
    print("PURE HELPERS: PASS")


def test_end_to_end(panel):
    section("END-TO-END run() — basic (no downsample)")
    import src.run as run_mod
    run_mod.ART_ROOT = pathlib.Path(tempfile.mkdtemp()) / "artifacts"
    reg = {"hdfs:///retail/snapshots/modelling_panel": panel}
    spark = _Spark(reg)

    res = run_mod.run(Cfg(), spark)
    out = pathlib.Path(res["out"])
    for f in ["config.frozen.json", "leakage_report.csv", "oot_metrics.json",
              "permutation_importance.csv", "model.pkl", "model_card.json"]:
        assert (out / f).exists(), f"missing artifact {f}"
    print("artifacts written:", sorted(p.name for p in out.iterdir()))
    print("metrics:", {k: (round(v, 3) if isinstance(v, float) else v)
                       for k, v in res["metrics"].items() if not isinstance(v, dict)})
    assert "top_1pct" in res["metrics"]["top_pct"] and "top_10pct" in res["metrics"]["top_pct"]
    print("  top_pct:", {k: {kk: round(vv, 3) for kk, vv in v.items()}
                         for k, v in res["metrics"]["top_pct"].items()})
    print("  top_n  :", res["metrics"]["top_n"], "(10000 skipped when > n_oot)")

    scores = [v for k, v in PARQUET.items() if k.endswith("scores.parquet")][-1]
    assert list(scores.columns) == ["cif", "score", "score_raw", "calibrated",
                                    "config_hash", "feature_set_signature", "infer_date", "run_id"]
    assert scores["calibrated"].iloc[0] == False
    assert scores["score"].between(0, 1).all()
    print("score log cols OK | rows:", len(scores), "| calibrated:", bool(scores['calibrated'].iloc[0]))

    card = json.loads((out / "model_card.json").read_text())
    assert card["model_selected"]["best_config"] == {"n_estimators": 60, "learning_rate": 0.1}
    assert card["model_selected"]["best_cv_loss"] == 0.2 and card["top_importance"]
    print("card best_config:", card["model_selected"]["best_config"],
          "| best_cv_loss:", card["model_selected"]["best_cv_loss"])
    print("END-TO-END basic: PASS")
    return run_mod


def test_end_to_end_downsample(panel, run_mod):
    section("END-TO-END run() — with downsampling + auto-calibration")
    reg = {"hdfs:///retail/snapshots/modelling_panel": panel}
    res = run_mod.run(Cfg(downsample=DS(1)), _Spark(reg))
    out = pathlib.Path(res["out"])
    scores = [v for k, v in PARQUET.items() if k.endswith("scores.parquet")][-1]
    card = json.loads((out / "model_card.json").read_text())
    assert scores["calibrated"].iloc[0] == True
    assert not np.allclose(scores["score"].values, scores["score_raw"].values)
    assert card["calibration"] and card["calibration"]["offset"] < 0
    assert card["downsample"] == {"neg_per_pos": 1, "seed": 42}
    print("calibrated:", bool(scores['calibrated'].iloc[0]),
          "| offset:", round(card["calibration"]["offset"], 3),
          "| mean raw->cal:", round(float(scores['score_raw'].mean()), 3), "->",
          round(float(scores['score'].mean()), 3))
    print("END-TO-END downsample: PASS")


def test_inference(panel, run_mod):
    section("INFERENCE — real resolve/load_scorer/score_product off persisted artifacts")
    from src.inference import score_product, load_scorer, resolve_run, discover_products

    art = run_mod.ART_ROOT
    prods = discover_products(art)
    assert "fx_activation" in prods
    run_dir = resolve_run("fx_activation", art)               # latest = the downsample run
    cfg2, model, calibrate, model_hash = load_scorer(run_dir)  # frozen cfg + unpickled model + card offset
    assert (run_dir / "model.pkl").exists() and len(model_hash) == 12
    print("discovered:", prods, "| run:", run_dir.name,
          "| model_hash:", model_hash, "| calibrator:", getattr(calibrate, "method", None))

    long = score_product(_Spark({cfg2.table: panel}), cfg2, model,
                         calibrate, "2026-08-01", model_hash)
    assert list(long.columns) == ["cif", "product", "model_hash", "infer_date", "score"]
    assert (long["infer_date"] == "2026-08-01").all()
    assert long["score"].between(0, 1).all() and len(long) > 0
    assert (long["model_hash"] == model_hash).all()
    print("long-format cols OK | rows:", len(long), "| eligible-only scored")
    print(long.head(3).to_string(index=False))

    # promote-on-inference: promote the used model into a curated store, then reproduce from it
    from src.inference import (promote_model, write_manifest, ARTIFACT_FILES,
                               verify_model, hash_model_pkl, resolve_from_manifest)
    assert hash_model_pkl(run_dir) == model_hash
    assert verify_model(run_dir, model_hash) is True
    try:
        verify_model(run_dir, "deadbeef0000"); raise AssertionError("verify should have raised")
    except ValueError:
        pass

    store = art.parent / "06_models"                       # curated promoted store
    promoted = promote_model(run_dir, str(store), "fx_activation", run_dir.name)
    for f in ARTIFACT_FILES:
        assert (pathlib.Path(promoted) / f).exists(), f"promoted bundle missing {f}"

    batch = art.parent / "07_model_output" / "test"
    mpath = write_manifest(batch, {"scoring_run_id": "test", "scores_path": "hdfs:///x",
                                   "models_dir": str(store),
                                   "products": [{"product": "fx_activation", "run_id": run_dir.name,
                                                 "model_hash": model_hash, "infer_date": "2026-08-01",
                                                 "rows": len(long)}]})
    rd, cfg3, model3, cal3, mh3 = resolve_from_manifest(mpath, "fx_activation")   # promoted model
    assert pathlib.Path(rd) == pathlib.Path(promoted) and mh3 == model_hash
    assert isinstance(rd, str)                              # canonical path stays a string (hdfs-safe)
    # reinfer: rescore the promoted model on a DIFFERENT month, no local scratch run needed
    long2 = score_product(_Spark({cfg3.table: panel}), cfg3, model3, cal3, "2026-07-01", mh3)
    assert len(long2) > 0 and (long2["infer_date"] == "2026-07-01").all()
    print("promote + verify + reproduce OK ->", promoted)
    print("reinfer @2026-07-01:", len(long2), "rows | INFERENCE: PASS")


def test_analysis(panel, run_mod):
    section("ANALYSIS SUITE (display-only helpers, Agg backend)")
    import matplotlib; matplotlib.use("Agg")
    from src import analysis
    from src.inference import resolve_run, load_scorer
    from src.dataset import load_labelled
    from src.importance import permutation_importance

    cfg2, model, calibrate, _ = load_scorer(resolve_run("fx_activation", run_mod.ART_ROOT))
    X_oot, y_oot = load_labelled(_Spark({cfg2.table: panel}), cfg2, cfg2.oot_date)
    s = model.predict_proba(X_oot[cfg2.features])[:, 1]
    s = calibrate(s) if calibrate else s
    imp = permutation_importance(model, X_oot, y_oot, cfg2.features, n_repeats=2)
    analysis.importance_bar(imp)
    analysis.pdp_ice(model, X_oot, cfg2.features, cfg2.features[0], grid=6, ice_n=8)
    analysis.gains_chart(y_oot, s)
    analysis.score_distribution(s, y_oot)
    analysis.calibration_plot(y_oot, s, bins=6)
    print("importance_bar / pdp_ice / gains / score_dist / calibration all ran")
    print("ANALYSIS SUITE: PASS")


def test_rollup_semantics():
    section("ROLLUP SEMANTICS (pandas illustration of the Spark window bounds)")
    # rollups.py needs a real Spark session; here we just confirm the *intended*
    # month bounds: backward INCLUDES current month, forward EXCLUDES it.
    src = (ROOT / "src" / "rollups.py").read_text()
    assert "rangeBetween(-(months - 1), 0)" in src, "backward must include current month"
    assert "rangeBetween(1, months)" in src, "forward must exclude current month"
    months = pd.Series(range(1, 7))
    val = pd.Series([1, 0, 1, 0, 0, 1])  # activity per month
    w = 3
    bwd = [int(val[(months >= m - (w - 1)) & (months <= m)].sum()) for m in months]  # incl current
    fwd = [int(val[(months >= m + 1) & (months <= m + w)].sum()) for m in months]    # excl current
    print("month :", list(months)); print("value :", list(val))
    print("bwd(3, incl current):", bwd); print("fwd(3, excl current):", fwd)
    assert bwd[2] == val[0:3].sum()          # month 3 backward = months 1..3
    assert fwd[0] == val[1:4].sum()          # month 1 forward  = months 2..4
    print("ROLLUP SEMANTICS: PASS")


if __name__ == "__main__":
    panel = build_panel()
    test_pure_helpers()
    rm = test_end_to_end(panel)
    test_end_to_end_downsample(panel, rm)
    test_inference(panel, rm)
    test_analysis(panel, rm)
    test_rollup_semantics()
    print("\n" + "=" * 8, "ALL SMOKE TESTS PASSED")
