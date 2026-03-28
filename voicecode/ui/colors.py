"""Color pair definitions for VoiceCode BBS."""

import curses

from voicecode.ui.themes import get_theme_dict, ROLE_TO_PAIR, FALLBACK_MAP

# Color pair IDs
CP_HEADER = 1
CP_PROMPT = 2
CP_DICTATION = 3
CP_STATUS = 4
CP_HELP = 5
CP_RECORDING = 6
CP_BANNER = 7
CP_ACCENT = 8
CP_AGENT = 9
CP_XFER = 10
CP_VOICE = 11
CP_CTX_GREEN = 12
CP_CTX_YELLOW = 13
CP_CTX_RED = 14
CP_SELECTION = 15  # unified selection highlight (yellow on blue)
CP_TTS = 18
CP_SECT_RED = 19
CP_SUBMENU = 20
CP_SETTINGS_TITLE = 21
CP_FAV_EMPTY = 22
CP_FAV_FILLED = 23
CP_PUBLISH = 24
CP_PUBLISH_TITLE = 25
CP_PUBLISH_HINT = 26
CP_DOC_BODY = 27
CP_DOC_HEADING = 28
CP_DOC_DIM = 29
CP_DOC_LIST_BG = 30
CP_DOC_LIST_BORDER = 32
CP_DOC_BADGE_CYAN = 33
CP_DOC_BADGE_GREEN = 34
CP_DOC_BADGE_MAGENTA = 35
CP_DOC_BADGE_YELLOW = 36

_active_theme: list[str] = ["pcboard"]


def _resolve_color(color_val: int) -> int:
    """Clamp 256-color values to 16-color fallbacks when needed."""
    if color_val >= curses.COLORS:
        return FALLBACK_MAP.get(color_val, curses.COLOR_WHITE)
    return color_val


def init_colors(theme_name: str = "pcboard", tts_available: bool = False):
    """Initialize curses color pairs from the named theme."""
    curses.start_color()
    curses.use_default_colors()
    theme = get_theme_dict(theme_name)
    for role, cp_id in ROLE_TO_PAIR.items():
        cdef = theme[role]
        curses.init_pair(cp_id, _resolve_color(cdef["fg"]),
                         _resolve_color(cdef["bg"]))
    # TTS pair varies by runtime state
    tts_role = "tts" if tts_available else "tts_unavailable"
    tts_def = theme[tts_role]
    curses.init_pair(CP_TTS, _resolve_color(tts_def["fg"]),
                     _resolve_color(tts_def["bg"]))
    _active_theme[0] = theme_name


def get_active_theme() -> str:
    """Return the name of the currently active theme."""
    return _active_theme[0]


def set_active_theme(name: str, tts_available: bool = False):
    """Switch to a new theme by reinitializing all color pairs."""
    init_colors(name, tts_available)
