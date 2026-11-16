"""The encoder on constructed frames: levels frozen from train and kept by distinct clients, the
codes of each kind, unseen levels counted, the clip, the numeric casts, the contract checks, the
JSON round trip and the `codes` switch. No Spark.
"""

import copy
import json
from decimal import Decimal

import numpy as np
import pandas as pd
import pytest

from core_modelling.model.encoder import encode_frame, fit_encoder

FEATURES = ["income", "rating", "channel"]
KINDS = {"income": "numeric", "rating": "categorical", "channel": "categorical"}
ORDER = {"rating": ["C", "B", "A"]}


def _train() -> pd.DataFrame:
    """13 train rows of 9 clients: `fax` has the most rows but one client, `atm` and `branch` tie
    on rows and clients, one `channel` and one `rating` are null."""
    return pd.DataFrame(
        {
            "unit_id": [1, 2, 3, 4, 5, 6, 7, 8, 8, 8, 8, 8, 9],
            "income": [1.5, 2.0, 3.0, 4.0, 5.0, np.nan, 0.0, 3.0, 4.0, 5.0, 6.0, 7.0, 8.0],
            "rating": ["C", "B", "A", None, "C", "B", "A", "C", "B", "A", "C", "B", "A"],
            "channel": ["online"] * 3 + ["atm"] * 2 + ["branch"] * 2 + ["fax"] * 5 + [None],
        }
    )


def _fit(train: pd.DataFrame, unordered: str = "native") -> dict:
    """The encoder of `FEATURES` fitted on `train`, a level kept at two distinct clients."""
    return fit_encoder(train, FEATURES, KINDS, ORDER, 2, unordered)


def _shares(shares: pd.DataFrame, feature: str) -> pd.Series:
    """One feature's row of the shares table."""
    return shares.set_index("feature").loc[feature]


def test_levels_are_frozen_from_train_and_kept_by_distinct_clients() -> None:
    """`fax` has five rows but one client, so it is pooled; `atm` and `branch` tie on rows and
    follow by name; encoding a frame with a new level leaves the encoder as fitted."""
    encoder = _fit(_train())
    assert encoder == {
        "schema_version": 1,
        "unordered": "native",
        "min_level_client_count": 2,
        "features": [
            {"name": "income", "kind": "numeric"},
            {"name": "rating", "kind": "ordered", "levels": ["C", "B", "A"]},
            {
                "name": "channel",
                "kind": "unordered",
                "levels": ["online", "atm", "branch"],
                "pooled": ["fax"],
            },
        ],
    }
    fitted = copy.deepcopy(encoder)
    encode_frame(pd.DataFrame({"income": [1.0], "rating": ["A"], "channel": ["telex"]}), encoder)
    assert encoder == fitted


def test_unordered_codes_are_null_kept_levels_and_other() -> None:
    """0 for a null, 1 … K for the kept levels by train rows, K + 1 for a pooled level; integers
    under `native`."""
    channel = [None, "online", "atm", "branch", "fax"]
    frame = pd.DataFrame({"income": 0.0, "rating": "A", "channel": channel})
    encoded, shares = encode_frame(frame, _fit(_train()))
    assert encoded["channel"].dtype == "int64"
    assert encoded["channel"].tolist() == [0, 1, 2, 3, 4]
    row = _shares(shares, "channel")
    assert (row["null_share"], row["other_share"], row["unseen_share"]) == (0.2, 0.2, 0.0)
    assert pd.isna(row["infinite_share"])


def test_an_unseen_level_is_null_when_ordered_and_other_when_unordered() -> None:
    """A level train never had: null for an ordered feature, `__other__` (K + 1) for an unordered
    one, counted as unseen either way (and as other for the unordered one); an ordered null
    stays null."""
    rating = ["AAA", "B", None, "C"]
    frame = pd.DataFrame(
        {"income": 1.0, "rating": rating, "channel": ["telex", "online", "atm", "atm"]}
    )
    encoded, shares = encode_frame(frame, _fit(_train()))
    assert encoded["rating"].isna().tolist() == [True, False, True, False]
    assert encoded["rating"].iloc[[1, 3]].tolist() == [1.0, 0.0]
    assert encoded["channel"].tolist() == [4, 1, 2, 2]
    rating, channel = _shares(shares, "rating"), _shares(shares, "channel")
    assert (rating["null_share"], rating["unseen_share"]) == (0.25, 0.25)
    assert pd.isna(rating["other_share"])
    assert (channel["other_share"], channel["unseen_share"]) == (0.25, 0.25)


def test_a_train_level_missing_from_the_declared_order_fails() -> None:
    """The declared order is a contract: a train level outside it fails loud, named."""
    with pytest.raises(ValueError, match=r"'rating' has train levels \['A'\] missing"):
        fit_encoder(_train(), FEATURES, KINDS, {"rating": ["C", "B"]}, 2, "native")


def test_numerics_are_clipped_to_1e30_and_a_null_stays_null() -> None:
    """±inf and a finite value beyond 1e30 are clipped and counted; a null is kept, never
    imputed."""
    income = [np.inf, -np.inf, 1e31, -2.5, np.nan]
    frame = pd.DataFrame({"income": income, "rating": "A", "channel": "atm"})
    encoded, shares = encode_frame(frame, _fit(_train()))
    assert encoded["income"].dtype == "float64"
    assert encoded["income"].iloc[:4].tolist() == [1e30, -1e30, 1e30, -2.5]
    assert np.isnan(encoded["income"].iloc[4])
    row = _shares(shares, "income")
    assert (row["infinite_share"], row["null_share"]) == (0.6, 0.2)
    assert pd.isna(row["unseen_share"])


def test_a_decimal_column_is_cast_and_a_text_column_refused() -> None:
    """A Spark decimal arrives as `Decimal` objects and is cast to float64, at fit and at
    scoring; numbers held as text are refused, never parsed."""
    train = _train()
    _fit(train.assign(income=[Decimal(value) for value in range(13)]))
    encoder = _fit(train)
    frame = pd.DataFrame({"income": [Decimal("1.25"), None], "rating": "A", "channel": "atm"})
    encoded, _ = encode_frame(frame, encoder)
    assert encoded["income"].dtype == "float64"
    assert encoded["income"].iloc[0] == 1.25 and np.isnan(encoded["income"].iloc[1])
    with pytest.raises(ValueError, match="numeric feature 'income'"):
        _fit(train.assign(income=train["income"].astype(str)))
    with pytest.raises(ValueError, match="numeric feature 'income'"):
        encode_frame(frame.assign(income=["1.25", None]), encoder)


def test_levels_compare_as_text_whatever_the_dtype() -> None:
    """An integer categorical with nulls arrives as floats (1.0) in train and as integers (1) in a
    frame without nulls; both name the level `1`, as EDA does, so neither reads as unseen. A
    boolean is `true` or `false`."""
    train = pd.DataFrame(
        {
            "unit_id": [1, 2, 3, 4, 5],
            "segment": [1.0, 1.0, 2.0, 2.0, np.nan],
            "flag": [True, True, False, False, None],
        }
    )
    kinds = {"segment": "categorical", "flag": "categorical"}
    encoder = fit_encoder(train, ["segment", "flag"], kinds, {}, 2, "native")
    assert [entry["levels"] for entry in encoder["features"]] == [["1", "2"], ["false", "true"]]
    encoded, shares = encode_frame(
        pd.DataFrame({"segment": [1, 2], "flag": [True, False]}), encoder
    )
    assert encoded.to_numpy().tolist() == [[1, 2], [2, 1]]
    assert shares["unseen_share"].eq(0.0).all()


def test_a_level_text_never_depends_on_the_value_before_it() -> None:
    """Equal-hashing values in one object column keep their own texts (`3.0` and `3`), whichever
    comes first, at fit and at scoring."""
    train = pd.DataFrame(
        {"unit_id": [1, 2, 3], "amount": [Decimal("3.0"), Decimal("3.0"), Decimal("3")]}
    )
    encoder = fit_encoder(train, ["amount"], {"amount": "categorical"}, {}, 1, "native")
    assert encoder["features"][0]["levels"] == ["3.0", "3"]
    encoded, _ = encode_frame(pd.DataFrame({"amount": [Decimal("3"), Decimal("3.0")]}), encoder)
    assert encoded["amount"].tolist() == [2, 1]


def test_the_encoded_frame_has_the_encoder_columns_in_order_and_the_input_index() -> None:
    """A booster reads columns by position: the encoded frame holds exactly the encoder's
    features in its order, whatever the input's order and extra columns, on the input's index;
    a missing feature fails loud."""
    encoder = _fit(_train())
    frame = _train()[["channel", "unit_id", "rating", "income"]].set_axis(range(100, 113))
    encoded, shares = encode_frame(frame, encoder)
    assert list(encoded.columns) == FEATURES and shares["feature"].tolist() == FEATURES
    assert encoded.index.equals(frame.index)
    with pytest.raises(ValueError, match=r"lacks the columns \['rating'\]"):
        encode_frame(frame.drop(columns="rating"), encoder)


def test_an_encoder_with_an_unknown_mode_fails_loud_at_scoring() -> None:
    """A bundle read from disk with an unknown `unordered` mode would otherwise encode as
    `native`."""
    encoder = {**_fit(_train()), "unordered": "onehot"}
    with pytest.raises(ValueError, match="the encoder's unordered is 'onehot'"):
        encode_frame(_train(), encoder)


@pytest.mark.parametrize(
    ("change", "message"),
    [
        ({"unordered": "onehot"}, "unordered is 'onehot'"),
        ({"order": {"income": ["1", "2"]}}, r"features.order names \['income'\]"),
        ({"train": _train().assign(channel="__other__")}, "level named '__other__'"),
        ({"train": _train().iloc[:0]}, "the train frame is empty"),
        ({"features": [*FEATURES, "income"]}, r"list \['income'\] more than once"),
    ],
)
def test_a_wrong_fit_argument_fails_loud(change: dict, message: str) -> None:
    """An unknown mode would encode as `native`, an order on a numeric would be ignored, a train
    level named `__other__` would collide with the pooled code, an empty train would fit no
    level and a repeated feature would feed the model one column twice: each fails loud."""
    arguments = {
        "train": _train(),
        "features": FEATURES,
        "kinds": KINDS,
        "order": ORDER,
        "min_level_client_count": 2,
        "unordered": "native",
        **change,
    }
    with pytest.raises(ValueError, match=message):
        fit_encoder(**arguments)


def test_the_encoder_survives_a_json_round_trip() -> None:
    """The encoder is plain data: after `json.dumps` and `json.loads` it is equal and encodes
    train and a frame with unseen levels identically."""
    train = _train()
    encoder = _fit(train)
    reloaded = json.loads(json.dumps(encoder))
    assert reloaded == encoder
    unseen = pd.DataFrame({"income": [np.inf], "rating": ["AAA"], "channel": ["telex"]})
    for frame in (train, unseen):
        encoded, shares = encode_frame(frame, encoder)
        again, shares_again = encode_frame(frame, reloaded)
        pd.testing.assert_frame_equal(again, encoded)
        pd.testing.assert_frame_equal(shares_again, shares)


def test_codes_gives_the_native_integers_as_floats() -> None:
    """`unordered: codes` passes the same codes as plain numbers; every other column is
    unchanged."""
    train = _train()
    native, _ = encode_frame(train, _fit(train, "native"))
    codes, _ = encode_frame(train, _fit(train, "codes"))
    assert codes["channel"].dtype == "float64"
    pd.testing.assert_frame_equal(codes, native.astype({"channel": "float64"}))
