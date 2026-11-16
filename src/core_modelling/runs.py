"""The runs of a use case (D-139): the numbered run folder, its identity record and the sign-off.

A run is one Training call and its Evaluation, in `<use_case>/06_models/r007/`. `create_run`
reserves the next number by creating that folder exclusively and writes `run.json` once: what the
run was built from (`model_bundle.md` → `run.json`), taken from the resolved config and the
environment. `next_run_id` counts the folders and every run the use case's audit logs name, so
a number an entry names is never given again, also after its folder is deleted; a crashed run
that wrote no entry and whose folder was deleted leaves no trace. Evaluation
finds its run with `find_run`; a person reads `list_runs` and `show_run`, which print what the
files hold (`run.json`, each stage json's flat `summary`, the audit log) and compute nothing of
their own, and records the feature sign-off with `sign_off`, which names the list it hashes.
Local paths only until the HDFS transport (M2.4, D-136).
"""

import getpass
import json
import re
from pathlib import Path

import pandas as pd

from core_modelling import __version__
from core_modelling.artifacts import (
    HOUSEKEEPING_KEYS,
    local_path,
    stage_identity,
    stage_json,
    utc_now,
    write_json,
)
from core_modelling.config.audit_log import read_entries, record_sign_off
from core_modelling.config.identities import (
    HASH_VERSION,
    data_definition_hash,
    feature_signature,
    short,
)
from core_modelling.config.replay import RUN_NUMBER, Entry, check_resolved, signed_off
from core_modelling.config.schema import UseCaseConfig
from core_modelling.environment import EnvironmentConfig, data_path, models_dir

RUN_SCHEMA_VERSION = 1
RUN_KEYS = ("run_schema_version", "run_id", "use_case", "entity", "started_at", "started_by",
            "config_hash", "data_definition_hash", "resolved_input_hash", "replayed_to",
            "hash_version", "training_settings_digest", "training_settings", "stage2",
            "sources_digest", "framework_version")  # fmt: skip
STAGE2_KEYS = {"eda", "feature_checks"}  # the Stage 2 runs a run was trained against
CREATE_ATTEMPTS = 5
CRASHED = "no run.json: the run crashed before it was written; inspect or remove the folder"
FIXED_COLUMNS = ["run", "started_at", "started_by", "data_definition"]
STATE_COLUMNS = ["trained", "evaluated", "signed_off"]


def _canonical_run(text: str) -> str:
    """A run number as typed (`r7`, `7`, `R007`) in its canonical form, `r007`; anything else
    fails."""
    match = re.fullmatch(r"[rR]?(\d+)", str(text).strip())
    if match is None or int(match.group(1)) == 0:
        raise ValueError(f"{text!r} is not a run number: write it as r007 (or r7, or 7)")
    return f"r{int(match.group(1)):03d}"


def next_run_id(folder: str, entries: list[Entry]) -> str:
    """One above the highest run number among the names under the models `folder` (any case,
    since `R003` and `r003` are one folder on a case-insensitive file system) and the runs the
    `entries` name (Training's and Evaluation's `run` entries, `sign_off`s); `r001` when there
    is none."""
    path = local_path(folder)
    names = [item.name.lower() for item in path.iterdir()] if path.is_dir() else []
    numbers = [int(name[1:]) for name in names if re.fullmatch(RUN_NUMBER, name)]
    numbers += [int(entry.run_id[1:]) for entry in entries if entry.run_id]
    return f"r{max(numbers, default=0) + 1:03d}"


def _use_case_entries(env: EnvironmentConfig, cfg: UseCaseConfig) -> list[Entry]:
    """The entries of every audit log of the use case, one per data definition
    (`04_feature/<ddh>/decisions`): run numbers are per use case, across data definitions."""
    feature = local_path(data_path(env, cfg.use_case, "04_feature"))
    logs = sorted(feature.glob("*/decisions")) if feature.is_dir() else []
    return [entry for log in logs for entry in read_entries(str(log))]


def _check_entity(resolved: UseCaseConfig, entity: str, what: str) -> None:
    """Refuse a resolved config of another entity than `entity`."""
    if resolved.housekeeping["entity"] != entity:
        raise ValueError(
            f"{what}: the config was resolved for entity {resolved.housekeeping['entity']!r}, "
            f"not {entity!r}: resolve it for {entity!r}"
        )


def _run_record(env: EnvironmentConfig, resolved: UseCaseConfig, stage2: dict[str, str]) -> dict:
    """`run.json`'s content but the run number: the resolved config's identity, Training's
    settings digest and values, the sources digest (as `stage_identity` computes them), the
    Stage 2 run tokens, who and when."""
    if set(stage2) != STAGE2_KEYS:
        raise ValueError(
            f"create_run: stage2 holds {sorted(stage2)}; it names exactly the run tokens of "
            f"{sorted(STAGE2_KEYS)} the run is trained against"
        )
    identity = stage_identity(resolved, "training", env)
    return {
        "run_schema_version": RUN_SCHEMA_VERSION,
        "use_case": resolved.use_case,
        "started_at": utc_now(),
        "started_by": getpass.getuser(),
        **{key: identity[key] for key in HOUSEKEEPING_KEYS},
        "training_settings_digest": identity["settings_digest"],
        "training_settings": identity["settings"],
        "stage2": stage2,
        "sources_digest": identity["sources_digest"],
        "framework_version": __version__,
    }


def create_run(
    env: EnvironmentConfig, resolved: UseCaseConfig, entity: str, stage2: dict[str, str]
) -> str:
    """Reserve the next run number and write its `run.json` once; returns the number. The folder
    is created exclusively: when another run took the number meanwhile, the next one is taken,
    so nothing is ever written into an existing run folder; after `CREATE_ATTEMPTS` clashes it
    fails."""
    check_resolved(resolved, "create_run")
    _check_entity(resolved, entity, "create_run")
    record = _run_record(env, resolved, stage2)
    models = local_path(models_dir(env, resolved))
    models.mkdir(parents=True, exist_ok=True)
    entries = _use_case_entries(env, resolved)
    for _ in range(CREATE_ATTEMPTS):
        run = next_run_id(str(models), entries)
        try:
            (models / run).mkdir()
        except FileExistsError:  # taken between the count and the create: count again
            continue
        record["run_id"] = run
        write_json({key: record[key] for key in RUN_KEYS}, models / run / "run.json",
                   exclusive=True)  # fmt: skip
        return run
    raise RuntimeError(
        f"create_run: {CREATE_ATTEMPTS} run numbers in a row were taken under {models}; look "
        "for a folder whose name differs only in case or form from a run number"
    )


def _read_json(path: Path) -> dict:
    """A run's json file as stored, or {} when it is not there; a truncated one fails naming it."""
    if not path.is_file():
        return {}
    try:
        return json.loads(path.read_text())
    except ValueError as err:
        raise ValueError(
            f"{path} is not valid JSON ({err}): inspect or remove the run folder {path.parent}"
        ) from err


def _summary(folder: Path, stage: str) -> dict:
    """A stage json's flat `summary` block in a run folder, {} when the stage has not run; a
    truncated stage json fails naming it."""
    try:
        return stage_json(folder, stage).get("summary", {})
    except ValueError as err:
        raise ValueError(
            f"{folder / stage / f'{stage}.json'} is not valid JSON ({err}): inspect or remove "
            f"the run folder {folder}"
        ) from err


def read_run(env: EnvironmentConfig, cfg: UseCaseConfig, run: str) -> dict:
    """A run's `run.json`; a missing run or `run.json`, or another `run_schema_version`, fails
    naming the fix."""
    run = _canonical_run(run)
    folder = local_path(models_dir(env, cfg, run))
    if not folder.is_dir():
        raise FileNotFoundError(f"no run {run} at {folder}: list the runs with list_runs (runs)")
    record = _read_json(folder / "run.json")
    if not record:
        raise FileNotFoundError(f"run {run} at {folder}: {CRASHED}")
    version = record.get("run_schema_version")
    if version != RUN_SCHEMA_VERSION:
        raise ValueError(
            f"{folder / 'run.json'} has run_schema_version {version}; this version reads "
            f"{RUN_SCHEMA_VERSION}: train a new run, or raise the use case's framework pin "
            "when it is newer"
        )
    return record


def _is_trained(folder: Path) -> bool:
    """Whether a run folder holds Training's commit marker, `training/training.json`."""
    return (folder / "training" / "training.json").is_file()


def _run_folders(env: EnvironmentConfig, cfg: UseCaseConfig) -> list[Path]:
    """The run folders under `06_models/`, newest (highest number) first."""
    models = local_path(models_dir(env, cfg))
    names = [p for p in models.iterdir() if p.is_dir()] if models.is_dir() else []
    folders = [p for p in names if re.fullmatch(RUN_NUMBER, p.name)]
    return sorted(folders, key=lambda p: int(p.name[1:]), reverse=True)


def _mismatch(folder: Path, current: dict) -> list[str]:
    """Why a run folder is not the one Evaluation takes, against `current` (the resolved
    config's `stage_identity` for Training): no `run.json` (a crash), another
    `run_schema_version`, another data definition, other Training settings, sources now mapped
    elsewhere, or not trained; [] when it is."""
    record = _read_json(folder / "run.json")
    if not record:
        return [CRASHED]
    if record["run_schema_version"] != RUN_SCHEMA_VERSION:
        return [f"run_schema_version {record['run_schema_version']}"]
    why = []
    if record["data_definition_hash"] != current["data_definition_hash"]:
        why.append(f"data definition {short(record['data_definition_hash'])}")
    if record["training_settings_digest"] != current["settings_digest"]:
        why.append("other training settings")
    if record["sources_digest"] != current["sources_digest"]:
        why.append("trained from sources the environment now maps elsewhere")
    if not _is_trained(folder):
        why.append("not trained (no training/)")
    return why


def find_run(
    env: EnvironmentConfig, resolved: UseCaseConfig, entity: str, run: str | None = None
) -> str:
    """The run Evaluation reads (D-139 (d)): by default the latest trained run of the resolved
    config's data definition, Training settings digest and sources; a named `run` must be of the
    same data definition, client split and sources, and trained. Never another run in its place:
    a refusal says why."""
    check_resolved(resolved, "find_run")
    _check_entity(resolved, entity, "find_run")
    current = stage_identity(resolved, "training", env)
    if run is not None:
        return _check_named_run(env, resolved, _canonical_run(run), current)
    nearest = []
    for folder in _run_folders(env, resolved):
        why = _mismatch(folder, current)
        if not why:
            return folder.name
        nearest.append(f"{folder.name}: {', '.join(why)}")
    raise ValueError(
        f"no trained run of data definition {short(current['data_definition_hash'])} with the "
        f"current training settings and sources under {models_dir(env, resolved)}; the latest "
        f"runs: {nearest[:3] or 'none'}. Run Training first"
    )


def _check_named_run(
    env: EnvironmentConfig, resolved: UseCaseConfig, run: str, current: dict
) -> str:
    """The named run when it is of the data definition, client split and sources of `current`
    (the resolved config's `stage_identity` for Training) and trained; refused otherwise."""
    record = read_run(env, resolved, run)
    ddh = current["data_definition_hash"]
    if record["data_definition_hash"] != ddh:
        raise ValueError(
            f"run {run} was trained for data definition {short(record['data_definition_hash'])}, "
            f"the config's is {short(ddh)}: name a run of this data definition (list_runs)"
        )
    split = record["training_settings"].get("data.split", "(not recorded)")
    if split != current["settings"]["data.split"]:
        raise ValueError(
            f"run {run} was trained with the client split {split!r}, the config's is "
            f"{current['settings']['data.split']!r}: Evaluation would score it on its own train "
            "clients; train again with this config"
        )
    if record["sources_digest"] != current["sources_digest"]:
        raise ValueError(
            f"run {run} was trained from sources the environment now maps elsewhere (other "
            "data under the same data definition): train again on the current sources"
        )
    folder = local_path(models_dir(env, resolved, run))
    if not _is_trained(folder):
        raise ValueError(f"run {run} is incomplete: {folder} has no training/; train a new run")
    return run


def _signed_features(folder: Path) -> tuple[str, list[str]]:
    """A trained run's feature signature, computed from `bundle/bundle.json`'s final list, and
    the list; a manifest whose `feature_signature` is missing or differs fails loud."""
    bundle = folder / "bundle"
    features = _read_json(bundle / "bundle.json").get("features")
    manifest = _read_json(bundle / "manifest.json")
    recorded = manifest.get("feature_signature")
    if not features or recorded is None:
        raise ValueError(
            f"{bundle} lacks bundle.json's features or the manifest's feature_signature: the run "
            "is not a complete trained run; train a new run"
        )
    if manifest.get("hash_version") != HASH_VERSION:
        raise ValueError(
            f"{bundle}: the manifest's feature_signature was computed under hash_version "
            f"{manifest.get('hash_version')}, this version computes {HASH_VERSION}: train a new "
            "run, or use the framework version that trained it"
        )
    signature = feature_signature(features)
    if recorded != signature:
        raise ValueError(
            f"{bundle}: the manifest's feature_signature {short(recorded)} is not the signature "
            f"of bundle.json's features ({short(signature)}): the bundle was changed; train a "
            "new run"
        )
    return signature, features


def _signing_entry(env: EnvironmentConfig, cfg: UseCaseConfig, folder: Path) -> Entry | None:
    """The effective `sign_off` entry covering a trained run's feature signature, read from the
    audit log of the run's own data definition; None for an incomplete or unsigned run."""
    if not _is_trained(folder):
        return None
    signature, _ = _signed_features(folder)
    ddh = _read_json(folder / "run.json")["data_definition_hash"]
    log = data_path(env, cfg.use_case, "04_feature", short(ddh), "decisions")
    return signed_off(read_entries(log), signature)


def _summary_columns(training: dict, evaluation: dict) -> dict:
    """The two stages' `summary` blocks as one row's columns, a key prefixed with its stage only
    when both blocks hold it or it is a fixed column."""
    taken = (set(training) & set(evaluation)) | set(FIXED_COLUMNS + STATE_COLUMNS)
    return {
        (f"{stage}_{key}" if key in taken else key): value
        for stage, block in (("training", training), ("evaluation", evaluation))
        for key, value in block.items()
    }


def _list_row(
    env: EnvironmentConfig, cfg: UseCaseConfig, folder: Path, record: dict | None
) -> dict:
    """One run folder's row of `list_runs` from its `run.json` (`record`); a folder without one
    (a crash, `record` None) has blank identity columns and false states."""
    if record is None:
        blank = dict.fromkeys(FIXED_COLUMNS[1:], "")
        return {"run": folder.name, **blank, **dict.fromkeys(STATE_COLUMNS, False)}
    return {"run": folder.name, "started_at": record["started_at"],
            "started_by": record["started_by"],
            "data_definition": short(record["data_definition_hash"]),
            **_summary_columns(_summary(folder, "training"), _summary(folder, "evaluation")),
            "trained": _is_trained(folder),
            "evaluated": (folder / "evaluation" / "evaluation.json").is_file(),
            "signed_off": _signing_entry(env, cfg, folder) is not None}  # fmt: skip


def list_runs(env: EnvironmentConfig, cfg: UseCaseConfig, entity: str) -> pd.DataFrame:
    """The use case's runs on `entity`, one row per run folder, newest first: `FIXED_COLUMNS`,
    every key of Training's and Evaluation's `summary`, then `STATE_COLUMNS`. A folder without
    `training/` is an incomplete run, its states false; a folder without `run.json` (a crash
    before it was written) is listed for every entity."""
    rows = []
    for folder in _run_folders(env, cfg):
        has_record = (folder / "run.json").is_file()
        record = read_run(env, cfg, folder.name) if has_record else None
        if record is None or record["entity"] == entity:
            rows.append(_list_row(env, cfg, folder, record))
    table = pd.DataFrame(rows, columns=None if rows else FIXED_COLUMNS + STATE_COLUMNS)
    middle = [column for column in table.columns if column not in FIXED_COLUMNS + STATE_COLUMNS]
    return table[FIXED_COLUMNS + middle + STATE_COLUMNS]


def _lines(block: dict) -> list[str]:
    """One indented `key: value` line per key, a list or mapping as compact JSON."""
    return [
        f"  {key}: {json.dumps(value) if isinstance(value, dict | list) else value}"
        for key, value in block.items()
    ]


def _stage_lines(folder: Path, stage: str, done: bool, missing: str) -> list[str]:
    """A stage json's `summary` block as lines, or one line saying the stage has not written it."""
    if not done:
        return [f"  {missing}"]
    return _lines(_summary(folder, stage)) or [f"  {stage}/{stage}.json holds no summary"]


def show_run(env: EnvironmentConfig, cfg: UseCaseConfig, entity: str, run: str) -> str:
    """A run's record as a short page of plain text: what went in, what Training did, what
    Evaluation found, the three states with the signing entry, where the files are. It prints
    what the files hold and computes nothing."""
    run = _canonical_run(run)
    record = read_run(env, cfg, run)
    if record["entity"] != entity:
        raise ValueError(f"run {run} was trained on entity {record['entity']!r}, not {entity!r}")
    folder = local_path(models_dir(env, cfg, run))
    trained = _is_trained(folder)
    evaluated = (folder / "evaluation" / "evaluation.json").is_file()
    entry = _signing_entry(env, cfg, folder)
    signing = (
        f"yes, entry {entry.seq} by {entry.by.id} at {entry.time}, signing {entry.run_id}: "
        f"{entry.reason}"
        if entry
        else "no"
    )
    return "\n".join([
        f"Run {run} of {record['use_case']} on {entity}", "", "What went in", *_lines(record),
        "", "What Training did",
        *_stage_lines(folder, "training", trained, "not trained (incomplete)"),
        "", "What Evaluation found",
        *_stage_lines(folder, "evaluation", evaluated, "not evaluated"),
        "", "States", f"  trained: {trained}", f"  evaluated: {evaluated}",
        f"  signed off: {signing}", "", "Files", f"  {folder}",
        *[f"  {p.name}{'/' if p.is_dir() else ''}" for p in sorted(folder.iterdir())],
    ])  # fmt: skip


def sign_off(
    cfg: UseCaseConfig, entity: str, env: EnvironmentConfig, run: str, reason: str
) -> Entry:
    """Record a person's feature sign-off for a trained run (D-031): the final list of
    `bundle/bundle.json` and its signature, which the manifest must record, with the reason. It
    covers every run of the same data definition with the same signature (D-125 (c)). A person
    signs off, never an LLM (`CLAUDE.md` §4.13). A run that is incomplete or of another data
    definition is refused."""
    run = _canonical_run(run)
    record = read_run(env, cfg, run)
    expected = data_definition_hash(cfg, entity)
    if record["data_definition_hash"] != expected:
        raise ValueError(
            f"sign-off refused: run {run} was trained for data definition "
            f"{short(record['data_definition_hash'])}, the config on {entity!r} defines "
            f"{short(expected)}"
        )
    folder = local_path(models_dir(env, cfg, run))
    if not _is_trained(folder):
        raise ValueError(f"sign-off refused: run {run} is incomplete ({folder} has no training/)")
    signature, features = _signed_features(folder)
    return record_sign_off(cfg, entity, env, run_id=run, signature=signature, features=features,
                           reason=reason)  # fmt: skip
