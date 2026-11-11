"""The trap acceptance test (D-064, D-137; test_harness.md "Framework tests assert against the
ground truth", feature_checks.md "Trap acceptance test").

Target Factory, EDA and Feature Checks run once on the `dev` preset (20,000 clients, generated
from its seed in the test run) for the two example configs, card and term-deposit acquisition.
The acceptance list is `truth.json`'s trap list: each row, keyed by trap kind and target, is
mapped to the findings that must catch it (`TRAP_FINDINGS`, `KIND_CHECKS`), to the findings it
must not raise as a control close to their thresholds (`CONTROL_FINDINGS`; a row may be both), a
null control (no signal, no flag), or listed in `NOT_CHECKS` with a reason; a row in none of them
fails, so a new trap cannot slip past. A target-specific row is asserted on its config, an "any
product" row on both; the deposit's sub-range missing leak is also asserted to raise no
missingness leak on the card config, where its nulls carry no signal. Assertions read the window
statistics (the ledger's `*_window` columns and the findings), never the snapshot's. The false
positives are checked on the controls (each forbidden finding's measure computed, so none passes
vacuously), on the null controls (pure noise, never flagged) and, count-free, on the card config's
legitimate columns, the real columns named only for a note or as a control among them: none raises
a leak or lag flag (`NEVER_ON_LEGITIMATE`). EDA's population counts per period (D-088) and the
numeric bins (T25) are checked against the truth too. Trap columns are found from the truth, never
by name.
"""

from dataclasses import dataclass
from pathlib import Path

import pandas as pd
import pytest
from pyspark.sql import SparkSession

from core_modelling.artifacts import read_stage
from core_modelling.config import UseCaseConfig, load_config
from core_modelling.feature_checks.findings import FINDINGS
from core_modelling.ledger import read_ledger
from core_modelling.run import run
from core_modelling.statistics.scope import NULL_SHARE_RANGE
from synthetic.mechanisms.mart import parse_column
from synthetic.output import read_output
from synthetic.truth.oracle import STANDARD_TARGETS, realised_target

pytestmark = pytest.mark.traps

ROOT = Path(__file__).resolve().parents[1]
CONFIGS = {
    "cc_acquire": ROOT / "tests/conf/cc_acquisition.yml",
    "td_acquire": ROOT / "tests/conf/td_acquisition.yml",
}  # the truth's target → the config modelling it (frozen copies of the shipped examples)
NO_LOAN_CONFIG = "no config: loan target"
# (trap kind, target) → the findings that must fire on the trap's column(s); None = any product
TRAP_FINDINGS = {
    ("leak", "cc_acquire"): ("leakage.too_strong",),  # the U-shaped one in best order
    ("upstream_target", "cc_acquire"): ("leakage.too_strong",),
    ("missing_leak", "cc_acquire"): ("leakage.missingness_leak",),
    ("missing_leak", "td_acquire"): ("leakage.missingness_leak",),  # below EDA's null-share range
    ("process_leak", "cc_acquire"): ("leakage.rare_value_leak",),  # the count and the status
    ("shifted", "cc_acquire"): ("time_alignment.lagged_signal_drop",),
    ("redundant", "cc_acquire"): ("redundancy.correlated_pair",),
    ("eligibility_defining", "cc_acquire"): ("quality.constant",),
    ("unstable", "cc_acquire"): ("stability.concordance_unstable",),
    ("shared_null_set", "cc_acquire"): ("quality.nulls_informative",),
    ("recency_null_zero", "cc_acquire"): ("quality.nulls_may_be_zeros",),
    ("constant", None): ("quality.constant",),
    ("near_constant", None): ("quality.near_constant",),
    ("all_null", None): ("quality.all_null",),
    ("low_fill", None): ("quality.high_missing",),
    ("high_cardinality", None): ("quality.high_cardinality",),
    # its concordance (≈ 0.78) sits at too_strong's 0.80, so only client_constant is asserted
    ("lookahead", None): ("time_alignment.client_constant",),
    # on the column or a roll-up: 0.37–0.50 on the canonical data, against psi_max 0.25
    ("drift", None): ("stability.psi_latest_large",),
    ("collinearity", None): ("redundancy.associated_pair",),
    ("drift_window", None): ("stability.psi_window_large", "quality.nulls_may_be_zeros"),
    ("drift_moderate", None): ("stability.psi_window", "stability.psi_latest",
                               "stability.new_levels"),
}  # fmt: skip
# (trap kind, target) → the findings a control row's columns must not raise; only findings that
# could fire there and that no trap assertion already excludes (a note and its flag are exclusive)
CONTROL_FINDINGS = {
    ("honest", "cc_acquire"): ("leakage.too_strong", "stability.concordance_unstable",
                               "time_alignment.lagged_signal_drop",
                               "time_alignment.client_constant"),
    ("unstable", "cc_acquire"): ("leakage.too_strong",),
    ("static_attribute", "cc_acquire"): ("time_alignment.client_constant",),
    ("dominant_level", "cc_acquire"): ("leakage.rare_value_leak",),
    ("recency_null_zero", "cc_acquire"): ("quality.high_missing",),
    ("recency_with_zeros", "cc_acquire"): ("quality.nulls_may_be_zeros", "quality.high_missing"),
    ("weak_nulls", "cc_acquire"): ("quality.nulls_informative", "leakage.missingness_leak"),
    ("one_value", None): ("quality.constant", "quality.near_constant", "quality.high_missing",
                          "quality.nulls_informative", "stability.new_levels"),
    ("drift_window", None): ("quality.high_missing", "quality.nulls_informative",
                             "stability.psi_latest_large", "stability.psi_latest"),
}  # fmt: skip
# a finding's measure → the ledger column it is read from, where the two names differ
MEASURE_COLUMNS = {"concordance_window_or_best_order": "concordance_window"}
# the rare-value effect is not in the ledger: it is computed where a filled value holds
# `dominant_share_min`, which a window value share at that bound (null counted) guarantees
RARE_EFFECT = "leakage.rare_value_leak"
# the deposit's sub-range missing leak on the card config, where its nulls carry no signal
SUB_RANGE_LEAK = ("missing_leak", "td_acquire")
KIND_CHECKS = {("decimal_type", None): "numeric"}  # (kind, target) → the ledger's `kind`
NOT_CHECKS = {
    ("simpson", "cc_acquire"): "an EDA view: the target by onboarding channel",
    ("onboarding", "cc_acquire"): "an EDA view: the onboarding wave in relationship_days",
    ("null_income_eligibility", "cc_acquire"): "an EDA view: the eligibility step log",
    ("process_leak", "loan_personal_open"): NO_LOAN_CONFIG,
    ("shifted", "loan_personal_open"): NO_LOAN_CONFIG,
    ("rare_level", "loan_personal_open"): NO_LOAN_CONFIG,
    ("inverted_u", "loan_personal_open"): NO_LOAN_CONFIG,
    ("hidden_openings", "loan_personal_open"): NO_LOAN_CONFIG,
    ("eligibility_defining", "loan_personal_open"): NO_LOAN_CONFIG,
    ("spend_leak", "spend_cc_next_3_months"): "asserted on the regression variant in "
    "test_feature_checks.py",
    ("dirty", None): "off by default",
    ("extra", None): "off by default",
}
NULL_CONCORDANCE_MAX = 0.55
# the flags no column outside the truth's trap list may raise on the card config (Q545): a
# leakage or time-alignment check firing on genuine signal; a real minority (rare_value_leak) and
# a static attribute (client_constant) raise theirs by design
NEVER_ON_LEGITIMATE = {"leakage.too_strong", "leakage.missingness_leak",
                       "time_alignment.lagged_signal_drop"}  # fmt: skip
MAX_BIN_SHARE = 0.05  # of a feature's non-null snapshot rows, for any bin but a singleton


def _income_known_or_salaried(mart: pd.DataFrame) -> pd.Series:
    """The card config's analysis filters restated on the mart."""
    return mart["income"].notna() | (mart["salary_transfer_flag"] == 1)


def _every_row(mart: pd.DataFrame) -> pd.Series:
    """The term-deposit config has no analysis filter."""
    return pd.Series(True, index=mart.index)


ANALYSIS_FILTERS = {"cc_acquire": _income_known_or_salaried, "td_acquire": _every_row}


@dataclass(frozen=True)
class TrapRun:
    """One config's artifacts: `eda.json`, EDA's cells, the ledger after Feature Checks and the
    findings."""

    eda: dict
    cells: pd.DataFrame
    ledger: pd.DataFrame
    findings: pd.DataFrame


@pytest.fixture(scope="module")
def trap_runs(spark: SparkSession, dev_env_file: str) -> dict[str, TrapRun]:
    """Target Factory on both configs (one model input), then EDA and Feature Checks per
    config, each run once; by the truth's target."""
    run(list(CONFIGS.values()), env_path=dev_env_file, stages=["target_factory"])
    out = {}
    for target, config in CONFIGS.items():
        run(config, env_path=dev_env_file, stages=["eda"])
        paths = run(config, env_path=dev_env_file, stages=["feature_checks"])
        folder = Path(paths["entity_a"]["feature_checks"][config.stem]["folder"])
        eda, tables = read_stage(str(folder.parent / "eda"), "eda")
        _, check_tables = read_stage(str(folder), "feature_checks")
        ledger = read_ledger(str(folder.parent))
        out[target] = TrapRun(eda=eda, cells=tables["cells"], ledger=ledger,
                              findings=check_tables["findings"])  # fmt: skip
    return out


@pytest.fixture(scope="module")
def configs() -> dict[str, UseCaseConfig]:
    """The example configs loaded, by the truth's target."""
    return {target: load_config(path) for target, path in CONFIGS.items()}


@pytest.fixture(scope="module")
def parsed(dev_output: tuple[str, dict]) -> dict[str, dict]:
    """Each mart column's name parts (`parse_column`, on the truth's products)."""
    truth = dev_output[1]
    products = list(truth["spec"]["products"])
    return {entry["name"]: parse_column(entry["name"], products) for entry in truth["columns"]}


def _traps(truth: dict) -> list[dict]:
    """The truth's trap list."""
    return truth["spec"]["traps"]


def _key(trap: dict) -> tuple[str, str | None]:
    """A trap row's (kind, target)."""
    return trap["kind"], trap["target"]


def _columns(trap: dict) -> list[str]:
    """The columns a trap row names: its column and the ones its parameters add (`also`)."""
    return [trap["column"], *trap["parameters"].get("also", [])] if trap["column"] else []


def _read_candidates(ledger: pd.DataFrame) -> pd.DataFrame:
    """The ledger's read candidates: neither lineage nor unsupported."""
    return ledger.loc[~(ledger["lineage"] | ledger["unsupported"])]


def _asserted_on(trap: dict, target: str) -> bool:
    """Whether a trap row is asserted on the config of `target`: its own target, or any."""
    return trap["target"] in (target, None)


def _may_leak_by_design(trap: dict) -> bool:
    """Whether a trap row's columns may raise a `NEVER_ON_LEGITIMATE` flag by design: a trap
    column, or a real-column row whose own findings include one. A row only listed (`NOT_CHECKS`,
    `KIND_CHECKS`) is not exempt: its real columns (`income`, `age`, `cc_limit`, …) stay guarded."""
    own = set(TRAP_FINDINGS.get(_key(trap), ()))
    return trap["trap_column"] or bool(own & NEVER_ON_LEGITIMATE)


def test_every_trap_row_is_mapped_or_listed(dev_output: tuple[str, dict]) -> None:
    """Every trap row is mapped, a control, a null control or in `NOT_CHECKS`, and every key
    names a row."""
    keys = {_key(trap) for trap in _traps(dev_output[1])}
    placed = {*TRAP_FINDINGS, *KIND_CHECKS, *NOT_CHECKS, *CONTROL_FINDINGS}
    unplaced = sorted(key for key in keys if key not in placed and key[0] != "null_control")
    assert not unplaced, f"trap rows neither mapped nor in NOT_CHECKS: {unplaced}"
    assert not placed - keys, f"keys naming no trap row: {sorted(placed - keys, key=str)}"


@pytest.mark.parametrize("target", list(CONFIGS))
def test_each_mapped_trap_fires_its_finding(
    target: str,
    trap_runs: dict[str, TrapRun],
    dev_output: tuple[str, dict],
    parsed: dict[str, dict],
) -> None:
    """Each mapped trap row of the config (its target or any product) raises each of its findings
    on the window statistics; the failure names every trap missed."""
    truth, result = dev_output[1], trap_runs[target]
    raised = _raised(result)
    missed = []
    for trap in _traps(truth):
        if _key(trap) in TRAP_FINDINGS and _asserted_on(trap, target):
            for finding in TRAP_FINDINGS[_key(trap)]:
                missed += _missed(trap, finding, raised, result.ledger, parsed)
    assert not missed, f"{target}: traps not caught:\n" + "\n".join(missed)


@pytest.mark.parametrize("target", list(CONFIGS))
def test_each_control_raises_no_forbidden_finding(
    target: str,
    trap_runs: dict[str, TrapRun],
    dev_output: tuple[str, dict],
    configs: dict[str, UseCaseConfig],
) -> None:
    """Each control row of the config (its target or any product) has every column read, each
    forbidden finding's measure computed on it (a check that never ran would pass vacuously) and
    none of them raised; the failure names every one."""
    result = trap_runs[target]
    raised, read = _raised(result), set(_read_candidates(result.ledger)["feature"])
    ledger = result.ledger.set_index("feature")
    dominant_min = configs[target].feature_checks.leakage.dominant_share_min
    unread, unmeasured, fired = [], [], []
    for trap in _traps(dev_output[1]):
        if _key(trap) not in CONTROL_FINDINGS or not _asserted_on(trap, target):
            continue
        unread += [column for column in _columns(trap) if column not in read]
        pairs = [(column, finding) for finding in CONTROL_FINDINGS[_key(trap)]
                 for column in _columns(trap) if column in read]  # fmt: skip
        unmeasured += [pair for pair in pairs if not _measured(ledger, *pair, dominant_min)]
        fired += [f"{trap['kind']} ({trap['target']}): {finding} on {column}"
                  for column, finding in pairs if (column, finding) in raised]  # fmt: skip
    assert not unread, f"{target}: control columns not read, so not asserted: {unread}"
    assert not unmeasured, f"{target}: controls whose measure was not computed: {unmeasured}"
    assert not fired, f"{target}: controls raised a forbidden finding:\n" + "\n".join(fired)


def _measured(ledger: pd.DataFrame, column: str, finding: str, dominant_min: float) -> bool:
    """Whether `finding`'s measure was computed on `column`: its ledger column is set, or, for
    the rare-value effect, a value holds `dominant_min` of the window; raises for a measure the
    test cannot see."""
    if finding == RARE_EFFECT:
        return bool(ledger.at[column, "dominant_share_window"] >= dominant_min)
    measure = FINDINGS[finding]["measure"]
    measure = MEASURE_COLUMNS.get(measure, measure)
    if measure not in ledger.columns:
        raise ValueError(f"{finding}: its measure {measure!r} is not a ledger column")
    return bool(pd.notna(ledger.at[column, measure]))


def test_sub_range_missing_leak_fires_on_its_target_only(
    trap_runs: dict[str, TrapRun], dev_output: tuple[str, dict]
) -> None:
    """The deposit's blanked rate is read below EDA's null-share range on both configs: on its
    own it raises the missingness leak through that path, and on the card config, where its
    nulls carry no signal, no missingness leak."""
    columns = [c for t in _traps(dev_output[1]) if _key(t) == SUB_RANGE_LEAK for c in _columns(t)]
    assert columns, f"no trap row {SUB_RANGE_LEAK}"
    for target in CONFIGS:
        missing = trap_runs[target].ledger.set_index("feature").loc[columns, "missing_share_window"]
        assert (missing < NULL_SHARE_RANGE[0]).all(), (target, missing.to_dict())
    findings = trap_runs["td_acquire"].findings
    leak = findings["feature"].isin(columns) & (findings["finding"] == "leakage.missingness_leak")
    details = findings.loc[leak, "detail"]
    assert len(details) == len(columns), f"td_acquire: missingness leaks {details.tolist()}"
    assert details.str.startswith("read below EDA's null-share range").all(), details.tolist()
    findings = trap_runs["cc_acquire"].findings
    fired = findings.loc[findings["feature"].isin(columns)
                         & (findings["finding"] == "leakage.missingness_leak")]  # fmt: skip
    assert fired.empty, fired[["feature", "finding", "value", "detail"]].to_string()


def _raised(result: TrapRun) -> set[tuple[str, str]]:
    """The run's (feature, finding) pairs."""
    return set(zip(result.findings["feature"], result.findings["finding"], strict=True))


def _missed(
    trap: dict,
    finding: str,
    raised: set[tuple[str, str]],
    ledger: pd.DataFrame,
    parsed: dict[str, dict],
) -> list[str]:
    """What a trap row should have raised and did not, one line each. A drift may show on the
    column or its roll-ups (the login roll-ups drift more than the monthly count); collinearity
    is asserted on the `<product>_status` ⇔ `<product>_flag` identities whose members are both
    read; the redundant column must pair with its source."""
    kind, partners = trap["kind"], ledger.set_index("feature")["partners"]
    if kind == "drift":
        family = [trap["column"], *_rollups(trap["column"], parsed)]
        hit = any((name, finding) in raised for name in family)
        return [] if hit else [f"{kind}: {finding} on none of {family}"]
    if kind == "collinearity":
        pairs = _status_pairs(parsed, ledger)
        if not pairs:
            return [f"{kind}: no <product>_status and _flag pair among the read candidates"]
        return [f"{kind}: {status} not paired with {flag}" for status, flag in pairs
                if (status, finding) not in raised or flag not in partners[status]]  # fmt: skip
    lines = [f"{kind} ({trap['target']}): {finding} not on {column}"
             for column in _columns(trap) if (column, finding) not in raised]  # fmt: skip
    source = trap["parameters"].get("of")
    if kind == "redundant" and source not in partners[trap["column"]]:
        lines.append(f"{kind}: {trap['column']} not paired with {source}")
    return lines


def _rollups(column: str, parsed: dict[str, dict]) -> list[str]:
    """The mart's roll-ups of `column` (their `base`)."""
    return [name for name, parts in parsed.items() if parts.get("base") == column]


def _status_pairs(parsed: dict[str, dict], ledger: pd.DataFrame) -> list[tuple[str, str]]:
    """Each product's (`<product>_status`, `<product>_flag`) from the truth's columns, both
    read candidates (a target's own flag is lineage)."""
    states = {(parts["product"], parts["kind"]): name
              for name, parts in parsed.items() if parts["group"] == "state"}  # fmt: skip
    read = set(_read_candidates(ledger)["feature"])
    pairs = [(name, states[product, "flag"]) for (product, kind), name in states.items()
             if kind == "status" and (product, "flag") in states]  # fmt: skip
    return [(status, flag) for status, flag in pairs if {status, flag} <= read]


@pytest.mark.parametrize("target", list(CONFIGS))
def test_kind_traps_read_as_their_kind(
    target: str, trap_runs: dict[str, TrapRun], dev_output: tuple[str, dict]
) -> None:
    """The decimal column is a numeric candidate (Spark's decimal read as a number)."""
    kinds = trap_runs[target].ledger.set_index("feature")["kind"]
    for trap in _traps(dev_output[1]):
        if _key(trap) in KIND_CHECKS and _asserted_on(trap, target):
            assert kinds[trap["column"]] == KIND_CHECKS[_key(trap)], trap["column"]


@pytest.mark.parametrize("target", list(CONFIGS))
def test_null_controls_carry_no_signal_and_no_flag(
    target: str, trap_runs: dict[str, TrapRun], dev_output: tuple[str, dict]
) -> None:
    """Every null control's window concordance is below 0.55 and it raises no flag."""
    ledger = trap_runs[target].ledger.set_index("feature")
    controls = [t["column"] for t in _traps(dev_output[1]) if t["kind"] == "null_control"]
    for column in controls:
        assert ledger.at[column, "concordance_window"] < NULL_CONCORDANCE_MAX, column
        assert len(ledger.at[column, "flags"]) == 0, (column, list(ledger.at[column, "flags"]))


def test_legitimate_columns_raise_no_leak_or_lag_flag(
    trap_runs: dict[str, TrapRun], dev_output: tuple[str, dict]
) -> None:
    """No card-config candidate raises a `NEVER_ON_LEGITIMATE` flag unless a trap row allows it
    (`_may_leak_by_design`): the checks may hold genuine features by design, but never as a leak
    or a lag; real columns named only for a note or as a control stay under the guard."""
    trap_columns = {column for trap in _traps(dev_output[1]) if _may_leak_by_design(trap)
                    for column in _columns(trap)}  # fmt: skip
    findings = trap_runs["cc_acquire"].findings
    fired = findings.loc[
        findings["finding"].isin(NEVER_ON_LEGITIMATE) & ~findings["feature"].isin(trap_columns)
    ]
    assert fired.empty, fired[["feature", "finding", "value", "detail"]].to_string()


@pytest.mark.parametrize("target", list(CONFIGS))
def test_population_counts_match_the_truth(
    target: str,
    trap_runs: dict[str, TrapRun],
    dev_output: tuple[str, dict],
    configs: dict[str, UseCaseConfig],
) -> None:
    """EDA's population counts per compared period (D-088) equal the mart's: rows after the
    analysis filters, the truth's eligible rows, and, in the window, the rows with a realised
    target and the positive ones (null outside the window)."""
    spec = STANDARD_TARGETS[target]
    columns = ["client_id", "snapshot_month", "income", "salary_transfer_flag", spec["column"],
               *spec["eligible"]]  # fmt: skip
    mart = read_output(dev_output[0], "mart", list(dict.fromkeys(columns)))
    kept = ANALYSIS_FILTERS[target](mart)
    eligible = pd.Series(True, index=mart.index)
    for column, value in spec["eligible"].items():
        eligible &= mart[column] == value
    realised = realised_target(mart, target, configs[target].time.target_window)
    truth = pd.DataFrame({
        "period": pd.to_datetime(mart["snapshot_month"]).dt.strftime("%Y-%m"),
        "rows": kept, "eligible_rows": kept & eligible,
        "known_target": kept & realised.notna(), "positive_rows": kept & (realised == 1),
    }).groupby("period").sum()  # fmt: skip
    result = trap_runs[target].eda
    population = pd.DataFrame(result["population"]).set_index("period")
    window = result["compared_periods"]["window"]
    for column in ["rows", "eligible_rows", "known_target", "positive_rows"]:
        expected = truth.loc[population.index, column].astype(float)
        if column in ("known_target", "positive_rows"):
            expected = expected.where(population.index.isin(window))
        pd.testing.assert_series_equal(population[column].astype(float), expected)


@pytest.mark.parametrize("target", list(CONFIGS))
def test_numeric_bins_follow_the_edges_rule(
    target: str, trap_runs: dict[str, TrapRun], configs: dict[str, UseCaseConfig]
) -> None:
    """In the snapshot's cells every numeric candidate has at least min(distinct values,
    `eda.bins // 2`) non-null bins, and no bin but a singleton holds more than 5% of its non-null
    rows (T25)."""
    result = trap_runs[target]
    # the facts spike's min(distinct, 50) at the configs' 100 bins
    max_floor = configs[target].eda.bins // 2
    read = _read_candidates(result.ledger)
    numeric = read.loc[read["kind"] == "numeric"]
    cells = result.cells
    current = (cells["period"] == result.eda["snapshot_period"]) & ~cells["lagged"]
    snapshot = cells.loc[current & ~cells["is_null"] & cells["feature"].isin(numeric["feature"])]
    rows = snapshot.groupby(["feature", "bin"])["n"].sum()
    rows = rows[rows > 0].reset_index()
    bins = rows.groupby("feature").size().reindex(numeric["feature"], fill_value=0)
    floor = numeric.set_index("feature")["levels"].clip(upper=max_floor)
    few = {name: int(bins[name]) for name in bins.index if bins[name] < floor[name]}
    assert not few, f"{target}: numerics with too few bins (feature: bins): {few}"
    share = rows["n"] / rows.groupby("feature")["n"].transform("sum")
    wide = rows.loc[~rows["bin"].str.startswith("= ") & (share > MAX_BIN_SHARE)]
    assert wide.empty, f"{target}: bins over {MAX_BIN_SHARE:.0%}:\n{wide.to_string()}"
