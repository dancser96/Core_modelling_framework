"""Planted trap columns and extra columns of the mart (test_harness.md, "Trap summary"; D-069).

Every planted column ends in `_trap_<kind>` and takes its parameters from the spec's trap list
(`trap_spec.TRAPS`, looked up by kind and column). Three kinds of column, by when they are known:
- persistent per client (`start_trap_state`, drawn with the client): the insurance premium
  (lognormal), the preferred language (Zipf over ten levels) and the paper-statement flag (0.1%
  ones); the month loop reindexes this state like the rest (`generate._keep_and_append`);
- monthly (`trap_columns`): those three, the branch visits (zero-inflated Poisson) and the all-null
  legacy grade. Null controls and quality columns depend on nothing else, so their AUC is 0.5;
- look-ahead (`finalize_leaks`): the calibrated leak, the upstream target and the process leak read
  the months after their own, so a panel month is final only once the next `lookahead_months`
  months exist (fewer at the panel's end: truncated windows). These are the only columns that look
  ahead; their draws are sized by the month's rows, never by outcomes, so prefix stability holds
  for every other column.
Extra columns (`extra_columns`, off by default) are weak (a hidden trait plus noise) or pure noise.
`trap_summary` is the trap list as a table, for the checking notebook. The mechanisms draw from
the `traps`, `leaks` and `extras` streams (`generate.STREAMS`).
"""

import numpy as np
import pandas as pd
from scipy.stats import norm

from synthetic.names import trap_name
from synthetic.presets import LATENTS

LEAK = trap_name("cc_preapproval_score", "leak")
UPSTREAM = trap_name("cc_acquire_next_3_months_flag", "upstream_target")
APPLICATION = trap_name("application_loan_personal_cnt", "process_leak")
PREMIUM = trap_name("insurance_premium_vol", "null_control")
BRANCH_VISITS = trap_name("branch_visit_cnt", "null_control")
LANGUAGE = trap_name("preferred_language", "null_control")
PAPER_STATEMENT = trap_name("paper_statement_flag", "near_constant")
RISK_GRADE = trap_name("legacy_risk_grade", "all_null")
SUMMARY_COLUMNS = ["product", "target", "kind", "column", "planted", "parameters", "expected"]


def trap_record(spec: dict, kind: str, column: str | None = None) -> dict:
    """The one trap of `kind` (and `column`, when given) in the spec's trap list."""
    found = [
        t for t in spec["traps"] if t["kind"] == kind and (column is None or t["column"] == column)
    ]
    if len(found) != 1:
        raise ValueError(f"the spec has {len(found)} traps of kind {kind!r} column {column!r}")
    return found[0]


def trap_summary(spec: dict) -> pd.DataFrame:
    """The spec's trap list as a table, one row per trap (planted and organic)."""
    return pd.DataFrame(spec["traps"], columns=SUMMARY_COLUMNS)


def lookahead_months(spec: dict) -> int:
    """Months after its own that a panel month's look-ahead columns read: the leak's and the
    upstream target's windows, and the process leak's next month."""
    windows = [trap_record(spec, k)["parameters"]["w"] for k in ("leak", "upstream_target")]
    return max(*windows, 1)


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


def finalize_leaks(
    spec: dict, frames: list[tuple[pd.DataFrame, pd.DataFrame]], rng: np.random.Generator
) -> pd.DataFrame:
    """The oldest buffered month's mart rows with the three look-ahead columns, placed before the
    month's other trap columns.

    `frames` are consecutive panel months as (mart, oracle), the month to finalise first, then up
    to `lookahead_months` later ones (fewer at the panel's end). Draws, one per row of the month:
    the leak's noise, then the application uniform.
    """
    mart = frames[0][0]
    noise, u = rng.standard_normal(len(mart)), rng.random(len(mart))
    leaks = {**_card_columns(spec, frames, noise), APPLICATION: _applications(spec, frames, u)}
    at = next(i for i, column in enumerate(mart.columns) if "_trap_" in column)
    leaks = pd.DataFrame(leaks, index=mart.index)
    return pd.concat([mart.iloc[:, :at], leaks, mart.iloc[:, at:]], axis=1)


def _card_columns(
    spec: dict, frames: list[tuple[pd.DataFrame, pd.DataFrame]], noise: np.ndarray
) -> dict[str, object]:
    """The calibrated leak and the upstream target of card acquisition.

    A non-holder acquires when its card flag is 1 in any later month it is still here (D-066),
    within the panel. Leak: round(centre + scale · (μ·acquired + noise)), μ = √2·Φ⁻¹(auc), so its
    AUC is Φ(μ/√2) = auc; holders get the noise only. Upstream target: acquired, leavers without a
    card at the spec's value; null for holders and where the window runs past the panel.
    """
    leak, upstream = (trap_record(spec, k) for k in ("leak", "upstream_target"))
    flag = f"{leak['product']}_flag"
    holder = frames[0][0][flag].to_numpy() == 1
    ahead = _ahead(frames, 0, flag)
    lp, up = leak["parameters"], upstream["parameters"]
    acquired = ~holder & (ahead[:, : lp["w"]] == 1).any(axis=1)
    mu = np.sqrt(2) * norm.ppf(lp["auc"])
    score = np.round(lp["centre"] + lp["scale"] * (mu * acquired + noise)).astype("int64")
    window = ahead[:, : up["w"]]
    taken = (window == 1).any(axis=1)
    left = np.isnan(window).any(axis=1)
    target = np.where(taken, 1.0, np.where(left, float(up["leavers_without_card"]), 0.0))
    defined = ~holder & (window.shape[1] == up["w"])
    return {LEAK: score, UPSTREAM: pd.array(np.where(defined, target, np.nan), dtype="Int64")}


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
