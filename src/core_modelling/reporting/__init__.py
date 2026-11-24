"""Reports: one writer, five chart primitives and the shared blocks (D-036, D-136).

`html.py` turns a stage's sections into one self-contained HTML file and styles tables,
`charts.py` holds the chart primitives that apply the chart rules, `blocks.py` the blocks every
report shares (the choices table, the identity values, headline numbers, warnings, "not
available" lines, the appendix), `formats.py` how a table's numbers read, by column name,
and `theme.py` the neutral palette. The package runs no stage: stages hand it tables and
figures. `training_views.py` turns Training's stored tables into the views notebook 04 and
Evaluation's report share, reading the run folder's names from `run_artifacts.py`. Nothing in
here is public API (D-137); stages import by module.
"""
