"""The mechanisms of the synthetic book: the functions that turn the spec into months of data.

`clients` draws who the clients are (description, income, hidden traits and attributes);
`holdings` gives every client's monthly chances and moves what they hold; `seasons` holds the
calendar effects; `variation`, `accounts`, `cards` and `logins` make the amounts, which `amounts`
runs in order each month; `mart` names the columns and derives rollups, recency and ratios;
`traps` adds the trap columns and the dirty-data defects. `synthetic.generate` runs them month by
month.
"""
