"""The model bundle on a small constructed frame (no Spark): written once as plain data, and only
after every check; loaded only while its `model_hash` matches the files; scoring exactly as the
model in memory did. The helpers above the tests build the raw frame, a fitted booster and its
bundle content as Training will; `test_scoring.py` imports them.
"""

import hashlib
import json
import re
from importlib.metadata import version
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from core_modelling.config.identities import HASH_VERSION, feature_signature, recipe_hash
from core_modelling.model import (
    FAMILIES,
    apply_calibration,
    check_bundle,
    encode_frame,
    fit_encoder,
    load_bundle,
    score_frame,
    write_bundle,
)
from core_modelling.model.bundle import BUNDLE_FILE, CONTENT_KEYS, MANIFEST_FILE

ROWS = 1200
SEED = 7
FEATURES = ["income", "channel", "rating", "age"]
KINDS = {"income": "numeric", "channel": "categorical", "rating": "categorical", "age": "numeric"}
ORDER = {"rating": ["C", "B", "A"]}
SEARCHED = {  # one small configuration per family, in FLAML's own parameter names
    "lgbm": {"n_estimators": 20, "num_leaves": 8, "learning_rate": 0.1},
    "xgboost": {"n_estimators": 20, "max_leaves": 8, "learning_rate": 0.1},
    "xgb_limitdepth": {"n_estimators": 20, "max_depth": 3, "learning_rate": 0.1},
    "catboost": {"n_estimators": 20, "learning_rate": 0.1},
}
OBJECTIVES = {"binary": "log_loss", "regression": "tweedie"}
CALIBRATIONS = {  # numbers no fit would give, so a dropped term shows in the scores
    "binary": {"link": "logit", "method": "platt", "parameters": {"a": 0.9, "b": -0.2},
               "offset": 0.3},
    "regression": {"link": "log", "method": "mean", "parameters": {"factor": 1.1}, "offset": 0.0},
}  # fmt: skip
IDENTITY = {"run_id": "r007", "data_definition_hash": "d" * 64, "config_hash": "c" * 64,
            "resolved_input_hash": "e" * 64}  # fmt: skip
BUNDLE_KEYS = [*CONTENT_KEYS, "bundle_schema_version", "family", "model_file", "output_columns",
               "library_version"]  # fmt: skip
MANIFEST_KEYS = ["manifest_schema_version", "files", "model_hash", "recipe_hash",
                 "feature_signature", "hash_version", *IDENTITY, "framework_version",
                 "written_at"]  # fmt: skip


def raw_frame(rows: int = ROWS, seed: int = 0) -> pd.DataFrame:
    """Raw feature values as scoring receives them, one row per client (`unit_id`): a numeric
    with nulls, an unordered categorical as text with nulls and a rare level (`phone`, pooled at
    50 clients), an ordered one with nulls, and a numeric without."""
    rng = np.random.default_rng(seed)
    channels = np.array(["branch", "online", "phone", None], dtype=object)
    ratings = np.array(["C", "B", "A", None], dtype=object)
    return pd.DataFrame(
        {
            "unit_id": np.arange(rows, dtype=np.int64),
            "income": np.where(rng.random(rows) < 0.05, np.nan, rng.normal(size=rows)),
            "channel": rng.choice(channels, rows, p=[0.5, 0.4, 0.02, 0.08]),
            "rating": rng.choice(ratings, rows),
            "age": rng.normal(45, 12, rows),
        }
    )


def targets(frame: pd.DataFrame, task: str) -> np.ndarray:
    """A binary target or a positive amount driven by income, channel and age."""
    rng = np.random.default_rng(1)
    signal = np.nan_to_num(frame["income"].to_numpy()) + 0.03 * (frame["age"].to_numpy() - 45)
    signal = signal + 0.8 * (frame["channel"] == "online").to_numpy()
    if task == "binary":
        return (rng.random(len(frame)) < 1 / (1 + np.exp(1 - signal))).astype(np.int64)
    return np.exp(1 + 0.3 * signal) * rng.gamma(2, 1, len(frame))


def bundle_content(encoder: dict, task: str, family: str, calibration: dict) -> dict:
    """The content Training gives `write_bundle`: the task, the encoder's features, the encoder,
    the calibration and a recipe that carries the calibration's spec, never its numbers, and the
    seed among the parameters."""
    features = [entry["name"] for entry in encoder["features"]]
    recipe = {"task": task, "family": family,
              "parameters": {**SEARCHED[family], "random_state": SEED},
              "features": features, "encoder": encoder, "monotone": {},
              "calibration": {"method": calibration["method"], "folds": 5},
              "sampling": {"rule": "none"}, "split": {"test_share": 0.2, "salt": "clients"},
              "data_definition_hash": IDENTITY["data_definition_hash"]}  # fmt: skip
    return {"task": task, "features": features, "encoder": encoder, "calibration": calibration,
            "recipe": recipe}  # fmt: skip


def trained(family: str = "lgbm", task: str = "binary") -> tuple[object, dict]:
    """A booster fitted on `raw_frame` as Training fits one (the encoder fitted on it, the
    searched configuration over the family's fixed parameters), and its bundle content."""
    frame = raw_frame()
    encoder = fit_encoder(frame, FEATURES, KINDS, ORDER, 50, "native")
    encoded, _ = encode_frame(frame, encoder)
    power = 1.5 if OBJECTIVES[task] == "tweedie" else None
    fixed = FAMILIES[family].fixed_params(task, OBJECTIVES[task], encoder, {}, SEED, 1, power)
    params = {**fixed, **SEARCHED[family]}
    booster = FAMILIES[family].fit(encoded, targets(frame, task), params, task)
    return booster, bundle_content(encoder, task, family, CALIBRATIONS[task])


def scores_in_memory(
    family: str, booster: object, content: dict, frame: pd.DataFrame
) -> pd.DataFrame:
    """The model in memory's scores of `frame`, without the bundle: encode, predict, calibrate."""
    encoded, _ = encode_frame(frame, content["encoder"])
    margin = FAMILIES[family].predict(booster, encoded)
    score_raw, score = apply_calibration(margin, content["calibration"], content["task"])
    return pd.DataFrame(
        {"margin": margin, "score_raw": score_raw, "score": score}, index=frame.index
    )


def scoring_frame() -> pd.DataFrame:
    """Rows the model never saw, on a client index, five of them with a level unseen in train."""
    frame = raw_frame(300, seed=1).set_index("unit_id")
    frame.iloc[:5, frame.columns.get_loc("channel")] = "fax"
    return frame


def spec_model_hash(folder: Path) -> str:
    """`model_hash` by the spec's rule, computed here: one SHA-256 over `bundle.json` and
    `model.txt` in name order, each as its name, NUL, its byte length, NUL and its bytes."""
    digest = hashlib.sha256()
    for name in (BUNDLE_FILE, "model.txt"):
        data = (folder / name).read_bytes()
        digest.update(name.encode() + b"\0" + str(len(data)).encode() + b"\0" + data)
    return digest.hexdigest()


def rehash_manifest(folder: Path) -> None:
    """Point the manifest at the files as they are now, as someone who knows the rule would."""
    manifest = json.loads((folder / MANIFEST_FILE).read_text())
    rehashed = {**manifest, "model_hash": spec_model_hash(folder)}
    (folder / MANIFEST_FILE).write_text(json.dumps(rehashed))


def written_bundle(tmp_path: Path) -> tuple[Path, object, dict]:
    """A binary LightGBM bundle written to `tmp_path/bundle`, with its booster and content."""
    booster, content = trained()
    folder = tmp_path / "bundle"
    write_bundle(str(folder), "lgbm", booster, content, IDENTITY)
    return folder, booster, content


ROUND_TRIPS = [(family, "binary") for family in FAMILIES] + [("lgbm", "regression")]


@pytest.mark.parametrize(("family", "task"), ROUND_TRIPS)
def test_a_written_bundle_loads_and_scores_as_the_model_in_memory(
    family: str, task: str, tmp_path: Path
) -> None:
    """The bundle is three plain files (D-051), and the model read back from them scores raw
    rows exactly as the fitted one, so the self-check passes."""
    booster, content = trained(family, task)
    folder = str(tmp_path / "bundle")
    model_hash = write_bundle(folder, family, booster, content, IDENTITY)
    bundle = load_bundle(folder)
    written = sorted(path.name for path in Path(folder).iterdir())
    assert written == sorted([BUNDLE_FILE, MANIFEST_FILE, FAMILIES[family].file_name])
    assert (bundle.model_hash, bundle.family, bundle.task) == (model_hash, family, task)
    assert bundle.features == FEATURES and bundle.content["features"] == FEATURES
    frame = scoring_frame()
    expected = scores_in_memory(family, booster, content, frame)
    pd.testing.assert_frame_equal(score_frame(bundle, frame), expected, check_exact=True)
    check_bundle(folder, frame, expected)


def test_model_hash_follows_the_rule_and_repeats(tmp_path: Path) -> None:
    """`model_hash` is the spec's SHA-256 over `bundle.json` and the model file, stored with
    the identities' `hash_version`; two writes of one model for two runs give the same bytes
    and hash, and a bundle folder is never written twice."""
    booster, content = trained()
    hashes = [
        write_bundle(str(tmp_path / run), "lgbm", booster, content, {**IDENTITY, "run_id": run})
        for run in ("r001", "r002")
    ]
    first, second = tmp_path / "r001", tmp_path / "r002"
    manifest = json.loads((first / MANIFEST_FILE).read_text())
    assert list(manifest) == MANIFEST_KEYS and manifest["hash_version"] == HASH_VERSION
    assert manifest["files"] == [BUNDLE_FILE, "model.txt"]
    assert manifest["model_hash"] == hashes[0] == hashes[1] == spec_model_hash(first)
    assert (first / BUNDLE_FILE).read_bytes() == (second / BUNDLE_FILE).read_bytes()
    with pytest.raises(FileExistsError, match="written once"):
        write_bundle(str(first), "lgbm", booster, content, IDENTITY)


@pytest.mark.parametrize("name", [BUNDLE_FILE, "model.txt"])
def test_one_changed_byte_in_either_file_is_refused_at_load(name: str, tmp_path: Path) -> None:
    """A loader verifies before it reads: one flipped bit moves the recomputed hash away from
    the manifest's, and the bundle is refused naming its folder."""
    folder, _, _ = written_bundle(tmp_path)
    data = bytearray((folder / name).read_bytes())
    data[len(data) // 2] ^= 1
    (folder / name).write_bytes(bytes(data))
    with pytest.raises(ValueError, match=f"^{re.escape(str(folder))}: .* hash to model_hash"):
        load_bundle(str(folder))


def test_bytes_moved_from_one_file_to_the_other_are_refused(tmp_path: Path) -> None:
    """The files joined end to end are unchanged when `bundle.json`'s last byte moves to the
    front of the model file; the names and lengths in the hash still tell the two apart."""
    folder, _, _ = written_bundle(tmp_path)
    bundle, model = (folder / BUNDLE_FILE).read_bytes(), (folder / "model.txt").read_bytes()
    (folder / BUNDLE_FILE).write_bytes(bundle[:-1])
    (folder / "model.txt").write_bytes(bundle[-1:] + model)
    joined = (folder / BUNDLE_FILE).read_bytes() + (folder / "model.txt").read_bytes()
    assert joined == bundle + model
    with pytest.raises(ValueError, match="hash to model_hash"):
        load_bundle(str(folder))


def rewrite_bundle_json(folder: Path, **changes: object) -> None:
    """Change top-level keys of `bundle.json` and point the manifest at the new file."""
    stored = json.loads((folder / BUNDLE_FILE).read_text())
    (folder / BUNDLE_FILE).write_text(json.dumps({**stored, **changes}))
    rehash_manifest(folder)


@pytest.mark.parametrize("what", ["manifest_schema_version", "hash_version"])
def test_another_manifest_or_hash_version_is_refused_naming_the_fix(
    what: str, tmp_path: Path
) -> None:
    """A reader refuses a manifest format or hash rule it does not read and says what to do,
    before any hash is compared, so a later bump is never read as a changed file."""
    folder, _, _ = written_bundle(tmp_path)
    manifest = json.loads((folder / MANIFEST_FILE).read_text())
    (folder / MANIFEST_FILE).write_text(json.dumps({**manifest, what: 2}))
    with pytest.raises(ValueError, match=f"{what} is 2; .* train the model again"):
        load_bundle(str(folder))


def test_a_bundle_read_from_disk_is_checked_as_written(tmp_path: Path) -> None:
    """Behind a matching hash, `bundle.json`'s own version, its encoder (its version naming
    the fix, a missing key named) and its calibration are checked again at load."""
    folder, _, content = written_bundle(tmp_path)
    original, encoder = (folder / BUNDLE_FILE).read_text(), content["encoder"]
    reversed_platt = {**content["calibration"], "parameters": {"a": -1.0, "b": 0.0}}
    without_mode = {key: value for key, value in encoder.items() if key != "unordered"}
    for changes, message in (
        ({"bundle_schema_version": 2}, "bundle_schema_version is 2; .* train the model again"),
        ({"encoder": {**encoder, "schema_version": 2}}, "encoder's schema_version is 2; .* train"),
        ({"encoder": without_mode}, r"the encoder lacks the keys \['unordered'\]"),
        ({"calibration": reversed_platt}, "reverses or flattens the model's order"),
    ):
        (folder / BUNDLE_FILE).write_text(original)  # one change at a time
        rewrite_bundle_json(folder, **changes)
        with pytest.raises(ValueError, match=message):
            load_bundle(str(folder))


def test_a_manifest_with_other_files_or_keys_is_refused(tmp_path: Path) -> None:
    """The manifest decides which files are read and hashed, so a name outside the bundle's
    folder, or a missing key, is refused naming the folder before any file is read."""
    folder, _, _ = written_bundle(tmp_path)
    manifest = json.loads((folder / MANIFEST_FILE).read_text())
    outside = {**manifest, "files": [BUNDLE_FILE, "../x"]}
    without_hash = {key: value for key, value in manifest.items() if key != "model_hash"}
    for changed, message in ((outside, "lists the files"), (without_hash, "holds the keys")):
        (folder / MANIFEST_FILE).write_text(json.dumps(changed))
        with pytest.raises(
            ValueError, match=f"^{re.escape(str(folder))}: {MANIFEST_FILE} {message}"
        ):
            load_bundle(str(folder))


def test_another_library_version_is_warned_not_refused(tmp_path: Path) -> None:
    """A native model file loads across library versions, so a bundle saved with another one
    loads and scores, with a warning that names both versions."""
    folder, booster, content = written_bundle(tmp_path)
    rewrite_bundle_json(folder, library_version={"lightgbm": "0.0.1"})
    installed = version("lightgbm")
    with pytest.warns(
        UserWarning, match=f"saved with lightgbm 0.0.1, and {installed} is installed"
    ):
        bundle = load_bundle(str(folder))
    frame = scoring_frame()
    expected = scores_in_memory("lgbm", booster, content, frame)
    pd.testing.assert_frame_equal(score_frame(bundle, frame), expected, check_exact=True)


def test_the_self_check_fails_loud_on_a_changed_expectation(tmp_path: Path) -> None:
    """Any difference from the model in memory, one unit in the last place included, fails and
    names the first differing column; a non-finite expectation and an empty sample fail too."""
    folder, booster, content = written_bundle(tmp_path)
    frame = scoring_frame()
    expected = scores_in_memory("lgbm", booster, content, frame)
    nudged = expected.copy()
    nudged.iloc[3, 2] = np.nextafter(nudged.iloc[3, 2], 1.0)
    with pytest.raises(ValueError, match="bundle's score differs .* by up to"):
        check_bundle(str(folder), frame, nudged)
    with pytest.raises(ValueError, match="bundle's margin differs"):
        check_bundle(str(folder), frame, expected.assign(margin=expected["margin"] + 1e-9))
    with pytest.raises(ValueError, match="non-finite score_raw"):
        check_bundle(str(folder), frame, expected.assign(score_raw=np.nan))
    with pytest.raises(ValueError, match="no rows to score"):
        check_bundle(str(folder), frame.iloc[:0], expected.iloc[:0])


def test_bundle_json_holds_no_time_run_or_person(tmp_path: Path) -> None:
    """Whatever is in `bundle.json` is in `model_hash`, so it holds the spec's keys only: a
    content that brings any other key, or features that are not the encoder's, is refused
    before anything is written."""
    folder, booster, content = written_bundle(tmp_path)
    text = (folder / BUNDLE_FILE).read_text()
    assert sorted(json.loads(text)) == sorted(BUNDLE_KEYS)
    written_at = json.loads((folder / MANIFEST_FILE).read_text())["written_at"]
    assert IDENTITY["run_id"] not in text and written_at[:10] not in text
    for key in ("written_at", "run_id", "trained_by"):
        with pytest.raises(ValueError, match=rf"carries \['{key}'\]"):
            write_bundle(str(tmp_path / key), "lgbm", booster, {**content, key: "x"}, IDENTITY)
        assert not (tmp_path / key).exists()
    reordered = {**content, "features": FEATURES[::-1]}
    with pytest.raises(ValueError, match="not the encoder's"):
        write_bundle(str(tmp_path / "reordered"), "lgbm", booster, reordered, IDENTITY)


REFUSED = [  # the part of the content changed, its key, the new value, the refusal
    ("calibration", "method", "isotonic", "method 'isotonic' does not apply"),
    ("calibration", "offset", float("nan"), "offset is nan"),
    ("calibration", "parameters", {"a": -1.0, "b": 0.0}, "reverses or flattens"),
    ("encoder", "schema_version", 2, "encoder's schema_version is 2; .* train the model again"),
    ("recipe", "seed", SEED, r"carries \['seed'\]"),
    ("recipe", "family", "xgboost", r"recipe's \['family'\] differ"),
    ("recipe", "parameters", {"learning_rate": float("nan")}, "never NaN or inf"),
    ("recipe", "parameters", {"n_estimators": 20, "n_jobs": 4}, r"thread counts \['n_jobs'\]"),
    ("recipe", "calibration", {"method": "platt", "folds": 5, "a": 0.9}, "never the fitted"),
]


@pytest.mark.parametrize(("part", "key", "value", "message"), REFUSED)
def test_a_refused_content_leaves_nothing_on_disk(
    part: str, key: str, value: object, message: str, tmp_path: Path
) -> None:
    """Every check comes before the folder is made: a calibration, an encoder or a recipe
    this version refuses (a recipe key outside the pinned list would carry something
    run-specific into both hashes) leaves no folder, so the corrected retry is not refused."""
    booster, content = trained()
    folder = tmp_path / "bundle"
    refused = {**content, part: {**content[part], key: value}}
    with pytest.raises(ValueError, match=message):
        write_bundle(str(folder), "lgbm", booster, refused, IDENTITY)
    assert not folder.exists()
    write_bundle(str(folder), "lgbm", booster, content, IDENTITY)


def test_recipe_hash_ignores_the_calibration_numbers_and_moves_with_a_feature(
    tmp_path: Path,
) -> None:
    """A production retrain keeps the recipe and refits the calibration numbers (D-052): they
    move `model_hash`, never `recipe_hash`, while a feature that leaves moves both the recipe
    hash and the feature signature, which follows the order."""
    booster, content = trained()
    refitted = {**content["calibration"], "parameters": {"a": 1.1, "b": 0.05}, "offset": 0.0}
    hashes = [
        write_bundle(str(tmp_path / name), "lgbm", booster, given, IDENTITY)
        for name, given in (("first", content), ("second", {**content, "calibration": refitted}))
    ]
    assert hashes[0] != hashes[1]
    manifests = [
        json.loads((tmp_path / name / MANIFEST_FILE).read_text()) for name in ("first", "second")
    ]
    recorded = {manifest["recipe_hash"] for manifest in manifests}
    assert recorded == {recipe_hash(content["recipe"])}
    assert manifests[0]["feature_signature"] == feature_signature(FEATURES)
    assert len(manifests[0]["recipe_hash"]) == len(manifests[0]["feature_signature"]) == 64
    fewer = {**content["recipe"], "features": FEATURES[:-1]}
    assert recipe_hash(fewer) != recipe_hash(content["recipe"])
    assert feature_signature(FEATURES[:-1]) != feature_signature(FEATURES)
    assert feature_signature(FEATURES[::-1]) != feature_signature(FEATURES)
