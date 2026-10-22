# No pickle at promotion: the disadvantages

**Verdict:** manageable for the three boosters, but the model we promote can't be the FLAML or
scikit-learn object we trained and evaluated. It is rebuilt from plain parts, and proving that the
rebuild is the same model is the main cost.

**Related:** D-037, D-051, D-094. _Scope (D-051): only what moves from the sandpit to
production must avoid pickle; whatever is saved on HDFS in the sandpit may be pickle. "Verified"
means run on the pinned versions._

1. **The evaluated model isn't the promoted one.** Unless Evaluation scores the non-pickle bundle
   too, the evidence (metrics, card, sign-off) was produced by a different object, and two scoring
   paths can drift apart.
2. **Fewer families reach production.** LightGBM (text) and XGBoost (JSON) round-trip identically;
   CatBoost only as binary `.cbm`, since its JSON drifts by up to 1e-15 (all verified).
   scikit-learn's forests have no format at all. FLAML must not search a family we can't promote,
   or a winning model gets stuck in the sandpit. Strict JSON would also drop CatBoost (D-037).
3. **More of our own code.** FLAML's `AutoML` object and scikit-learn's encoders and calibrators
   can't move. Encoding, calibration (Platt, isotonic) and the prior shift become our own
   parameters and predict code, and inference redoes FLAML's in-memory preprocessing (D-094). With
   pickle, one `predict_proba` call would do.
4. **Library upgrades.** Production must keep loading old bundles when the pins move (D-047).
   XGBoost promises that older JSON models load; LightGBM and CatBoost make no formal promise, so
   every pin bump needs a reload test against stored predictions.
5. **MLflow, if its registry is the promotion path** (unverified; the bank's version isn't
   pinned). Its default flavors for scikit-learn models, LightGBM's scikit-learn API and custom
   `pyfunc` chains all pickle. The way round it is to register the bundle as plain files and load
   it with our own code, which loses MLflow's `pyfunc` loading, `spark_udf` and serving. "Models
   from code" avoids pickle but moves executable code instead.
6. **Security still has to accept the alternatives.** `.cbm` is binary and LightGBM's model is
   text, not JSON.

**What the scope makes easier:** the sandpit can pickle freely (FLAML objects, caches, notebook
work), so one check at promote replaces any codebase-wide ban.

## Open questions
- **Q297** The promote gate: the non-pickle bundle is written at training and Evaluation scores it
  (one scoring path); promote accepts only listed file types; pin bumps rerun stored bundles
  against stored predictions. Default: yes to all three.
- **Q298** (first raised as Q296, a number D-106 has since reused) Strict JSON, or any
  non-executable plain data, JSON preferred? This decides CatBoost. Default: plain data, as D-051
  reads now.
- **Q299** Who confirms with security that `.cbm`, LightGBM's text model and, if it is ever used,
  MLflow's models from code are acceptable? Default: the SDS raises it through the CDS before the
  pre-release.
