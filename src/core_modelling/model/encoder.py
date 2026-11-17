"""The encoder: the framework's own coding of the feature frame before any model library sees it.

FLAML's own transform is off (it median-imputes, Q603), so this is the only step between the
raw feature values and the boosters, at training and at every later scoring. `fit_encoder`
reads the train frame only (§4.4) and returns plain, JSON-serialisable data that the families,
the bundle and the recipe hash read; `encode_frame` applies it to any frame and returns, beside
the encoded frame, one row of shares per feature for the log and the per-run ledger. No value
is ever imputed, and the levels are the only fitted statistic.

The code rule of `schema_version` 1:
- **numeric**: float64, clipped to ±1e30 so ±inf sorts beyond every real value in each family
  (Q601); a null stays null. A `Decimal` column is cast; any other non-numeric column fails.
- **ordered** (a categorical named in `features.order`): the level's position in the declared
  list (0 … K−1) as float64; a null stays null, a level not in the list is null and counted as
  unseen. A train level missing from the list fails: the list is a contract (Q609, Q657).
- **unordered** (every other categorical): 0 for a null, 1 … K for the kept levels by train
  rows (most first, ties by name), K + 1 for `__other__`: a train level held by fewer than
  `min_level_client_count` distinct train clients (`pooled`, Q610) and any level unseen in
  train (A35). Integers under `unordered: native`, the same values as float64 under `codes`.
  A categorical with no level at the client count (K = 0), or with only nulls, is allowed: it
  then codes only null against `__other__`; the shares show it, Training warns and selection
  judges it.

Levels are compared as text, row by row, by the one rule EDA names them with
(`statistics.distributions.level_text`): a boolean lower case, an integral float without `.0`,
so an integer column that arrives as floats because it holds nulls codes like the same column
without them. A stored level is that text, so the rule is part of `schema_version` 1.
"""

import pandas as pd

from core_modelling.statistics.distributions import level_text

ENCODER_SCHEMA_VERSION = 1
ENCODER_KEYS = ("schema_version", "unordered", "features")  # what `check_encoder` reads
CLIP = 1e30  # every family keeps it apart from null and beyond every real value (Q601)
OTHER = "__other__"
UNORDERED_MODES = ("native", "codes")
NUMERIC_OBJECTS = ("decimal", "empty")  # infer_dtype of `Decimal` objects or an all-null column
SHARE_COLUMNS = ["feature", "kind", "null_share", "infinite_share", "other_share", "unseen_share"]


def fit_encoder(
    train: pd.DataFrame,
    features: list[str],
    kinds: dict[str, str],
    order: dict[str, list[str]],
    min_level_client_count: int,
    unordered: str,
) -> dict:
    """The encoder fitted on the train frame (one row per client and period, with `unit_id`):
    per feature in `features`' order its kind and, for a categorical, its levels. `kinds` maps
    each feature to `numeric` or `categorical`; a categorical named in `order` is ordered."""
    _check_fit_inputs(train, features, kinds, order, unordered)
    entries = []
    for name in features:
        if kinds[name] == "numeric":
            _check_numeric(train[name], name)
            entries.append({"name": name, "kind": "numeric"})
        elif name in order:
            entries.append(_fit_ordered(_level_texts(train[name]), name, order[name]))
        else:
            texts = _level_texts(train[name])
            entries.append(_fit_unordered(texts, train["unit_id"], name, min_level_client_count))
    return {
        "schema_version": ENCODER_SCHEMA_VERSION,
        "unordered": unordered,
        "min_level_client_count": min_level_client_count,
        "features": entries,
    }


def encode_frame(frame: pd.DataFrame, encoder: dict) -> tuple[pd.DataFrame, pd.DataFrame]:
    """The frame coded by `encoder` and its shares. Receives any frame holding the encoder's
    features (one row per client and period); returns the encoded frame (the same rows and
    index, exactly the encoder's features in its order) and one row per feature (`SHARE_COLUMNS`:
    each share of the frame's rows, null where it does not apply to the kind)."""
    check_encoder(encoder)
    names = [entry["name"] for entry in encoder["features"]]
    _check_columns(frame, names, "the frame to encode")
    columns, shares = {}, []
    for entry in encoder["features"]:
        codes, row = ENCODE_BY_KIND[entry["kind"]](frame[entry["name"]], entry)
        if entry["kind"] == "unordered" and encoder["unordered"] == "codes":
            codes = codes.astype("float64")
        columns[entry["name"]] = codes.to_numpy()  # positional: a repeated index stays as it is
        shares.append({"feature": entry["name"], "kind": entry["kind"], **row})
    encoded = pd.DataFrame(columns, index=frame.index, columns=names)
    return encoded, pd.DataFrame(shares, columns=SHARE_COLUMNS)


def select_encoder(encoder: dict, features: list[str]) -> dict:
    """The encoder restricted to `features`, in the encoder's own order: what is left after
    selection, and the final features' encoder a bundle holds. Each entry is the fitted one,
    unchanged, so a code keeps its meaning; a name the encoder lacks fails loud."""
    check_encoder(encoder)
    known = [entry["name"] for entry in encoder["features"]]
    unknown = [name for name in features if name not in known]
    if unknown:
        raise ValueError(f"the encoder holds no feature named {unknown}; it holds {known}")
    wanted = set(features)
    return {**encoder, "features": [e for e in encoder["features"] if e["name"] in wanted]}


def _check_fit_inputs(
    train: pd.DataFrame,
    features: list[str],
    kinds: dict[str, str],
    order: dict[str, list[str]],
    unordered: str,
) -> None:
    """Fail loud on an unknown `unordered` mode, a repeated feature, a feature without a numeric
    or categorical kind, an unusable `order` entry, or a train frame that lacks or repeats a
    column, is empty or has a null client."""
    if unordered not in UNORDERED_MODES:
        raise ValueError(
            f"training.categoricals.unordered is {unordered!r}; it must be one of {UNORDERED_MODES}"
        )
    repeated = sorted({name for name in features if features.count(name) > 1})
    if repeated:
        raise ValueError(f"the features to encode list {repeated} more than once")
    unkinded = [name for name in features if kinds.get(name) not in ("numeric", "categorical")]
    if unkinded:
        raise ValueError(f"the features {unkinded} have no kind numeric or categorical in {kinds}")
    _check_order(order, features, kinds)
    _check_columns(train, [*features, "unit_id"], "the train frame")
    if train.empty:
        raise ValueError("the train frame is empty: no row to fit the encoder on")
    if train["unit_id"].isna().any():
        raise ValueError(
            "the train frame has a null unit_id; a level's clients would be under-counted"
        )


def _check_order(order: dict[str, list[str]], features: list[str], kinds: dict[str, str]) -> None:
    """Fail loud when `order` names a feature not being encoded, or a numeric one."""
    absent = sorted(set(order) - set(features))
    if absent:
        raise ValueError(
            f"features.order names {absent}, which are not among the features being encoded; "
            "pass the order filtered to the final features"
        )
    numeric = sorted(name for name in order if kinds[name] == "numeric")
    if numeric:
        raise ValueError(
            f"features.order names {numeric}, which are numeric features; an order applies to "
            "a categorical feature only"
        )


def _check_columns(frame: pd.DataFrame, names: list[str], what: str) -> None:
    """Fail loud when `frame` lacks one of `names` or holds one of them in two columns."""
    missing = [name for name in names if name not in frame.columns]
    if missing:
        raise ValueError(f"{what} lacks the columns {missing}")
    repeated = sorted(set(frame.columns[frame.columns.duplicated()]) & set(names))
    if repeated:
        raise ValueError(f"{what} holds the columns {repeated} more than once")


def check_encoder(encoder: dict) -> None:
    """Fail loud on an encoder this version cannot read (a bundle read from disk): a missing
    key, another `schema_version` (naming the fix, as the bundle's own versions do), an unknown
    `unordered` mode or an unknown kind."""
    missing = [key for key in ENCODER_KEYS if key not in encoder]
    if missing:
        raise ValueError(
            f"the encoder lacks the keys {missing}; an encoder holds {list(ENCODER_KEYS)}, as "
            "fit_encoder writes it"
        )
    if encoder["schema_version"] != ENCODER_SCHEMA_VERSION:
        raise ValueError(
            f"the encoder's schema_version is {encoder['schema_version']}; this version of the "
            f"framework reads {ENCODER_SCHEMA_VERSION}: train the model again with this version, "
            "or raise the use case's framework pin when the bundle is newer"
        )
    if encoder["unordered"] not in UNORDERED_MODES:
        raise ValueError(
            f"the encoder's unordered is {encoder['unordered']!r}; it must be one of "
            f"{UNORDERED_MODES}"
        )
    unknown = sorted({entry["kind"] for entry in encoder["features"]} - set(ENCODE_BY_KIND))
    if unknown:
        raise ValueError(
            f"the encoder holds the unknown kinds {unknown}; this version reads "
            f"{list(ENCODE_BY_KIND)}"
        )


def _fit_ordered(texts: pd.Series, name: str, levels: list[str]) -> dict:
    """An ordered feature's entry: its declared levels, after checking that they are distinct
    and that every train level (`texts`, None for a null) is one of them."""
    if len(set(levels)) < len(levels):
        raise ValueError(f"features.order lists a level of {name!r} more than once: {levels}")
    undeclared = sorted(set(texts.dropna()) - set(levels))
    if undeclared:
        raise ValueError(
            f"the ordered feature {name!r} has train levels {undeclared} missing from its "
            f"declared order {levels}; features.order is a contract, add them in their place"
        )
    return {"name": name, "kind": "ordered", "levels": list(levels)}


def _fit_unordered(texts: pd.Series, clients: pd.Series, name: str, min_clients: int) -> dict:
    """An unordered feature's entry from its train level texts (None for a null) and each row's
    client: `levels` the levels held by at least `min_clients` distinct clients, most rows first
    (ties by name), `pooled` the other train levels by name."""
    if (texts == OTHER).any():
        raise ValueError(
            f"the unordered feature {name!r} has a train level named {OTHER!r}, the reserved "
            "level of pooled and unseen levels; rename it upstream"
        )
    known = texts.notna()
    by_level = pd.DataFrame({"level": texts[known], "client": clients[known]}).groupby("level")
    counts = by_level["client"].agg(rows="size", clients="nunique").reset_index()
    counts = counts.sort_values(["rows", "level"], ascending=[False, True])
    kept = counts["clients"] >= min_clients
    return {
        "name": name,
        "kind": "unordered",
        "levels": counts.loc[kept, "level"].tolist(),
        "pooled": sorted(counts.loc[~kept, "level"]),
    }


def _encode_numeric(values: pd.Series, entry: dict) -> tuple[pd.Series, dict]:
    """A numeric column as float64 clipped to ±`CLIP`, a null kept; its null and clipped
    (`infinite_share`) shares."""
    _check_numeric(values, entry["name"])
    numbers = values.astype("float64")
    shares = {"null_share": numbers.isna().mean(), "infinite_share": (numbers.abs() > CLIP).mean()}
    return numbers.clip(-CLIP, CLIP), shares


def _encode_ordered(values: pd.Series, entry: dict) -> tuple[pd.Series, dict]:
    """An ordered column as its level's position in the declared levels (float64), null for a
    null and for an unseen level; its null and unseen shares."""
    texts = _level_texts(values)
    position = {level: float(index) for index, level in enumerate(entry["levels"])}
    codes = texts.map(position).astype("float64")
    null = texts.isna()
    return codes, {"null_share": null.mean(), "unseen_share": (codes.isna() & ~null).mean()}


def _encode_unordered(values: pd.Series, entry: dict) -> tuple[pd.Series, dict]:
    """An unordered column as int64 codes: 0 for a null, 1 … K for the kept levels, K + 1 for
    `__other__` (pooled or unseen); its null, other and unseen shares."""
    texts = _level_texts(values)
    code = {level: index for index, level in enumerate(entry["levels"], start=1)}
    null = texts.isna()
    other = ~null & ~texts.isin(entry["levels"])
    unseen = ~null & ~texts.isin([*entry["levels"], *entry["pooled"]])
    codes = texts.map(code).mask(null, 0).mask(other, len(code) + 1).astype("int64")
    shares = {"null_share": null.mean(), "other_share": other.mean(), "unseen_share": unseen.mean()}
    return codes, shares


ENCODE_BY_KIND = {
    "numeric": _encode_numeric,
    "ordered": _encode_ordered,
    "unordered": _encode_unordered,
}


def _check_numeric(values: pd.Series, name: str) -> None:
    """Fail loud unless a numeric feature holds numbers: a numeric dtype other than boolean, or
    `Decimal` objects (how a Spark decimal arrives, A1); text is never parsed into numbers."""
    is_number = pd.api.types.is_numeric_dtype(values) and not pd.api.types.is_bool_dtype(values)
    held = pd.api.types.infer_dtype(values, skipna=True)
    if not (is_number or (values.dtype == object and held in NUMERIC_OBJECTS)):
        raise ValueError(
            f"the numeric feature {name!r} arrives as {values.dtype} holding {held} values, not "
            "as numbers; fix its type upstream or kind it categorical (features.kinds)"
        )


def _level_texts(values: pd.Series) -> pd.Series:
    """Each value's level text (`level_text`) on the same index, a null (None, NaN or NA) kept
    null. Row by row: grouping equal values first (factorize, a dict) would merge `True` with
    `1` and `Decimal('3')` with `Decimal('3.0')` under the first one's text."""
    return values.map(level_text, na_action="ignore")
