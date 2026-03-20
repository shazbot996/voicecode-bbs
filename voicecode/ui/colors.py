"""Color pair definitions for VoiceCode BBS."""

import curses

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
CP_XTREE_BG = 15
CP_XTREE_SEL = 16
CP_XTREE_BORDER = 17
CP_TTS = 18
CP_SECT_RED = 19
CP_SUBMENU = 20
CP_SETTINGS_TITLE = 21
CP_FAV_EMPTY = 22
CP_FAV_FILLED = 23


def init_colors(tts_available: bool = False):
    """Initialize curses color pairs."""
    curses.start_color()
    curses.use_default_colors()
    bg_blue = 18 if curses.COLORS >= 256 else curses.COLOR_BLUE

    curses.init_pair(CP_HEADER, curses.COLOR_YELLOW, bg_blue)
    curses.init_pair(CP_PROMPT, curses.COLOR_WHITE, -1)
    curses.init_pair(CP_DICTATION, curses.COLOR_CYAN, -1)
    curses.init_pair(CP_STATUS, curses.COLOR_WHITE, bg_blue)
    curses.init_pair(CP_HELP, curses.COLOR_YELLOW, bg_blue)
    curses.init_pair(CP_RECORDING, curses.COLOR_WHITE, curses.COLOR_RED)
    curses.init_pair(CP_BANNER, curses.COLOR_CYAN, -1)
    curses.init_pair(CP_ACCENT, curses.COLOR_MAGENTA, -1)
    curses.init_pair(CP_AGENT, curses.COLOR_GREEN, -1)
    curses.init_pair(CP_XFER, curses.COLOR_YELLOW, -1)
    curses.init_pair(CP_VOICE, curses.COLOR_YELLOW, -1)
    curses.init_pair(CP_CTX_GREEN, curses.COLOR_GREEN, -1)
    curses.init_pair(CP_CTX_YELLOW, curses.COLOR_YELLOW, -1)
    curses.init_pair(CP_CTX_RED, curses.COLOR_RED, -1)
    curses.init_pair(CP_XTREE_BG, curses.COLOR_BLACK, curses.COLOR_YELLOW)
    curses.init_pair(CP_XTREE_SEL, curses.COLOR_YELLOW, bg_blue)
    curses.init_pair(CP_XTREE_BORDER, curses.COLOR_WHITE, curses.COLOR_YELLOW)
    curses.init_pair(CP_SECT_RED, curses.COLOR_RED, bg_blue)
    curses.init_pair(CP_SUBMENU, curses.COLOR_CYAN, bg_blue)
    curses.init_pair(CP_SETTINGS_TITLE, curses.COLOR_BLACK, curses.COLOR_YELLOW)
    curses.init_pair(CP_FAV_EMPTY, 8, -1)
    curses.init_pair(CP_FAV_FILLED, curses.COLOR_RED, -1)
    if tts_available:
        curses.init_pair(CP_TTS, curses.COLOR_WHITE, -1)
    else:
        curses.init_pair(CP_TTS, curses.COLOR_GREEN, -1)
