"""Trap columns and dirty data (test_harness.md, "Trap summary"; D-064).

A trap column ends in `_trap_<kind>` (`trap_name`) and takes its parameters from the spec's trap
list (`spec.traps.TRAPS`, looked up by kind and column, `trap_record`). By when they are known:
- persistent per client, drawn with the client: the insurance premium, the preferred language and
  the paper-statement flag (`start_trap_state`); the consent flag, the referral branch code and
  loyalty membership (`start_noise_state`, the `noise` stream);
- monthly: those three, the branch visits and the all-null legacy grade (`trap_columns`); the
  consent flag, the branch code, the two constants, the redundant relationship months and the two
  low-fill columns (`noise_columns`). Null controls and quality columns depend on nothing else, so
  their AUC is 0.5; the redundant column repeats `relationship_days`;
- look-ahead (`finalize_lookahead`): the leaks, the upstream target, the missing leak, the process
  leaks and the shifted columns read the months after their own, so a panel month is final only
  once the next `lookahead_months` months exist (fewer at the panel's end). These are the only
  columns that look ahead; their draws are sized by the month's rows, never by outcomes, so prefix
  stability holds for every other column.
Extra columns (`extra_columns`, off by default) are weak (a hidden trait plus noise) or pure noise.

Dirty data (off by default): `apply_dirty` plants duplicate client-months, a month whose login
columns are null (an outage), declared income × 12 from one month on (a unit change) and a few
current/savings balances × 1,000 (typos) in a finished panel, and returns the record that goes to
`truth["dirty"]`; `dirty_panel` does it for the month loop's months (small presets: the panel is
held in memory). Its draws come from the `traps` stream after every month has run, so switching
the defects on changes no clean value; the oracle stays clean. Streams: `traps`, `leaks`, `extras`,
`noise` (the 0.5.0 noise and quality columns) and `card_leaks` (the 0.5.0 look-ahead draws).
"""

import numpy as np
import pandas as pd
import pyarrow as pa
from scipy.stats import norm

from synthetic.spec.presets import LATENTS

TRAP_KINDS = ("leak", "upstream_target", "process_leak", "shifted", "null_control",
              "near_constant", "all_null", "weak", "noise", "high_cardinality", "constant",
              "redundant", "low_fill", "missing_leak")  # fmt: skip


def trap_name(name: str, kind: str) -> str:
    """`{name}_trap_{kind}`: a trap column (D-064), e.g. `extra_0001_trap_weak`."""
    if kind not in TRAP_KINDS:
        raise ValueError(f"unknown trap kind {kind!r}; one of {TRAP_KINDS}")
    return f"{name}_trap_{kind}"


LEAK = trap_name("cc_preapproval_score", "leak")
CAMPAIGN = trap_name("cc_campaign_response_score", "leak")
UPSTREAM = trap_name("cc_acquire_next_3_months_flag", "upstream_target")
APPLICATION = trap_name("application_loan_personal_cnt", "process_leak")
SHIFTED_OF = "loan_personal_bal"  # the real column the shifted trap column holds a month on
SHIFTED = trap_name(SHIFTED_OF, "shifted")
SHIFTED_SUFFIX = trap_name("", "shifted")  # a shifted column's name is its real column's plus this
PREMIUM = trap_name("insurance_premium_vol", "null_control")
BRANCH_VISITS = trap_name("branch_visit_cnt", "null_control")
LANGUAGE = trap_name("preferred_language", "null_control")
PAPER_STATEMENT = trap_name("paper_statement_flag", "near_constant")
RISK_GRADE = trap_name("legacy_risk_grade", "all_null")
OFFER_CODE = trap_name("cc_offer_code", "missing_leak")
CC_APPLICATION = trap_name("application_cc_cnt", "process_leak")
CC_SHIFTED = trap_name("cc_limit", "shifted")
CONSENT = trap_name("marketing_consent_flag", "null_control")
BRANCH_CODE = trap_name("referral_branch_code", "high_cardinality")
COUNTRY = trap_name("booking_country", "constant")
CYCLE_DAYS = trap_name("statement_cycle_days", "constant")
RELATIONSHIP_MONTHS = trap_name("relationship_months", "redundant")
LOYALTY = trap_name("loyalty_points_bal", "low_fill")
COMPLAINT = trap_name("complaint_category", "low_fill")
# Written type of each trap column; the all-null grade is a string column, not null-typed.
TRAP_TYPES = {
    LEAK: pa.int64(),
    CAMPAIGN: pa.int64(),
    UPSTREAM: pa.int64(),  # 0/1 with nulls
    APPLICATION: pa.int64(),
    SHIFTED: pa.float64(),
    OFFER_CODE: pa.string(),  # null where no offer
    CC_APPLICATION: pa.int64(),
    CC_SHIFTED: pa.float64(),
    PREMIUM: pa.float64(),
    BRANCH_VISITS: pa.int64(),
    LANGUAGE: pa.string(),
    PAPER_STATEMENT: pa.int32(),  # a flag
    RISK_GRADE: pa.string(),
    CONSENT: pa.int32(),  # a flag
    BRANCH_CODE: pa.string(),
    COUNTRY: pa.string(),
    CYCLE_DAYS: pa.int64(),
    RELATIONSHIP_MONTHS: pa.int64(),
    LOYALTY: pa.float64(),  # null for clients outside the scheme
    COMPLAINT: pa.string(),  # null where no complaint
}
KEYS = ["client_id", "snapshot_month"]
SUMMARY_COLUMNS = ["product", "target", "kind", "column", "trap_column", "parameters", "expected"]


def trap_record(spec: dict, kind: str, column: str | None = None) -> dict:
    """The one trap of `kind` (and `column`, when given) in the spec's trap list."""
    found = [
        t for t in spec["traps"] if t["kind"] == kind and (column is None or t["column"] == column)
    ]
    if len(found) != 1:
        raise ValueError(f"the spec has {len(found)} traps of kind {kind!r} column {column!r}")
    return found[0]


def trap_summary(spec: dict) -> pd.DataFrame:
    """The spec's trap list as a table, one row per trap (trap columns and real-column traps)."""
    return pd.DataFrame(spec["traps"], columns=SUMMARY_COLUMNS)


def lookahead_months(spec: dict) -> int:
    """Months after its own that a panel month's look-ahead columns read: the leaks', the upstream
    target's and the missing leak's windows, the shifted columns' shifts, and the process leaks'
    next month."""
    windowed = ("leak", "upstream_target", "missing_leak")
    windows = [t["parameters"]["w"] for t in spec["traps"] if t["kind"] in windowed]
    shifts = [t["parameters"]["months"] for t in spec["traps"] if t["kind"] == "shifted"]
    return max(*windows, *shifts, 1)


def _zipf_choice(
    levels: np.ndarray, exponent: float, n: int, rng: np.random.Generator
) -> np.ndarray:
    """`n` draws of `levels` with Zipf frequencies (level k weighs k^-exponent); one draw each."""
    zipf = np.arange(1, len(levels) + 1) ** -float(exponent)
    return rng.choice(levels, size=n, p=zipf / zipf.sum())


def _lognormal_amount(median: float, sigma: float, n: int, rng: np.random.Generator) -> np.ndarray:
    """`n` lognormal amounts around `median` (log-scale sd `sigma`) to 0.01; one normal each."""
    return np.round(np.exp(np.log(median) + sigma * rng.standard_normal(n)), 2)


def start_trap_state(spec: dict, n: int, rng: np.random.Generator) -> dict[str, np.ndarray]:
    """Persistent trap values of `n` new clients: premium, language, paper-statement flag.

    Draws, one per client each: the premium's normal, the language, the paper-statement uniform.
    """
    premium = trap_record(spec, "null_control", PREMIUM)["parameters"]
    language = trap_record(spec, "null_control", LANGUAGE)["parameters"]
    paper = trap_record(spec, "near_constant", PAPER_STATEMENT)["parameters"]
    levels = np.array(language["levels"], dtype=object)
    return {
        "premium": _lognormal_amount(premium["median"], premium["sigma"], n, rng),
        "language": _zipf_choice(levels, language["exponent"], n, rng),
        "paper_statement": (rng.random(n) >= paper["share_zero"]).astype("int32"),
    }


def trap_columns(
    spec: dict, state: dict[str, np.ndarray], rng: np.random.Generator
) -> dict[str, object]:
    """The month's null controls and quality columns, in the mart's order.

    Branch visits: 0 with the structural-zero share, else Poisson with the spec's mean. Draws, one
    per client each: the zero uniform, the Poisson count.
    """
    visits = trap_record(spec, "null_control", BRANCH_VISITS)["parameters"]
    n = len(state["premium"])
    structural_zero = rng.random(n) < visits["zero_share"]
    count = rng.poisson(visits["mean"], n)
    return {
        PREMIUM: state["premium"],
        BRANCH_VISITS: np.where(structural_zero, 0, count).astype("int64"),
        LANGUAGE: state["language"],
        PAPER_STATEMENT: state["paper_statement"],
        RISK_GRADE: np.full(n, None, dtype=object),
    }


def start_noise_state(spec: dict, n: int, rng: np.random.Generator) -> dict[str, np.ndarray]:
    """Persistent noise values of `n` new clients: consent flag, referral branch code, loyalty
    membership.

    Draws, one per client each: the consent uniform, the branch code, the loyalty uniform.
    """
    consent = trap_record(spec, "null_control", CONSENT)["parameters"]
    branch = trap_record(spec, "high_cardinality", BRANCH_CODE)["parameters"]
    loyalty = trap_record(spec, "low_fill", LOYALTY)["parameters"]
    levels = np.array(
        [f"{branch['prefix']}{k:03d}" for k in range(1, branch["levels"] + 1)], dtype=object
    )
    return {
        "consent": (rng.random(n) < consent["share_one"]).astype("int32"),
        "branch_code": _zipf_choice(levels, branch["exponent"], n, rng),
        "has_loyalty": rng.random(n) < loyalty["fill_share"],
    }


def noise_columns(
    spec: dict,
    state: dict[str, np.ndarray],
    relationship_days: np.ndarray,
    rng: np.random.Generator,
) -> dict[str, object]:
    """The month's noise, constant, redundant and low-fill columns, in the mart's order.

    `relationship_days` is the month's real column the redundant one repeats. Loyalty points are
    a fresh lognormal amount each month for members, NaN for the rest; a complaint category is
    filled at the fill share, None otherwise. Draws, one per client each: the points' normal, the
    complaint uniform, the complaint level.
    """
    country = trap_record(spec, "constant", COUNTRY)["parameters"]
    cycle = trap_record(spec, "constant", CYCLE_DAYS)["parameters"]
    redundant = trap_record(spec, "redundant", RELATIONSHIP_MONTHS)["parameters"]
    loyalty = trap_record(spec, "low_fill", LOYALTY)["parameters"]
    complaint = trap_record(spec, "low_fill", COMPLAINT)["parameters"]
    n = len(state["consent"])
    points = _lognormal_amount(loyalty["median"], loyalty["sigma"], n, rng)
    filed = rng.random(n) < complaint["fill_share"]
    category = rng.choice(np.array(complaint["levels"], dtype=object), size=n)
    months = np.floor(relationship_days / redundant["days_per_month"]).astype("int64")
    return {
        CONSENT: state["consent"],
        BRANCH_CODE: state["branch_code"],
        COUNTRY: np.full(n, country["value"], dtype=object),
        CYCLE_DAYS: np.full(n, cycle["value"], dtype="int64"),
        RELATIONSHIP_MONTHS: months,
        LOYALTY: np.where(state["has_loyalty"], points, np.nan),
        COMPLAINT: np.where(filed, category, None),
    }


def finalize_lookahead(
    spec: dict,
    frames: list[tuple[pd.DataFrame, pd.DataFrame]],
    rng: np.random.Generator,
    card_rng: np.random.Generator,
) -> pd.DataFrame:
    """The oldest buffered month's mart rows with the look-ahead columns, placed before the
    month's other trap columns.

    `frames` are consecutive panel months as (mart, oracle), the month to finalise first, then up
    to `lookahead_months` later ones (fewer at the panel's end). Draws, per row of the month: one
    normal per leak, then the loan application uniform, from `rng` (the `leaks` stream); the card
    application uniform, the offer fill uniform, then the offer code, from `card_rng` (the
    `card_leaks` stream, so the 0.4.0 columns keep their draws).
    """
    mart, n = frames[0][0], len(frames[0][0])
    leaks = [t for t in spec["traps"] if t["kind"] == "leak"]
    codes = trap_record(spec, "missing_leak", OFFER_CODE)["parameters"]["codes"]
    normals, u = rng.standard_normal((n, len(leaks))), rng.random(n)
    u_cc, fill = card_rng.random(n), card_rng.random(n)
    code = card_rng.integers(0, codes, n)
    columns = {t["column"]: _leak(t, frames, normals[:, j]) for j, t in enumerate(leaks)}
    columns |= {
        UPSTREAM: _upstream_target(spec, frames),
        APPLICATION: _applications(spec, frames, u, APPLICATION),
        SHIFTED: _shifted(spec, frames, SHIFTED),
        OFFER_CODE: _offer_codes(spec, frames, fill, code),
        CC_APPLICATION: _applications(spec, frames, u_cc, CC_APPLICATION),
        CC_SHIFTED: _shifted(spec, frames, CC_SHIFTED),
    }
    at = next(i for i, column in enumerate(mart.columns) if "_trap_" in column)
    columns = pd.DataFrame(columns, index=mart.index)
    return pd.concat([mart.iloc[:, :at], columns, mart.iloc[:, at:]], axis=1)


def _leak(
    record: dict, frames: list[tuple[pd.DataFrame, pd.DataFrame]], noise: np.ndarray
) -> np.ndarray:
    """A calibrated leak of an acquisition: round(centre + scale · (μ·acquired + noise)), μ =
    √2·Φ⁻¹(auc), so its AUC is Φ(μ/√2) = auc; holders get the noise only.

    `_acquired` tells the holders (noise only) from the non-holders who acquire.
    """
    p = record["parameters"]
    _, acquired = _acquired(frames, f"{record['product']}_flag", p["w"])
    mu = np.sqrt(2) * norm.ppf(p["auc"])
    return np.round(p["centre"] + p["scale"] * (mu * acquired + noise)).astype("int64")


def _offer_codes(
    spec: dict, frames: list[tuple[pd.DataFrame, pd.DataFrame]], fill: np.ndarray, code: np.ndarray
) -> np.ndarray:
    """The missing leak: an offer code (`prefix` + two digits, `code` picks it) for non-holders,
    filled with the acquirers' chance when they acquire within w months, else the others' chance;
    None for holders and the unfilled."""
    record = trap_record(spec, "missing_leak", OFFER_CODE)
    p = record["parameters"]
    holder, acquired = _acquired(frames, f"{record['product']}_flag", p["w"])
    filled = ~holder & (fill < np.where(acquired, p["fill_acquirers"], p["fill_others"]))
    codes = np.array([f"{p['prefix']}{k + 1:02d}" for k in range(p["codes"])], dtype=object)
    return np.where(filled, codes[code], None)


def _acquired(
    frames: list[tuple[pd.DataFrame, pd.DataFrame]], flag: str, w: int
) -> tuple[np.ndarray, np.ndarray]:
    """Who holds the product this month, and which non-holders acquire it: the flag is 1 in any
    of the next `w` months they are still here (D-029), within the panel."""
    holder = frames[0][0][flag].to_numpy() == 1
    acquired = ~holder & (_ahead(frames, 0, flag)[:, :w] == 1).any(axis=1)
    return holder, acquired


def _upstream_target(spec: dict, frames: list[tuple[pd.DataFrame, pd.DataFrame]]) -> object:
    """The upstream target of card acquisition: 1 if acquired within its window, leavers without a
    card at the spec's value, else 0; null for holders and where the window runs past the panel."""
    record = trap_record(spec, "upstream_target")
    p, flag = record["parameters"], f"{record['product']}_flag"
    holder = frames[0][0][flag].to_numpy() == 1
    window = _ahead(frames, 0, flag)[:, : p["w"]]
    taken = (window == 1).any(axis=1)
    left = np.isnan(window).any(axis=1)
    target = np.where(taken, 1.0, np.where(left, float(p["leavers_without_card"]), 0.0))
    defined = ~holder & (window.shape[1] == p["w"])
    return pd.array(np.where(defined, target, np.nan), dtype="Int64")


def _shifted(
    spec: dict, frames: list[tuple[pd.DataFrame, pd.DataFrame]], column: str
) -> np.ndarray:
    """The as-of misalignment `column`: its real column's value `months` later (NaN where the
    client has no row then: it left, or the panel ends first). The real column is the trap
    column's name without its suffix, so the two can't disagree."""
    p = trap_record(spec, "shifted", column)["parameters"]
    ahead = _ahead(frames, 0, column.removesuffix(SHIFTED_SUFFIX))
    if ahead.shape[1] < p["months"]:
        return np.full(len(ahead), np.nan)
    return ahead[:, p["months"] - 1]


def _applications(
    spec: dict, frames: list[tuple[pd.DataFrame, pd.DataFrame]], u: np.ndarray, column: str
) -> np.ndarray:
    """The process leak `column`: applications for its product this month (0/1), 0 in the panel's
    last month.

    A client whose loan count (or holding flag) rises next month applied this month with the
    precede chance. Clients still here who don't open apply (and are declined) with a chance ∝
    their opening chance next month (oracle), scaled so that declined applications are the
    declined share of all applications in expectation, given the month's openings.
    """
    record = trap_record(spec, "process_leak", column)
    p, product = record["parameters"], record["product"]
    if len(frames) == 1:
        return np.zeros(len(u), dtype="int64")
    kind = spec["products"][product]["kind"]
    held = f"{product}_cnt" if kind == "loans" else f"{product}_flag"
    now = frames[0][0][held].to_numpy(dtype=float)
    opened = _ahead(frames[:2], 0, held)[:, 0] > now  # NaN (left) compares False
    # No chance next month: the client left, every loan slot is taken, or it holds the product.
    chance = np.nan_to_num(_ahead(frames[:2], 1, f"p_{record['target']}")[:, 0])
    odds = p["declined_share"] / (1 - p["declined_share"])
    pool = chance[~opened].sum()
    scale = odds * p["precede_chance"] * opened.sum() / pool if pool > 0 else 0.0
    applied = np.where(opened, u < p["precede_chance"], u < scale * chance)
    return applied.astype("int64")


def _ahead(frames: list[tuple[pd.DataFrame, pd.DataFrame]], table: int, column: str) -> np.ndarray:
    """`column` of the first month's clients in each later month (rows × later months), matched
    by `client_id`; NaN where the client has no row (it left). `table` 0 is the mart, 1 the
    oracle."""
    ids = frames[0][0]["client_id"].to_numpy()
    values = np.full((len(ids), len(frames) - 1), np.nan)
    for j, frame in enumerate(pair[table] for pair in frames[1:]):
        position = pd.Index(frame["client_id"]).get_indexer(ids)
        found = position >= 0
        values[found, j] = frame[column].to_numpy(dtype=float)[position[found]]
    return values


def extra_columns(spec: dict, n_extra: int, z: np.ndarray, rng: np.random.Generator) -> dict:
    """`n_extra` extra columns: the first weak share weak, the rest pure noise (floats).

    Weak column j follows hidden trait j mod 5 (`z`, standardised over the month's clients) plus
    noise, at the Pearson correlation ρ whose rank correlation, (6/π)·asin(ρ/2) for normal data,
    is the middle of the spec's range. Draws: one standard normal per client and column.
    """
    p = trap_record(spec, "extra")["parameters"]
    n_weak = round(p["weak_share"] * n_extra)
    noise = rng.standard_normal((len(z), n_extra))
    rho = 2 * np.sin(np.pi * np.mean(p["weak_rank_corr"]) / 6)
    columns = {}
    for j in range(n_extra):
        if j < n_weak:
            trait = z[:, j % len(LATENTS)]
            standard = (trait - trait.mean()) / trait.std()
            columns[trap_name(f"extra_{j + 1:04d}", "weak")] = (
                rho * standard + np.sqrt(1 - rho**2) * noise[:, j]
            )
        else:
            columns[trap_name(f"extra_{j + 1:04d}", "noise")] = noise[:, j]
    return columns


def dirty_panel(
    sim: dict, frames: list[tuple[pd.DataFrame, pd.DataFrame]]
) -> tuple[dict, list[tuple[pd.DataFrame, pd.DataFrame]]]:
    """The panel months with the defects planted in their mart rows, and the simulation with the
    record (`sim["dirty"]`, for truth); each mart month keeps its duplicates."""
    mart = pd.concat([m for m, _ in frames], ignore_index=True)
    mart, record = apply_dirty(sim["spec"], mart, sim["rngs"]["traps"])
    months = mart["snapshot_month"].to_numpy()
    dirty = [
        (mart[months == m["snapshot_month"].iloc[0]].reset_index(drop=True), o) for m, o in frames
    ]
    return dict(sim, dirty=record), dirty


def apply_dirty(
    spec: dict, mart: pd.DataFrame, rng: np.random.Generator
) -> tuple[pd.DataFrame, dict]:
    """The mart with every defect planted, and its record for `truth["dirty"]`.

    Record: `duplicate_rows` (extra rows repeating a client-month), `outage_month` and
    `unit_change_month` ("YYYY-MM-DD"), `outage_columns`, `unit_change_factor`, `typo_factor` and
    `typos` (a list of `{client_id, snapshot_month}`). Duplicates are copied last, so they repeat
    the defective rows, and sit right after their originals. Draws: the typo rows, then the
    duplicated rows.
    """
    p = trap_record(spec, "dirty")["parameters"]
    outage, change = (_month_of(mart, p[key]) for key in ("outage_month", "unit_change_month"))
    month = mart["snapshot_month"].to_numpy()
    in_outage = month == outage
    mart = mart.assign(
        income=np.where(month >= change, mart["income"] * p["unit_change_factor"], mart["income"]),
        **{c: _nulled(mart[c], in_outage) for c in p["outage_columns"]},
    )
    typos = rng.choice(_typo_candidates(mart), size=p["typos"], replace=False)
    balance = mart["casa_bal"].to_numpy().copy()
    balance[typos] *= p["typo_factor"]
    mart = mart.assign(casa_bal=balance)
    copies = rng.choice(len(mart), size=round(p["duplicate_share"] * len(mart)), replace=False)
    rows = np.sort(np.concatenate([np.arange(len(mart)), copies]), kind="stable")
    record = {
        "duplicate_rows": len(copies),
        "outage_month": outage.isoformat(),
        "outage_columns": p["outage_columns"],
        "unit_change_month": change.isoformat(),
        "unit_change_factor": p["unit_change_factor"],
        "typo_factor": p["typo_factor"],
        "typos": [
            {"client_id": int(c), "snapshot_month": m.isoformat()}
            for c, m in mart.iloc[np.sort(typos)][KEYS].itertuples(index=False)
        ],
    }
    return mart.iloc[rows].reset_index(drop=True), record


def _month_of(mart: pd.DataFrame, month: str) -> object:
    """The panel's `snapshot_month` value of a "YYYY-MM" month; raises if the panel lacks it."""
    found = [m for m in mart["snapshot_month"].unique() if m.isoformat()[:7] == month]
    if len(found) != 1:
        raise ValueError(f"dirty-data month {month} is not in the panel")
    return found[0]


def _nulled(column: pd.Series, where: np.ndarray) -> pd.Series:
    """`column` with nulls where `where` holds; integer counts become nullable integers."""
    if pd.api.types.is_integer_dtype(column):
        column = column.astype("Int64")
    return column.mask(where)


def _typo_candidates(mart: pd.DataFrame) -> np.ndarray:
    """Rows a typo stands out in: a positive balance at least the client's median, of a client
    with two or more months (so × 1,000 lies far above its other months)."""
    by_client = mart.groupby("client_id")["casa_bal"]
    median, months = by_client.transform("median"), by_client.transform("size")
    usable = (mart["casa_bal"] > 0) & (mart["casa_bal"] >= median) & (months >= 2)
    return np.flatnonzero(usable.to_numpy())
