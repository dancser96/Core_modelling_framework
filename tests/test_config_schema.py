"""The config spine: the example and the template load, level defaults resolve, every rule fails
loud with a message naming the problem."""

import copy
import re
from datetime import date
from pathlib import Path
from typing import get_args, get_origin

import pytest
import yaml
from pydantic import BaseModel, TypeAdapter, ValidationError
from pydantic.fields import FieldInfo

from core_modelling.config import UseCaseConfig, load_config
from core_modelling.config.levels import (
    LEVEL_DEFAULTS,
    LEVELS,
    apply_level_defaults,
    unmark_level_filled,
)
from core_modelling.config.migrations import MIGRATIONS

ROOT = Path(__file__).resolve().parents[1]
EXAMPLE = ROOT / "conf/base/cc_acquisition.yml"
TEMPLATE = ROOT / "conf/base/TEMPLATE.yml"
PLACEHOLDERS = {
    "<product>": "cc",
    "<activity>": "acquisition",
    "<domain>": "retail",
    "<entity>": "entity_a",
    "<feature_source>": "retail_mart",
    "<target_source>": "retail_holdings",
    "<unit_id_column>": "client_id",
    "<month_column>": "snapshot_month",
    "<step_name>": "non_holders",
    "<spark_sql>": "cc_flag = 0",
    "<reason>": "scored for non-holders",
    "<target_column>": "cc_flag",
    "<first_month>": "2025-03-01",
    "<last_month>": "2025-08-01",
    "<validation_month>": "2025-11-01",
    "<strata_variable>": "segment",
}
REPLAY_ONLY = {"features.excluded", "features.kept_despite_flags", "housekeeping"}


@pytest.fixture
def raw() -> dict:
    """The example config as a fresh raw dict, for one test to mutate."""
    return yaml.safe_load(EXAMPLE.read_text())


def _load(tmp_path: Path, raw: dict) -> UseCaseConfig:
    """Write a raw dict as YAML and load it through the public path."""
    path = tmp_path / "config.yml"
    path.write_text(yaml.safe_dump(raw))
    return load_config(path)


def _error(tmp_path: Path, raw: dict) -> str:
    """The validation error message a raw dict produces."""
    with pytest.raises(ValidationError) as info:
        _load(tmp_path, raw)
    return str(info.value)


def test_example_loads_with_level_defaults_and_explicit_values() -> None:
    """Null level fields take the assisted defaults; explicit values stay."""
    cfg = load_config(EXAMPLE)
    assert cfg.eda.key_features.top_n == 20
    assert cfg.training.max_iter == 200
    assert cfg.evaluation.slices.top_pct == [0.01, 0.10]  # explicit, not the level's list
    assert cfg.training.calibration.method == "platt"
    assert cfg.features.excluded == []
    assert cfg.housekeeping == {"level_filled": ["eda.key_features.top_n", "training.max_iter"]}


def test_autonomous_level_gives_its_own_defaults(tmp_path: Path, raw: dict) -> None:
    """The same file at the autonomous level, without its `evaluation` and `training` sections,
    resolves the smaller budgets."""
    raw["automation_level"] = "autonomous"
    del raw["evaluation"], raw["training"]  # every training field defaults or is level-filled
    cfg = _load(tmp_path, raw)
    assert (cfg.eda.key_features.top_n, cfg.training.max_iter) == (10, 50)
    assert cfg.training.calibration.method == "platt"
    assert cfg.evaluation.slices.top_pct == [0.01, 0.1]
    assert cfg.housekeeping["level_filled"] == list(LEVEL_DEFAULTS)


def test_levels_match_the_schema_and_a_bad_level_fails_before_validation(raw: dict) -> None:
    """`LEVELS` is the schema's Literal; a missing or retired level stops the level fill loud."""
    assert set(LEVELS) == set(get_args(UseCaseConfig.model_fields["automation_level"].annotation))
    for level in ("standard", None):
        raw["automation_level"] = level
        with pytest.raises(ValueError, match=f"automation_level must be one of .*got {level!r}"):
            apply_level_defaults(raw)


def test_a_set_on_a_section_unmarks_the_level_paths_under_it_only() -> None:
    """A section path takes its level paths off the list; a mere name prefix does not."""
    raw = {"housekeeping": {"level_filled": ["eda.key_features.top_n", "training.max_iter"]}}
    assert unmark_level_filled(raw, "eda.key")["housekeeping"]["level_filled"] == [
        "eda.key_features.top_n",
        "training.max_iter",
    ]
    assert unmark_level_filled(raw, "eda.key_features")["housekeeping"]["level_filled"] == [
        "training.max_iter"
    ]


def test_filled_template_loads(tmp_path: Path) -> None:
    """The template loads once every placeholder is replaced."""
    text = TEMPLATE.read_text()
    for placeholder, value in PLACEHOLDERS.items():
        text = text.replace(placeholder, value)
    assert not re.search(r"<[a-z_]+>", text), "a placeholder is missing from PLACEHOLDERS"
    path = tmp_path / "filled.yml"
    path.write_text(text)
    cfg = load_config(path)
    assert cfg.use_case == "cc_acquisition"
    assert cfg.housekeeping["level_filled"] == list(LEVEL_DEFAULTS)  # the template leaves them all


def _section(field: FieldInfo) -> type[BaseModel] | None:
    """The section model a field holds (`Sampling | None`, `dict[str, Entity]`, also the item of
    `list[CheckStep]`, though lists are compared whole), else None."""
    for arg in (field.annotation, *get_args(field.annotation)):
        if isinstance(arg, type) and issubclass(arg, BaseModel):
            return arg
    return None


def _says_required(name: str, text: str) -> bool:
    """Whether a template line of key `name` carries `# required`."""
    return re.search(rf"^\s*{name}:.*# required", text, re.MULTILINE) is not None


def _level_problem(path: str, value: object, text: str) -> str | None:
    """A level path is null, and its own line names both levels' values."""
    levels, name = LEVEL_DEFAULTS[path], path.rsplit(".", 1)[-1]
    named = f"autonomous {levels['autonomous']} · assisted {levels['assisted']}"
    if value is None and re.search(rf"\b{name}: null\b.*{re.escape(named)}", text):
        return None
    return f"{path}: must be null with `{named}` in its line's comment"


def _template_problems(model: type[BaseModel], node: dict, prefix: str, text: str) -> list[str]:
    """`model`'s fields against the template's `node`: each is present; a required one not filled
    by the level says `# required` (a placeholder value marks itself); a level path is null with
    both values named; any other optional value is the schema default."""
    problems = []
    for name, field in model.model_fields.items():
        path, section, value = prefix + name, _section(field), node.get(name)
        if path in REPLAY_ONLY:
            continue
        if name not in node:
            problems.append(f"{path}: not in the template")
            continue
        by_level = any(key == path or key.startswith(f"{path}.") for key in LEVEL_DEFAULTS)
        placeholder = section is None and "<" in str(value)
        if field.is_required() and not (by_level or placeholder or _says_required(name, text)):
            problems.append(f"{path}: required, its line needs `# required`")
        if section is not None and get_origin(field.annotation) is dict:
            for key, item in value.items():
                problems += _template_problems(section, item, f"{path}.{key}.", text)
        elif section is not None and isinstance(value, dict):
            problems += _template_problems(section, value, f"{path}.", text)
        elif path in LEVEL_DEFAULTS:
            problems += [problem for problem in [_level_problem(path, value, text)] if problem]
        elif not field.is_required():
            default = field.get_default(call_default_factory=True)
            default = TypeAdapter(field.annotation).dump_python(default, mode="json")
            if value != default:
                problems.append(f"{path}: the template shows {value!r}, the default is {default!r}")
    return problems


def test_template_shows_every_field_with_its_default() -> None:
    """Every schema field is in the template, and the template's header key holds line by line,
    so an omitted value's default is always on display."""
    text = TEMPLATE.read_text()
    assert _template_problems(UseCaseConfig, yaml.safe_load(text), "", text) == []


def test_unknown_key_fails_naming_it(tmp_path: Path, raw: dict) -> None:
    """A leftover or misspelt key is refused by name, at any depth."""
    raw["profile"] = "standard"
    raw["training"]["max_iters"] = 10
    message = _error(tmp_path, raw)
    assert "profile" in message and "max_iters" in message


def test_window_first_after_last_refused(tmp_path: Path, raw: dict) -> None:
    """The observation window's first month must not be after its last."""
    raw["time"]["train_months"]["first"] = date(2025, 9, 1)
    assert "is after last" in _error(tmp_path, raw)


def test_validation_month_inside_target_window_refused(tmp_path: Path, raw: dict) -> None:
    """v >= tk + w: 2025-10 is two months after 2025-08 with w = 3."""
    raw["time"]["validation_month"] = date(2025, 10, 1)
    assert "at least target_window_months" in _error(tmp_path, raw)


def test_validation_month_exactly_at_window_end_accepted(tmp_path: Path, raw: dict) -> None:
    """v = tk + w is the earliest allowed validation month."""
    raw["time"]["validation_month"] = date(2025, 11, 1)
    raw["time"]["target_window_months"] = 3
    assert _load(tmp_path, raw).time.validation_month == date(2025, 11, 30)


def test_mid_month_date_refused(tmp_path: Path, raw: dict) -> None:
    """A month is written as its first or its last day; any other day is a likely typo."""
    raw["time"]["validation_month"] = date(2025, 11, 15)
    assert "first or the last day of a month, e.g. 2025-11-30" in _error(tmp_path, raw)


def test_first_or_last_day_name_the_same_month(tmp_path: Path, raw: dict) -> None:
    """Both spellings of a month load as its last day, the framework's one convention, so they
    give the same config and the same hashes."""
    first_days = _load(tmp_path, raw)
    raw["time"]["train_months"] = {"first": date(2025, 3, 31), "last": date(2025, 8, 31)}
    raw["time"]["validation_month"] = date(2025, 11, 30)
    assert _load(tmp_path, raw) == first_days
    assert first_days.time.train_months.first == date(2025, 3, 31)


def test_target_window_below_one_refused(tmp_path: Path, raw: dict) -> None:
    """w >= 1: the target window never includes the observation month."""
    raw["time"]["target_window_months"] = 0
    assert "target_window_months" in _error(tmp_path, raw)


@pytest.mark.parametrize(
    ("name", "product", "activity"),
    [("cc_acquisition", "cc", "acquisition"), ("fx_card_activation", "fx_card", "activation")],
)
def test_use_case_splits_into_product_and_activity(
    tmp_path: Path, raw: dict, name: str, product: str, activity: str
) -> None:
    """The last token is the activity, everything before it the product (D-128)."""
    raw["use_case"] = name
    cfg = _load(tmp_path, raw)
    assert (cfg.product, cfg.activity) == (product, activity)


def test_single_token_use_case_refused(tmp_path: Path, raw: dict) -> None:
    """A name without an activity token fails at load."""
    raw["use_case"] = "single"
    assert "<product>_<activity>" in _error(tmp_path, raw)


def test_top_n_decision_needs_n(tmp_path: Path, raw: dict) -> None:
    """A top-N decision without a list size is refused."""
    raw["decision"]["type"] = "top_n"
    assert "decision.n" in _error(tmp_path, raw)


def test_metric_must_be_a_flaml_name(tmp_path: Path, raw: dict) -> None:
    """scikit-learn's 'average_precision' is FLAML's 'ap' (T9)."""
    raw["decision"]["metric"] = "average_precision"
    assert "not a FLAML metric name" in _error(tmp_path, raw)
    raw["decision"]["metric"] = "ap"
    assert _load(tmp_path, raw).decision.metric == "ap"


def test_eligibility_step_needs_exactly_one_of_define_and_filter(tmp_path: Path, raw: dict) -> None:
    """A step with both, or neither, is refused by name."""
    raw["data"]["eligibility"][0] = {"name": "both", "define": "a", "filter": "b", "reason": "r"}
    assert "both" in _error(tmp_path, raw) and "exactly one" in _error(tmp_path, raw)
    raw["data"]["eligibility"][0] = {"name": "neither"}
    assert "exactly one" in _error(tmp_path, raw)


def test_eligibility_filter_needs_a_reason(tmp_path: Path, raw: dict) -> None:
    """A filter removes rows, so it says why."""
    del raw["data"]["eligibility"][1]["reason"]
    assert "needs a reason" in _error(tmp_path, raw)


def test_eligibility_filter_needs_before(tmp_path: Path, raw: dict) -> None:
    """A filter says whether its rows go before EDA or before modelling; the message explains."""
    del raw["data"]["eligibility"][1]["before"]
    message = _error(tmp_path, raw)
    assert "filter 'non_holders' needs `before`" in message
    assert "tagged by the step's name" in message


def test_eligibility_define_takes_no_before(tmp_path: Path, raw: dict) -> None:
    """A define names a condition and drops nothing."""
    raw["data"]["eligibility"][0]["before"] = "eda"
    assert "define 'has_income' takes no `before`" in _error(tmp_path, raw)


def test_eligibility_names_unique(tmp_path: Path, raw: dict) -> None:
    """Two steps with the same name would make the log ambiguous."""
    raw["data"]["eligibility"].append(copy.deepcopy(raw["data"]["eligibility"][1]))
    assert "non_holders" in _error(tmp_path, raw)


def test_upstream_target_is_column_without_rule(tmp_path: Path, raw: dict) -> None:
    """An upstream target gives only the column, optionally with its lineage; leaver and null
    handling belong to a built target."""
    raw["data"]["target"] = {"column": "cc_target", "lineage": ["cc_flag"]}
    target = _load(tmp_path, raw).data.target
    assert target.rule is None and target.lineage == ["cc_flag"]
    raw["data"]["target"]["leavers"] = "negative"
    assert "`leavers` applies to a built target" in _error(tmp_path, raw)
    raw["data"]["target"] = {"column": "cc_target", "null_as": 0}
    assert "`null_as` applies to a built target" in _error(tmp_path, raw)


def test_sampling_parameter_must_match_method(tmp_path: Path, raw: dict) -> None:
    """negative_downsampling takes keep_fraction, client_sample takes share, never the other."""
    raw["training"]["sampling"] = {"method": "negative_downsampling", "share": 0.3}
    assert "takes keep_fraction only" in _error(tmp_path, raw)
    raw["training"]["sampling"] = {"method": "client_sample", "keep_fraction": 0.1}
    assert "takes share only" in _error(tmp_path, raw)
    raw["training"]["sampling"] = {"method": "client_sample", "share": 1.0}
    assert "share" in _error(tmp_path, raw)
    raw["training"]["sampling"] = {"method": "negative_downsampling", "keep_fraction": 0.1}
    assert _load(tmp_path, raw).training.sampling.seed == 42


def test_forest_estimator_refused(tmp_path: Path, raw: dict) -> None:
    """The scikit-learn forests are never in the list (D-037); the message names the entry."""
    raw["training"]["estimator_list"] = ["lgbm", "rf"]
    message = _error(tmp_path, raw)
    assert "training.estimator_list.1" in message and "Input should be 'lgbm'" in message
    raw["training"]["estimator_list"] = []
    assert "estimator_list" in _error(tmp_path, raw)


def test_slice_entries_are_checked_one_by_one(tmp_path: Path, raw: dict) -> None:
    """A share outside (0, 1] or a count below 1 is refused naming its position."""
    raw["evaluation"]["slices"] = {"top_pct": [0.01, 1.5], "top_n": [0]}
    message = _error(tmp_path, raw)
    assert "evaluation.slices.top_pct.1" in message and "evaluation.slices.top_n.0" in message


def test_future_schema_version_refused(tmp_path: Path, raw: dict) -> None:
    """A config from a newer framework stops the load before validation."""
    raw["schema_version"] = 99
    with pytest.raises(ValueError, match="newer than this framework"):
        _load(tmp_path, raw)
    del raw["schema_version"]
    with pytest.raises(ValueError, match="integer schema_version"):
        _load(tmp_path, raw)


def test_old_schema_version_migrates_with_a_warning(
    tmp_path: Path, raw: dict, monkeypatch: pytest.MonkeyPatch
) -> None:
    """A version-0 file loads through its migration and warns; without one it fails naming it."""
    raw["schema_version"] = 0
    raw["training"]["selection"] = {"auc_floor": 0.6}  # the old name a migration would rename

    def rename_floor(old: dict) -> dict:
        """The dummy 0 → 1 migration."""
        old["training"]["selection"] = {
            "univariate_floor": old["training"]["selection"]["auc_floor"]
        }
        return {**old, "schema_version": 1}

    with pytest.raises(ValueError, match="no migration from config schema_version 0"):
        _load(tmp_path, raw)
    monkeypatch.setitem(MIGRATIONS, 0, rename_floor)
    with pytest.warns(DeprecationWarning, match="config schema_version 0 is deprecated"):
        cfg = _load(tmp_path, raw)
    assert cfg.training.selection.univariate_floor == 0.6


def test_file_with_replay_fields_refused(tmp_path: Path, raw: dict) -> None:
    """The replayed lists and housekeeping come from the audit log, never from the file (D-125)."""
    for field, text in (
        ("excluded", "record an exclude entry"),
        ("kept_despite_flags", "record a keep_despite_flag entry"),
    ):
        raw["features"][field] = ["cc_flag"]
        with pytest.raises(
            ValueError, match=f"features.{field} is written by the audit log.*{text}"
        ):
            _load(tmp_path, raw)
        raw["features"][field] = []
    raw["housekeeping"] = {"framework_version": "0.1.0"}
    with pytest.raises(ValueError, match="housekeeping is written by resolve_config"):
        _load(tmp_path, raw)


def test_missing_entities_refused(tmp_path: Path, raw: dict) -> None:
    """A use case lists at least one entity (D-034)."""
    raw["entities"] = {}
    assert "entities" in _error(tmp_path, raw)
