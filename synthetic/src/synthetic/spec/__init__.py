"""The spec of the synthetic retail book, as plain data: rules and numbers, no logic.

`presets` holds the population (subsegments, profiles, mixes, income) and assembles `RETAIL`, the
one spec dict every mechanism reads, plus the presets (`unit`, `canonical`); `products` holds what
clients hold and how often that changes; `amounts` how large amounts are, how they move and when
(`LEVELS`, `SEASONS`); `traps` the trap list. The only functions are two small dict builders in
`presets`. Another domain or entity is another spec, not new code. Tables in
docs/components/test_harness.md explain the values.
"""
