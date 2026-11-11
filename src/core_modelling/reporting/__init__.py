"""Reports: one writer, five chart primitives and the shared blocks (D-036, D-136).

`html.py` turns a stage's sections into one self-contained HTML file and styles tables,
`charts.py` holds the chart primitives that apply the chart rules, `blocks.py` the blocks every
report shares (the choices table, the identity values, headline numbers, warnings, "not
available" lines, the appendix), `formats.py` how a table's numbers read, by column name,
and `theme.py` the neutral palette. The package knows nothing about any stage: stages hand it
tables and figures. Nothing in here is public API (D-137); stages import by module.
"""
