"""What every user of a trained model shares: the encoder (`encoder.py`), the model families
(`families.py`, one module per library), the calibration (`calibration.py`), the bundle
(`bundle.py`: the model as plain data under one `model_hash`) and scoring (`scoring.py`: one
path in pandas and inside Spark). Training fits and writes them, Evaluation and Inference read
them, so a model scores the same way wherever it runs. The recipe hash and the feature signature
are identities, in `config/identities.py`.

Public (D-024): `load_bundle`, the `Bundle` it returns and `score_frame`, the only names this
package exports; Training and Evaluation import the rest from the modules.
"""

from core_modelling.model.bundle import Bundle, load_bundle
from core_modelling.model.scoring import score_frame

__all__ = ["Bundle", "load_bundle", "score_frame"]
