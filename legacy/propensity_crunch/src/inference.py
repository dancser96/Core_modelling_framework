"""Batch inference: score eligible clients at an inference date using persisted
trained models, emitting long-format rows.

Decoupled from training and reproducible: each product is scored with its own
FROZEN config + saved model + the calibration offset recorded in its card, so
scoring is independent of any later YAML edits. Only the inference date is a
free parameter (you retrain periodically, then score forward).

Promote-on-inference, two-directory output tied by a manifest:
  - LOCAL SCRATCH RUNS: run() writes every training run to a local, cwd-relative
    store (`artifacts/<product>/<run_id>/`) — you may have many, and pick among
    them. Read-only here.
  - PROMOTED MODEL STORE (`06_models`): the run actually used for scoring is
    PROMOTED (copied) into `<store>/<product>/<run_id>/` — the curated model
    exposed for audit / rerun / reinfer, independent of the scratch pile.
  - MODEL OUTPUT (`07_model_output`): per scoring batch, the long-format scores
    plus a `manifest.json` that references the PROMOTED model by run_id +
    model_hash and records the scores path.
Reproduction resolves the run_id in the promoted store and verifies the hash
(`resolve_from_manifest` / `verify_model`). Transport is filesystem for
local/mounted paths and `hdfs dfs` for hdfs:// roots (the CLI branch is untested
offline; a mounted path is simplest).
"""
from __future__ import annotations

import hashlib
import json
import os
import pickle
import shutil
import subprocess
import tempfile
from pathlib import Path

import pandas as pd

from configs._schema import RunConfig
from src.calibration import from_offset
from src.io import load_snapshot

# The minimal bundle that lets a model be loaded back, re-scored on a new month
# (same schema), and fully described: the model, its frozen config, its card.
ARTIFACT_FILES = ("model.pkl", "config.frozen.json", "model_card.json")


def discover_products(art_root="artifacts"):
    """Products that have at least one runnable trained model."""
    root = Path(art_root)
    if not root.exists():
        return []
    return sorted(p.name for p in root.iterdir()
                  if p.is_dir() and _latest_run(p) is not None)


def resolve_run(product, art_root="artifacts", run_id=None) -> Path:
    """Latest run for a product (default) or a pinned run_id."""
    pdir = Path(art_root) / product
    run_dir = (pdir / run_id) if run_id else _latest_run(pdir)
    if run_dir is None or not (run_dir / "model.pkl").exists():
        raise FileNotFoundError(f"no runnable model for {product!r} under {pdir}")
    return run_dir


def _latest_run(pdir: Path):
    if not pdir.exists():
        return None
    runs = [d for d in pdir.iterdir() if d.is_dir() and (d / "model.pkl").exists()]
    # run_id = <config_hash>_<YYYYmmdd-HHMMSS>; sort by the timestamp suffix
    return max(runs, key=lambda d: d.name.split("_")[-1], default=None)


def load_scorer(run_dir):
    """Return (cfg, model, calibrate_or_None, model_hash) for a run directory.
    Accepts a str or Path (local/mounted); a raw hdfs:// dir must be fetched
    local first (see _fetch_dir)."""
    run_dir = Path(run_dir)
    cfg = RunConfig(**json.loads((run_dir / "config.frozen.json").read_text()))
    model_bytes = (run_dir / "model.pkl").read_bytes()
    model = pickle.loads(model_bytes)
    model_hash = hashlib.sha1(model_bytes).hexdigest()[:12]

    calibrate = None
    card_p = run_dir / "model_card.json"
    if card_p.exists():
        cal = json.loads(card_p.read_text()).get("calibration")
        if cal and cal.get("offset") is not None:
            calibrate = from_offset(cal["offset"])
    return cfg, model, calibrate, model_hash


def score_product(spark, cfg, model, calibrate, infer_date, model_hash) -> pd.DataFrame:
    """Score all eligible clients for one product at infer_date; long format:
    (cif, product, model_hash, infer_date, score)."""
    X = load_snapshot(spark, cfg, infer_date)          # eligible population + features
    p = model.predict_proba(X[cfg.features])[:, 1]
    if calibrate:
        p = calibrate(p)
    return pd.DataFrame(
        {
            cfg.id_col: X[cfg.id_col].values,
            "product": cfg.product,
            "model_hash": model_hash,
            "infer_date": str(infer_date),
            "score": p,
        }
    )


def copy_run_artifacts(run_dir, dest_dir, files=ARTIFACT_FILES):
    """Low-level: copy a run's key files into dest_dir (filesystem). Returns the
    filenames copied. `promote_model` is the higher-level entry point."""
    dest = Path(dest_dir)
    dest.mkdir(parents=True, exist_ok=True)
    copied = []
    for f in files:
        src = Path(run_dir) / f
        if src.exists():
            shutil.copy2(src, dest / f)
            copied.append(f)
    return copied


# --- transport: filesystem for local/mounted paths, `hdfs dfs` for hdfs:// URIs -----
# The hdfs:// branch shells out to the Hadoop CLI and is UNTESTED offline; a
# mounted/DBFS path (where plain filesystem ops work) is the simplest target.
def _is_hdfs(p):
    return str(p).startswith("hdfs:")   # tolerant of hdfs:// and a pathlib-mangled hdfs:/


def _put_file(src, dest):
    dest = str(dest)
    if _is_hdfs(dest):
        subprocess.run(["hdfs", "dfs", "-mkdir", "-p", dest.rsplit("/", 1)[0]], check=True)
        subprocess.run(["hdfs", "dfs", "-put", "-f", str(src), dest], check=True)
    else:
        d = Path(dest); d.parent.mkdir(parents=True, exist_ok=True); shutil.copy2(src, d)


def _write_text(dest, text):
    dest = str(dest)
    if _is_hdfs(dest):
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
            fh.write(text); tmp = fh.name
        _put_file(tmp, dest); os.unlink(tmp)
    else:
        p = Path(dest); p.parent.mkdir(parents=True, exist_ok=True); p.write_text(text)


def _read_text(src):
    src = str(src)
    if _is_hdfs(src):
        return subprocess.run(["hdfs", "dfs", "-cat", src], check=True,
                              capture_output=True, text=True).stdout
    return Path(src).read_text()


def _fetch_dir(src_dir, files=ARTIFACT_FILES):
    """If src_dir is on hdfs://, copy its bundle to a local temp dir and return
    that local path; otherwise return src_dir unchanged. Lets pathlib/pickle read
    a promoted model that lives on raw HDFS. No-op for local/mounted stores."""
    if not _is_hdfs(src_dir):
        return str(src_dir)
    local = tempfile.mkdtemp()
    base = str(src_dir).rstrip("/")
    for f in files:
        subprocess.run(["hdfs", "dfs", "-get", "-f", f"{base}/{f}", f"{local}/{f}"], check=False)
    return local


def promote_model(run_dir, store_root, product, run_id, files=ARTIFACT_FILES):
    """PROMOTE a chosen local scratch run into the curated model store at
    <store_root>/<product>/<run_id>/ (your 06_models). Copies the model + frozen
    config + card so the promoted model is the audit/rerun/reinfer source of
    truth, independent of the many local runs. Idempotent (re-copies same bytes).
    Filesystem copy for local/mounted paths; `hdfs dfs -put` for hdfs:// roots.
    Returns the promoted directory path (str)."""
    dest = f"{str(store_root).rstrip('/')}/{product}/{run_id}"
    for f in files:
        src = Path(run_dir) / f
        if src.exists():
            _put_file(src, f"{dest}/{f}")
    return dest


def write_manifest(dest_root, rows):
    """Write manifest.json tying a scoring batch to the PROMOTED models that
    produced it. Filesystem or hdfs:// (via CLI). Returns the manifest path."""
    dest = f"{str(dest_root).rstrip('/')}/manifest.json"
    _write_text(dest, json.dumps(rows, indent=2, default=str))
    return dest


def hash_model_pkl(run_dir) -> str:
    """Content hash of a run's model.pkl (matches the model_hash load_scorer returns)."""
    return hashlib.sha1((Path(run_dir) / "model.pkl").read_bytes()).hexdigest()[:12]


def verify_model(run_dir, expected_hash) -> bool:
    """Immutability guard for reproduction: the referenced model must still exist
    and hash to what produced the scores. Raises on missing/mismatch — this is
    what makes reference-by-run_id (no copy) safe against a mutated model store."""
    mp = Path(run_dir) / "model.pkl"
    if not mp.exists():
        raise FileNotFoundError(f"model missing for reproduction: {mp}")
    actual = hashlib.sha1(mp.read_bytes()).hexdigest()[:12]
    if actual != expected_hash:
        raise ValueError(
            f"model_hash mismatch at {run_dir}: {actual} != {expected_hash} "
            "(model store was altered — these scores are not reproducible from it)"
        )
    return True


def resolve_from_manifest(manifest_path, product, models_dir=None):
    """Reproduce a scored product from a manifest: locate its PROMOTED model dir
    in the curated store, fetch it local if it's on HDFS, verify the hash, and
    load the scorer back. Returns (run_dir, cfg, model, calibrate, model_hash),
    where run_dir is the canonical (possibly hdfs://) promoted path."""
    man = json.loads(_read_text(manifest_path))
    root = str(models_dir or man.get("models_dir", "06_models")).rstrip("/")
    row = next(r for r in man["products"] if r["product"] == product)
    run_dir = f"{root}/{product}/{row['run_id']}"     # string join preserves hdfs://
    local_dir = _fetch_dir(run_dir)                   # hdfs:// -> local temp; no-op otherwise
    verify_model(local_dir, row["model_hash"])
    cfg, model, calibrate, model_hash = load_scorer(local_dir)
    return run_dir, cfg, model, calibrate, model_hash
