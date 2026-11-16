"""What every user of a trained model shares: the encoder (`encoder.py`), the model families
(`families.py`, one module per library), the calibration (`calibration.py`), the bundle
(`bundle.py`: the model as plain data under one `model_hash`) and scoring (`scoring.py`: one
path in pandas and inside Spark). Training fits and writes them, Evaluation and Inference read
them, so a model scores the same way wherever it runs. The recipe hash and the feature signature
are identities, in `config/identities.py`.

Public (D-024): `load_bundle` and `score_frame`; the other names are what Training and
Evaluation import.
"""

from core_modelling.model.bundle import Bundle, load_bundle, write_bundle
from core_modelling.model.calibration import apply_calibration
from core_modelling.model.encoder import encode_frame, fit_encoder
from core_modelling.model.families import FAMILIES, check_monotone
from core_modelling.model.scoring import check_bundle, score_frame, score_spark

__all__ = [
    "FAMILIES",
    "Bundle",
    "apply_calibration",
    "check_bundle",
    "check_monotone",
    "encode_frame",
    "fit_encoder",
    "load_bundle",
    "score_frame",
    "score_spark",
    "write_bundle",
]
