"""Synthetic data, build step 4: the feature mart (names, column order, null rule, written types),
with every rollup, recency and ratio recomputed independently by Spark window functions."""

import pandas as pd
import pytest
from pyspark.sql import Column, SparkSession, Window, WindowSpec
from pyspark.sql import functions as F

from synthetic.check_suite import run_checks
from synthetic.checks_mart import snapshot_columns
from synthetic.names import parse_column
from synthetic.presets import PRESETS

# Build stage D adds the 8 trap columns and removes this exclusion: until then the mart lacks them.
SNAPSHOT_ROW = "column list equals the snapshot"
TOLERANCE = 1e-6


def _without_snapshot_row(checks: pd.DataFrame) -> pd.DataFrame:
    """The check table without the column-list row, which fails until stage D (trap columns)."""
    return checks[checks["check"] != SNAPSHOT_ROW]


def test_mart_rules_hold_on_unit(unit_output: tuple[str, dict]) -> None:
    """On the unit preset, every row of the mart family (all rules) passes."""
    checks = _without_snapshot_row(run_checks(unit_output[0], ["mart"])["mart"])
    rules = checks[checks["rule"]]
    assert len(rules) == len(checks) and rules["passed"].all(), rules[~rules["passed"]].to_string()


@pytest.mark.slow
def test_mart_checks_pass_on_canonical(canonical_output: tuple[str, dict, dict]) -> None:
    """Every row passes at the canonical size, on a fifth of the clients (every column is read)."""
    checks = run_checks(canonical_output[0], ["mart"], client_sample=5)["mart"]
    checks = _without_snapshot_row(checks)
    assert checks["passed"].all(), checks[~checks["passed"]].to_string()


def test_mart_columns_follow_the_snapshot(unit: tuple[pd.DataFrame, pd.DataFrame, dict]) -> None:
    """The mart's columns are the committed snapshot's, in order, but for the trap columns that
    build stage D adds (it then drops this filter: the mart family checks the full list)."""
    expected = [c for c in snapshot_columns() if "_trap_" not in c]
    assert list(unit[0].columns) == expected


def test_names_parse_into_their_parts() -> None:
    """The grammar reads each kind of name back into its parts and rejects names outside it."""
    products = list(PRESETS["unit"]["spec"]["products"])
    rollup = parse_column("spend_cc_travel_vol_0_2_months_avg", products)
    assert [rollup[k] for k in ("group", "first", "last", "agg")] == ["rollup", 0, 2, "avg"]
    assert rollup["of"] == {"group": "activity", "measure": "spend", "product": "cc",
                            "subcat": "travel", "kind": "vol"}  # fmt: skip
    assert parse_column("cc_active_flag", products)["product"] == "cc"
    assert parse_column("loan_personal_maturity_months", products)["kind"] == "maturity_months"
    assert parse_column("months_since_last_fx", products)["of"]["kind"] == "vol"
    assert parse_column("casa_bal_0_2_vs_3_5_months_ratio", products)["base"] == "casa_bal"
    assert parse_column("extra_0001_trap_weak", products)["kind"] == "weak"
    for name in ("cc_flagg", "spend_xx_vol", "casa_bal_0_2_months_mean", "months_since_last_x"):
        with pytest.raises(ValueError):
            parse_column(name, products)


def test_spark_reads_the_written_types(spark: SparkSession, unit_output: tuple[str, dict]) -> None:
    """Spark reads flags as int, counts as bigint, `cc_limit` as decimal(18,2), the month a date."""
    types = dict(spark.read.parquet(f"{unit_output[0]}/mart").dtypes)
    assert {t for c, t in types.items() if c.endswith("_flag")} == {"int"}
    assert types["cc_limit"] == "decimal(18,2)"
    assert types["snapshot_month"] == "date"
    counters = [
        "fx_cnt",
        "loan_home_maturity_months",
        "months_since_last_fx",
        "fx_vol_0_5_months_nz",
    ]
    assert {types[c] for c in counters} == {"bigint"}
    assert (types["casa_bal_0_5_months_std"], types["td_status"]) == ("double", "string")


def _months(first: int, last: int) -> WindowSpec:
    """A client's months from `first` to `last` relative to the row's (0 = the row's month)."""
    return Window.partitionBy("client_id").orderBy("m").rangeBetween(first, last)


def _spark_rollup(base: str, months: int, agg: str) -> Column:
    """A rollup over the row's month and the `months − 1` before it; null unless the client has
    a row in every one of them (Spark's own aggregates skip nulls, so months are counted)."""
    window = _months(1 - months, 0)
    nonzero = F.sum(F.when(F.col(base) != 0, 1).otherwise(0))
    value = {"avg": F.avg(base), "max": F.max(base), "min": F.min(base), "sum": F.sum(base),
             "std": F.stddev_samp(base), "nz": nonzero}[agg]  # fmt: skip
    return F.when(F.count(F.lit(1)).over(window) == months, value.over(window))


def _spark_ratio(base: str) -> Column:
    """Average of months 0–2 over months 3–5; null without 6 months or with a zero 3–5 average."""
    recent, earlier = F.avg(base).over(_months(-2, 0)), F.avg(base).over(_months(-5, -3))
    full = F.count(F.lit(1)).over(_months(-5, 0)) == 6
    return F.when(full & (earlier != 0), recent / earlier)


def _spark_last_nonzero(base: str) -> Column:
    """The month number of the client's last non-zero `base` up to the row's month (in the mart)."""
    up_to_now = (
        Window.partitionBy("client_id").orderBy("m").rowsBetween(Window.unboundedPreceding, 0)
    )
    return F.max(F.when(F.col(base) != 0, F.col("m"))).over(up_to_now)


def _month_number(date: Column) -> Column:
    """Months since year 0 of a date column, for month arithmetic."""
    return F.year(date) * 12 + F.month(date)


def _spark_expected(parts: dict[str, dict]) -> tuple[dict[str, Column], dict[str, Column]]:
    """Spark's value of every rollup, ratio and months-since column of the parsed mart columns,
    and for the months-since columns the last non-zero month Spark saw."""
    expected, last = {}, {}
    for name, p in parts.items():
        if p["group"] == "rollup":
            expected[name] = _spark_rollup(p["base"], p["last"] + 1, p["agg"])
        elif p["group"] == "ratio":
            expected[name] = _spark_ratio(p["base"])
        elif p["group"] == "recency" and p["unit"] == "months":
            last[name] = _spark_last_nonzero(name.removeprefix("months_since_last_") + "_vol")
            expected[name] = F.col("m") - last[name]
    return expected, last


def test_spark_recomputes_every_rollup_recency_and_ratio(
    spark: SparkSession, unit_output: tuple[str, dict]
) -> None:
    """Spark window functions over each client's months give the written rollups, recency and
    ratios: values within 1e-6, nulls exactly.

    The burn-in months the generator saw are not in the mart, so only rows whose history lies
    inside the written panel are compared: rollups and ratios from the panel's 6th month on (the
    6-month window inside the panel); recency where the last non-zero month is inside the panel, or
    the client joined inside it (then a null must stay null).
    """
    out_dir, truth = unit_output
    sdf = spark.read.parquet(f"{out_dir}/mart")
    expected, last = _spark_expected(
        {c: parse_column(c, list(truth["spec"]["products"])) for c in sdf.columns}
    )
    assert len(expected) == 65  # 56 rollups, 5 recency, 4 ratios
    joined = F.date_sub(F.last_day("snapshot_month"), F.col("relationship_days").cast("int"))
    first = F.min(F.col("m")).over(Window.partitionBy("client_id"))
    df = (
        sdf.withColumn("m", _month_number(F.col("snapshot_month")))
        .select(
            "m",
            (_month_number(joined) == first).alias("joined_in_panel"),
            *expected,
            *[e.alias(f"expected_{c}") for c, e in expected.items()],
            *[e.isNotNull().alias(f"seen_{c}") for c, e in last.items()],
        )
        .toPandas()
    )
    full_window = (df["m"] >= df["m"].min() + 5).to_numpy()
    wrong = []
    for name in expected:
        compared = df[f"seen_{name}"] | df["joined_in_panel"] if name in last else full_window
        got, want = df.loc[compared, name], df.loc[compared, f"expected_{name}"]
        nulls_differ = (got.isna() != want.isna()).sum()
        values_differ = ((got - want).abs() > TOLERANCE).sum()
        if nulls_differ or values_differ or not compared.any():
            wrong.append(
                f"{name}: {nulls_differ} nulls, {values_differ} values of {compared.sum()}"
            )
    assert not wrong, "\n".join(wrong)
