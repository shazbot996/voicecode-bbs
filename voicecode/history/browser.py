"""Prompt history scanning, loading, navigation."""

import re
from pathlib import Path

from voicecode.ui.colors import *


class BrowserHelper:
    def __init__(self, app):
        self.app = app

    def scan_history_prompts(self):
        app = self.app
        app.history_prompts = sorted(app.history_base.glob("[0-9]*_*_prompt.md"))

    def current_browser_list(self) -> list[Path]:
        """Return the prompt list for the current browser view."""
        app = self.app
        if app.browser_view == "favorites":
            return app.favorites.favorites_as_paths()
        return app.history_prompts  # "active" view browses history via left/right

    def load_browser_prompt(self, width: int):
        app = self.app
        prompt_list = self.current_browser_list()

        if app.browser_index < 0 or app.browser_index >= len(prompt_list):
            app.browser_index = -1
            if app.browser_view == "favorites":
                app.prompt_pane.title = "FAVORITES [1-9, 0]"
                slots_info = app.favorites.format_favorites_slots()
                app.prompt_pane.set_text(
                    f"★ Favorites — {app.favorites.favorites_slot_count()}/10 slots used\n\n"
                    f"{slots_info}\n\n"
                    "Press 1-9/0 to quick-load\n"
                    "[F] return to prompt view\n"
                    "HOME reset to new prompt", width)
            elif app.executed_prompt_text:
                app.prompt_pane.title = "EXECUTING PROMPT"
                app.prompt_pane.set_text(app.executed_prompt_text, width)
            elif app.current_prompt:
                app.prompt_pane.title = f"PROMPT WORKSHOP — session v{app.prompt_version}"
                app.prompt_pane.set_text(app.current_prompt, width)
            else:
                app.prompt_pane.title = "NEW PROMPT — ready for dictation"
                # Clear lines so welcome_art renders (left-justified & dimmed)
                app.prompt_pane.lines = []
            app.prompt_pane.scroll_offset = 0
            return

        path = prompt_list[app.browser_index]
        if app.browser_view == "favorites":
            # Find which slot this favorite is in
            slot_label = "★"
            for si, sp in enumerate(app.favorites_slots):
                if sp and Path(sp) == path:
                    key = str((si + 1) % 10)
                    slot_label = f"★ Slot {si + 1} [key {key}]"
                    break
            n = len(prompt_list)
            idx = app.browser_index + 1
            app.prompt_pane.title = f"[{idx}/{n}] {slot_label}"
        else:
            try:
                rel = path.relative_to(app.history_base)
            except ValueError:
                rel = path
            n = len(prompt_list)
            idx = app.browser_index + 1
            app.prompt_pane.title = f"[{idx}/{n}] HISTORY: {rel}"

        try:
            content = path.read_text()
        except Exception as e:
            content = f"[Error: {e}]"

        # For history entries, combine prompt and response with ASCII headers
        if app.browser_view != "favorites":
            response_path = Path(str(path).replace("_prompt.md", "_response.md"))
            divider_w = max(1, width - 4)
            combined = f"{'=' * divider_w}\n  PROMPT\n{'=' * divider_w}\n\n{content}"
            if response_path.exists():
                try:
                    response_content = response_path.read_text()
                except Exception as e:
                    response_content = f"[Error: {e}]"
                combined += f"\n\n{'-' * divider_w}\n  RESPONSE\n{'-' * divider_w}\n\n{response_content}"
            else:
                combined += f"\n\n{'-' * divider_w}\n  RESPONSE\n{'-' * divider_w}\n\n(no response recorded)"
            app.prompt_pane.set_text(combined, width)
        else:
            app.prompt_pane.set_text(content, width)
        app.prompt_pane.scroll_offset = 0

    def set_dictation_info(self, width: int):
        """Show info box in dictation buffer when it's empty."""
        app = self.app
        if app.dictation_pane.lines:
            return  # don't overwrite existing content
        # Clear lines so welcome_art renders (left-justified & dimmed)
        app.dictation_pane.lines = []
        app.dictation_pane.scroll_offset = 0

    def set_agent_welcome(self, width: int):
        """Show welcome/help text in the agent terminal pane (first launch only)."""
        app = self.app
        if app.agent_welcome_shown:
            return
        app.agent_welcome_shown = True
        # Clear lines so welcome_art renders (left-justified & dimmed)
        app.agent_pane.lines = []
        app.agent_pane.line_colors = {}
        app.agent_pane.scroll_offset = 0

    def get_active_prompt_text(self) -> str | None:
        """Get the prompt text currently shown in the browser, for execution."""
        app = self.app
        prompt_list = self.current_browser_list()
        if app.browser_index >= 0 and app.browser_index < len(prompt_list):
            path = prompt_list[app.browser_index]
            try:
                raw = path.read_text()
                # Strip comment headers
                lines = [l for l in raw.split("\n") if not l.startswith("#")]
                return "\n".join(lines).strip()
            except Exception:
                return None
        elif app.current_prompt:
            return app.current_prompt
        elif app.executed_prompt_text:
            return app.executed_prompt_text
        return None
