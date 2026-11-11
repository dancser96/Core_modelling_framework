"""Every statistical calculation of the framework, on counts (D-135, D-137).

A statistic is a function of one feature's cells (the counts table rows for a set of periods)
or of plain arrays and frames, with numbers and frames out: nothing in here reads a table, a
file or Spark, so every stage computes the same numbers from the same functions. The modules:
`cells.py` (cells pooled into count tables and shares), `concordance.py` (the concordance, its
SEs, Cochran's Q, the level encoding, the best order), `scope.py` (a feature's concordance over
a scope, the rules every stage shares), `capture.py` (an ordered list cut at shares of its
rows), `distributions.py` (binning, chart groups, PSI, new levels, the standardised difference,
Cohen's h and d), `intervals.py` (Wilson and t intervals) and `association.py` (the pairwise
association table and the redundancy clusters). Nothing is public API (D-024): stages import
the functions they need by module.
"""
