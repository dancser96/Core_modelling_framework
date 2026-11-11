"""Every statistical calculation of the framework, on counts (D-135, D-137).

A statistic is a function of one feature's cells (the counts table rows for a set of periods)
or of plain arrays and frames handed in, with numbers and frames out: nothing in here reads a
table, a file or Spark, so EDA, Feature Checks, Training, Evaluation and Monitoring compute the
same numbers from the same functions. The modules are named for their concept:
`cells.py` (one feature's cells pooled into the count tables and shares the others read),
`concordance.py` (the concordance, its standard error, Cochran's Q, the shrunk level encoding and
the best order), `scope.py` (a feature's concordance over a scope: its SE, direction,
availability guards and null concordance, the rules every stage shares), `capture.py` (an ordered
list cut at shares of its rows: counts, lift and capture), `distributions.py` (the edges rule
that bins a numeric, the merge rule for charts, PSI, new levels, the standardised difference,
Cohen's h and d), `intervals.py` (Wilson and t intervals) and `association.py` (the pairwise
association table and the redundancy clusters cut from it).
Nothing is public API (D-024): stages import the functions they need by module.
"""
