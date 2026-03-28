"""Theme definitions for VoiceCode BBS."""

import curses
from typing import TypedDict


class ColorDef(TypedDict):
    fg: int
    bg: int
    attrs: int  # advisory — not used by init_colors, available for future use


ThemeDict = dict[str, ColorDef]

# Maps semantic role name -> CP_* pair ID
ROLE_TO_PAIR: dict[str, int] = {
    "header": 1,
    "prompt": 2,
    "dictation": 3,
    "status": 4,
    "help_bar": 5,
    "recording": 6,
    "banner": 7,
    "accent": 8,
    "agent": 9,
    "xfer": 10,
    "voice": 11,
    "ctx_green": 12,
    "ctx_yellow": 13,
    "ctx_red": 14,
    "selection": 15,
    "sect_red": 19,
    "submenu": 20,
    "settings_title": 21,
    "fav_empty": 22,
    "fav_filled": 23,
    "publish": 24,
    "publish_title": 25,
    "publish_hint": 26,
    "doc_body": 27,
    "doc_heading": 28,
    "doc_dim": 29,
    "doc_list_bg": 30,
    "doc_list_border": 32,
    "doc_badge_cyan": 33,
    "doc_badge_green": 34,
    "doc_badge_magenta": 35,
    "doc_badge_yellow": 36,
}

# 256-color -> 16-color fallback mapping
FALLBACK_MAP: dict[int, int] = {
    8: curses.COLOR_WHITE,      # bright black (gray) -> white
    18: curses.COLOR_BLUE,      # bg_blue 256 -> 16 fallback
    94: curses.COLOR_YELLOW,    # wildcat gold
    52: curses.COLOR_RED,       # telegard dark red
    22: curses.COLOR_GREEN,     # wwiv dark green
}

# bg_blue: deep blue for 256-color, standard blue for 16-color
_BG_BLUE = 18

THEMES: dict[str, ThemeDict] = {
    "pcboard": {
        "header":            {"fg": curses.COLOR_YELLOW,  "bg": _BG_BLUE,            "attrs": curses.A_BOLD},
        "prompt":            {"fg": curses.COLOR_WHITE,   "bg": -1,                   "attrs": 0},
        "dictation":         {"fg": curses.COLOR_CYAN,    "bg": -1,                   "attrs": 0},
        "status":            {"fg": curses.COLOR_WHITE,   "bg": _BG_BLUE,            "attrs": 0},
        "help_bar":          {"fg": curses.COLOR_YELLOW,  "bg": _BG_BLUE,            "attrs": 0},
        "recording":         {"fg": curses.COLOR_WHITE,   "bg": curses.COLOR_RED,     "attrs": curses.A_BOLD},
        "banner":            {"fg": curses.COLOR_CYAN,    "bg": -1,                   "attrs": 0},
        "accent":            {"fg": curses.COLOR_MAGENTA, "bg": -1,                   "attrs": 0},
        "agent":             {"fg": curses.COLOR_GREEN,   "bg": -1,                   "attrs": 0},
        "xfer":              {"fg": curses.COLOR_YELLOW,  "bg": -1,                   "attrs": 0},
        "voice":             {"fg": curses.COLOR_YELLOW,  "bg": -1,                   "attrs": 0},
        "ctx_green":         {"fg": curses.COLOR_GREEN,   "bg": -1,                   "attrs": 0},
        "ctx_yellow":        {"fg": curses.COLOR_YELLOW,  "bg": -1,                   "attrs": 0},
        "ctx_red":           {"fg": curses.COLOR_RED,     "bg": -1,                   "attrs": 0},
        "selection":         {"fg": curses.COLOR_YELLOW,  "bg": _BG_BLUE,            "attrs": curses.A_BOLD},
        "tts":               {"fg": curses.COLOR_WHITE,   "bg": -1,                   "attrs": 0},
        "tts_unavailable":   {"fg": curses.COLOR_GREEN,   "bg": -1,                   "attrs": 0},
        "sect_red":          {"fg": curses.COLOR_RED,     "bg": _BG_BLUE,            "attrs": 0},
        "submenu":           {"fg": curses.COLOR_CYAN,    "bg": _BG_BLUE,            "attrs": 0},
        "settings_title":    {"fg": curses.COLOR_BLACK,   "bg": curses.COLOR_YELLOW,  "attrs": curses.A_BOLD},
        "fav_empty":         {"fg": 8,                    "bg": -1,                   "attrs": 0},
        "fav_filled":        {"fg": curses.COLOR_RED,     "bg": -1,                   "attrs": 0},
        "publish":           {"fg": curses.COLOR_MAGENTA, "bg": -1,                   "attrs": 0},
        "publish_title":     {"fg": curses.COLOR_BLACK,   "bg": curses.COLOR_MAGENTA, "attrs": curses.A_BOLD},
        "publish_hint":      {"fg": curses.COLOR_MAGENTA, "bg": _BG_BLUE,            "attrs": 0},
        "doc_body":          {"fg": curses.COLOR_WHITE,   "bg": curses.COLOR_BLACK,   "attrs": 0},
        "doc_heading":       {"fg": curses.COLOR_GREEN,   "bg": curses.COLOR_BLACK,   "attrs": curses.A_BOLD},
        "doc_dim":           {"fg": curses.COLOR_YELLOW,  "bg": curses.COLOR_BLACK,   "attrs": 0},
        "doc_list_bg":       {"fg": curses.COLOR_WHITE,   "bg": curses.COLOR_BLACK,   "attrs": 0},
        "doc_list_border":   {"fg": curses.COLOR_GREEN,   "bg": curses.COLOR_BLACK,   "attrs": 0},
        "doc_badge_cyan":    {"fg": curses.COLOR_CYAN,    "bg": curses.COLOR_BLACK,   "attrs": 0},
        "doc_badge_green":   {"fg": curses.COLOR_GREEN,   "bg": curses.COLOR_BLACK,   "attrs": 0},
        "doc_badge_magenta": {"fg": curses.COLOR_MAGENTA, "bg": curses.COLOR_BLACK,   "attrs": 0},
        "doc_badge_yellow":  {"fg": curses.COLOR_YELLOW,  "bg": curses.COLOR_BLACK,   "attrs": 0},
    },
    "wwiv": {
        "header":            {"fg": curses.COLOR_GREEN,   "bg": 22,                   "attrs": curses.A_BOLD},
        "prompt":            {"fg": curses.COLOR_GREEN,   "bg": -1,                   "attrs": 0},
        "dictation":         {"fg": curses.COLOR_GREEN,   "bg": -1,                   "attrs": 0},
        "status":            {"fg": curses.COLOR_GREEN,   "bg": 22,                   "attrs": 0},
        "help_bar":          {"fg": curses.COLOR_WHITE,   "bg": 22,                   "attrs": 0},
        "recording":         {"fg": curses.COLOR_WHITE,   "bg": curses.COLOR_RED,     "attrs": curses.A_BOLD},
        "banner":            {"fg": curses.COLOR_GREEN,   "bg": -1,                   "attrs": 0},
        "accent":            {"fg": curses.COLOR_WHITE,   "bg": -1,                   "attrs": 0},
        "agent":             {"fg": curses.COLOR_GREEN,   "bg": -1,                   "attrs": 0},
        "xfer":              {"fg": curses.COLOR_GREEN,   "bg": -1,                   "attrs": curses.A_BOLD},
        "voice":             {"fg": curses.COLOR_GREEN,   "bg": -1,                   "attrs": curses.A_BOLD},
        "ctx_green":         {"fg": curses.COLOR_GREEN,   "bg": -1,                   "attrs": 0},
        "ctx_yellow":        {"fg": curses.COLOR_WHITE,   "bg": -1,                   "attrs": 0},
        "ctx_red":           {"fg": curses.COLOR_RED,     "bg": -1,                   "attrs": 0},
        "selection":         {"fg": curses.COLOR_BLACK,   "bg": curses.COLOR_GREEN,   "attrs": curses.A_BOLD},
        "tts":               {"fg": curses.COLOR_GREEN,   "bg": -1,                   "attrs": 0},
        "tts_unavailable":   {"fg": curses.COLOR_WHITE,   "bg": -1,                   "attrs": 0},
        "sect_red":          {"fg": curses.COLOR_RED,     "bg": 22,                   "attrs": 0},
        "submenu":           {"fg": curses.COLOR_WHITE,   "bg": 22,                   "attrs": 0},
        "settings_title":    {"fg": curses.COLOR_BLACK,   "bg": curses.COLOR_GREEN,   "attrs": curses.A_BOLD},
        "fav_empty":         {"fg": 22,                   "bg": -1,                   "attrs": 0},
        "fav_filled":        {"fg": curses.COLOR_GREEN,   "bg": -1,                   "attrs": curses.A_BOLD},
        "publish":           {"fg": curses.COLOR_GREEN,   "bg": -1,                   "attrs": 0},
        "publish_title":     {"fg": curses.COLOR_BLACK,   "bg": curses.COLOR_GREEN,   "attrs": curses.A_BOLD},
        "publish_hint":      {"fg": curses.COLOR_GREEN,   "bg": 22,                   "attrs": 0},
        "doc_body":          {"fg": curses.COLOR_GREEN,   "bg": curses.COLOR_BLACK,   "attrs": 0},
        "doc_heading":       {"fg": curses.COLOR_WHITE,   "bg": curses.COLOR_BLACK,   "attrs": curses.A_BOLD},
        "doc_dim":           {"fg": curses.COLOR_GREEN,   "bg": curses.COLOR_BLACK,   "attrs": 0},
        "doc_list_bg":       {"fg": curses.COLOR_GREEN,   "bg": curses.COLOR_BLACK,   "attrs": 0},
        "doc_list_border":   {"fg": curses.COLOR_GREEN,   "bg": curses.COLOR_BLACK,   "attrs": 0},
        "doc_badge_cyan":    {"fg": curses.COLOR_GREEN,   "bg": curses.COLOR_BLACK,   "attrs": 0},
        "doc_badge_green":   {"fg": curses.COLOR_GREEN,   "bg": curses.COLOR_BLACK,   "attrs": curses.A_BOLD},
        "doc_badge_magenta": {"fg": curses.COLOR_WHITE,   "bg": curses.COLOR_BLACK,   "attrs": 0},
        "doc_badge_yellow":  {"fg": curses.COLOR_GREEN,   "bg": curses.COLOR_BLACK,   "attrs": 0},
    },
    "telegard": {
        "header":            {"fg": curses.COLOR_YELLOW,  "bg": 52,                   "attrs": curses.A_BOLD},
        "prompt":            {"fg": curses.COLOR_WHITE,   "bg": -1,                   "attrs": 0},
        "dictation":         {"fg": curses.COLOR_WHITE,   "bg": -1,                   "attrs": 0},
        "status":            {"fg": curses.COLOR_YELLOW,  "bg": 52,                   "attrs": 0},
        "help_bar":          {"fg": curses.COLOR_WHITE,   "bg": 52,                   "attrs": 0},
        "recording":         {"fg": curses.COLOR_WHITE,   "bg": curses.COLOR_RED,     "attrs": curses.A_BOLD},
        "banner":            {"fg": curses.COLOR_RED,     "bg": -1,                   "attrs": 0},
        "accent":            {"fg": curses.COLOR_RED,     "bg": -1,                   "attrs": 0},
        "agent":             {"fg": curses.COLOR_WHITE,   "bg": -1,                   "attrs": 0},
        "xfer":              {"fg": curses.COLOR_YELLOW,  "bg": -1,                   "attrs": 0},
        "voice":             {"fg": curses.COLOR_YELLOW,  "bg": -1,                   "attrs": 0},
        "ctx_green":         {"fg": curses.COLOR_GREEN,   "bg": -1,                   "attrs": 0},
        "ctx_yellow":        {"fg": curses.COLOR_YELLOW,  "bg": -1,                   "attrs": 0},
        "ctx_red":           {"fg": curses.COLOR_RED,     "bg": -1,                   "attrs": 0},
        "selection":         {"fg": curses.COLOR_WHITE,   "bg": curses.COLOR_RED,     "attrs": curses.A_BOLD},
        "tts":               {"fg": curses.COLOR_WHITE,   "bg": -1,                   "attrs": 0},
        "tts_unavailable":   {"fg": curses.COLOR_RED,     "bg": -1,                   "attrs": 0},
        "sect_red":          {"fg": curses.COLOR_RED,     "bg": 52,                   "attrs": 0},
        "submenu":           {"fg": curses.COLOR_WHITE,   "bg": 52,                   "attrs": 0},
        "settings_title":    {"fg": curses.COLOR_BLACK,   "bg": curses.COLOR_YELLOW,  "attrs": curses.A_BOLD},
        "fav_empty":         {"fg": 52,                   "bg": -1,                   "attrs": 0},
        "fav_filled":        {"fg": curses.COLOR_RED,     "bg": -1,                   "attrs": curses.A_BOLD},
        "publish":           {"fg": curses.COLOR_RED,     "bg": -1,                   "attrs": 0},
        "publish_title":     {"fg": curses.COLOR_WHITE,   "bg": curses.COLOR_RED,     "attrs": curses.A_BOLD},
        "publish_hint":      {"fg": curses.COLOR_YELLOW,  "bg": 52,                   "attrs": 0},
        "doc_body":          {"fg": curses.COLOR_WHITE,   "bg": curses.COLOR_BLACK,   "attrs": 0},
        "doc_heading":       {"fg": curses.COLOR_YELLOW,  "bg": curses.COLOR_BLACK,   "attrs": curses.A_BOLD},
        "doc_dim":           {"fg": curses.COLOR_RED,     "bg": curses.COLOR_BLACK,   "attrs": 0},
        "doc_list_bg":       {"fg": curses.COLOR_WHITE,   "bg": curses.COLOR_BLACK,   "attrs": 0},
        "doc_list_border":   {"fg": curses.COLOR_RED,     "bg": curses.COLOR_BLACK,   "attrs": 0},
        "doc_badge_cyan":    {"fg": curses.COLOR_YELLOW,  "bg": curses.COLOR_BLACK,   "attrs": 0},
        "doc_badge_green":   {"fg": curses.COLOR_GREEN,   "bg": curses.COLOR_BLACK,   "attrs": 0},
        "doc_badge_magenta": {"fg": curses.COLOR_RED,     "bg": curses.COLOR_BLACK,   "attrs": 0},
        "doc_badge_yellow":  {"fg": curses.COLOR_YELLOW,  "bg": curses.COLOR_BLACK,   "attrs": 0},
    },
    "wildcat": {
        "header":            {"fg": curses.COLOR_BLACK,   "bg": curses.COLOR_YELLOW,  "attrs": curses.A_BOLD},
        "prompt":            {"fg": curses.COLOR_YELLOW,  "bg": -1,                   "attrs": 0},
        "dictation":         {"fg": curses.COLOR_YELLOW,  "bg": -1,                   "attrs": 0},
        "status":            {"fg": curses.COLOR_BLACK,   "bg": curses.COLOR_YELLOW,  "attrs": 0},
        "help_bar":          {"fg": curses.COLOR_BLACK,   "bg": curses.COLOR_YELLOW,  "attrs": 0},
        "recording":         {"fg": curses.COLOR_WHITE,   "bg": curses.COLOR_RED,     "attrs": curses.A_BOLD},
        "banner":            {"fg": curses.COLOR_YELLOW,  "bg": -1,                   "attrs": 0},
        "accent":            {"fg": curses.COLOR_WHITE,   "bg": -1,                   "attrs": 0},
        "agent":             {"fg": curses.COLOR_YELLOW,  "bg": -1,                   "attrs": 0},
        "xfer":              {"fg": curses.COLOR_YELLOW,  "bg": -1,                   "attrs": curses.A_BOLD},
        "voice":             {"fg": curses.COLOR_YELLOW,  "bg": -1,                   "attrs": curses.A_BOLD},
        "ctx_green":         {"fg": curses.COLOR_GREEN,   "bg": -1,                   "attrs": 0},
        "ctx_yellow":        {"fg": curses.COLOR_YELLOW,  "bg": -1,                   "attrs": 0},
        "ctx_red":           {"fg": curses.COLOR_RED,     "bg": -1,                   "attrs": 0},
        "selection":         {"fg": curses.COLOR_BLACK,   "bg": curses.COLOR_YELLOW,  "attrs": curses.A_BOLD},
        "tts":               {"fg": curses.COLOR_YELLOW,  "bg": -1,                   "attrs": 0},
        "tts_unavailable":   {"fg": curses.COLOR_WHITE,   "bg": -1,                   "attrs": 0},
        "sect_red":          {"fg": curses.COLOR_RED,     "bg": curses.COLOR_YELLOW,  "attrs": 0},
        "submenu":           {"fg": curses.COLOR_BLACK,   "bg": curses.COLOR_YELLOW,  "attrs": 0},
        "settings_title":    {"fg": curses.COLOR_BLACK,   "bg": curses.COLOR_YELLOW,  "attrs": curses.A_BOLD},
        "fav_empty":         {"fg": 94,                   "bg": -1,                   "attrs": 0},
        "fav_filled":        {"fg": curses.COLOR_YELLOW,  "bg": -1,                   "attrs": curses.A_BOLD},
        "publish":           {"fg": curses.COLOR_YELLOW,  "bg": -1,                   "attrs": 0},
        "publish_title":     {"fg": curses.COLOR_BLACK,   "bg": curses.COLOR_YELLOW,  "attrs": curses.A_BOLD},
        "publish_hint":      {"fg": curses.COLOR_YELLOW,  "bg": 94,                   "attrs": 0},
        "doc_body":          {"fg": curses.COLOR_YELLOW,  "bg": curses.COLOR_BLACK,   "attrs": 0},
        "doc_heading":       {"fg": curses.COLOR_WHITE,   "bg": curses.COLOR_BLACK,   "attrs": curses.A_BOLD},
        "doc_dim":           {"fg": 94,                   "bg": curses.COLOR_BLACK,   "attrs": 0},
        "doc_list_bg":       {"fg": curses.COLOR_YELLOW,  "bg": curses.COLOR_BLACK,   "attrs": 0},
        "doc_list_border":   {"fg": curses.COLOR_YELLOW,  "bg": curses.COLOR_BLACK,   "attrs": 0},
        "doc_badge_cyan":    {"fg": curses.COLOR_WHITE,   "bg": curses.COLOR_BLACK,   "attrs": 0},
        "doc_badge_green":   {"fg": curses.COLOR_YELLOW,  "bg": curses.COLOR_BLACK,   "attrs": curses.A_BOLD},
        "doc_badge_magenta": {"fg": curses.COLOR_YELLOW,  "bg": curses.COLOR_BLACK,   "attrs": 0},
        "doc_badge_yellow":  {"fg": curses.COLOR_YELLOW,  "bg": curses.COLOR_BLACK,   "attrs": 0},
    },
}

THEME_DISPLAY_NAMES: dict[str, str] = {
    "pcboard": "PCBoard Blue",
    "wwiv": "WWIV Green",
    "telegard": "Telegard Dark",
    "wildcat": "Wildcat! Gold",
}


def get_theme_dict(name: str) -> ThemeDict:
    """Return the theme dict for the given name, falling back to pcboard."""
    return THEMES.get(name, THEMES["pcboard"])


def get_theme_names() -> list[str]:
    """Return a list of available theme names."""
    return list(THEMES.keys())


def validate_theme(theme: ThemeDict) -> list[str]:
    """Return a list of semantic roles missing from the theme dict."""
    required = set(ROLE_TO_PAIR.keys()) | {"tts", "tts_unavailable"}
    return [role for role in sorted(required) if role not in theme]
