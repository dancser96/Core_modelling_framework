"""Evaluation's explanation tables (evaluation.md → "The explanation tables").

The driver holds one set of rows here: `collect_explanation_sample`, a seeded sample of test rows
with their raw feature values and scores, plus the three waterfall rows, one of them at the
score `explanation_cut` reads off the slices table. Everything else reads
that sample, or Spark aggregates: the families' own contributions on the encoder's codes
(`compute_contributions`, in the shape of Training's `explanation_sample`, so the importance view
puts train out of fold beside test), the encoder's null and unseen shares per part
(`encoding_shares`), the feature table, permutation importance per redundancy cluster and
partial dependence with ICE. Nothing is fitted and nothing is chosen on these numbers
(`CLAUDE.md` §4.4, §4.5); validation appears only in the shares, which are reported. The
contributions are on the margin's scale (the log scale for Tweedie and Poisson).
"""

from collections.abc import Callable, Iterator, Sequence
from functools import reduce
from operator import and_

import numpy as np
import pandas as pd
from pyspark.sql import Column, DataFrame, Row
from pyspark.sql import functions as F
from pyspark.sql.types import DoubleType, LongType, StringType, StructField, StructType

from core_modelling.config import UseCaseConfig
from core_modelling.dataset.frames import collect_frame
from core_modelling.environment import EnvironmentConfig
from core_modelling.evaluation.tables import decision_slice
from core_modelling.model.bundle import OUTPUT_COLUMNS, Bundle
from core_modelling.model.encoder import encode_frame
from core_modelling.model.families import FAMILIES
from core_modelling.model.scoring import score_frame
from core_modelling.sources import KEYS
from core_modelling.statistics.distributions import level_text
from core_modelling.statistics.metrics import slice_labels
from core_modelling.statistics.score_cells import PARTS, POOLED
from core_modelling.training.tables import BASE_COLUMN, CONTRIBUTION_SUFFIX, EXPLANATION_ROWS

WATERFALL_COLUMN = "waterfall"  # null for a sampled row, else which waterfall row it is
WATERFALL_ROWS = ("highest", "cut", "typical")
FALLBACK_SLICE = "top 10%"  # the cut without a usable decision slice; a capture depth, always cut
# A float32 library (XGBoost) sums its contributions to the margin within rounding only
SUM_TOLERANCE = 1e-4
DISAGREEMENTS = 3  # the clusters whose two ranks differ most, marked for the rank check
PERMUTATIONS = 5  # seeded permutations per cluster: the loss change is their mean
PERMUTATION_COLUMNS = ["cluster", "members", "loss_change", "loss_change_sd",
                       "contribution_share", "importance_rank", "contribution_rank", "rank_gap",
                       "disagrees", "rank_correlation"]  # fmt: skip
ONE_TARGET_VALUE = "not available: one target value in the explanation sample"
GRID_POINTS = 20  # partial dependence: quantiles of a numeric, the most frequent levels
ICE_ROWS = 50  # ICE lines drawn, evenly spaced through the sample
TOP_EFFECTS, MAX_EFFECTS = 10, 20  # the effect features (A23)
SHARE_SCHEMA = StructType(
    [
        StructField("part", StringType()),
        StructField("feature", StringType()),
        StructField("rows", LongType()),
        StructField("nulls", DoubleType()),
        StructField("unseen", DoubleType()),
    ]
)


def explanation_cut(slices: pd.DataFrame, curves: pd.DataFrame, cfg: UseCaseConfig) -> dict:
    """Where the explanation sample's `cut` row is taken: the decision's slice (`decision_slice`)
    on the test part, pooled over its periods, or `FALLBACK_SLICE` when no slice is configured
    or its row is unavailable; a configured slice without a row fails loud. Returns `slice`,
    `available` (False on the fallback), `reason` (why it fell back, else ''), `depth` (the
    slice's rows over the part's) and `score`, the lowest score of the first score bin of the
    test curve that reaches the depth (`curve_at_depths`)."""
    test = slices.loc[(slices["part"] == "test") & (slices["period"] == POOLED)]
    chosen = decision_slice(cfg)
    label = None if chosen is None else slice_labels(chosen)[0]
    reason = "no slice is configured" if label is None else ""
    if label is not None:
        row = test.loc[test["slice"] == label]
        if row.empty:
            raise ValueError(f"the test slices hold no row for the decision's slice {label!r}")
        if row["unavailable"].iloc[0]:
            reason = f"the decision's slice {label} is {row['unavailable'].iloc[0]}"
    if reason:
        row = test.loc[test["slice"] == FALLBACK_SLICE]
        if row.empty:
            raise ValueError(f"the test slices hold no row for {FALLBACK_SLICE!r}")
    depth = float(row["rows"].iloc[0] / row["part_rows"].iloc[0])
    at = curve_at_depths(curves.loc[curves["part"] == "test"], [depth])
    return {"slice": row["slice"].iloc[0], "available": not reason, "reason": reason,
            "depth": depth, "score": float(at["threshold"].iloc[0])}  # fmt: skip


def curve_at_depths(curve: pd.DataFrame, depths: Sequence[float]) -> pd.DataFrame:
    """One part's curve rows at `depths`: for each, the first score bin from the top whose
    cumulative share of rows reaches it (the last bin when none does), each bin once, in depth
    order. Same columns as `curve` (`statistics.metrics.threshold_table`'s)."""
    ordered = curve.sort_values("depth", kind="stable")
    at = ordered["depth"].searchsorted(list(depths)).clip(max=len(ordered) - 1)
    return ordered.iloc[sorted(set(at))]


def collect_explanation_sample(
    rows: DataFrame, scores: DataFrame, cfg: UseCaseConfig, env: EnvironmentConfig, cut: float
) -> tuple[pd.DataFrame, dict]:
    """The explanation sample of the test part, collected: `EXPLANATION_ROWS` test rows chosen
    by a hash of the keys and `training.seed` (so a rerun takes the same rows), plus the three
    waterfall rows. Receives Evaluation's rows (one per client, period and part, with the
    features) and the scores table; `cut` is the score at the decision's cut, which only the
    slices table knows. The rows are picked on the scores alone, and `rows` is read once more
    only to join the features to those few keys. Returns the sample and the collect's log entry
    (`collect_frame`'s): one row per sampled row, `rows`' columns, `OUTPUT_COLUMNS` and
    `waterfall` (`highest`: the top score of the part; `cut`: the score nearest `cut`;
    `typical`: the sampled row nearest the sample's median score; else null)."""
    test = scores.where(F.col("part") == "test").select(*KEYS, *OUTPUT_COLUMNS)
    order = F.xxhash64(*KEYS, F.lit(cfg.training.seed))
    highest = _pick_row(test, [F.col("score").desc(), order], [])
    at_cut = _pick_row(test, [F.abs(F.col("score") - F.lit(cut)), order], [highest])
    mark = F.when(_is_row(highest), "highest").when(_is_row(at_cut), "cut")
    marked = test.withColumn(WATERFALL_COLUMN, mark)
    sampled = marked.orderBy(order, *KEYS).limit(EXPLANATION_ROWS)
    chosen = sampled.unionByName(marked.where(F.col(WATERFALL_COLUMN).isNotNull()))
    picked = rows.where(F.col("part") == "test").join(
        F.broadcast(chosen.dropDuplicates(KEYS)), KEYS
    )
    sample, entry = collect_frame(picked, "explanation_sample", env)
    return _mark_typical(sample), entry


def _pick_row(test: DataFrame, order: list[Column], taken: list[Row]) -> Row:
    """The keys of the first test row in `order`, other than the rows `taken`; an empty part
    fails loud."""
    left = test
    for row in taken:
        left = left.where(~_is_row(row))
    found = left.orderBy(*order).select(*KEYS).first()
    if found is None:
        raise ValueError("the test part has too few rows for the three waterfall rows")
    return found


def _is_row(row: Row) -> Column:
    """True on the row with `row`'s keys, every one of `KEYS`."""
    return reduce(and_, [F.col(key) == F.lit(row[key]) for key in KEYS])


def _mark_typical(sample: pd.DataFrame) -> pd.DataFrame:
    """The sample with its typical row marked: of the unmarked rows, the one whose score is
    nearest their median (the first in key order on a tie)."""
    free = sample.loc[sample[WATERFALL_COLUMN].isna(), "score"]
    if free.empty:
        raise ValueError("the explanation sample holds no row besides the waterfall rows")
    sample.loc[(free - free.median()).abs().idxmin(), WATERFALL_COLUMN] = "typical"
    return sample


def compute_contributions(bundle: Bundle, sample: pd.DataFrame) -> pd.DataFrame:
    """The family's own contributions on the encoder's codes of `sample` (the explanation
    sample, with its `margin`). Returns the same rows in the shape of Training's
    `explanation_sample`: the keys, the features' raw values, `<feature>__contribution` per
    feature, `base_value`; then the sample's other columns. A row's contributions and base
    value sum to its stored margin, or it fails loud (the rows are not what was scored)."""
    encoded, _ = encode_frame(sample, bundle.encoder)
    values = FAMILIES[bundle.family].contributions(bundle.booster, encoded)
    names = [f"{name}{CONTRIBUTION_SUFFIX}" for name in bundle.features]
    parts = pd.DataFrame(values, index=sample.index, columns=[*names, BASE_COLUMN])
    margin = sample["margin"].to_numpy(dtype=np.float64)
    gap = np.abs(values.sum(axis=1) - margin)
    if (gap > SUM_TOLERANCE * np.maximum(1.0, np.abs(margin))).any():
        raise ValueError(
            f"the contributions differ from the stored margin by up to {gap.max():.3g}: the "
            "sample's feature values are not the ones its scores were computed from"
        )
    front = [*KEYS, *bundle.features]
    rest = [name for name in sample.columns if name not in front]
    return pd.concat([sample[front], parts, sample[rest]], axis=1)


def encoding_shares(rows: DataFrame, bundle: Bundle) -> pd.DataFrame:
    """Per part and feature of the bundle, the rows and the encoder's null and unseen shares
    (an unseen level: one the encoder did not see in train; null for a numeric), in one Spark
    pass. Each partition counts with `encode_frame` itself, so a level is told seen or unseen
    exactly as scoring codes it. Returns `part, feature, rows, null_share, unseen_share`."""
    encoder = bundle.encoder

    def count_batches(batches: Iterator[pd.DataFrame]) -> Iterator[pd.DataFrame]:
        """One partition's counts per part and feature, from the encoder's shares."""
        for batch in batches:
            for part, group in batch.groupby("part", sort=False):
                _, shares = encode_frame(group, encoder)
                yield pd.DataFrame(
                    {"part": part, "feature": shares["feature"], "rows": len(group),
                     "nulls": np.rint(shares["null_share"] * len(group)),
                     "unseen": np.rint(shares["unseen_share"] * len(group))}
                )  # fmt: skip

    counted = rows.select("part", *bundle.features).mapInPandas(count_batches, SHARE_SCHEMA)
    sums = [F.sum(name).alias(name) for name in ("rows", "nulls", "unseen")]
    table = counted.groupBy("part", "feature").agg(*sums).toPandas()
    table["null_share"] = table["nulls"] / table["rows"]
    table["unseen_share"] = table["unseen"] / table["rows"]
    position = table["feature"].map({name: index for index, name in enumerate(bundle.features)})
    table = table.assign(position=position).sort_values(["part", "position"])
    return table[["part", "feature", "rows", "null_share", "unseen_share"]].reset_index(drop=True)


def _contribution_shares(contributions: pd.DataFrame, features: list[str]) -> pd.Series:
    """Each feature's share of the mean absolute contribution, from a frame with
    `<feature>__contribution` columns; a frame of only zero contributions fails loud."""
    columns = [f"{name}{CONTRIBUTION_SUFFIX}" for name in features]
    missing = [name for name in columns if name not in contributions.columns]
    if missing:
        raise ValueError(f"the contributions lack the columns {missing}")
    mean_abs = contributions[columns].abs().mean().set_axis(features)
    if not mean_abs.sum() > 0:
        raise ValueError("every contribution is 0, so no feature has a share")
    return mean_abs / mean_abs.sum()


def feature_table(
    contributions: pd.DataFrame, shares: pd.DataFrame, run_ledger: pd.DataFrame
) -> pd.DataFrame:
    """One row per final feature (the per-run ledger's `selected`), largest test contribution
    share first: `feature, contribution_share, contribution_rank, null_share_train`, the null
    and unseen shares on test and validation (`encoding_shares`), and `null_not_in_train`, true
    when a feature holds nulls at scoring and none in train. Train's null share is the per-run
    ledger's, the encoder's on the frame the model was fitted on (the Stage 2 copy's is EDA's,
    over every client, test included); a final feature without one fails loud."""
    final = run_ledger.loc[run_ledger["selected"].astype(bool), "feature"].tolist()
    share = _contribution_shares(contributions, final)
    table = pd.DataFrame({"feature": final, "contribution_share": share.to_numpy()})
    table["contribution_rank"] = table["contribution_share"].rank(ascending=False, method="min")
    train = run_ledger.set_index("feature")["null_share"]
    table["null_share_train"] = train.reindex(final).to_numpy(dtype=np.float64)
    unknown = table.loc[table["null_share_train"].isna(), "feature"].tolist()
    if unknown:
        raise ValueError(f"the per-run ledger has no train null_share for the features {unknown}")
    wide = shares.set_index(["feature", "part"])[["null_share", "unseen_share"]]
    absent = [(name, part) for name in final for part in PARTS if (name, part) not in wide.index]
    if absent:
        raise ValueError(f"the encoding shares lack the feature and part pairs {absent}")
    for part in PARTS:
        for column in ("null_share", "unseen_share"):
            table[f"{column}_{part}"] = [wide.loc[(name, part), column] for name in final]
    at_scoring = table[[f"null_share_{part}" for part in PARTS]].max(axis=1) > 0
    table["null_not_in_train"] = at_scoring & (table["null_share_train"] == 0)
    table = table.astype({"contribution_rank": "int64"})
    return table.sort_values("contribution_share", ascending=False, kind="stable").reset_index(
        drop=True
    )


def permutation_importance(
    bundle: Bundle,
    contributions: pd.DataFrame,
    clusters: pd.DataFrame,
    metric: Callable[[np.ndarray, np.ndarray], float],
    seed: int,
) -> pd.DataFrame:
    """Per redundancy cluster, the loss change when its members are permuted together, the mean
    over `PERMUTATIONS` seeded permutations of the sample's rows, and the rank check against the
    contributions. Run it only when `permutation_unavailable` gives no reason.

    `contributions` is `compute_contributions`' frame, not the bare sample: the rows' raw
    features, their `<feature>__contribution` columns and `target` are all read from it.
    `clusters` holds `feature, cluster` (the Stage 2 ledger's; a null cluster is the feature
    alone), `metric(y, score)` a loss (lower is better). Returns one row per cluster, largest mean
    loss change first, in `PERMUTATION_COLUMNS`: `loss_change` the mean and `loss_change_sd` the
    standard deviation (ddof 1) over the permutations, the ranks and `disagrees` (the
    `DISAGREEMENTS` largest non-zero gaps) on the mean, and `rank_correlation` (Spearman's
    between the two, the same on every row; null when undefined).
    """
    groups = _cluster_members(bundle.features, clusters)
    y = contributions["target"].to_numpy()
    frame = contributions[bundle.features]
    base = metric(y, score_frame(bundle, frame)["score"].to_numpy())
    shares = _contribution_shares(contributions, bundle.features)
    rng = np.random.default_rng(seed)
    rows = []
    for cluster, members in groups:
        changes = [_permuted_loss(bundle, frame, members, rng.permutation(len(frame)), y, metric)
                   - base for _ in range(PERMUTATIONS)]  # fmt: skip
        rows.append({"cluster": cluster, "members": members,
                     "loss_change": float(np.mean(changes)),
                     "loss_change_sd": float(np.std(changes, ddof=1)),
                     "contribution_share": float(shares[members].sum())})  # fmt: skip
    table = pd.DataFrame(rows).astype({"cluster": "Int64"})
    return _rank_check(table)[PERMUTATION_COLUMNS]


def permutation_unavailable(contributions: pd.DataFrame) -> str | None:
    """Why permutation importance cannot be computed on the explanation sample, decided before
    it runs (D-035): a target of one value (no positive row, or no negative one, or a constant
    amount under a concordance or R² loss) gives no loss to compare. None when it can."""
    if contributions["target"].nunique() < 2:
        return ONE_TARGET_VALUE
    return None


def _permuted_loss(
    bundle: Bundle,
    frame: pd.DataFrame,
    members: list[str],
    order: np.ndarray,
    y: np.ndarray,
    metric: Callable[[np.ndarray, np.ndarray], float],
) -> float:
    """The loss with `members`' values reordered by `order`, one order for every member, so
    their rows move together and the other features stay in place."""
    permuted = frame.copy()
    for name in members:
        permuted[name] = frame[name].to_numpy()[order]
    return metric(y, score_frame(bundle, permuted)["score"].to_numpy())


def _cluster_members(
    features: list[str], clusters: pd.DataFrame
) -> list[tuple[int | None, list[str]]]:
    """The model's features grouped by their cluster, in the features' order: `(cluster,
    members)`, a feature with a null cluster alone under None; a feature without a row fails."""
    known = clusters.set_index("feature")["cluster"]
    missing = [name for name in features if name not in known.index]
    if missing:
        raise ValueError(f"the clusters table has no row for the model's features {missing}")
    groups: dict[int | str, list[str]] = {}
    for name in features:
        key = name if pd.isna(known[name]) else int(known[name])  # alone: keyed by its name
        groups.setdefault(key, []).append(name)
    return [(None if isinstance(key, str) else key, members) for key, members in groups.items()]


def _rank_check(table: pd.DataFrame) -> pd.DataFrame:
    """The permutation table with both ranks, their gap, the largest gaps marked and Spearman's
    rank correlation between the loss change and the contribution share."""
    table["importance_rank"] = table["loss_change"].rank(ascending=False, method="min")
    table["contribution_rank"] = table["contribution_share"].rank(ascending=False, method="min")
    table = table.astype({"importance_rank": "int64", "contribution_rank": "int64"})
    table["rank_gap"] = table["importance_rank"] - table["contribution_rank"]
    gap = table["rank_gap"].abs()
    largest = gap[gap > 0].sort_values(ascending=False, kind="stable").index[:DISAGREEMENTS]
    table["disagrees"] = table.index.isin(largest)
    correlation = table["loss_change"].corr(table["contribution_share"], method="spearman")
    table["rank_correlation"] = None if pd.isna(correlation) else float(correlation)
    return table.sort_values("loss_change", ascending=False, kind="stable").reset_index(drop=True)


def partial_dependence(bundle: Bundle, sample: pd.DataFrame, features: list[str]) -> pd.DataFrame:
    """Partial dependence and ICE of each of `features` on the sample's score. Each feature is
    set in turn to every point of its grid on every sample row (numeric: `GRID_POINTS` quantiles
    of its sample values; categorical: its `GRID_POINTS` most frequent sample levels). Returns
    long rows `feature, curve, row, point, value, level, score`: `curve` `pdp` (the mean over
    the rows, `row` null) or `ice` (one of `ICE_ROWS` evenly spaced rows, by position);
    `value` the numeric's grid value, `level` the categorical's level text."""
    kinds = {entry["name"]: entry["kind"] for entry in bundle.encoder["features"]}
    unknown = [name for name in features if name not in kinds]
    if unknown:
        raise ValueError(f"the bundle has no features {unknown}")
    frame, rows = sample[bundle.features], len(sample)
    ice = np.unique(np.linspace(0, rows - 1, min(ICE_ROWS, rows)).astype(int))
    tables = []
    for name in features:
        numeric = kinds[name] == "numeric"
        grid = _grid(frame[name], numeric, name)
        swept = pd.concat([frame.assign(**{name: value}) for value in grid], ignore_index=True)
        scores = score_frame(bundle, swept)["score"].to_numpy().reshape(len(grid), rows)
        pdp = scores.mean(axis=1)[:, None]
        tables.append(_curve_rows(name, "pdp", grid, numeric, pdp, [None]))
        tables.append(_curve_rows(name, "ice", grid, numeric, scores[:, ice], ice.tolist()))
    return pd.concat(tables, ignore_index=True)


def _curve_rows(
    name: str, curve: str, grid: list, numeric: bool, scores: np.ndarray, rows: list
) -> pd.DataFrame:
    """One curve kind of a feature as long rows: `scores` holds one row per grid point and one
    column per entry of `rows` (the sample positions, or `[None]` for the mean)."""
    points = np.repeat(np.arange(len(grid)), len(rows))
    return pd.DataFrame(
        {
            "feature": name,
            "curve": curve,
            "row": pd.array(rows * len(grid), dtype="Int64"),
            "point": points,
            "value": [float(grid[point]) if numeric else np.nan for point in points],
            "level": [None if numeric else level_text(grid[point]) for point in points],
            "score": scores.ravel(),
        }
    )


def _grid(values: pd.Series, numeric: bool, name: str) -> list:
    """A feature's grid from its sample values, null left out: about `GRID_POINTS` quantiles of
    a numeric, or a categorical's `GRID_POINTS` most frequent raw values (ties by value)."""
    known = values.dropna()
    if known.empty:
        raise ValueError(f"the feature {name!r} is null on every sample row: no grid to sweep")
    if numeric:
        points = np.linspace(0, 1, GRID_POINTS)
        return list(np.unique(np.quantile(known.astype(float), points, method="nearest")))
    counts = known.value_counts().sort_index().sort_values(ascending=False, kind="stable")
    return list(counts.index[:GRID_POINTS])


def effect_features(run_ledger: pd.DataFrame, key_features: list[str]) -> list[str]:
    """The features the effect views draw (A23): every key feature the model uses (EDA's key
    features and a person's `include`, as given) and the model's `TOP_EFFECTS` largest by
    Training's out-of-fold contribution share, `MAX_EFFECTS` at most, the key features first
    when they do not all fit; returned largest share first."""
    used = run_ledger.loc[run_ledger["in_model"].fillna(False).astype(bool)]
    used = used.sort_values("contribution_share", ascending=False, kind="stable")[
        "feature"
    ].tolist()
    keys = [name for name in used if name in set(key_features)]
    chosen = set(list(dict.fromkeys([*keys, *used[:TOP_EFFECTS]]))[:MAX_EFFECTS])
    return [name for name in used if name in chosen]
