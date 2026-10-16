"""The month's rows: what upstream would publish (mart) and the hidden truth beside it (oracle).

Called by the month loop (`generate.advance_simulation`) once a panel month has run. Mart rows hold
the keys, the client description, day counters, holdings and states, the current-month amounts and
the columns derived from each client's history (rollups, recency, ratios: `mart`), then the trap
columns that need no look-ahead and the extra columns (`traps`), in the spec's column order (the
look-ahead trap columns join before the other trap columns once the month is final); oracle rows
hold the hidden traits, the chance behind every event, the hidden client attributes (true income,
wealth base, remitter and school-fee payer flags, bonus month), the hidden chains (revolver state)
and the power-law multipliers. Flags become 0/1 integers, the mart's flag type.
"""

import numpy as np
import pandas as pd

from synthetic.holdings import holding_columns
from synthetic.mart import history_columns
from synthetic.population import client_age, months_on_book
from synthetic.presets import LATENTS

DESCRIPTION_COLUMNS = [
    "segment",
    "subsegment",
    "nationality_group",
    "nationality",
    "employment_status",
    "income",
    "salary_transfer_flag",
    "emirate",
]
# Oracle columns from the client table: hidden attributes, drawn once per client.
HIDDEN_CLIENT_COLUMNS = [
    "true_income",
    "wealth_base",
    "remitter_flag",
    "school_payer_flag",
    "bonus_month",
]


def month_rows(
    sim: dict,
    chances: dict[str, np.ndarray],
    mart_amounts: dict[str, object],
    oracle_amounts: dict[str, np.ndarray],
    traps: dict[str, object],
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The mart rows and oracle rows of the month; day counters are as of the month's last day.

    `mart_amounts` and `oracle_amounts` are the month's amount columns (`amounts.step_amounts`),
    `traps` its trap and extra columns (`traps.trap_columns`, `traps.extra_columns`).
    """
    clients, month = sim["clients"], sim["month"]
    month_end = (month + 1).astype("datetime64[D]").astype(int) - 1
    keys = {
        "client_id": clients["client_id"].to_numpy(),
        "snapshot_month": [month.astype("datetime64[D]").item()] * len(clients),
    }
    mart_holdings, hidden_holdings = holding_columns(sim["spec"], sim["holdings"])
    mart = pd.DataFrame(
        {
            **keys,
            **{col: clients[col].to_numpy() for col in DESCRIPTION_COLUMNS},
            "age": client_age(clients, month),
            "residence_days": (month_end - clients["residence_start"]).astype("Int64").array,
            "relationship_days": month_end - clients["relationship_start"].to_numpy(),
            **mart_holdings,
            **mart_amounts,
            **history_columns(sim["history"], months_on_book(clients, month), month.astype(int)),
            **traps,
        }
    )
    oracle = pd.DataFrame(
        {
            **keys,
            **{f"z_{n}": sim["z"][:, i] for i, n in enumerate(LATENTS)},
            **{f"p_{event}": chance for event, chance in chances.items()},
            **{col: clients[col].to_numpy() for col in HIDDEN_CLIENT_COLUMNS},
            **hidden_holdings,
            **oracle_amounts,
        }
    )
    return with_int_flags(mart), with_int_flags(oracle)


def with_int_flags(df: pd.DataFrame) -> pd.DataFrame:
    """`*_flag` columns as 0/1 int32, the mart's flag type (test_harness.md, types).

    Selected by name, as the checks read them; a boolean column with another name, or a flag that
    isn't boolean, is a naming error and fails loud.
    """
    flags = [c for c in df.columns if c.endswith("_flag")]
    bools = [c for c, dtype in df.dtypes.items() if dtype == np.dtype(bool)]
    if set(flags) != set(bools):
        raise ValueError(
            f"flags must be boolean and booleans named *_flag: {set(flags) ^ set(bools)}"
        )
    return df.astype(dict.fromkeys(flags, "int32"))
