"""Settings and shortcuts persistence for VoiceCode BBS."""

import json
import re
from pathlib import Path

from voicecode.constants import SETTINGS_DIR, SETTINGS_FILE, SHORTCUTS_FILE


def load_settings() -> dict:
    """Load settings from disk, returning empty dict on any error."""
    try:
        return json.loads(SETTINGS_FILE.read_text())
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def save_settings(settings: dict):
    """Persist settings to disk."""
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    SETTINGS_FILE.write_text(json.dumps(settings, indent=2) + "\n")


def load_shortcuts() -> list[str]:
    """Load user-defined shortcut strings from disk."""
    try:
        lines = SHORTCUTS_FILE.read_text().splitlines()
        return [l for l in lines if l.strip()]
    except (FileNotFoundError, OSError):
        return []


def save_shortcuts(shortcuts: list[str]):
    """Persist shortcut strings to disk."""
    SETTINGS_DIR.mkdir(parents=True, exist_ok=True)
    SHORTCUTS_FILE.write_text("\n".join(shortcuts) + "\n" if shortcuts else "")


def persist_setting(key, val):
    """Load, update one key, and save settings."""
    s = load_settings()
    s[key] = val
    save_settings(s)


def slug_from_text(text: str, max_words: int = 5) -> str:
    """Derive a short filesystem-safe slug from prompt text."""
    for line in text.split("\n"):
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            break
    else:
        stripped = text.strip()
    words = re.sub(r"[^a-z0-9\s]", "", stripped.lower()).split()[:max_words]
    return "_".join(words) if words else "prompt"


def next_seq(directory: Path) -> int:
    """Return the next sequence number for flat-indexed files in directory."""
    max_seq = 0
    if directory.exists():
        for p in directory.iterdir():
            m = re.match(r"(\d+)_", p.name)
            if m:
                max_seq = max(max_seq, int(m.group(1)))
    return max_seq + 1
