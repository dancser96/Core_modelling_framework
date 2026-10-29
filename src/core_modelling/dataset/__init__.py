"""The dataset: the frames every stage works on, from one data definition (D-030, D-131).

Public (D-024): `build_frames` and `save_model_input`, with the `Frames` they return and write.
The modules: `panel.py` (the sources joined with one target column per use case, and the
panel prepared for one config: eligibility, the candidates, the contract, the split),
`eligibility.py` (who is in: the two lists, the SQL guard, the candidates), `split.py` (the
client split, train-only sampling), `contract.py` (the contract checks),
`frames.py` (the frames with the collect printout) and `model_input.py` (the joined panel saved
once for one or several use cases, prepared on read by each reader's config).
"""

from core_modelling.dataset.frames import Frames, build_frames
from core_modelling.dataset.model_input import save_model_input

__all__ = ["Frames", "build_frames", "save_model_input"]
