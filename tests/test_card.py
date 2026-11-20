"""The model card: built from an evaluated run folder of the card config and of the regression
variant (the session fixtures of `conftest.py`, Spark), it holds every section in order under
its schema version, survives a JSON round trip, carries the bundle's final features and every
metric row, and is the same built from Evaluation's result in memory as from the written folder.
The page renders a card read back from JSON, names every section and embeds no script. The
helpers' tests (the considerations, the refusals, the page of a small card) need no Spark.
"""

import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from core_modelling.artifacts import StageResult, read_stage
from core_modelling.evaluation.card import (
    CARD_SCHEMA_VERSION,
    _check_evaluation,
    _check_run_pieces,
    _plain,
    _read_run_json,
    _recorded_considerations,
    _require,
    _warning_codes,
    build_card,
)
from core_modelling.model.bundle import Bundle, load_bundle
from core_modelling.reporting.card import CARD_SECTIONS, render_card
from core_modelling.runs import RUN_SCHEMA_VERSION


@pytest.fixture(params=["evaluated_card", "evaluated_regression"])
def evaluated(request: pytest.FixtureRequest) -> StageResult:
    """Each config's evaluated run in turn."""
    return request.getfixturevalue(request.param)


def _written_card(evaluated: StageResult) -> tuple[dict, dict, str]:
    """The card built from the written run folder as a later reader rebuilds it, with
    Evaluation's tables read back and the run folder."""
    folder = evaluated.paths["folder"]
    meta, tables = read_stage(folder, "evaluation")
    run_folder = str(Path(folder).parent)
    return build_card(run_folder, tables, meta, evaluated.config), tables, run_folder


def _headings() -> list[str]:
    """Each section's heading as the page writes it."""
    return [name.replace("_", " ").capitalize() for name in CARD_SECTIONS]


def test_card_holds_every_section_and_survives_json(evaluated: StageResult) -> None:
    """The schema version, then the sections in order; sign-off and lifecycle empty, the model
    key None; the JSON round trip changes nothing."""
    card, _, _ = _written_card(evaluated)
    assert list(card) == ["schema_version", *CARD_SECTIONS]
    assert card["schema_version"] == CARD_SCHEMA_VERSION
    assert card["sign_off"] == {} and card["lifecycle"] == {}
    assert card["details"]["model_key"] is None
    assert json.loads(json.dumps(card, allow_nan=False)) == card


def test_card_holds_the_final_features_and_the_metric_rows(evaluated: StageResult) -> None:
    """The final list is the bundle's; every metric row of Evaluation's table is a record."""
    card, tables, run_folder = _written_card(evaluated)
    final = [row["feature"] for row in card["features"]["final"]]
    assert sorted(final) == sorted(load_bundle(f"{run_folder}/bundle").features)
    assert len(card["performance"]["metrics"]) == len(tables["metrics"])
    assert card["details"]["task"] == evaluated.config.task


def test_card_from_memory_is_the_card_from_the_folder(evaluated: StageResult) -> None:
    """Evaluation builds the card from its result before writing; a rebuild from the written
    folder gives the same facts but the time the card was written."""
    written, _, run_folder = _written_card(evaluated)
    in_memory = build_card(run_folder, evaluated.tables, evaluated.meta, evaluated.config)
    for card in (written, in_memory):
        card["details"]["dates"].pop("card_written_at")
    assert in_memory == written


def test_card_refuses_another_model(evaluated: StageResult) -> None:
    """A meta of another model than the bundle's is refused, naming both."""
    folder = evaluated.paths["folder"]
    meta, tables = read_stage(folder, "evaluation")
    with pytest.raises(ValueError, match="the bundle holds"):
        build_card(str(Path(folder).parent), tables, {**meta, "model_hash": "0" * 64},
                   evaluated.config)  # fmt: skip


def test_render_card_names_every_section_without_script(evaluated: StageResult) -> None:
    """The page of a card read back from JSON: every section's heading, no script."""
    card, _, _ = _written_card(evaluated)
    page = render_card(json.loads(json.dumps(card)))
    assert "<script" not in page
    assert all(f">{heading}</h2>" in page for heading in _headings())


def test_plain_gives_json_types() -> None:
    """Numpy values become Python, tuples and arrays lists, missing values None; an infinity and
    an unknown type fail."""
    value = {"a": np.int64(3), "b": np.float64("nan"), "c": (1, pd.NA), "d": np.array([1.5]),
             "e": [{"f": np.bool_(True)}]}  # fmt: skip
    assert _plain(value) == {"a": 3, "b": None, "c": [1, None], "d": [1.5], "e": [{"f": True}]}
    with pytest.raises(ValueError, match="infinite"):
        _plain({"a": float("inf")})
    with pytest.raises(TypeError, match="Timestamp"):
        _plain({"a": pd.Timestamp("2025-01-31")})


def test_considerations_are_codes_from_facts() -> None:
    """Evaluation's warnings are copied without their text, a sentence warning fails; the
    recorded facts raise their own codes."""
    warnings = [{"code": "nulls_not_in_train", "features": ["a"], "text": "a sentence"}]
    assert _warning_codes(warnings) == [{"code": "nulls_not_in_train", "features": ["a"]}]
    with pytest.raises(ValueError, match="carries no code"):
        _warning_codes(["a sentence"])
    meta = {
        "validation_period": "2025-11",
        "earlier_validations": [{"validation_period": "2025-10"}],
    }
    training = {"reproducible_to": "recipe", "settings": {"training": {"time_budget_s": 60}}}
    selection = pd.DataFrame({"feature": ["a", "b"], "outcome": ["undone", "passed"]})
    agrees = pd.array([False, pd.NA], dtype="boolean")
    ledger = pd.DataFrame({"feature": ["a", "b"], "monotone_agrees": agrees})
    assert _recorded_considerations(meta, training, selection, ledger) == [
        {"code": "validation_period_moved", "earlier_periods": ["2025-10"]},
        {"code": "reproducible_to_recipe", "time_budget_s": 60},
        {"code": "monotone_against_eda", "features": ["a"]},
        {"code": "pruning_undone", "features": ["a"]},
    ]


def _run_pieces() -> tuple[dict, dict, dict, dict, Bundle]:
    """One run's `run.json`, manifest, `training.json` and Evaluation meta, reduced to the keys
    `_check_run_pieces` and `_check_evaluation` read, and its bundle."""
    bundle = Bundle(booster=None, family="lgbm", task="binary", encoder={}, calibration={},
                    features=["a"], content={}, model_hash="m")  # fmt: skip
    run, manifest = {"run_id": "r001"}, {"run_id": "r001"}
    training = {"run_id": "r001", "final_features": ["a"]}
    meta = {"run_id": "r001", "model_hash": "m", "config_hash": "c"}
    return run, manifest, training, meta, bundle


def test_card_refuses_another_run_or_config() -> None:
    """One run's pieces under the config Evaluation ran with pass; another run id, or a config
    changed since Evaluation ran, is refused."""
    run, manifest, training, meta, bundle = _run_pieces()
    _check_run_pieces(run, manifest, training, bundle)
    _check_evaluation(run, meta, bundle, "c")
    with pytest.raises(ValueError, match="name the runs"):
        _check_run_pieces(run, manifest, {**training, "run_id": "r002"}, bundle)
    with pytest.raises(ValueError, match="meta names run r002"):
        _check_evaluation(run, {**meta, "run_id": "r002"}, bundle, "c")
    with pytest.raises(ValueError, match="Evaluation ran with config c"):
        _check_evaluation(run, meta, bundle, "d")


def test_card_refuses_a_missing_key(tmp_path: Path) -> None:
    """A `run.json` or a meta without a key the card reads fails naming the key."""
    path = tmp_path / "run.json"
    path.write_text(json.dumps({"run_schema_version": RUN_SCHEMA_VERSION, "run_id": "r001"}))
    with pytest.raises(ValueError, match="lacks .*'use_case'"):
        _read_run_json(str(path))
    with pytest.raises(ValueError, match=r"Evaluation's meta lacks \['warnings'\]"):
        _require({"run_id": "r001"}, ("run_id", "warnings"), "Evaluation's meta")


def test_render_card_on_a_small_card() -> None:
    """Nested facts are dotted, a list of records is its own table, text is escaped, a missing
    key or a null number is blank (never `nan`) and an empty section reads `none`."""
    card = {
        "schema_version": CARD_SCHEMA_VERSION,
        "details": {"use_case": "u", "run_id": "r001", "entity": "e", "hashes": {"model": "h"}},
        "intended_use": {"population": [{"name": "<b>", "filter": "x > 1"}, {"name": "c"}]},
        "data": {"rows": [{"part": "test", "rows": None}, {"part": "validation", "rows": 3}]},
        **{name: {} for name in CARD_SECTIONS[3:]},
    }
    page = render_card(card)
    assert "hashes.model" in page and "&lt;b&gt;" in page and "<b>" not in page
    assert page.count("<p>none</p>") == len(CARD_SECTIONS) - 3
    assert ">nan<" not in page
    assert "<script" not in page
