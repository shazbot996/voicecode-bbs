"""Voice Activity Detection model loader."""

import os

_vad_model = None


def get_vad_model():
    global _vad_model
    if _vad_model is None:
        os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")
        # Load from the installed silero-vad package, not torch.hub: the hub
        # cache is an unpinned repo snapshot whose hubconf imports torchaudio.
        from silero_vad import load_silero_vad
        _vad_model = load_silero_vad(onnx=False)
    return _vad_model
