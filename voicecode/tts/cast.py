"""Google Cast TTS integration — discover devices and cast speech."""

import os
import time
import threading
import subprocess

from voicecode.tts.voices import get_tts_voice_model, get_tts_piper_extra_args, TTS_AVAILABLE

CAST_AVAILABLE = False
try:
    import pychromecast
    CAST_AVAILABLE = True
except ImportError:
    pass


def discover_cast_devices(ui_queue=None):
    """Discover Chromecast / Google Cast devices on the local network.

    Runs synchronously — call from a background thread.  Returns a list
    of friendly-name strings.  Optionally posts status updates to *ui_queue*.
    """
    if not CAST_AVAILABLE:
        return []
    try:
        if ui_queue:
            ui_queue.put(("status", "Scanning for Cast devices...", 4))
        chromecasts, browser = pychromecast.get_chromecasts()
        names = sorted({cc.cast_info.friendly_name for cc in chromecasts})
        browser.stop_discovery()
        if ui_queue:
            n = len(names)
            ui_queue.put(("status", f"Found {n} Cast device{'s' if n != 1 else ''}.", 4))
            ui_queue.put(("cast_scan_result", names))
        return names
    except Exception as e:
        if ui_queue:
            ui_queue.put(("status", f"Cast scan error: {e}", 4))
        return []


def cast_tts_to_devices(text, device_names, ui_queue=None, volume=None):
    """Generate TTS audio via Piper and cast it to selected Cast devices.

    Runs in a background daemon thread.  Requires both CAST_AVAILABLE and
    TTS_AVAILABLE.  If *volume* is given (0.0–1.0), the device volume is
    forced to that level before playback.
    """
    if not CAST_AVAILABLE or not TTS_AVAILABLE or not device_names:
        return

    def _run():
        import tempfile
        import socket
        import http.server

        tmp_path = None
        server = None
        browser = None
        try:
            voice_model = get_tts_voice_model()
            if not voice_model.exists():
                return

            # Generate WAV via piper
            fd, tmp_path = tempfile.mkstemp(suffix=".wav", prefix="vc_cast_")
            os.close(fd)
            extra_args = get_tts_piper_extra_args()
            piper_cmd = ["piper", "--model", str(voice_model),
                         "--output_file", tmp_path] + extra_args
            proc = subprocess.Popen(piper_cmd, stdin=subprocess.PIPE,
                                    stdout=subprocess.DEVNULL,
                                    stderr=subprocess.DEVNULL)
            single_line = " ".join(text.split())
            proc.stdin.write((single_line + "\n").encode("utf-8"))
            proc.stdin.close()
            proc.wait()

            if not os.path.exists(tmp_path) or os.path.getsize(tmp_path) == 0:
                return

            # Resolve local IP visible to the LAN
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            try:
                s.connect(("8.8.8.8", 80))
                local_ip = s.getsockname()[0]
            finally:
                s.close()

            # Minimal HTTP server to serve the WAV file
            tmp_dir = os.path.dirname(tmp_path)

            class _Handler(http.server.SimpleHTTPRequestHandler):
                def __init__(self, *a, **kw):
                    super().__init__(*a, directory=tmp_dir, **kw)
                def log_message(self, *_a):
                    pass

            server = http.server.HTTPServer(("0.0.0.0", 0), _Handler)
            port = server.server_address[1]
            srv_thread = threading.Thread(target=server.serve_forever,
                                          daemon=True)
            srv_thread.start()

            url = f"http://{local_ip}:{port}/{os.path.basename(tmp_path)}"

            if ui_queue:
                ui_queue.put(("status",
                              f"Casting to {len(device_names)} device(s)...", 4))

            chromecasts, browser = pychromecast.get_listed_chromecasts(
                friendly_names=list(device_names))

            # Save original volumes, set target, and start playback
            original_volumes = {}
            for cast in chromecasts:
                cast.wait()
                if volume is not None:
                    original_volumes[cast] = cast.status.volume_level
                    cast.set_volume(volume)
                    time.sleep(0.3)
                mc = cast.media_controller
                mc.play_media(url, "audio/wav")
                mc.block_until_active()

            # Keep server alive long enough for devices to finish playback
            time.sleep(30)

            # Restore original volumes
            for cast, orig_vol in original_volumes.items():
                try:
                    cast.set_volume(orig_vol)
                except Exception:
                    pass

        except Exception as e:
            if ui_queue:
                ui_queue.put(("status", f"Cast error: {e}", 4))
        else:
            if ui_queue:
                ui_queue.put(("status", "Cast complete.", 4))
        finally:
            if server:
                server.shutdown()
            if browser:
                try:
                    browser.stop_discovery()
                except Exception:
                    pass
            if tmp_path:
                try:
                    os.unlink(tmp_path)
                except OSError:
                    pass

    threading.Thread(target=_run, daemon=True).start()
