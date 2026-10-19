"""Checks of a generated dataset, written from the spec, never from the generator's code.

Each family is one module with a `check_<family>(mart, oracle, truth)` returning a table (check,
stratum, n, expected, realised, tolerance, passed, rule); `suite` lists the families and runs them
on a written dataset, each in its own process. `table` holds the row helpers and estimators;
`events` reads the data the checks' own way (month-on-month events, forward-window targets, spec
values restated); `switches` checks the off-by-default switches (dirty data, extra columns), which
are not a family. The checks call exactly two generator functions, both under test:
`mechanisms.mart.parse_column` (every name parses) and `truth.oracle.window_probability` (the
ceiling). They never call the mechanisms that make the data, so a generator bug can't pass its own
check.
"""
