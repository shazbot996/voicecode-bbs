"""Input device selection and capture-format fallback."""

import numpy as np
import pytest
import sounddevice as sd

from voicecode.audio import utils
from voicecode.constants import SAMPLE_RATE, BLOCK_SIZE


class FakeStream:
    """Stands in for sd.InputStream; accepts only the listed (rate, channels)."""

    supported: set = set()
    opened: list = []

    def __init__(self, samplerate, channels, dtype, blocksize, callback, device):
        if (samplerate, channels) not in self.supported:
            raise sd.PortAudioError("Invalid sample rate")
        self.samplerate, self.channels = samplerate, channels
        self.blocksize, self.callback = blocksize, callback
        FakeStream.opened.append(self)

    def start(self):
        pass

    def close(self):
        pass


@pytest.fixture
def fake_audio(monkeypatch):
    """Install a fake device table; returns a setter for (devices, default)."""
    state = {"devices": [], "default": -1}

    def query_devices(device=None, kind=None):
        if device is None:
            return state["devices"]
        return state["devices"][device]

    class Default:
        @property
        def device(self):
            return (state["default"], -1)

    monkeypatch.setattr(utils.sd, "query_devices", query_devices)
    monkeypatch.setattr(utils.sd, "default", Default())
    monkeypatch.setattr(utils.sd, "InputStream", FakeStream)
    monkeypatch.setattr(utils, "refresh_devices", lambda: None)
    FakeStream.opened = []

    def configure(devices, default=-1, supported=()):
        state["devices"], state["default"] = devices, default
        FakeStream.supported = set(supported)

    return configure


def mic(name, channels=1, rate=48000.0):
    return {"name": name, "max_input_channels": channels,
            "default_samplerate": rate}


SPEAKER = {"name": "Speakers", "max_input_channels": 0,
           "default_samplerate": 48000.0}


def test_saved_device_is_used_when_present(fake_audio):
    fake_audio([mic("Laptop Mic"), mic("USB Webcam")], default=0)
    assert utils.resolve_input_device("USB Webcam") == 1


def test_unplugged_saved_device_falls_back_to_default(fake_audio):
    fake_audio([mic("Laptop Mic"), mic("USB Webcam")], default=0)
    assert utils.resolve_input_device("Mute Button Mic") == 0


def test_no_default_falls_back_to_first_capture_device(fake_audio):
    fake_audio([SPEAKER, mic("USB Audio: - (hw:1,0)")], default=-1)
    assert utils.find_input_device(None) == (1, None)


def test_no_devices_reports_friendly_error_not_index(fake_audio):
    fake_audio([], default=-1)
    device, err = utils.find_input_device(None)
    assert device is None
    assert err and "-1" not in err


def test_wsl_without_wslg_names_the_cause(fake_audio, monkeypatch):
    fake_audio([], default=-1)
    monkeypatch.setattr(utils, "_is_wsl", lambda: True)
    monkeypatch.setattr(utils, "_WSLG_PULSE_SOCKET", "/nonexistent/PulseServer")
    assert "guiApplications" in utils.find_input_device(None)[1]


def test_stream_opens_directly_when_device_accepts_16k_mono(fake_audio):
    fake_audio([mic("pulse", rate=44100.0)], supported={(SAMPLE_RATE, 1)})
    stream = utils.open_input_stream(0, lambda samples, status: None)
    assert (stream.samplerate, stream.blocksize) == (SAMPLE_RATE, BLOCK_SIZE)


@pytest.mark.parametrize("rate,channels", [(48000, 1), (48000, 2), (44100, 2)])
def test_stream_falls_back_to_native_format_and_converts(fake_audio, rate, channels):
    fake_audio([mic("USB hw", channels=channels, rate=float(rate))],
               supported={(rate, channels)})
    got = []
    stream = utils.open_input_stream(0, lambda samples, status: got.append(samples))
    assert (stream.samplerate, stream.channels) == (rate, channels)

    block = np.full((stream.blocksize, channels), 16384, dtype=np.int16)
    stream.callback(block, stream.blocksize, None, None)
    assert got[0].dtype == np.float32
    assert len(got[0]) == BLOCK_SIZE
    assert np.allclose(got[0], 0.5)


def test_stream_raises_original_error_when_nothing_works(fake_audio):
    fake_audio([mic("Broken")], supported=set())
    with pytest.raises(sd.PortAudioError, match="Invalid sample rate"):
        utils.open_input_stream(0, lambda samples, status: None)
