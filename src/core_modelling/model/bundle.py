"""The model bundle: a trained model as plain data, three files under one `model_hash` (D-051).

`write_bundle` checks everything it is given first, so a refused content leaves nothing on
disk; it then saves the model in its family's native format and writes `bundle.json` (the task,
the features, the encoder, the calibration, the recipe) and `manifest.json` (the hashes with
their `hash_version`, the run, the time). `model_hash` is one SHA-256 over the model file and
`bundle.json` in name order, each file's bytes preceded by its name and byte length, so bytes
moved from one file to the other cannot keep the hash. `bundle.json` holds no time, run or person
and is written in one fixed layout, so the same model always has the same hash. `build_bundle`
recomputes the hash on the bytes it is given before it parses `bundle.json`, and the model is
built from those same bytes: a changed file never scores. `load_bundle` is `build_bundle` on a
folder's files; `score_spark` ships those bytes to each partition, never a path, so an executor
writes nothing. The keys and the hashes are `docs/components/model_bundle.md`'s; the recipe hash
and the feature signature are the identities' (`config/identities.py`). Local paths only until
the HDFS transport (D-136).
"""

import hashlib
import json
import warnings
from dataclasses import dataclass
from importlib.metadata import version

from core_modelling import __version__
from core_modelling.artifacts import local_path, utc_now, write_json
from core_modelling.config.identities import HASH_VERSION, feature_signature, recipe_hash
from core_modelling.model.calibration import check_calibration
from core_modelling.model.encoder import check_encoder
from core_modelling.model.families import FAMILIES

BUNDLE_SCHEMA_VERSION = 1
MANIFEST_SCHEMA_VERSION = 1
BUNDLE_FILE = "bundle.json"
MANIFEST_FILE = "manifest.json"
OUTPUT_COLUMNS = ["margin", "score_raw", "score"]
CONTENT_KEYS = ("task", "features", "encoder", "calibration", "recipe")  # the caller's part
# What a retrain repeats; the seed and the tree count are among the `parameters`, and `split` is
# the config's `data.split`, so a retrain deals the same clients.
RECIPE_KEYS = ("task", "family", "parameters", "features", "encoder", "monotone", "calibration",
               "sampling", "split", "data_definition_hash")  # fmt: skip
RECIPE_CALIBRATION_KEYS = ("method", "folds")  # the spec only, never the fitted numbers
# A run setting, not part of the model: in the recipe it would give one model two hashes.
THREAD_PARAMS = ("n_jobs", "thread_count", "nthread", "num_threads")
IDENTITY_KEYS = ("run_id", "data_definition_hash", "config_hash", "resolved_input_hash")
MANIFEST_KEYS = ("manifest_schema_version", "files", "model_hash", "recipe_hash",
                 "feature_signature", "hash_version", *IDENTITY_KEYS, "framework_version",
                 "written_at")  # fmt: skip
LIBRARY_BY_FAMILY = {"lgbm": "lightgbm", "xgboost": "xgboost", "xgb_limitdepth": "xgboost",
                     "catboost": "catboost"}  # fmt: skip
MODEL_FILES = sorted({family.file_name for family in FAMILIES.values()})


@dataclass(frozen=True)
class Bundle:
    """A bundle verified and built: the model in memory and what scoring reads from
    `bundle.json` (`content` is the file as read)."""

    booster: object
    family: str
    task: str
    encoder: dict
    calibration: dict
    features: list[str]
    content: dict
    model_hash: str


def write_bundle(folder: str, family: str, booster: object, content: dict, identity: dict) -> str:
    """Write the bundle into `folder`, which must not exist yet, and return its `model_hash`.
    `content` holds exactly `CONTENT_KEYS` (its features the encoder's, in order, its recipe
    `RECIPE_KEYS`); `identity` exactly `IDENTITY_KEYS`, which go to the manifest only. Every
    check, and `bundle.json`'s bytes, come before the folder is made."""
    _check_content(family, content)
    _check_identity(identity)
    model_file, library = FAMILIES[family].file_name, LIBRARY_BY_FAMILY[family]
    bundle = {
        **content,
        "bundle_schema_version": BUNDLE_SCHEMA_VERSION,
        "family": family,
        "model_file": model_file,
        "output_columns": OUTPUT_COLUMNS,
        "library_version": {library: version(library)},
    }
    bundle_bytes = _bundle_bytes(bundle, folder)
    hashes = {"recipe_hash": recipe_hash(content["recipe"]),
              "feature_signature": feature_signature(content["features"]),
              "hash_version": HASH_VERSION}  # fmt: skip
    target = local_path(folder)
    if target.exists():
        raise FileExistsError(f"{folder} exists: a bundle is written once, into a new folder")
    target.mkdir(parents=True)
    FAMILIES[family].save(booster, str(target / model_file))
    (target / BUNDLE_FILE).write_bytes(bundle_bytes)
    names = sorted([BUNDLE_FILE, model_file])
    model_hash = _model_hash({name: (target / name).read_bytes() for name in names})
    manifest = {"manifest_schema_version": MANIFEST_SCHEMA_VERSION, "files": names,
                "model_hash": model_hash, **hashes, **{key: identity[key] for key in IDENTITY_KEYS},
                "framework_version": __version__, "written_at": utc_now()}  # fmt: skip
    write_json(manifest, target / MANIFEST_FILE, exclusive=True)
    return model_hash


def read_bundle_files(folder: str) -> dict[str, bytes]:
    """The bundle's three files as bytes by name: `manifest.json` and the two it lists, read
    once the manifest is checked (`_parse_manifest`)."""
    root = local_path(folder)
    if not (root / MANIFEST_FILE).is_file():
        raise FileNotFoundError(f"no model bundle at {folder}: {MANIFEST_FILE} is missing")
    data = (root / MANIFEST_FILE).read_bytes()
    names = _parse_manifest(data, folder)["files"]
    return {MANIFEST_FILE: data, **{name: (root / name).read_bytes() for name in names}}


def load_bundle(folder: str) -> Bundle:
    """The bundle in `folder`, verified and built from the bytes read (`build_bundle`)."""
    return build_bundle(read_bundle_files(folder), folder)


def build_bundle(files: dict[str, bytes], folder: str) -> Bundle:
    """The bundle from its three files' bytes (`read_bundle_files`; `folder` names their origin
    in messages only): `model_hash` recomputed over the two files before `bundle.json` is parsed
    and refused when it differs from the manifest's, another schema version refused naming the
    fix, another library version warned, and the model built from the verified bytes."""
    manifest = _parse_manifest(files[MANIFEST_FILE], folder)
    names = manifest["files"]
    model_hash = _model_hash({name: files[name] for name in names})
    if model_hash != manifest["model_hash"]:
        raise ValueError(
            f"{folder}: the files {names} hash to model_hash {model_hash}, the manifest records "
            f"{manifest['model_hash']}: a file changed after the bundle was written; never "
            "score it, restore the bundle or train again"
        )
    content = json.loads(files[BUNDLE_FILE])
    _check_version(content.get("bundle_schema_version"), BUNDLE_SCHEMA_VERSION,
                   f"{BUNDLE_FILE}'s bundle_schema_version", folder)  # fmt: skip
    if names[1] != content["model_file"] or content["family"] not in FAMILIES:
        raise ValueError(
            f"{folder}: {BUNDLE_FILE} names the family {content['family']!r} and the model "
            f"file {content['model_file']!r}; the manifest lists {names}"
        )
    check_encoder(content["encoder"])
    check_calibration(content["calibration"], content["task"])
    _warn_library_version(content["library_version"], folder)
    return Bundle(
        booster=FAMILIES[content["family"]].load(files[content["model_file"]]),
        family=content["family"],
        task=content["task"],
        encoder=content["encoder"],
        calibration=content["calibration"],
        features=content["features"],
        content=content,
        model_hash=model_hash,
    )


def _check_content(family: str, content: dict) -> None:
    """Fail loud on an unknown family, a content without exactly `CONTENT_KEYS` (anything else
    could carry a time, run or person into the hash), an encoder or a calibration this version
    cannot read, features that are not the encoder's, or a recipe `_check_recipe` refuses."""
    if family not in FAMILIES:
        raise ValueError(f"unknown family {family!r}; the families are {list(FAMILIES)}")
    if sorted(content) != sorted(CONTENT_KEYS):
        raise ValueError(
            f"the bundle content must hold exactly {list(CONTENT_KEYS)}: it lacks "
            f"{sorted(set(CONTENT_KEYS) - set(content))} and carries "
            f"{sorted(set(content) - set(CONTENT_KEYS))}; times, runs and people go to the "
            "manifest, and write_bundle adds the family, model file, output columns and "
            "library version itself"
        )
    check_encoder(content["encoder"])
    encoded = [entry["name"] for entry in content["encoder"]["features"]]
    if list(content["features"]) != encoded:
        raise ValueError(
            f"the bundle's features {content['features']} are not the encoder's {encoded}; "
            "they must be the same names in the same order"
        )
    check_calibration(content["calibration"], content["task"])
    _check_recipe(family, content)


def _check_recipe(family: str, content: dict) -> None:
    """Fail loud unless the recipe holds exactly `RECIPE_KEYS` (any other key would carry
    something run-specific into `recipe_hash` and `model_hash`) and describes this model: its
    task, family, features and encoder are the content's and `family`."""
    recipe = content["recipe"]
    if sorted(recipe) != sorted(RECIPE_KEYS):
        raise ValueError(
            f"the recipe must hold exactly {list(RECIPE_KEYS)}: it lacks "
            f"{sorted(set(RECIPE_KEYS) - set(recipe))} and carries "
            f"{sorted(set(recipe) - set(RECIPE_KEYS))}; the seed and the tree count go among "
            "the parameters"
        )
    own = {"task": content["task"], "family": family, "features": list(content["features"]),
           "encoder": content["encoder"]}  # fmt: skip
    differing = [key for key, value in own.items() if recipe[key] != value]
    if differing:
        raise ValueError(
            f"the recipe's {differing} differ from the bundle's own; a recipe describes the "
            "model it is saved with"
        )
    _check_recipe_parts(recipe)


def _check_recipe_parts(recipe: dict) -> None:
    """Fail loud on a run setting among the recipe's parameters (a thread count would give one
    model two hashes on two machines) or a recipe calibration other than its spec (`method` and
    `folds`, never fitted numbers, which a production retrain recomputes)."""
    threads = sorted(set(recipe["parameters"]) & set(THREAD_PARAMS))
    if threads:
        raise ValueError(
            f"the recipe's parameters hold the thread counts {threads}; a thread count is a "
            "run setting, not part of the model, so it stays out of the recipe"
        )
    if sorted(recipe["calibration"]) != sorted(RECIPE_CALIBRATION_KEYS):
        raise ValueError(
            f"the recipe's calibration holds {sorted(recipe['calibration'])}; it holds exactly "
            f"{list(RECIPE_CALIBRATION_KEYS)}, the spec, never the fitted numbers"
        )


def _check_identity(identity: dict) -> None:
    """Fail loud unless `identity` holds exactly the manifest's run keys, `IDENTITY_KEYS`."""
    if sorted(identity) != sorted(IDENTITY_KEYS):
        raise ValueError(
            f"the bundle identity must hold exactly {list(IDENTITY_KEYS)}; it holds "
            f"{sorted(identity)}"
        )


def _parse_manifest(data: bytes, folder: str) -> dict:
    """The manifest from its bytes, after checking its version, that it holds exactly
    `MANIFEST_KEYS`, its `hash_version`, and that it lists `bundle.json` and one model file by
    plain name."""
    manifest = json.loads(data)
    _check_version(manifest.get("manifest_schema_version"), MANIFEST_SCHEMA_VERSION,
                   f"{MANIFEST_FILE}'s manifest_schema_version", folder)  # fmt: skip
    if sorted(manifest) != sorted(MANIFEST_KEYS):
        raise ValueError(
            f"{folder}: {MANIFEST_FILE} holds the keys {sorted(manifest)}; a manifest of "
            f"version {MANIFEST_SCHEMA_VERSION} holds {list(MANIFEST_KEYS)}"
        )
    # Before any hash is compared, so a later bump is never read as "a file changed".
    _check_version(manifest["hash_version"], HASH_VERSION, f"{MANIFEST_FILE}'s hash_version",
                   folder)  # fmt: skip
    names = manifest["files"]
    if not (isinstance(names, list) and len(names) == 2 and names[0] == BUNDLE_FILE
            and names[1] in MODEL_FILES):  # fmt: skip
        raise ValueError(
            f"{folder}: {MANIFEST_FILE} lists the files {names}; a bundle holds {BUNDLE_FILE} "
            f"and one model file of {MODEL_FILES}, in name order"
        )
    return manifest


def _check_version(found: object, expected: int, what: str, folder: str) -> None:
    """Fail loud on a format version this framework does not read, naming the fix."""
    if found != expected:
        raise ValueError(
            f"{folder}: {what} is {found}; this version of the framework reads {expected}: "
            "train the model again with this version, or raise the use case's framework pin "
            "when the bundle is newer"
        )


def _warn_library_version(libraries: dict[str, str], folder: str) -> None:
    """Warn, never refuse, when an installed model library's version differs from the one the
    model was saved with: a native model file is built to load across versions."""
    for library, written in libraries.items():
        installed = version(library)
        if installed != written:
            warnings.warn(
                f"{folder}: the model was saved with {library} {written}, and {installed} is "
                "installed; its native file loads across versions, but its scores may differ "
                "from those it gave at training",
                stacklevel=2,
            )


def _bundle_bytes(bundle: dict, folder: str) -> bytes:
    """`bundle.json`'s one fixed layout: sorted keys, two-space indent, ASCII with escapes, a
    final newline, written as bytes; the same content gives the same bytes. NaN fails."""
    try:
        text = json.dumps(bundle, sort_keys=True, indent=2, allow_nan=False)
    except ValueError as err:
        raise ValueError(f"{folder}/{BUNDLE_FILE}: {err}; never NaN or inf in a bundle") from err
    return (text + "\n").encode("ascii")


def _model_hash(files: dict[str, bytes]) -> str:
    """One SHA-256 over the files in name order, each file's bytes preceded by its name and its
    byte length (NUL-separated), so no bytes can move from one file to the other under one hash."""
    digest = hashlib.sha256()
    for name in sorted(files):
        data = files[name]
        digest.update(name.encode("utf-8") + b"\0" + str(len(data)).encode("ascii") + b"\0")
        digest.update(data)
    return digest.hexdigest()
