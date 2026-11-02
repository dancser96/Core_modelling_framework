"""Spec of the feature-store extract (`fs_extract`): a second feature source beside the mart.

It stands in for a saved feature-store dataset that a use case joins like any other source: its
own key names (`customer_no`, the mart's client id as a string; `as_of_date`, the month's last
day), about 85% of the clients (chosen once per client), and six features, each a moderate proxy
of one hidden trait: a standard normal mixing the trait's normal score with noise at the rank
correlation `rank_corr`, then a monotone `form` (`count`: round(median · e^(spread · s));
`score`: round(centre + scale · s), clipped; `logistic`: the logistic of centre + scale · s, three
decimals; `levels`: cut at the standard normal quantiles of the level shares, listed from the
trait's low end). Its look-ahead trap column is in the trap list (`spec.traps`, kind
`lookahead`). Tables in docs/components/test_harness.md ("Feature-store extract") explain it.
"""

# fmt: off
EXTRACT = {
    "table": "fs_extract",
    "coverage": 0.85,  # share of clients in the extract, in every one of their months
    "rank_corr_range": [0.4, 0.6],  # a feature's rank correlation with its trait: a moderate proxy
    "features": {
        "app_sessions_30d": dict(trait="digital", rank_corr=0.55, form="count",
                                 median=12, spread=0.8),
        "bureau_score": dict(trait="credit", rank_corr=0.5, form="score",
                             centre=650, scale=80, low=300, high=900),
        "external_assets_band": dict(trait="wealth", rank_corr=0.5, form="levels",
                                     levels={"E": 0.3, "D": 0.3, "C": 0.2, "B": 0.12, "A": 0.08}),
        "travel_spend_share": dict(trait="crossborder", rank_corr=0.5, form="logistic",
                                   centre=-1.5, scale=1.0),
        "preferred_channel": dict(trait="digital", rank_corr=0.55, form="levels",
                                  levels={"branch": 0.25, "web": 0.3, "mobile": 0.45}),
        "salary_regularity_score": dict(trait="activity", rank_corr=0.45, form="logistic",
                                        centre=0.0, scale=1.0),
    },
}
# fmt: on
