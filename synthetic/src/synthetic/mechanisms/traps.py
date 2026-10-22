"""Trap columns and dirty data (test_harness.md, "Trap summary"; D-064).

A trap column ends in `_trap_<kind>` (`trap_name`) and takes its parameters from the spec's trap
list (`spec.traps.TRAPS`, looked up by kind and column, `trap_record`). By when they are known:
- persistent per client (`start_trap_state`, drawn with the client): the insurance premium, the
  preferred language and the paper-statement flag;
- monthly (`trap_columns`): those three, the branch visits and the all-null legacy grade. Null
  controls and quality columns depend on nothing else, so their AUC is 0.5;
- look-ahead (`finalize_lookahead`): the leaks, the upstream target, the process leak and the
  shifted column read the months after their own, so a panel month is final only once the next
  `lookahead_months` months exist (fewer at the panel's end). These are the only columns that look
  ahead; their draws are sized by the month's rows, never by outcomes, so prefix stability holds
  for every other column.
Extra columns (`extra_columns`, off by default) are weak (a hidden trait plus noise) or pure noise.

Dirty data (off by default): `apply_dirty` plants duplicate client-months, a month whose login
columns are null (an outage), declared income × 12 from one month on (a unit change) and a few
current/savings balances × 1,000 (typos) in a finished panel, and returns the record that goes to
`truth["dirty"]`; `dirty_panel` does it for the month loop's months (small presets: the panel is
held in memory). Its draws come from the `traps` stream after every month has run, so switching
the defects on changes no clean value; the oracle stays clean. Streams: `traps`, `leaks`, `extras`.
"""

import numpy as np
import pandas as pd
import pyarrow as pa
from scipy.stats import norm

from synthetic.spec.presets import LATENTS

TRAP_KINDS = ("leak", "upstream_target", "process_leak", "shifted", "null_control",
              "near_constant", "all_null", "weak", "noise")  # fmt: skip


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
PREMIUM = trap_name("insurance_premium_vol", "null_control")
BRANCH_VISITS = trap_name("branch_visit_cnt", "null_control")
LANGUAGE = trap_name("preferred_language", "null_control")
PAPER_STATEMENT = trap_name("paper_statement_flag", "near_constant")
RISK_GRADE = trap_name("legacy_risk_grade", "all_null")
# Written type of each trap column; the all-null grade is a string column, not null-typed.
TRAP_TYPES = {
    LEAK: pa.int64(),
    CAMPAIGN: pa.int64(),
    UPSTREAM: pa.int64(),  # 0/1 with nulls
    APPLICATION: pa.int64(),
    SHIFTED: pa.float64(),
    PREMIUM: pa.float64(),
    BRANCH_VISITS: pa.int64(),
    LANGUAGE: pa.string(),
    PAPER_STATEMENT: pa.int32(),  # a flag
    RISK_GRADE: pa.string(),
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
    """Months after its own that a panel month's look-ahead columns read: the leaks' and the
    upstream target's windows, the shifted column's shift, and the process leak's next month."""
    windows = [
        t["parameters"]["w"] for t in spec["traps"] if t["kind"] in ("leak", "upstream_target")
    ]
    return max(*windows, trap_record(spec, "shifted", SHIFTED)["parameters"]["months"], 1)


def start_trap_state(spec: dict, n: int, rng: np.random.Generator) -> dict[str, np.ndarray]:
    """Persistent trap values of `n` new clients: premium, language, paper-statement flag.

    Draws, one per client each: the premium's normal, the language, the paper-statement uniform.
    """
    premium = trap_record(spec, "null_control", PREMIUM)["parameters"]
    language = trap_record(spec, "null_control", LANGUAGE)["parameters"]
    paper = trap_record(spec, "near_constant", PAPER_STATEMENT)["parameters"]
    levels = np.array(language["levels"], dtype=object)
    zipf = np.arange(1, len(levels) + 1) ** -float(language["exponent"])
    log_premium = np.log(premium["median"]) + premium["sigma"] * rng.standard_normal(n)
    return {
        "premium": np.round(np.exp(log_premium), 2),
        "language": rng.choice(levels, size=n, p=zipf / zipf.sum()),
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


def finalize_lookahead(
    spec: dict, frames: list[tuple[pd.DataFrame, pd.DataFrame]], rng: np.random.Generator
) -> pd.DataFrame:
    """The oldest buffered month's mart rows with the look-ahead columns, placed before the
    month's other trap columns.

    `frames` are consecutive panel months as (mart, oracle), the month to finalise first, then up
    to `lookahead_months` later ones (fewer at the panel's end). Draws, per row of the month: one
    normal per leak, then the application uniform.
    """
    mart = frames[0][0]
    leaks = [t for t in spec["traps"] if t["kind"] == "leak"]
    noise, u = rng.standard_normal((len(mart), len(leaks))), rng.random(len(mart))
    columns = {t["column"]: _leak(t, frames, noise[:, j]) for j, t in enumerate(leaks)}
    columns |= {
        UPSTREAM: _upstream_target(spec, frames),
        APPLICATION: _applications(spec, frames, u),
        SHIFTED: _shifted(spec, frames),
    }
    at = next(i for i, column in enumerate(mart.columns) if "_trap_" in column)
    columns = pd.DataFrame(columns, index=mart.index)
    return pd.concat([mart.iloc[:, :at], columns, mart.iloc[:, at:]], axis=1)


def _leak(
    record: dict, frames: list[tuple[pd.DataFrame, pd.DataFrame]], noise: np.ndarray
) -> np.ndarray:
    """A calibrated leak of an acquisition: round(centre + scale · (μ·acquired + noise)), μ =
    √2·Φ⁻¹(auc), so its AUC is Φ(μ/√2) = auc; holders get the noise only.

    A non-holder acquires when its flag is 1 in any of the next w months it is still here (D-029),
    within the panel.
    """
    p, flag = record["parameters"], f"{record['product']}_flag"
    holder = frames[0][0][flag].to_numpy() == 1
    acquired = ~holder & (_ahead(frames, 0, flag)[:, : p["w"]] == 1).any(axis=1)
    mu = np.sqrt(2) * norm.ppf(p["auc"])
    return np.round(p["centre"] + p["scale"] * (mu * acquired + noise)).astype("int64")


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


def _shifted(spec: dict, frames: list[tuple[pd.DataFrame, pd.DataFrame]]) -> np.ndarray:
    """The as-of misalignment: its real column's value `months` later (NaN where the client has no
    row then: it left, or the panel ends first). The trap column's name is built from the real
    column's (`SHIFTED_OF`), so the two can't disagree."""
    p = trap_record(spec, "shifted", SHIFTED)["parameters"]
    ahead = _ahead(frames, 0, SHIFTED_OF)
    if ahead.shape[1] < p["months"]:
        return np.full(len(ahead), np.nan)
    return ahead[:, p["months"] - 1]


def _applications(
    spec: dict, frames: list[tuple[pd.DataFrame, pd.DataFrame]], u: np.ndarray
) -> np.ndarray:
    """The process leak: personal-loan applications this month (0/1), 0 in the panel's last month.

    A client whose loan count rises next month applied this month with the precede chance. Clients
    still here who don't open apply (and are declined) with a chance ∝ their opening chance next
    month (oracle), scaled so that declined applications are the declined share of all
    applications in expectation, given the month's openings.
    """
    record = trap_record(spec, "process_leak", APPLICATION)
    p = record["parameters"]
    if len(frames) == 1:
        return np.zeros(len(u), dtype="int64")
    count = f"{record['product']}_cnt"
    now = frames[0][0][count].to_numpy(dtype=float)
    opened = _ahead(frames[:2], 0, count)[:, 0] > now  # NaN (left) compares False
    # No chance next month: the client left, or every loan slot is taken.
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
