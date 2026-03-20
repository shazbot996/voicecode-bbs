"""Voice Activity Detection model loader."""

import os

_vad_model = None


def get_vad_model():
    global _vad_model
    if _vad_model is None:
        os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
        import torch
        _vad_model, _ = torch.hub.load(
            "snakers4/silero-vad", "silero_vad", force_reload=False, onnx=False
        )
    return _vad_model
