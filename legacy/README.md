# legacy/propensity_crunch — reference only

The working implementation from the 2–3 week crunch that produced scores for ~10 retail products:
configs, `src/` modules, stage notebooks and an offline smoke test.

- **Reference, not a constraint.** Reuse ideas and proven logic, and rewrite freely. See
  `docs/context/lessons.md` for what worked, what broke, and a file map.
- **Don't import from it and don't edit it.** It isn't part of the package, and linting and tests
  exclude it.
- **Close to, but not exactly, the internal state.** Some changes made inside the bank were never
  brought back. Reported: plot tweaks. Likely but unverified: a PR-AUC line in OOT evaluation, a
  trial-count inspection cell, per-product downsampling ratios, and possibly a prevalence-based MI
  skip.
- Its own offline smoke test (stub-based) still runs from inside the folder:
  `cd legacy/propensity_crunch && python tests/smoke_test.py`.
