"""What the checks read from the data their own way, independently of the generator.

- Spec values restated from `truth["spec"]` alone: `expected_medians`, `expected_latent_means`,
  `trait_deviation`.
- Month-on-month events (`build_panel`, `oracle_events`, `leave_events`): mart and oracle side by
  side, sorted by client and month (`to_panel`), so each row sees the client's state at the end of
  last month (its previous row, or "empty" for a new client's first row, which is no transition).
  Events read from the mart are set against the oracle's chances, so the oracle is checked against
  the data, not the other way round.
- Forward windows (`realised_target`, `values_at`): the checks' own realised standard targets, a
  second implementation written from the spec's targets table, so the oracle checks compare two
  implementations. For an observation at month t: `any_flag` (the column is 1 in any month of
  (t, t+w]), `count_rise` (it rises month on month in (t, t+w]) or `sum` (over t+1..t+w); null
  where not eligible at t, where the client left or the window runs past the mart's last month.
"""

import numpy as np
import pandas as pd

from synthetic.checks.table import flags_as_bool, profile_of
from synthetic.spec.presets import LATENTS

KEYS = ["client_id", "snapshot_month"]

# The spec's standard targets: the event, the column it is read from, and eligibility at t as
# column → required value (docs/components/test_harness.md, "Ground truth and oracle").
STANDARD_TARGETS = {
    **{
        f"{key}_acquire": dict(event="any_flag", column=f"{key}_flag", eligible={f"{key}_flag": 0})
        for key in ("cc", "td", "wealth_digital", "wealth_trad", "ebanking")
    },
    **{
        f"{key}_open": dict(event="count_rise", column=f"{key}_cnt", eligible={})
        for key in ("loan_personal", "loan_auto", "loan_home")
    },
    "fx_activate": dict(event="any_flag", column="fx_active_flag", eligible={"fx_active_flag": 0}),
    "digital_activate": dict(
        event="any_flag",
        column="digital_active_flag",
        eligible={"ebanking_flag": 1, "digital_active_flag": 0},
    ),
    "cc_activate": dict(
        event="any_flag", column="cc_active_flag", eligible={"cc_flag": 1, "cc_active_flag": 0}
    ),
    "casa_reactivate": dict(
        event="any_flag",
        column="casa_active_flag",
        eligible={"casa_flag": 1, "casa_active_flag": 0},
    ),
    "spend_cc_next_3_months": dict(event="sum", column="spend_cc_vol", eligible={"cc_flag": 1}),
}
BINARY_TARGETS = [name for name, t in STANDARD_TARGETS.items() if t["event"] != "sum"]
LATENT_COLUMNS = ["z_wealth", "z_activity", "z_digital", "z_credit", "z_crossborder"]
PANEL_MART_COLUMNS = [
    "client_id",
    "snapshot_month",
    "subsegment",
    "nationality_group",
    "nationality",
    "employment_status",
    "income",
    "salary_transfer_flag",
    "onboarding_channel",
    "age",
    "relationship_days",
    "casa_flag",
    "cc_flag",
    "td_flag",
    "td_status",
    "wealth_digital_flag",
    "wealth_digital_status",
    "wealth_trad_flag",
    "wealth_trad_status",
    "ebanking_flag",
    "loan_personal_cnt",
    "loan_personal_maturity_months",
    "loan_auto_cnt",
    "loan_auto_maturity_months",
    "loan_home_cnt",
    "loan_home_maturity_months",
    "fx_active_flag",
    "digital_active_flag",
    "cc_active_flag",
    "casa_active_flag",
    "product_cnt",
]
PANEL_ORACLE_COLUMNS = [
    "client_id",
    "snapshot_month",
    *LATENT_COLUMNS,
    *[f"p_{key}_acquire" for key in ("cc", "td", "wealth_digital", "wealth_trad", "ebanking")],
    *[f"p_{key}_open" for key in ("loan_personal", "loan_auto", "loan_home")],
    *[
        f"p_{key}_{move}"
        for key in ("fx", "digital", "cc_activity", "casa_activity", "cc_revolver")
        for move in ("activate", "lapse")
    ],
    "revolver_flag",
]


def build_panel(spec: dict, mart: pd.DataFrame, oracle: pd.DataFrame) -> pd.DataFrame:
    """Mart and oracle side by side in client and month order (`to_panel`), with flags as bools
    (so the checks can use them as masks), each row's profile, whether it has a previous row
    (`has_prev`), whether its last month is known (`known`: a previous row, or after the panel's
    first month) and tenure in whole months (0 in the entry month)."""
    panel = flags_as_bool(to_panel(mart, oracle))
    for key in product_keys(spec, "loans"):  # NaN instead of NA, for plain numpy comparisons
        panel[f"{key}_maturity_months"] = panel[f"{key}_maturity_months"].astype("float64")
    panel["profile"] = profile_of(spec, panel)
    panel["has_prev"] = panel["client_id"].eq(panel["client_id"].shift())
    panel["known"] = panel["has_prev"] | (panel["snapshot_month"] > panel["snapshot_month"].min())
    month = pd.to_datetime(panel["snapshot_month"])
    month_end = month + pd.to_timedelta(month.dt.days_in_month - 1, unit="D")
    start = month_end - pd.to_timedelta(panel["relationship_days"], unit="D")
    panel["tenure_months"] = (month.dt.year - start.dt.year) * 12 + month.dt.month - start.dt.month
    return panel


def product_keys(spec: dict, kind: str) -> list[str]:
    """The spec's products of one kind."""
    return [key for key, p in spec["products"].items() if p["kind"] == kind]


def usage_flag(spec: dict, key: str) -> str:
    """The column of a usage chain: the spec's `flag`, by default `<key>_active_flag`."""
    return spec["products"][key].get("flag", f"{key}_active_flag")


def before(panel: pd.DataFrame, column: str, empty: object) -> np.ndarray:
    """Each row's `column` at the end of last month: its previous row, or `empty` if none."""
    return np.where(panel["has_prev"], np.roll(panel[column].to_numpy(), 1), empty)


def _event(scope: np.ndarray, at_risk: np.ndarray, realised: np.ndarray, chance: object) -> dict:
    """One event: rows with a previous month, rows at risk, the event read from the mart (NaN where
    it can't be read) and the chance applied."""
    return dict(
        scope=scope, at_risk=scope & at_risk, realised=realised.astype(float), chance=chance
    )


def oracle_events(spec: dict, panel: pd.DataFrame) -> dict[str, dict]:
    """Every event the oracle carries a chance for, read from the mart as month-on-month moves.

    A client's first row is no transition, so it is left out (its entry-month events too).
    """
    has_prev, events = panel["has_prev"].to_numpy(), {}
    cap = spec["holding_rules"]["max_loan_accounts"]
    for key, product in spec["products"].items():
        if product["kind"] == "holding":
            held_before = before(panel, f"{key}_flag", False).astype(bool)
            chance = panel[f"p_{key}_acquire"].to_numpy()
            events[f"{key} acquire"] = _event(has_prev, ~held_before, panel[f"{key}_flag"], chance)
        elif product["kind"] == "loans":
            cnt, cnt0 = panel[f"{key}_cnt"].to_numpy(), before(panel, f"{key}_cnt", 0)
            matured = before(panel, f"{key}_maturity_months", np.nan) == 1
            # Openings are count rises. When an account matures the count can't rise, and an
            # opening hides behind the closure: those rows are quantified in `_check_volumes`.
            opened = np.where(matured, np.nan, cnt > cnt0)
            chance = panel[f"p_{key}_open"].to_numpy()
            events[f"{key} open"] = _event(has_prev, (cnt0 < cap) | matured, opened, chance)
        elif product["kind"] == "usage":
            flag = usage_flag(spec, key)
            active_before = before(panel, flag, False).astype(bool)
            active = panel[flag].to_numpy()
            needs = product.get("requires")  # held at the end of last month
            eligible = before(panel, f"{needs}_flag", False).astype(bool) if needs else True
            chance = panel[f"p_{key}_activate"].to_numpy()
            events[f"{key} activate"] = _event(has_prev, ~active_before & eligible, active, chance)
            chance = panel[f"p_{key}_lapse"].to_numpy()
            events[f"{key} lapse"] = _event(has_prev, active_before, ~active, chance)
    return events


def leave_events(spec: dict, calib: dict, panel: pd.DataFrame) -> dict[str, dict]:
    """Losses of 0/1 products, at the constant leaving chance recorded in the truth."""
    has_prev, events = panel["has_prev"].to_numpy(), {}
    for key in product_keys(spec, "holding"):
        held_before = before(panel, f"{key}_flag", False).astype(bool)
        chance = np.full(len(panel), calib[key]["leave_chance"])
        events[f"{key} leave"] = _event(has_prev, held_before, ~panel[f"{key}_flag"], chance)
    return events


def realised_target(mart: pd.DataFrame, target: str, w: int) -> pd.Series:
    """The realised `target` over the `w` months after each row's month, aligned with `mart`.

    0/1 (or the window sum) where defined, NaN where not eligible, left or past the last month.
    """
    spec = STANDARD_TARGETS[target]  # an unknown target raises KeyError
    values = values_at(mart, spec["column"], range(w + 1))
    future = values[:, 1:]
    if spec["event"] == "any_flag":
        hit = (future == 1).any(axis=1)
    elif spec["event"] == "count_rise":
        hit = (np.diff(values, axis=1) > 0).any(axis=1)
    else:
        hit = future.sum(axis=1)
    eligible = np.ones(len(mart), dtype=bool)
    for column, value in spec["eligible"].items():
        eligible &= mart[column].astype("float64").to_numpy() == value
    defined = eligible & ~np.isnan(future).any(axis=1)
    return pd.Series(np.where(defined, hit, np.nan), index=mart.index, name=target)


def values_at(mart: pd.DataFrame, column: str, offsets: range | list[int]) -> np.ndarray:
    """Rows × offsets: each row's client's `column` that many months after the row's month.

    Offsets may be negative (earlier months). NaN where the client has no row in that month or the
    month lies outside the mart's months. Mart rows may come in any order.
    """
    client, month, n_months = _positions(mart)
    grid = np.full((client.max() + 1, n_months), np.nan)
    grid[client, month] = mart[column].astype("float64").to_numpy()
    at = month[:, None] + np.asarray(offsets)[None, :]
    inside = (at >= 0) & (at < n_months)
    values = np.full(at.shape, np.nan)
    values[inside] = grid[np.broadcast_to(client[:, None], at.shape)[inside], at[inside]]
    return values


def _positions(mart: pd.DataFrame) -> tuple[np.ndarray, np.ndarray, int]:
    """Each row's client position, month position (0 = the mart's first month), and the number of
    months from the first to the last; raises on duplicate client-months."""
    client = pd.factorize(mart["client_id"])[0]
    stamps = pd.to_datetime(mart["snapshot_month"])
    number = (stamps.dt.year * 12 + stamps.dt.month).to_numpy()
    month = number - number.min()
    n_months = int(month.max()) + 1
    if np.bincount(client * n_months + month).max() > 1:
        raise ValueError("the mart has duplicate client-months")
    return client, month, n_months


def to_panel(mart: pd.DataFrame, oracle: pd.DataFrame) -> pd.DataFrame:
    """Mart and oracle columns side by side, sorted by client and month, indexed 0..n−1.

    Raises unless both tables hold the same client-months.
    """
    mart, oracle = (df.sort_values(KEYS, ignore_index=True) for df in (mart, oracle))
    if not mart[KEYS].equals(oracle[KEYS]):
        raise ValueError("oracle rows must line up with mart rows")
    return pd.concat([mart, oracle.drop(columns=KEYS)], axis=1)


def observation_month(mart: pd.DataFrame) -> pd.Timestamp:
    """The mart's middle month, for one row per client (of 24: month 12, so 6-month windows fit)."""
    months = np.sort(pd.to_datetime(mart["snapshot_month"]).unique())
    return pd.Timestamp(months[(len(months) - 1) // 2])


def expected_medians(spec: dict) -> dict[str, float]:
    """Subsegment median incomes, as the spec states them."""
    return {name: s["median_income"] for name, s in spec["subsegments"].items()}


def expected_latent_means(spec: dict, df: pd.DataFrame) -> np.ndarray:
    """Each row's trait means, (rows, traits): subsegment mean + nationality shift + employment
    shift."""
    subs = spec["subsegments"]
    rows = zip(df["subsegment"], df["nationality_group"], df["employment_status"], strict=True)
    return np.array(
        [
            np.add(subs[s]["latent_mean"], spec["latent_shift_nationality"][g])
            + spec["latent_shift_employment"][e]
            for s, g, e in rows
        ]
    ).reshape(len(df), len(LATENTS))


def trait_deviation(spec: dict, df: pd.DataFrame, trait: str) -> np.ndarray:
    """Δz = z − m for one trait: the row's `z_<trait>` less its restated mean."""
    means = expected_latent_means(spec, df)[:, LATENTS.index(trait)]
    return df[f"z_{trait}"].to_numpy(dtype=float) - means
