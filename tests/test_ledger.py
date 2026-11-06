"""The feature ledger: stages append only their own columns, decisions are derived when it is read
and never stored, and Training's feature set leaves out lineage, unsupported, excluded and held
features (§4.6, D-134)."""

import json
from collections.abc import Callable
from pathlib import Path

import pandas as pd
import pytest

from core_modelling.config.replay import By, Entry, replay, validate_raw
from core_modelling.config.schema import UseCaseConfig
from core_modelling.ledger import (
    COLUMNS_BY_STAGE,
    add_columns,
    create_ledger,
    read_ledger,
    render_decisions,
    resolve_features,
    save_ledger,
)

# Deliberately not alphabetical, so the tests see the ledger's order kept.
CANDIDATES = ["tenure", "bal", "prod", "flag_x", "fwd_txn", "open_date"]
READ = ["tenure", "bal", "prod", "flag_x"]  # neither lineage nor unsupported
KINDS = {"tenure": "numeric", "bal": "numeric", "prod": "categorical", "flag_x": "categorical"}
# Every candidate's source but the lineage column's: an upstream target's, in no source.
SOURCES = {name: "mart" for name in CANDIDATES if name != "fwd_txn"} | {"prod": "extract"}
META = {"stage": "feature_checks", "data_definition_hash": "d" * 64, "settings_digest": "abc"}


def _ledger() -> pd.DataFrame:
    """A ledger with one lineage and one unsupported column."""
    return create_ledger(CANDIDATES, KINDS, ["fwd_txn"], ["open_date"], SOURCES)


def _with_stages() -> pd.DataFrame:
    """The ledger with a few EDA and Feature Checks columns: list, nullable-int and bool ones,
    and a null cell (`prod`'s partners)."""
    eda = pd.DataFrame(
        {
            "feature": READ,
            "levels": pd.array([40, 900, 12, 2], dtype="Int64"),
            "concordance": [0.64, 0.71, 0.63, 0.99],
            "non_monotone": [False, True, False, False],
            "rank": pd.array([3, 2, 4, 1], dtype="Int64"),
        }
    )
    checks = pd.DataFrame(
        {
            "feature": READ,
            "flags": [[], [], ["quality.high_cardinality"], ["leakage.too_strong"]],
            "partners": [[], ["prod"], None, ["bal", "prod"]],
            "cluster": pd.array([None, None, None, 1], dtype="Int64"),
        }
    )
    return add_columns(add_columns(_ledger(), eda, "eda"), checks, "feature_checks")


def test_create_ledger_gives_one_row_per_candidate() -> None:
    """Lineage and unsupported columns keep a row, flagged; an unsupported column's kind says so
    and a lineage column without a kind has none; each row names its source, the lineage column
    in no source none."""
    ledger = _ledger()
    assert ledger["feature"].tolist() == CANDIDATES
    assert ledger["kind"].tolist() == [*KINDS.values(), None, "unsupported"]
    assert ledger["lineage"].tolist() == [False] * 4 + [True, False]
    assert ledger["unsupported"].tolist() == [False] * 5 + [True]
    assert ledger["source"].tolist() == ["mart", "mart", "extract", "mart", None, "mart"]


def test_create_ledger_refuses_what_it_cannot_record() -> None:
    """A repeated candidate, a lineage or unsupported column that is no candidate, a kind other
    than numeric or categorical, a read candidate without a kind and an unsupported one with a
    kind, and a candidate without a source are refused, naming only the features at fault."""
    with pytest.raises(ValueError, match="more than once"):
        create_ledger(["bal", "bal"], {"bal": "numeric"}, [], [], SOURCES)
    with pytest.raises(ValueError, match=r"\['fwd_txn', 'open_date'\] are not among"):
        create_ledger(["bal"], {"bal": "numeric"}, ["fwd_txn"], ["open_date"], SOURCES)
    with pytest.raises(ValueError, match=r"refused \{'bal': 'numeric_typo'\}"):
        create_ledger(["bal"], {"bal": "numeric_typo"}, [], [], SOURCES)
    with pytest.raises(ValueError, match=r"no kind for the candidates \['prod'\]"):
        create_ledger(["bal", "prod"], {"bal": "numeric"}, [], [], SOURCES)
    kinds = {"open_date": "numeric", "bal": "numeric"}
    with pytest.raises(ValueError, match=r"have a kind: \{'open_date': 'numeric'\}$"):
        create_ledger(["open_date", "bal"], kinds, [], ["open_date"], SOURCES)
    with pytest.raises(ValueError, match=r"no source for the candidates \['tenure'\]"):
        create_ledger(["bal", "tenure"], KINDS, [], [], {"bal": "mart"})


def test_add_columns_appends_only_the_stages_own_columns() -> None:
    """Another stage's column, a derived column, a feature not in the ledger, a repeated feature
    and a read candidate left out are refused; the rest is untouched, and the lineage and
    unsupported rows hold None in object and list columns, as the saved ledger reads back."""
    ledger = _with_stages()
    with pytest.raises(ValueError, match="'flags': 'feature_checks'"):
        add_columns(ledger, pd.DataFrame({"feature": READ, "flags": [["x.y"]] * 4}), "eda")
    with pytest.raises(ValueError, match="'held': 'derived when read'"):
        add_columns(ledger, pd.DataFrame({"feature": READ, "held": True}), "feature_checks")
    with pytest.raises(ValueError, match=r"\['ghost'\] are not in the ledger"):
        add_columns(ledger, pd.DataFrame({"feature": [*READ, "ghost"], "rank": 1}), "eda")
    with pytest.raises(ValueError, match=r"stage eda: .* repeat the features \['bal'\]"):
        add_columns(ledger, pd.DataFrame({"feature": [*READ, "bal"], "rank": 1}), "eda")
    with pytest.raises(ValueError, match=r"stage eda: no row for the candidates \['flag_x'\]"):
        add_columns(ledger, pd.DataFrame({"feature": READ[:3], "rank": 1}), "eda")
    assert ledger["concordance"].tolist()[:4] == [0.64, 0.71, 0.63, 0.99]
    unread = ledger.set_index("feature").loc[["fwd_txn", "open_date"]]
    assert unread[["flags", "partners", "non_monotone"]].map(lambda v: v is None).all().all()


def test_a_rerun_replaces_every_column_the_stage_wrote_before() -> None:
    """A Feature Checks rerun that writes fewer columns (a skipped step) leaves none of its
    earlier ones, and EDA's stay as they were."""
    ledger = _with_stages()
    flags = [[], ["redundancy.correlated_pair"], [], []]
    after = add_columns(ledger, pd.DataFrame({"feature": READ, "flags": flags}), "feature_checks")
    assert "cluster" not in after and "partners" not in after
    assert after.loc[after["feature"] == "bal", "flags"].item() == ["redundancy.correlated_pair"]
    assert after["flags"].isna().sum() == 2  # the lineage and unsupported rows
    others = [c for c in ledger if c not in COLUMNS_BY_STAGE["feature_checks"]]
    pd.testing.assert_frame_equal(after[others], ledger[others])


def test_the_ledger_reads_back_as_saved(tmp_path: Path) -> None:
    """List, nullable-int and bool columns survive the parquet round trip unchanged; the sidecar
    names its version, the stages present and the writer's hash and digest."""
    ledger = _with_stages()
    save_ledger(ledger, str(tmp_path), META)
    pd.testing.assert_frame_equal(read_ledger(str(tmp_path), "d" * 64), ledger)
    sidecar = json.loads((tmp_path / "_ledger.json").read_text())
    assert sidecar["ledger_schema_version"] == 2
    assert sidecar["stages"] == ["eda", "feature_checks"]
    assert {k: sidecar[k] for k in META} == META
    assert sorted(path.name for path in tmp_path.iterdir()) == ["_ledger.json", "ledger.parquet"]


def test_save_ledger_refuses_a_derived_or_unowned_column_and_a_bad_meta(tmp_path: Path) -> None:
    """A stored decision would go stale with the next entry (V10); a column no stage owns has no
    place in the file; the meta must name the writer and its data definition, and nothing else."""
    with pytest.raises(ValueError, match=r"\['held'\] are derived"):
        save_ledger(_ledger().assign(held=False), str(tmp_path), META)
    with pytest.raises(ValueError, match="belong to no stage"):
        save_ledger(_ledger().assign(note="x"), str(tmp_path), META)
    with pytest.raises(ValueError, match=r"lacks \['data_definition_hash'\]"):
        save_ledger(_ledger(), str(tmp_path), {"stage": "eda"})
    with pytest.raises(ValueError, match=r"may not set \['settings'\]"):
        save_ledger(_ledger(), str(tmp_path), {**META, "settings": {}})
    with pytest.raises(ValueError, match="names stage 'training'"):
        save_ledger(_ledger(), str(tmp_path), {**META, "stage": "training"})
    assert list(tmp_path.iterdir()) == []


def test_a_failed_save_keeps_the_previous_ledger(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A write failing mid-way leaves the previous ledger and sidecar as they were and no
    temporary file."""
    save_ledger(_ledger(), str(tmp_path), {**META, "stage": "eda"})

    def to_parquet(frame: pd.DataFrame, path: Path, **kwargs: object) -> None:
        """Half a file, then a full disk."""
        Path(path).write_text("half")
        raise OSError("planted: disk full")

    monkeypatch.setattr(pd.DataFrame, "to_parquet", to_parquet)
    with pytest.raises(OSError, match="planted"):
        save_ledger(_with_stages(), str(tmp_path), META)
    monkeypatch.undo()
    assert sorted(path.name for path in tmp_path.iterdir()) == ["_ledger.json", "ledger.parquet"]
    pd.testing.assert_frame_equal(read_ledger(str(tmp_path)), _ledger())


def test_read_ledger_refuses_a_missing_ledger_another_version_and_definition(
    tmp_path: Path,
) -> None:
    """No ledger asks for EDA; another `ledger_schema_version` (an older one without `source`)
    is refused, and so is a ledger written for another data definition, naming both."""
    with pytest.raises(FileNotFoundError, match="run EDA first"):
        read_ledger(str(tmp_path))
    save_ledger(_ledger(), str(tmp_path), META)
    with pytest.raises(ValueError, match="data definition dddddddddddd, the config's is eeee"):
        read_ledger(str(tmp_path), "e" * 64)
    sidecar = tmp_path / "_ledger.json"
    older = sidecar.read_text().replace('"ledger_schema_version": 2', '"ledger_schema_version": 1')
    sidecar.write_text(older)
    with pytest.raises(ValueError, match="ledger_schema_version 1 .* reads 2: rerun EDA"):
        read_ledger(str(tmp_path))


def test_resolve_features_leaves_out_lineage_unsupported_excluded_and_held(
    variant: Callable[..., UseCaseConfig],
) -> None:
    """Training's set keeps the ledger's order; a held feature is out like an excluded one, a
    kept one is in, and a held feature that is also kept stays out."""
    ledger = _ledger()
    assert resolve_features(ledger, variant()) == READ
    resolved = variant(features={"excluded": ["flag_x"], "held": ["prod"], "kept": ["tenure"]})
    assert resolve_features(ledger, resolved) == ["tenure", "bal"]
    both = variant(features={"held": ["tenure"], "kept": ["tenure"]})
    assert resolve_features(ledger, both) == ["bal", "prod", "flag_x"]


def test_resolve_features_refuses_a_name_that_is_no_ledger_row(
    variant: Callable[..., UseCaseConfig],
) -> None:
    """A mistyped exclude would otherwise leave the feature in training without a word."""
    typo = variant(features={"excluded": ["balanse"], "kept": ["tenure", "ghost"]})
    with pytest.raises(ValueError, match=r"'features.excluded': \['balanse'\].*\['ghost'\]"):
        resolve_features(_ledger(), typo)


def _entry(seq: int, op: str, **fields: object) -> Entry:
    """A person's entry on the test's data definition."""
    return Entry(
        seq=seq,
        time="2026-11-03T10:00:00+00:00",
        by=By(kind="person", id="ds"),
        stage="feature_checks",
        op=op,
        reason="test",
        data_definition_hash="d" * 64,
        hash_version=1,
        log_schema_version=1,
        **fields,
    )


ENTRIES = [
    _entry(1, "exclude", features=["flag_x"]),
    _entry(2, "keep", features=["tenure"], findings=["time_alignment.client_constant"]),
    _entry(3, "exclude", features=["bal"]),
    _entry(4, "include", features=["bal"]),
    _entry(5, "exclude", features=["prod"]),
    _entry(6, "revert", to_seq=4),
]


def test_render_decisions_derives_the_decisions_in_force(
    cc_config: UseCaseConfig,
) -> None:
    """An exclude in force carries its number, an include reverses one, a reverted exclude is
    gone, a keep is listed, and the verdict follows auto_excluded > excluded > held > kept >
    pass; the stored columns are left as they were."""
    ledger = _with_stages()
    resolved = validate_raw(replay(cc_config, ENTRIES), "the test's replay")
    resolved.features.held = ["prod", "flag_x"]  # flag_x is excluded, so not held
    view = render_decisions(ledger, resolved, ENTRIES)
    by_feature = view.set_index("feature")
    assert by_feature["excluded"].tolist() == [pd.NA, pd.NA, pd.NA, 1, pd.NA, pd.NA]
    assert by_feature["kept"].tolist() == [[2], [], [], [], [], []]
    assert by_feature["held"].tolist() == [False, False, True, False, False, False]
    assert by_feature["verdict"].tolist() == [
        "kept", "pass", "held", "excluded", "auto_excluded", "auto_excluded",
    ]  # fmt: skip
    pd.testing.assert_frame_equal(view[ledger.columns], ledger)


def test_render_decisions_refuses_entries_of_another_state_and_unknown_names(
    cc_config: UseCaseConfig,
) -> None:
    """Entries other than those the config was resolved from would number another state; a held
    name that is no ledger row is refused before anything is rendered."""
    resolved = validate_raw(replay(cc_config, ENTRIES), "the test's replay")
    with pytest.raises(ValueError, match="disagree on features.excluded"):
        render_decisions(_ledger(), resolved, ENTRIES[:3])
    resolved.features.held = ["ghost"]
    with pytest.raises(ValueError, match=r"'features.held': \['ghost'\]"):
        render_decisions(_ledger(), resolved, ENTRIES)
