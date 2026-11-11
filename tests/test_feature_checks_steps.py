"""Feature Checks' five steps and the measures they read, on hand-built ledgers and cells (pure
pandas, no Spark): every finding fires at its threshold and stays silent one step below, the
exclusive quality order, a null concordance without null rows not available, the null sets, the
minority beside a dominant value (Cohen's h on rates, d on means, at its `dominant_share_min`;
a monotone top bin is no rare value), the support and SE every finding with an SE states and
"not significant" both ways (Q540: no skip for support), the best-order `too_strong`, the lagged
signal of a shifted column over the window after its first period with a flip named, Cochran's Q
over EDA's per-period concordance with the range relative to the signal, PSI and new levels on
named periods, the clusters with a not-compared pair, and `check_inputs` with every step over
one small panel, refusing a stale EDA.
"""

import numpy as np
import pandas as pd
import pytest

from core_modelling.config import UseCaseConfig
from core_modelling.config.schema import Leakage, Quality, Redundancy, Stability, TimeAlignment
from core_modelling.eda.deep_dives import per_period_concordance
from core_modelling.feature_checks.findings import FINDING_COLUMNS, FINDINGS, STEP_ORDER
from core_modelling.feature_checks.inputs import CheckInputs, check_inputs
from core_modelling.feature_checks.measures import (
    PER_PERIOD_COLUMNS,
    per_period_table,
    period_psi,
)
from core_modelling.feature_checks.steps import (
    FEW_PERIODS,
    FLIPPED,
    NO_LATEST,
    NO_NULL_ROWS,
    NOT_SIGNIFICANT,
    STEP_COLUMNS,
    STEPS,
    check_leakage,
    check_quality,
    check_redundancy,
    check_stability,
    check_time_alignment,
)
from core_modelling.statistics.concordance import cochran_q, concordance_se
from core_modelling.statistics.distributions import psi

NAN = float("nan")
LEDGER_DEFAULTS = {
    "kind": "numeric", "levels": 10.0, "concordance": 0.55, "concordance_window": 0.55,
    "missing_share_window": 0.0, "null_concordance_window": NAN, "zero_share_window": 0.1,
    "dominant_share_window": 0.2, "lineage": False, "unsupported": False,
}  # fmt: skip
STRONG = {"lo": (90, 10), "hi": (10, 90)}  # a two-bin table whose concordance is 0.9
DROP = "time_alignment.lagged_signal_drop"


def _clients(ratio: float) -> dict[str, float]:
    """`eda.json`'s `clients` with `ratio` effective clients per labelled row in every class."""
    rows = {"event_rows": 1.0, "non_event_rows": 1.0, "rows": 1.0}
    return {**rows, "event_effective": ratio, "non_event_effective": ratio, "effective": ratio}


def _ledger(*rows: dict) -> pd.DataFrame:
    """A ledger of read candidates: each row's columns over `LEDGER_DEFAULTS`."""
    return pd.DataFrame([{**LEDGER_DEFAULTS, **row} for row in rows])


def _cells(
    feature: str, counts: dict[str, dict[str, tuple[int, int] | int]], lagged: bool = False
) -> pd.DataFrame:
    """One feature's binary cells: per period, per bin label in bin order (`null` the null bin),
    `(rows with target 0, rows with target 1)` or a count of unlabelled rows."""
    records = []
    for period, bins in counts.items():
        for order, (label, count) in enumerate(bins.items()):
            targets = {"0": count[0], "1": count[1]} if isinstance(count, tuple) else {None: count}
            for target, n in targets.items():
                y = NAN if target is None else float(n if target == "1" else 0)
                records += [{"feature": feature, "period": period, "lagged": lagged,
                             "fold": pd.NA, "bin": label, "bin_order": order,
                             "is_null": label == "null", "target_bin": target, "n": n,
                             "sum_y": y, "sum_y2": y}] if n else []  # fmt: skip
    return pd.DataFrame(records).astype({"fold": "Int64"})


def _eda_per_period(
    cells: pd.DataFrame, kinds: dict[str, str], window: list[str], task: str
) -> pd.DataFrame:
    """EDA's `concordance_per_period` table over hand-built cells: raw window signs +1."""
    return pd.concat([
        per_period_concordance(cells, name, kind, task=task, window_periods=window,
                               prior_rows=50.0, min_events=50, sign=1, exact=False)
        for name, kind in kinds.items()
    ], ignore_index=True)  # fmt: skip


def _inputs(
    ledger: pd.DataFrame, cells: pd.DataFrame, per_period: bool = False, **settings: object
) -> CheckInputs:
    """`CheckInputs` over a hand-built ledger and cells: one window period `p1` unless `periods`
    says otherwise, raw window signs +1, no best order and no EDA reason unless `ranking` is
    given, the label-free per-period table and EDA's per-period concordance computed with
    `per_period` (else empty), one effective client per labelled row, no client-constant shares
    or correlation unless given."""
    periods = settings.pop("periods", {"window": ["p1"], "gap": [], "latest": []})
    features = list(ledger["feature"])
    kinds = dict(zip(features, ledger["kind"], strict=True))
    task = settings.pop("task", "binary")
    snapshot = periods["window"][-1]
    table = pd.DataFrame(columns=PER_PERIOD_COLUMNS)
    concordances = pd.DataFrame(
        columns=["feature", "period", "rows", "support", "concordance", "se", "unavailable"]
    )
    if per_period:
        table = per_period_table(cells, kinds, periods=periods, snapshot_period=snapshot)
        concordances = _eda_per_period(cells, kinds, periods["window"], task)
    defaults = {
        "ranking": _ranking(ledger, {}),
        "client_constant": pd.DataFrame({"feature": features, "constant_share": NAN}),
        "correlation": pd.DataFrame(columns=["a", "b", "statistic", "method", "rows"]),
        "per_period": table,
        "concordance_per_period": concordances,
        "clients": _clients(1.0),
        "dominant_share_min": 0.90,
    }
    values = {**defaults, **settings}
    return CheckInputs(
        ledger=ledger, cells=cells, periods=periods, snapshot_period=snapshot,
        over_ceiling=[], task=task, exact=False, prior_rows=50.0, null_concordance_max=0.70,
        **values,
    )  # fmt: skip


def _ranking(
    ledger: pd.DataFrame, reasons: dict[str, str], best: dict[str, float] | None = None
) -> pd.DataFrame:
    """EDA's ranking columns the steps read: raw window signs +1, the ledger's window concordance,
    each feature's `best` order (NaN elsewhere) and `reasons` entry as its `unavailable` (''
    elsewhere)."""
    features = ledger["feature"]
    return pd.DataFrame({
        "feature": features, "raw_sign_window": 1,
        "concordance_window": ledger["concordance_window"],
        "concordance_best_order_window": features.map(best or {}).astype(float),
        "unavailable": features.map(reasons).fillna(""),
    })  # fmt: skip


def _pairs(frame: pd.DataFrame) -> set[tuple[str, str]]:
    """The (feature, finding) pairs of a findings or unavailable table."""
    return set(zip(frame["feature"], frame["finding"], strict=True))


def _guarded(feature: str, null_rows: int) -> pd.DataFrame:
    """A feature's cells with 120 labelled non-null rows and `null_rows` labelled null rows."""
    return _cells(feature, {"p1": {"a": (100, 20), "null": (null_rows - 5, 5)}})


def test_quality_findings_fire_at_their_thresholds_in_the_exclusive_order() -> None:
    """The four exclusive flags in order, high-cardinality and the two notes at and one step
    below their thresholds; a 1/null column is not constant; a null concordance without a
    labelled null row is not available, while 20 null rows are read (no support guard, Q540);
    near-constant's detail is its minority's effect."""
    ledger = _ledger(
        {"feature": "all_null", "missing_share_window": 1.0, "dominant_share_window": 1.0,
         "zero_share_window": NAN},
        {"feature": "constant", "dominant_share_window": 1.0},
        {"feature": "one_or_null", "missing_share_window": 0.5, "dominant_share_window": 0.5},
        {"feature": "high_missing", "missing_share_window": 0.95, "dominant_share_window": 0.995},
        {"feature": "missing_below", "missing_share_window": 0.9499},
        {"feature": "near_constant", "dominant_share_window": 0.99},
        {"feature": "near_below", "dominant_share_window": 0.9899},
        {"feature": "codes", "kind": "categorical", "levels": 51.0},
        {"feature": "codes_at_cap", "kind": "categorical", "levels": 50.0},
        {"feature": "wide_numeric", "levels": 5000.0},
        {"feature": "zeros", "missing_share_window": 0.2, "zero_share_window": 0.005},
        {"feature": "zeros_below", "missing_share_window": 0.1999, "zero_share_window": 0.0},
        {"feature": "zeros_seen", "missing_share_window": 0.5, "zero_share_window": 0.0051},
        {"feature": "informative", "null_concordance_window": 0.55},
        {"feature": "informative_below", "null_concordance_window": 0.5499},
        {"feature": "informative_at_leak", "null_concordance_window": 0.70},
        {"feature": "informative_no_nulls", "null_concordance_window": 0.6},
    )  # fmt: skip
    near = {
        "all_null": {"null": (95, 5)}, "constant": {"a": (95, 5)},
        "high_missing": {"a": (95, 5), "null": (1900, 100)},
        "near_constant": {"= 0": (9800, 100), "1": (40, 60)},
        "informative_no_nulls": {"a": (100, 20), "null": 5},
    }  # fmt: skip
    cells = pd.concat(
        [_cells(f, {"p1": bins}) for f, bins in near.items()]
        + [_guarded(f, 20) for f in ["informative", "informative_below", "informative_at_leak"]]
    )
    result = check_quality(_inputs(ledger, cells), Quality())
    assert _pairs(result.findings) == {
        ("all_null", "quality.all_null"), ("constant", "quality.constant"),
        ("high_missing", "quality.high_missing"), ("near_constant", "quality.near_constant"),
        ("codes", "quality.high_cardinality"), ("zeros", "quality.nulls_may_be_zeros"),
        ("informative", "quality.nulls_informative"),
    }  # fmt: skip
    assert result.unavailable.values.tolist() == [
        ["informative_no_nulls", "quality.nulls_informative", NO_NULL_ROWS]
    ]
    row = result.findings.set_index("feature").loc["zeros"]
    assert (row["kind"], row["value"], row["threshold"]) == ("note", 0.2, 0.2)
    assert row["text"] == FINDINGS["quality.nulls_may_be_zeros"]["text"]
    assert row["detail"] == "zero share among the values 0.50%"
    near_detail = result.findings.set_index("feature").loc["near_constant", "detail"]
    assert near_detail == (
        "the 1.0% of filled rows outside the dominant value = 0: rate 60.00% against 1.01%, "
        "Cohen's h 1.57"
    )
    assert list(result.findings.columns) == FINDING_COLUMNS
    assert list(result.columns.columns) == ["feature"]


def test_nulls_informative_names_its_null_set_and_sorts_by_it() -> None:
    """Features with the same null counts in every window period and target bin share a null
    set, numbered by size, largest first; a feature alone names none; the notes are ordered by
    set, then in ledger order, the features alone last; each states its support and SE."""
    names = ["alone", "pair_a", "trio_a", "pair_b", "trio_b", "trio_c"]
    ledger = _ledger(*[{"feature": f, "null_concordance_window": 0.6} for f in names])
    nulls = {"alone": (60, 10), "pair_a": (80, 5), "pair_b": (80, 5)}
    cells = pd.concat([
        _cells(f, {"p1": {"a": (900, 100), "null": nulls.get(f, (70, 8))}})
        for f in ledger["feature"]
    ])  # fmt: skip
    found = check_quality(_inputs(ledger, cells), Quality()).findings
    assert list(found["feature"]) == ["trio_a", "trio_b", "trio_c", "pair_a", "pair_b", "alone"]
    details = found.set_index("feature")["detail"]
    same = "the same null counts per period and target as"
    assert details["trio_b"].startswith(f"null set 1: {same} 2 other features; ")
    assert details["pair_b"].startswith(f"null set 2: {same} 1 other feature; ")
    assert details["alone"].startswith("support 110 effective positive events, SE ")


def test_null_sets_are_told_apart_by_their_unlabelled_null_counts() -> None:
    """Two features with the same labelled null counts in the window but different null counts
    in the latest period (unlabelled) are two null sets, not one."""
    latest_nulls = {"a": 30, "b": 40, "c": 30}
    ledger = _ledger(*[{"feature": f, "null_concordance_window": 0.6} for f in latest_nulls])
    cells = pd.concat([
        _cells(f, {"p1": {"a": (900, 100), "null": (70, 8)}, "l1": {"a": 900, "null": count}})
        for f, count in latest_nulls.items()
    ])  # fmt: skip
    periods = {"window": ["p1"], "gap": [], "latest": ["l1"]}
    found = check_quality(_inputs(ledger, cells, periods=periods), Quality()).findings
    details = found.set_index("feature")["detail"]
    assert list(found["feature"]) == ["a", "c", "b"]
    assert details["a"].startswith("null set 1: ") and details["c"].startswith("null set 1: ")
    assert details["b"].startswith("support ")


def test_leakage_flags_fire_at_their_thresholds() -> None:
    """Too strong and the missingness leak at and below their thresholds; 19 null rows are read,
    not skipped; a value at its threshold is not significant, one far past it is."""
    ledger = _ledger(
        {"feature": "strong", "concordance_window": 0.80},
        {"feature": "strong_below", "concordance_window": 0.7999},
        {"feature": "null_leak", "null_concordance_window": 0.70},
        {"feature": "null_leak_below", "null_concordance_window": 0.6999},
        {"feature": "null_leak_few", "null_concordance_window": 0.9},
    )  # fmt: skip
    cells = pd.concat(
        [_cells(f, {"p1": {"a": (9000, 1000)}}) for f in ["strong", "strong_below"]]
        + [_guarded(f, 40) for f in ["null_leak", "null_leak_below"]]
        + [_guarded("null_leak_few", 19)]
    )
    result = check_leakage(_inputs(ledger, cells), Leakage())
    assert _pairs(result.findings) == {
        ("strong", "leakage.too_strong"), ("null_leak", "leakage.missingness_leak"),
        ("null_leak_few", "leakage.missingness_leak"),
    }  # fmt: skip
    assert result.unavailable.empty
    details = result.findings.set_index("feature")["detail"]
    assert details["null_leak_few"].startswith("support 25 effective positive events, SE ")
    assert not details["null_leak_few"].endswith(NOT_SIGNIFICANT)  # 0.9 is far past 0.70
    assert details["null_leak"].endswith(f"; {NOT_SIGNIFICANT}")  # at its threshold


def test_evidence_states_the_window_se_and_significance_both_ways() -> None:
    """`too_strong` states the window concordance's support in effective events and its
    Hanley–McNeil SE on effective clients (as EDA computes it): 1,000 events at 0.9 sit far past
    0.80, the same table on a tenth of the clients does not; the best order fires a U-shaped
    feature whose plain value is weak, the detail naming it."""
    ledger = _ledger(
        {"feature": "strong", "concordance_window": 0.9},
        {"feature": "u_shape", "concordance_window": 0.55},
    )  # fmt: skip
    cells = pd.concat([
        _cells("strong", {"p1": {"lo": (9000, 100), "hi": (1000, 900)}}),
        _cells("u_shape", {"p1": {"lo": (100, 400), "mid": (9800, 200), "hi": (100, 400)}}),
    ])  # fmt: skip
    ranking = _ranking(ledger, {}, best={"strong": 0.85, "u_shape": 0.86})
    found = check_leakage(_inputs(ledger, cells, ranking=ranking), Leakage()).findings
    found = found.loc[found["finding"] == "leakage.too_strong"].set_index("feature")
    se = concordance_se(0.8, 1000, 10000)  # at the threshold
    assert found.loc["strong", "detail"] == f"support 1,000 effective positive events, SE {se:.3f}"
    assert found.loc["u_shape", "value"] == 0.86
    assert found.loc["u_shape", "detail"].startswith("best order; in bin order 0.550; support ")
    thin = check_leakage(_inputs(ledger, cells, ranking=ranking, clients=_clients(0.001)),
                         Leakage()).findings  # fmt: skip
    thin = thin.loc[thin["finding"] == "leakage.too_strong"].set_index("feature")
    assert thin.loc["strong", "detail"].startswith("support 1 effective positive events, SE ")
    assert thin.loc["strong", "detail"].endswith(f"; {NOT_SIGNIFICANT}")


def test_a_perfect_concordance_on_three_events_is_not_significant() -> None:
    """At 1.0 the SE at the estimate is the floor on any support, so significance is judged with
    the SE at the threshold: three events at 1.0 do not clear 0.80 by 2 SE."""
    ledger = _ledger({"feature": "perfect", "concordance_window": 1.0})
    cells = _cells("perfect", {"p1": {"lo": (1000, 0), "hi": (0, 3)}})
    found = check_leakage(_inputs(ledger, cells), Leakage()).findings
    found = found.loc[found["finding"] == "leakage.too_strong"].set_index("feature")
    se = concordance_se(0.8, 3, 1000)
    assert found.loc["perfect", "detail"] == (
        f"support 3 effective positive events, SE {se:.3f}; {NOT_SIGNIFICANT}"
    )


def test_a_best_order_too_strong_needs_four_se() -> None:
    """A best-order value is fitted in sample, so it needs 4 SE past the threshold (EDA's
    non-monotone margin): 3 SE past is significant for a plain value only, 5 SE for both."""
    ledger = _ledger(
        {"feature": "plain", "concordance_window": 0.8},
        {"feature": "best", "concordance_window": 0.6},
    )  # fmt: skip
    u_shape = {"lo": (100, 400), "mid": (9800, 200), "hi": (100, 400)}
    cells = pd.concat([_cells(f, {"p1": u_shape}) for f in ["plain", "best"]])
    se = concordance_se(0.8, 1000, 10000)
    for multiple, best_significant in [(3, False), (5, True)]:
        value = 0.8 + multiple * se
        both = ledger.assign(concordance_window=[value, 0.6])
        ranking = _ranking(both, {}, best={"best": value})
        found = check_leakage(_inputs(both, cells, ranking=ranking), Leakage()).findings
        details = found.loc[found["finding"] == "leakage.too_strong"].set_index("feature")["detail"]
        assert not details["plain"].endswith(NOT_SIGNIFICANT)
        assert details["best"].endswith(NOT_SIGNIFICANT) is not best_significant


def test_missingness_leak_is_read_below_edas_null_share_range() -> None:
    """A field blanked on the events, at a 0.2% null share EDA reads no null concordance for,
    fires with its detail saying so; 0.2% nulls among non-events does not; ten null rows are
    read too; the `nulls_informative` note stays on EDA's value."""
    ledger = _ledger(
        {"feature": "blanked", "missing_share_window": 0.002},
        {"feature": "random", "missing_share_window": 0.002},
        {"feature": "few", "missing_share_window": 0.0005},
    )  # fmt: skip
    cells = pd.concat([
        _cells("blanked", {"p1": {"a": (19960, 0), "null": (0, 40)}}),
        _cells("random", {"p1": {"a": (19920, 40), "null": (40, 0)}}),
        _cells("few", {"p1": {"a": (19980, 10), "null": (0, 10)}}),
    ])  # fmt: skip
    inputs = _inputs(ledger, cells)
    result = check_leakage(inputs, Leakage())
    found = result.findings.set_index("feature")
    assert list(found.index) == ["blanked", "few"]
    assert set(found["finding"]) == {"leakage.missingness_leak"}
    assert found.loc["blanked", "value"] == pytest.approx(1.0)
    assert found.loc["blanked", "detail"].startswith(
        "read below EDA's null-share range (missing share 0.20%); support 40 effective "
    )
    assert result.unavailable.empty
    assert check_quality(inputs, Quality()).findings.empty


def test_a_feature_without_a_window_concordance_carries_edas_reason() -> None:
    """`too_strong` and `concordance_unstable` name EDA's reason for a feature EDA has no window
    concordance for; a feature with a concordance in one window period only is not available
    for Cochran's Q, while a period below `strata.min_events` support is read."""
    ledger = _ledger(
        {"feature": "no_events", "concordance_window": NAN}, {"feature": "one_period"},
        {"feature": "sparse"},
    )  # fmt: skip
    reason = "not available: no events among the non-null rows in the window"
    cells = pd.concat([
        _cells("no_events", {"p1": {"lo": (100, 0), "hi": (100, 0)}, "p2": {"lo": (100, 0)}}),
        _cells("one_period", {"p1": STRONG, "p2": {"lo": (90, 0), "hi": (10, 0)}}),
        _cells("sparse", {"p1": STRONG, "p2": {"lo": (90, 10), "hi": (10, 30)}}),
    ])  # fmt: skip
    periods = {"window": ["p1", "p2"], "gap": [], "latest": []}
    ranking = _ranking(ledger, {"no_events": reason})
    inputs = _inputs(ledger, cells, True, periods=periods, ranking=ranking)
    strong = check_leakage(inputs, Leakage()).unavailable
    assert strong.values.tolist() == [["no_events", "leakage.too_strong", reason]]
    unstable = check_stability(inputs, Stability()).unavailable.set_index("finding")
    unstable = unstable.loc["stability.concordance_unstable"].set_index("feature")["reason"]
    assert unstable.to_dict() == {"no_events": reason, "one_period": FEW_PERIODS}


def _h(minority: float, dominant: float) -> float:
    """Cohen's h of two rates."""
    return 2 * np.arcsin(np.sqrt(minority)) - 2 * np.arcsin(np.sqrt(dominant))


def test_rare_value_leak_compares_the_minority_with_the_dominant_value() -> None:
    """The process-leak shape (98.7% of the filled rows at 0, the others converting at 80%)
    fires as Cohen's h, its nulls left out, at its effect and not just past it; a monotone column
    whose small top bin converts at 10× is not dominated, so neither fires nor is listed; 49
    minority events are read, not skipped; on a hundredth of the clients the process leak is not
    significant; a dominant level of a categorical; a dominant value without events; a value at
    exactly `dominant_share_min` of the filled rows dominates, one just below does not, and the
    leaf moves that line."""
    window = {
        "process_leak": {"= 0": (9480, 390), "1": (26, 104), "null": (4000, 1000)},
        "monotone": {**{f"q{i}": (970, 30) for i in range(19)}, "q19": (35, 15)},
        "support_below": {"a": (9500, 100), "b": (0, 49)},
        "level": {"STANDARD": (9300, 200), "GOLD": (100, 200), "PLATINUM": (50, 150)},
        "no_event_dominant": {"a": (10000, 0), "b": (10, 50)},
        "dominant_at": {"a": (8900, 100), "b": (0, 1000)},
        "dominant_below": {"a": (8899, 100), "b": (0, 1001)},
    }  # fmt: skip
    ledger = _ledger(*[{"feature": f} for f in window])
    ledger.loc[ledger["feature"] == "level", "kind"] = "categorical"
    cells = pd.concat([_cells(f, {"p1": bins}) for f, bins in window.items()])
    inputs = _inputs(ledger, cells)
    result = check_leakage(inputs, Leakage())
    found = result.findings.set_index("feature")
    hits = ["process_leak", "support_below", "level", "no_event_dominant", "dominant_at"]
    assert list(found.index) == hits and result.unavailable.empty
    effect = found.loc["process_leak", "value"]
    assert effect == pytest.approx(_h(0.8, 390 / 9870))
    se = np.sqrt(1 / 130 + 1 / 9870)
    assert found.loc["process_leak", "detail"] == (
        "the 1.3% of filled rows outside the dominant value = 0: rate 80.00% against 3.95%, "
        f"Cohen's h {effect:.2f}; support 104 effective positive events, SE {se:.3f}"
    )
    assert found.loc["level", "detail"].startswith(
        "the 5.0% of filled rows outside the dominant value STANDARD: rate 70.00% against 2.11%"
    )
    assert found.loc["no_event_dominant", "value"] == pytest.approx(_h(50 / 60, 0))
    thin = check_leakage(_inputs(ledger, cells, clients=_clients(0.01)), Leakage()).findings
    assert (
        thin.set_index("feature")
        .loc["process_leak", "detail"]
        .endswith(f"support 1 effective positive events, SE 0.707; {NOT_SIGNIFICANT}")
    )
    at = check_leakage(inputs, Leakage(rare_effect_max=effect)).findings
    past = check_leakage(inputs, Leakage(rare_effect_max=effect + 1e-9)).findings
    assert "process_leak" in set(at["feature"]) and "process_leak" not in set(past["feature"])
    looser = _inputs(ledger, cells, dominant_share_min=0.85)
    assert "dominant_below" in set(check_leakage(looser, Leakage()).findings["feature"])


def _amount_cells(feature: str, bins: dict[str, tuple[int, int, float]]) -> pd.DataFrame:
    """One feature's regression cells in `p1`: per bin, the rows with a zero target, the rows
    with a positive one and their total amount, each positive row the same amount."""
    records = []
    for order, (label, (zeros, positives, total)) in enumerate(bins.items()):
        for target, n, y in (("= 0", zeros, 0.0), ("> 0", positives, total)):
            square = y * y / n if n else 0.0
            records += [{"feature": feature, "period": "p1", "lagged": False, "fold": pd.NA,
                         "bin": label, "bin_order": order, "is_null": False, "target_bin": target,
                         "n": n, "sum_y": y, "sum_y2": square}] if n else []  # fmt: skip
    return pd.DataFrame(records).astype({"fold": "Int64"})


def test_regression_rare_value_is_cohens_d_over_the_pooled_spread() -> None:
    """A minority whose mean is far above the dominant value's fires as Cohen's d, the pooled SD
    from the cells' sums of squares; a dominant value whose mean is 0 is compared too (no ratio
    is needed); a target without spread on both sides is named in `unavailable` instead."""
    ledger = _ledger({"feature": "amount"}, {"feature": "zero_dominant"}, {"feature": "flat"})
    cells = pd.concat([
        _amount_cells("amount", {"= 0": (4750, 4750, 19000.0), "b": (100, 400, 8000.0)}),
        _amount_cells("zero_dominant", {"= 0": (9500, 0, 0.0), "b": (100, 400, 8000.0)}),
        _amount_cells("flat", {"= 0": (0, 9500, 9500.0), "b": (0, 500, 500.0)}),
    ])  # fmt: skip
    result = check_leakage(_inputs(ledger, cells, task="regression"), Leakage())
    found = result.findings.loc[result.findings["finding"] == "leakage.rare_value_leak"]
    found = found.set_index("feature")
    y_minority = np.repeat([0.0, 20.0], [100, 400])
    y_dominant = np.repeat([0.0, 4.0], [4750, 4750])
    pooled = np.sqrt((499 * y_minority.var(ddof=1) + 9499 * y_dominant.var(ddof=1)) / 9998)
    assert found.loc["amount", "value"] == pytest.approx((16 - 2) / pooled)
    assert found.loc["amount", "detail"].startswith(
        "the 5.0% of filled rows outside the dominant value = 0: mean 16.00 against 2.00, "
        "Cohen's d "
    )
    assert "zero_dominant" in found.index
    reason = result.unavailable.set_index("feature").loc["flat", "reason"]
    assert reason == "not available: no spread in the target on both sides"


def _lagged_feature(feature: str, lagged: dict[str, tuple[int, int]]) -> pd.DataFrame:
    """A feature at concordance 0.9 in `p1` to `p3` whose lagged cells hold `lagged` and 10 null
    rows in `p2` and `p3`; `p1`'s lagged cells are null (no previous period, N11)."""
    current = _cells(feature, dict.fromkeys(["p1", "p2", "p3"], STRONG))
    later = {**lagged, "null": (5, 5)}
    lag = {"p1": {"lo": 0, "hi": 0, "null": (100, 100)}, "p2": later, "p3": later}
    return pd.concat([current, _cells(feature, lag, lagged=True)])


def test_time_alignment_on_a_shifted_column_and_client_constant_shares() -> None:
    """A shifted column's lagged signal collapses (signal kept 0) and a flipped lag goes negative,
    its detail naming the flip; a legitimate column keeps it; nothing is looked at below
    `concordance_min`; the share with no lagged value leaves out the window's first period, and a
    one-period window has no lagged value; a thin lagged pool is read, not skipped, and on a
    hundredth of the clients its drop is not significant; the client-constant flag at and below
    its threshold, with no detail (the concordance sits beside it in the report), and not
    available without a share."""
    ledger = _ledger(
        {"feature": "shifted", "concordance_window": 0.9},
        {"feature": "flipped", "concordance_window": 0.9},
        {"feature": "legit", "concordance_window": 0.9},
        {"feature": "partial", "concordance_window": 0.9},
        {"feature": "weak_shifted", "concordance_window": 0.5999},
        {"feature": "static", "concordance_window": 0.6},
        {"feature": "static_below", "concordance_window": 0.6},
        {"feature": "static_weak", "concordance_window": 0.5999},
        {"feature": "unknown", "concordance_window": 0.9},
        {"feature": "thin", "concordance_window": 0.9},
    )  # fmt: skip
    flat, flipped = {"lo": (50, 50), "hi": (50, 50)}, {"lo": (10, 90), "hi": (90, 10)}
    lags = {"shifted": flat, "flipped": flipped, "weak_shifted": flat,
            "partial": {"lo": (75, 25), "hi": (25, 75)},
            "thin": {"lo": (40, 12), "hi": (40, 12)}}  # fmt: skip
    cells = pd.concat([_lagged_feature(f, lags.get(f, STRONG)) for f in ledger["feature"]])
    shares = [0.1, 0.1, 0.1, 0.1, NAN, 0.99, 0.9899, 1.0, NAN, 0.1]
    constant = pd.DataFrame({"feature": ledger["feature"], "constant_share": shares})
    periods = {"window": ["p1", "p2", "p3"], "gap": [], "latest": []}
    inputs = _inputs(ledger, cells, periods=periods, client_constant=constant)
    result = check_time_alignment(inputs, TimeAlignment())
    assert _pairs(result.findings) == {
        ("shifted", DROP), ("flipped", DROP), ("thin", DROP),
        ("static", "time_alignment.client_constant"),
    }  # fmt: skip
    assert _pairs(result.unavailable) == {("unknown", "time_alignment.client_constant")}
    columns = result.columns.set_index("feature")
    assert columns.loc[["shifted", "flipped", "legit"], "lagged_concordance"].tolist() == (
        pytest.approx([0.5, 0.1, 0.9])
    )
    assert columns.loc[["shifted", "flipped", "legit", "partial"], "signal_kept"].tolist() == (
        pytest.approx([0.0, -1.0, 1.0, 0.625])
    )
    assert np.isnan(columns.loc["weak_shifted", "signal_kept"])
    details = result.findings.set_index("feature")["detail"]
    no_lag = "no lagged value on 4.8% of the window's rows after its first period"
    assert details["shifted"].startswith(f"{no_lag}; support 200 effective positive events, SE ")
    assert NOT_SIGNIFICANT not in details["shifted"] and FLIPPED not in details["shifted"]
    assert details["flipped"].startswith(f"no lagged value on 4.8% of the window's rows after "
                                         f"its first period; {FLIPPED}; support ")  # fmt: skip
    assert details["static"] == ""
    kept = columns.loc["partial", "signal_kept"]
    at = check_time_alignment(inputs, TimeAlignment(signal_kept_min=kept))
    above = check_time_alignment(inputs, TimeAlignment(signal_kept_min=kept + 1e-9))
    assert "partial" not in set(at.findings["feature"])
    assert "partial" in set(above.findings["feature"])
    one = {"window": ["p2"], "gap": [], "latest": []}
    single = check_time_alignment(_inputs(ledger, cells, periods=one), TimeAlignment())
    unlagged = single.unavailable.set_index("finding").loc[DROP]
    assert set(unlagged["reason"]) == {"not available: a one-period window has no lagged value"}
    assert single.columns["lagged_concordance"].isna().all()
    scaled = _inputs(ledger, cells, periods=periods, client_constant=constant,
                     clients=_clients(0.01))  # fmt: skip
    thin = check_time_alignment(scaled, TimeAlignment()).findings.set_index("feature")["detail"]
    assert thin["shifted"].endswith(NOT_SIGNIFICANT)


def test_cochran_q_flags_a_flipped_period_and_reads_a_thin_one() -> None:
    """A period whose direction flips reads below 0.5 in the window's direction and is flagged;
    a period below `strata.min_events` support is read too (Q540); a drifting feature fires at
    its p-value, at its range relative to the signal and at the range floor (Q547), and not
    just past any of them."""
    ledger = _ledger(
        {"feature": "flips"}, {"feature": "sparse"}, {"feature": "steady"},
        {"feature": "drifts", "concordance_window": 0.65},
    )  # fmt: skip
    reversed_ = {"lo": (10, 90), "hi": (90, 10)}
    cells = pd.concat([
        _cells("flips", {"p1": {"lo": (180, 20), "hi": (20, 180)}, "p2": reversed_}),
        _cells("sparse", {"p1": STRONG, "p2": {"lo": (90, 10), "hi": (10, 30)}}),
        _cells("steady", {"p1": STRONG, "p2": STRONG}),
        _cells("drifts", {"p1": {"lo": (900, 100), "hi": (100, 900)},
                          "p2": {"lo": (800, 200), "hi": (200, 800)}}),
    ])  # fmt: skip
    periods = {"window": ["p1", "p2"], "gap": [], "latest": []}
    inputs = _inputs(ledger, cells, True, periods=periods)
    result = check_stability(inputs, Stability())
    name = "stability.concordance_unstable"
    flagged = result.findings.loc[result.findings["finding"] == name]
    assert list(flagged["feature"]) == ["flips", "drifts"]
    assert flagged["detail"].iloc[0] == (
        "range 0.800 over p1, p2; support 100 positive events in the thinnest period"
    )
    assert name not in set(result.unavailable["finding"])
    columns = result.columns.set_index("feature")
    assert columns.loc["flips", "concordance_range"] == pytest.approx(0.8)
    assert columns.loc["steady", "heterogeneity_p"] == pytest.approx(1.0)
    assert columns.loc["sparse", "concordance_range"] == pytest.approx(0.075)
    p, spread = columns.loc["drifts", ["heterogeneity_p", "concordance_range"]]
    relative = spread / 0.15  # its concordance_window 0.65: a signal of 0.15
    for params, fires in [
        (Stability(heterogeneity_p_max=p), True), (Stability(heterogeneity_p_max=p - 1e-9), False),
        (Stability(concordance_range_min=relative * (1 - 1e-9)), True),
        (Stability(concordance_range_min=relative * (1 + 1e-9)), False),
        (Stability(concordance_range_min=0, concordance_range_floor=spread * (1 - 1e-9)), True),
        (Stability(concordance_range_min=0, concordance_range_floor=spread * (1 + 1e-9)), False),
    ]:  # fmt: skip
        assert (("drifts", name) in _pairs(check_stability(inputs, params).findings)) is fires


def test_a_thin_period_near_one_does_not_dominate_cochrans_q() -> None:
    """A homogeneous 0.7 feature whose second period holds three events, all in the top bin,
    reads 0.995 there: weighted by the SE at its own value (near the floor) Q would flag it;
    weighted by the SE at the window's 0.7 on the period's own rows, it stays below α."""
    ledger = _ledger({"feature": "thin", "concordance_window": 0.7})
    cells = _cells("thin", {"p1": {"lo": (7000, 300), "hi": (3000, 700)},
                            "p2": {"lo": (990, 0), "hi": (10, 3)}})  # fmt: skip
    inputs = _inputs(ledger, cells, True, periods={"window": ["p1", "p2"], "gap": [], "latest": []})
    result = check_stability(inputs, Stability())
    assert "stability.concordance_unstable" not in set(result.findings["finding"])
    own = inputs.concordance_per_period
    assert cochran_q(own["concordance"], own["se"]) < 0.01  # EDA's SE at each period's value
    assert result.columns["heterogeneity_p"].iloc[0] > 0.01


def _ordered(share: float, n: int = 10000) -> dict[str, tuple[int, int]]:
    """A two-bin period of `n` events and `n` non-events whose concordance is `share`."""
    high, low = round(n * share), n - round(n * share)
    return {"lo": (high, low), "hi": (low, high)}


def test_the_concordance_range_is_relative_to_the_signal() -> None:
    """The same swing of 0.06 between two periods, on 10,000 events each, is the whole signal of
    a weak feature (0.59 → 0.53) and a sixth of a strong one's (0.89 → 0.83): only the weak one
    is unstable at the default (past the floor 0.05, which binds for it), though Cochran's Q
    finds both."""
    ledger = _ledger(
        {"feature": "weak", "concordance_window": 0.56},
        {"feature": "strong", "concordance_window": 0.86},
    )  # fmt: skip
    cells = pd.concat([
        _cells("weak", {"p1": _ordered(0.59), "p2": _ordered(0.53)}),
        _cells("strong", {"p1": _ordered(0.89), "p2": _ordered(0.83)}),
    ])  # fmt: skip
    periods = {"window": ["p1", "p2"], "gap": [], "latest": []}
    result = check_stability(_inputs(ledger, cells, True, periods=periods), Stability())
    columns = result.columns.set_index("feature")
    assert columns["concordance_range"].tolist() == pytest.approx([0.06, 0.06])
    assert (columns["heterogeneity_p"] < 0.01).all()
    assert list(result.findings["feature"]) == ["weak"]


def test_psi_on_named_periods_and_new_levels_with_a_null() -> None:
    """`psi_window` compares the window's first and last periods and `psi_latest` its last with
    the latest; a null in the latest period that no window period had counts as a new level;
    without a latest period both latest findings, flag and note, read not available."""
    ledger = _ledger(
        {"feature": "trend"}, {"feature": "moved"}, {"feature": "code", "kind": "categorical"},
        {"feature": "code_had_nulls", "kind": "categorical"},
    )  # fmt: skip
    even, skewed = {"a": (900, 100), "b": (900, 100)}, {"a": (1700, 100), "b": (180, 20)}
    cells = pd.concat([
        _cells("trend", {"p1": even, "p2": skewed, "l1": {"a": 1800, "b": 200}}),
        _cells("moved", {"p1": even, "p2": even, "l1": {"a": 1800, "b": 200}}),
        _cells("code", {"p1": even, "p2": even,
                        "l1": {"a": 900, "b": 50, "__new__": 20, "null": 30}}),
        _cells("code_had_nulls", {"p1": even, "p2": {"a": (900, 100), "b": (885, 100),
                                  "null": (14, 1)}, "l1": {"a": 500, "b": 485, "null": 15}}),
    ])  # fmt: skip
    periods = {"window": ["p1", "p2"], "gap": [], "latest": ["l1"]}
    inputs = _inputs(ledger, cells, True, periods=periods)
    result = check_stability(inputs, Stability())
    found = result.findings.set_index(["feature", "finding"])
    assert set(found.index) == {
        ("trend", "stability.psi_window_large"), ("moved", "stability.psi_latest_large"),
        ("code", "stability.psi_latest_large"), ("code", "stability.new_levels"),
    }  # fmt: skip
    assert found.loc[("trend", "stability.psi_window_large"), "detail"] == "p1 → p2"
    assert found.loc[("moved", "stability.psi_latest_large"), "detail"] == "p2 → l1"
    expected = psi(np.array([0.5, 0.5, 0.0]), np.array([0.9, 0.1, 0.0]))
    assert found.loc[("moved", "stability.psi_latest_large"), "value"] == pytest.approx(expected)
    shares = result.columns.set_index("feature")["new_level_share"]
    assert shares["code"] == pytest.approx(0.05) and shares["code_had_nulls"] == 0
    assert np.isnan(shares["trend"])
    values = result.columns.set_index("feature")
    for feature, finding, field, column in [
        ("trend", "stability.psi_window_large", "psi_max", "psi_window"),
        ("moved", "stability.psi_latest_large", "psi_max", "psi_latest"),
        ("code", "stability.new_levels", "new_level_share_max", "new_level_share"),
    ]:
        value = values.loc[feature, column]
        at = check_stability(inputs, Stability(**{field: value})).findings
        past = check_stability(inputs, Stability(**{field: value + 1e-9})).findings
        assert (feature, finding) in _pairs(at) and (feature, finding) not in _pairs(past)
    no_latest = {"window": ["p1", "p2"], "gap": [], "latest": []}
    bare = check_stability(_inputs(ledger, cells, True, periods=no_latest), Stability())
    latest = bare.unavailable.loc[bare.unavailable["reason"] == NO_LATEST]
    names = ["stability.psi_latest_large", "stability.psi_latest"]
    assert _pairs(latest) == {(f, n) for f in ledger["feature"] for n in names} | {
        ("code", "stability.new_levels"), ("code_had_nulls", "stability.new_levels"),
    }  # fmt: skip


def _shifted_to(share: float) -> dict[str, tuple[int, int]]:
    """A two-bin period of 2,000 labelled rows whose first bin holds `share` of them."""
    first = round(2000 * share)
    events = first // 10
    return {"a": (first - events, events), "b": (1800 - first + events, 200 - events)}


def test_psi_is_a_note_from_psi_note_min_and_a_flag_from_psi_max() -> None:
    """PSI about 0.15 raises the note at `psi_note_min`, about 0.30 the flag at `psi_max` and no
    note, a PSI exactly at `psi_max` the flag, below `psi_note_min` nothing; a one-period window
    makes both `psi_window` findings not available."""
    ledger = _ledger({"feature": "still"}, {"feature": "noted"}, {"feature": "large"})
    even = _shifted_to(0.5)
    shares = {"still": 0.6, "noted": 0.69, "large": 0.76}  # PSI ≈ 0.04, 0.15, 0.30 from even
    cells = pd.concat([_cells(f, {"p1": even, "p2": _shifted_to(shares[f])}) for f in shares])
    periods = {"window": ["p1", "p2"], "gap": [], "latest": []}
    inputs = _inputs(ledger, cells, True, periods=periods)
    result = check_stability(inputs, Stability())
    psi_rows = result.findings.loc[result.findings["finding"].str.startswith("stability.psi")]
    found = psi_rows.set_index("feature")
    assert _pairs(psi_rows) == {("noted", "stability.psi_window"),
                                ("large", "stability.psi_window_large")}  # fmt: skip
    assert found.loc["noted", ["kind", "threshold"]].tolist() == ["note", 0.10]
    assert found.loc["large", ["kind", "threshold"]].tolist() == ["flag", 0.25]
    values = result.columns.set_index("feature")["psi_window"]
    assert values.tolist() == pytest.approx([0.04, 0.15, 0.30], abs=0.01)
    at = check_stability(inputs, Stability(psi_max=values["noted"])).findings
    assert ("noted", "stability.psi_window_large") in _pairs(at)
    assert ("noted", "stability.psi_window") not in _pairs(at)
    one = _inputs(ledger, cells, True, periods={"window": ["p2"], "gap": [], "latest": []})
    single = check_stability(one, Stability()).unavailable
    names = ["stability.psi_window_large", "stability.psi_window"]
    assert {(f, n) for f in shares for n in names} <= _pairs(single)


def test_period_psi_places_an_unseen_bin_in_the_group_at_or_below_it() -> None:
    """A numeric's groups are cut on the expected period's bins; a bin the expected period lacks
    joins the group whose range starts at or below it, the first group when below every range;
    the null bin is its own group and nothing is renormalised."""
    cells = pd.DataFrame({
        "feature": "f", "period": ["e", "e", "e", "a", "a", "a", "a"], "lagged": False,
        "bin": ["b1", "b3", "null", "b0", "b2", "b3", "null"], "bin_order": [1, 3, 9, 0, 2, 3, 9],
        "is_null": [False, False, True, False, False, False, True], "target_bin": None,
        "n": [40, 40, 20, 10, 30, 40, 20], "sum_y": NAN, "sum_y2": NAN,
    })  # fmt: skip
    expected = psi(np.array([0.4, 0.4, 0.2]), np.array([0.4, 0.4, 0.2]))
    assert period_psi(cells, "numeric", "e", "a") == pytest.approx(expected) == 0
    moved = cells.assign(n=[40, 40, 20, 10, 30, 10, 50])
    shifted = psi(np.array([0.4, 0.4, 0.2]), np.array([0.4, 0.1, 0.5]))
    assert period_psi(moved, "numeric", "e", "a") == pytest.approx(shifted)


def test_redundancy_pairs_and_clusters_with_a_categorical_and_a_not_compared_pair() -> None:
    """Pairs at and below their thresholds, one row per member with its partners; a mixed
    cluster names its categorical member; a cluster holding a not-compared pair (linked at a
    lower cut) has no `explained_by_others` and that pair's association with the best is NaN."""
    ledger = _ledger(
        {"feature": "x", "concordance": 0.70}, {"feature": "y", "concordance": 0.60},
        {"feature": "z", "kind": "categorical", "concordance": 0.65},
        {"feature": "w"}, {"feature": "v"},
    )  # fmt: skip
    table = pd.DataFrame(
        [("x", "y", 0.95, "spearman"), ("x", "z", 0.92, "eta"), ("y", "z", 0.91, "eta"),
         ("w", "v", -0.8999, "spearman"), ("x", "w", 0.1, "spearman"), ("x", "v", 0.1, "spearman"),
         ("y", "w", 0.1, "spearman"), ("y", "v", 0.1, "spearman"), ("w", "z", 0.1, "eta"),
         ("v", "z", 0.1, "eta")],
        columns=["a", "b", "statistic", "method"],
    ).assign(rows=1000)  # fmt: skip
    result = check_redundancy(_inputs(ledger, pd.DataFrame(), correlation=table), Redundancy())
    found = result.findings.set_index(["feature", "finding"])
    assert set(found.index) == {
        ("x", "redundancy.correlated_pair"), ("y", "redundancy.correlated_pair"),
        ("x", "redundancy.associated_pair"), ("y", "redundancy.associated_pair"),
        ("z", "redundancy.associated_pair"),
    }  # fmt: skip
    assert found.loc[("z", "redundancy.associated_pair"), "detail"] == "x 0.920, y 0.910"
    clusters = result.tables["clusters"].set_index("feature")
    assert list(clusters.index) == ["x", "z", "y"]
    assert clusters.loc["z", "unavailable"] == "not available: a categorical member"
    assert clusters.loc["y", "explained_by_others"] == pytest.approx(0.95**2)
    columns = result.columns.set_index("feature")
    assert columns["cluster"].tolist()[:3] == [1, 1, 1] and columns["cluster"].isna().sum() == 2
    assert columns.loc["z", "partners"] == ["x", "y"] and columns.loc["w", "partners"] == []
    linked = pd.DataFrame(
        [("a", "b", 0.99, "spearman"), ("a", "c", 0.99, "spearman"), ("b", "c", NAN, "spearman")],
        columns=["a", "b", "statistic", "method"],
    ).assign(rows=1000)
    three = _ledger(
        {"feature": "a", "concordance": 0.6}, {"feature": "b", "concordance": 0.7},
        {"feature": "c", "concordance": 0.65},
    )  # fmt: skip
    inputs = _inputs(three, pd.DataFrame(), correlation=linked)
    loose = check_redundancy(inputs, Redundancy(correlation_max=0.4)).tables["clusters"]
    assert list(loose["feature"]) == ["b", "c", "a"]
    assert np.isnan(loose["association_with_best"].iloc[1])
    assert set(loose["unavailable"]) == {"not available: a pair in the cluster was not compared"}
    exact = pd.DataFrame(
        [("s", "t", 0.90, "spearman"), ("s", "k", 0.90, "eta")],
        columns=["a", "b", "statistic", "method"],
    ).assign(rows=1000)
    pair = _ledger({"feature": "s"}, {"feature": "t"}, {"feature": "k", "kind": "categorical"})
    inputs = _inputs(pair, pd.DataFrame(), correlation=exact)
    at = check_redundancy(inputs, Redundancy()).findings
    assert set(at["finding"]) == {"redundancy.correlated_pair", "redundancy.associated_pair"}
    past = Redundancy(correlation_max=0.9 + 1e-9, association_max=0.9 + 1e-9)
    assert check_redundancy(inputs, past).findings.empty


def _panel_cells(rng: np.random.Generator) -> pd.DataFrame:
    """The cells of a 2,000-client panel over window periods `w1`–`w3`, a gap `g1` and a latest
    `l1` (no label outside the window): a numeric in four bins and a categorical with client folds
    in the window, both current and lagged, the target rising with both."""
    clients, periods = np.arange(2000), ["w1", "w2", "w3", "g1", "l1"]
    x = rng.normal(size=(clients.size, len(periods))).cumsum(axis=1)
    code = rng.integers(0, 3, clients.size)
    rows = []
    for i, period in enumerate(periods):
        rate = 1 / (1 + np.exp(3.5 - 0.6 * x[:, i] - 0.8 * code))
        unlabelled = np.full(clients.size, NAN)
        y = (rng.random(clients.size) < rate).astype(float) if period[0] == "w" else unlabelled
        for lagged in [False, True] if period.startswith("w") else [False]:
            values = x[:, i - 1] if lagged and i > 0 else (None if lagged else x[:, i])
            rows.append(_rows(clients, period, lagged, values, code, y))
    frame = pd.concat(rows, ignore_index=True)
    keys = ["feature", "period", "lagged", "fold", "bin", "bin_order", "is_null", "target_bin"]
    grouped = frame.assign(y2=frame["y"] ** 2).groupby(keys, dropna=False)
    sums = grouped[["y", "y2"]].sum(min_count=1).set_axis(["sum_y", "sum_y2"], axis=1)
    cells = pd.concat([grouped.size().rename("n"), sums], axis=1).reset_index()
    return cells.astype({"fold": "Int64", "bin_order": int})


def _rows(
    clients: np.ndarray,
    period: str,
    lagged: bool,
    values: np.ndarray | None,
    code: np.ndarray,
    y: np.ndarray,
) -> pd.DataFrame:
    """One period's rows of both features (`values` None: every value null, the first lag)."""
    in_window = period.startswith("w")
    target = np.where(np.isnan(y), None, np.nan_to_num(y).astype(int).astype(str))
    null = values is None
    bins = np.zeros(clients.size, dtype=int) if null else np.digitize(values, [-1.0, 0.0, 1.0])
    numeric = pd.DataFrame({"feature": "x", "bin_order": np.where(null, 4, bins), "is_null": null,
                            "fold": pd.NA})  # fmt: skip
    numeric["bin"] = np.where(null, "null", "b" + numeric["bin_order"].astype(str))
    levels = np.array(["a", "b", "c"])[code]
    categorical = pd.DataFrame({"feature": "code", "bin": np.where(null, "null", levels),
                                "bin_order": np.where(null, 3, code), "is_null": null,
                                "fold": clients % 5 if in_window else pd.NA})  # fmt: skip
    both = pd.concat([numeric, categorical], ignore_index=True)
    return both.assign(period=period, lagged=lagged, target_bin=np.tile(target, 2),
                       y=np.tile(y, 2))  # fmt: skip


def test_check_inputs_and_every_step_over_one_panel(cc_config: UseCaseConfig) -> None:
    """`check_inputs` keeps the read candidates only, builds the label-free per-period table (PSI
    0 at the snapshot) and keeps EDA's per-period concordance; every step returns its columns for
    every read candidate in run order; EDA's artifacts without its columns, the ledger's identity
    columns included, without the ranking columns read (the window's best order among them),
    without the per-period concordance table or a column of it, or without `eda.json`'s window
    clients or headline are refused, and so is a ledger without a read candidate."""
    cells = _panel_cells(np.random.default_rng(0))
    ledger = pd.concat([
        _ledger({"feature": "x", "concordance_window": 0.7},
                {"feature": "code", "kind": "categorical", "levels": 3.0}),
        _ledger({"feature": "target_source", "lineage": True},
                {"feature": "blob", "kind": "unsupported", "unsupported": True}),
    ], ignore_index=True)  # fmt: skip
    window = ["w1", "w2", "w3"]
    tables = {
        "cells": cells,
        "client_constant": pd.DataFrame({"feature": ["x", "code"], "constant_share": [0.1, 1.0]}),
        "correlation": pd.DataFrame([("x", "code", 0.3, "eta", 2000)],
                                    columns=["a", "b", "statistic", "method", "rows"]),
        "ranking": _ranking(ledger.iloc[:2], {}),
        "concordance_per_period": _eda_per_period(
            cells, {"x": "numeric", "code": "categorical"}, window, "binary"
        ),
    }  # fmt: skip
    meta = {"compared_periods": {"window": window, "gap": ["g1"], "latest": ["l1"]},
            "snapshot_period": "w3", "over_ceiling": [], "clients": _clients(1.0),
            "headline": {}}  # fmt: skip
    inputs = check_inputs(ledger, tables, meta, cc_config)
    assert list(inputs.ledger["feature"]) == ["x", "code"] and inputs.null_concordance_max == 0.7
    assert inputs.dominant_share_min == 0.9
    assert inputs.concordance_per_period is tables["concordance_per_period"]
    table = inputs.per_period
    assert list(table.columns) == PER_PERIOD_COLUMNS and len(table) == 10
    assert (table.loc[table["period"] == "w3", "psi"] == 0).all()
    latest = table.set_index(["feature", "period"]).loc[("x", "l1"), "psi"]
    assert latest > 0.01 and latest == period_psi(
        cells.loc[cells["feature"] == "x"], "numeric", "w3", "l1"
    )
    assert list(STEPS) == STEP_ORDER
    for step, check in STEPS.items():
        result = check(inputs, getattr(cc_config.feature_checks, step))
        assert list(result.columns.columns) == ["feature", *STEP_COLUMNS[step]]
        assert list(result.columns["feature"]) == ["x", "code"]
        assert set(result.findings["step"]) <= {step}
        assert not result.unavailable["reason"].str.startswith("not tested").any()
    lagged = check_time_alignment(inputs, TimeAlignment()).columns.set_index("feature")
    assert lagged["lagged_concordance"].between(0.5, 1).all()
    for column in ["null_concordance_window", "lineage"]:
        with pytest.raises(ValueError, match=f"lack .*{column}.*run EDA"):
            check_inputs(ledger.drop(columns=column), tables, meta, cc_config)
    for key in ["clients", "headline"]:
        without = {name: value for name, value in meta.items() if name != key}
        with pytest.raises(ValueError, match=f"lack .*eda.json keys.*{key}"):
            check_inputs(ledger, tables, without, cc_config)
    for column in ["unavailable", "concordance_best_order_window"]:
        stale = {**tables, "ranking": tables["ranking"].drop(columns=column)}
        with pytest.raises(ValueError, match=f"lack .*ranking columns.*{column}"):
            check_inputs(ledger, stale, meta, cc_config)
    no_table = {name: table for name, table in tables.items() if name != "concordance_per_period"}
    with pytest.raises(ValueError, match="lack .*tables.*concordance_per_period"):
        check_inputs(ledger, no_table, meta, cc_config)
    no_se = {
        **tables,
        "concordance_per_period": tables["concordance_per_period"].drop(columns="se"),
    }
    with pytest.raises(ValueError, match="lack .*concordance_per_period columns.*se"):
        check_inputs(ledger, no_se, meta, cc_config)
    with pytest.raises(ValueError, match="no read candidates"):
        check_inputs(ledger.assign(lineage=True), tables, meta, cc_config)
