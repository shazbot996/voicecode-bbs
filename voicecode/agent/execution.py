"""Prompt execution — execute, save, history management."""

import datetime
import time
import threading
from pathlib import Path

from voicecode.constants import AgentState
from voicecode.ui.colors import *
from voicecode.settings import slug_from_text, next_seq


class ExecutionHelper:
    def __init__(self, app):
        self.app = app

    def execute_prompt(self):
        app = self.app
        prompt_text = app.browser.get_active_prompt_text()
        if not prompt_text:
            app.set_status("No prompt to execute. Refine or browse to one first!")
            return

        # Show executed prompt in yellow in the prompt browser (persists until new prompt)
        app.executed_prompt_text = prompt_text
        if app._prompt_pane_original_color is None:
            app._prompt_pane_original_color = app.prompt_pane.color_pair
        app.prompt_pane.color_pair = CP_XFER
        app.browser_view = "active"
        app.browser_index = -1
        w = app.stdscr.getmaxyx()[1] // 2
        app.browser.load_browser_prompt(w)

        # Clear prompt state so next dictation starts fresh.
        # Note: fragments and buffer file are preserved until the agent
        # succeeds — see the "clear_dictation_buffer" UI queue handler.
        app.current_prompt = None
        app.prompt_version = 0
        app.prompt_saved = True
        app.dictation_pane.lines.clear()
        app.dictation_pane.scroll_offset = 0

        app._last_history_prompt_path = self.save_to_history(prompt_text)

        app.xfer_prompt_text = prompt_text
        app.xfer_bytes = len(prompt_text.encode())
        app.xfer_progress = 0.0
        app.xfer_frame = 0
        app.xfer_start_time = time.time()
        app.agent_state = AgentState.DOWNLOADING
        app.typewriter_queue.clear()
        app._typewriter_budget = 0.0
        app._typewriter_last_ts = 0.0
        app.agent_first_output = False
        app.agent_last_activity = 0.0
        app._typewriter_line_color = None
        app._tts_detect_buf = ''
        app._tts_in_summary = False

        # Reset agent pane with welcome text (visible until output arrives)
        app.browser.set_agent_welcome(40)

        app.set_status("Initiating ZMODEM transfer to agent...")

        # Start agent after a brief animation delay
        app._agent_cancel.clear()
        threading.Thread(target=app.runner.run_agent, daemon=True).start()

    def execute_raw(self):
        """Execute raw dictation fragments directly, skipping refinement."""
        app = self.app
        if not app.fragments:
            app.set_status("No fragments to execute. Dictate something first!")
            return
        if app.agent_state not in (AgentState.IDLE, AgentState.DONE):
            app.set_status("Agent is busy. Wait or kill it first.")
            return
        prompt_text = " ".join(app.fragments)
        # Fragments and buffer file preserved until agent succeeds —
        # see the "clear_dictation_buffer" UI queue handler.
        app._last_history_prompt_path = self.save_to_history(prompt_text)
        # Show executed prompt in yellow in the prompt browser (persists until new prompt)
        app.executed_prompt_text = prompt_text
        if app._prompt_pane_original_color is None:
            app._prompt_pane_original_color = app.prompt_pane.color_pair
        app.prompt_pane.color_pair = CP_XFER
        app.browser_view = "active"
        app.browser_index = -1
        w = app.stdscr.getmaxyx()[1] // 2
        app.browser.load_browser_prompt(w)
        # Clear dictation buffer
        app.dictation_pane.lines.clear()
        app.dictation_pane.scroll_offset = 0
        app.set_status("Executing raw dictation directly...")
        # Reuse the standard execution path
        app.xfer_prompt_text = prompt_text
        app.xfer_bytes = len(prompt_text.encode())
        app.xfer_progress = 0.0
        app.xfer_frame = 0
        app.xfer_start_time = time.time()
        app.agent_state = AgentState.DOWNLOADING
        app.typewriter_queue.clear()
        app._typewriter_budget = 0.0
        app._typewriter_last_ts = 0.0
        app.agent_first_output = False
        app.agent_last_activity = 0.0
        app._typewriter_line_color = None
        app._tts_detect_buf = ''
        app._tts_in_summary = False
        app.browser.set_agent_welcome(40)
        app._agent_cancel.clear()
        threading.Thread(target=app.runner.run_agent, daemon=True).start()

    def save_prompt(self):
        app = self.app
        if not app.current_prompt:
            app.set_status("No prompt to save. Refine first!")
            return

        now = datetime.datetime.now()
        app.history_base.mkdir(parents=True, exist_ok=True)

        seq = next_seq(app.history_base)
        slug = slug_from_text(app.current_prompt)
        filename = app.history_base / f"{seq:03d}_{slug}_prompt.md"

        with open(filename, "w") as f:
            f.write(f"# Prompt v{app.prompt_version}\n")
            f.write(f"# Saved: {now.isoformat()}\n")
            f.write(f"# Fragments: {len(app.fragments)}\n\n")
            f.write(app.current_prompt)
            f.write("\n")

        app.browser.scan_history_prompts()
        app.browser_index = -1
        app.prompt_saved = True
        app.set_status(f"Saved: {filename}")

    def save_to_history(self, prompt_text) -> Path | None:
        """Auto-save every executed prompt to the history subfolder.

        Returns the prompt file path so the response can be written later.
        """
        app = self.app
        if not prompt_text:
            return None
        now = datetime.datetime.now()
        app.history_base.mkdir(parents=True, exist_ok=True)
        seq = next_seq(app.history_base)
        slug = slug_from_text(prompt_text)
        filename = app.history_base / f"{seq:03d}_{slug}_prompt.md"
        with open(filename, "w") as f:
            f.write(f"# Executed: {now.isoformat()}\n\n")
            f.write(prompt_text)
            f.write("\n")
        app.browser.scan_history_prompts()
        return filename

    def save_response_to_history(self, response_text: str, is_error: bool = False):
        """Write a response file paired with the last saved prompt file."""
        app = self.app
        prompt_path = app._last_history_prompt_path
        if not prompt_path:
            return
        response_path = Path(str(prompt_path).replace("_prompt.md", "_response.md"))
        try:
            now = datetime.datetime.now()
            with open(response_path, "w") as f:
                if is_error:
                    f.write(f"# Error: {now.isoformat()}\n\n")
                else:
                    f.write(f"# Response: {now.isoformat()}\n\n")
                f.write(response_text)
                f.write("\n")
        except OSError:
            pass

    def start_refine(self):
        app = self.app
        if not app.fragments:
            app.set_status("No fragments to refine. Dictate something first!")
            return
        app.refining = True
        app.set_status(f"Sending to {app.ai_provider.name} for refinement...", CP_STATUS)
        threading.Thread(target=self.do_refine, daemon=True).start()

    def do_refine(self):
        app = self.app
        fragments_copy = list(app.fragments)
        current = app.current_prompt
        from voicecode.agent.refine import refine_with_llm
        result = refine_with_llm(
            fragments_copy, current,
            status_callback=lambda msg: app.ui_queue.put(("status", msg, CP_STATUS)),
            provider=app.ai_provider)
        app.ui_queue.put(("refined", result))
        app.ui_queue.put(("status", f"Prompt refined! (v{app.prompt_version + 1})", CP_STATUS))

    def new_prompt(self):
        """Start a new prompt. If current is unsaved, ask to save first."""
        app = self.app
        if app.current_prompt and not app.prompt_saved:
            app.confirming_new = True
            app.set_status("Unsaved prompt! Save first? [Y]es / [N]o / any key to cancel")
            return
        self.do_new_prompt()

    def clear_executed_prompt(self):
        """Clear the executed prompt display from the prompt browser."""
        app = self.app
        if app.executed_prompt_text is not None:
            app.executed_prompt_text = None
            if app._prompt_pane_original_color is not None:
                app.prompt_pane.color_pair = app._prompt_pane_original_color
                app._prompt_pane_original_color = None

    def do_new_prompt(self):
        """Actually reset to a new prompt."""
        app = self.app
        self.clear_executed_prompt()
        app.fragments.clear()
        app.input_handler.clear_buffer_file()
        app.current_prompt = None
        app.prompt_version = 0
        app.prompt_saved = True
        app.dictation_pane.lines.clear()
        app.dictation_pane.scroll_offset = 0
        app.browser_view = "active"
        app.browser_index = -1
        w = app.stdscr.getmaxyx()[1] // 2
        app.browser.load_browser_prompt(w)
        app.browser.set_dictation_info(w)
        app.browser.set_agent_welcome(w)
        app.set_status("New prompt started. Dictate away!")

    def confirm_edit_historical(self):
        """Show confirmation before editing a historical/saved prompt."""
        app = self.app
        app.confirming_edit_historical = True
        app.set_status("Edit this historical prompt? [Y] Copy as new working prompt / [other] Cancel")

    def copy_historical_to_current(self):
        """Copy the currently browsed historical prompt into the current prompt slot."""
        app = self.app
        prompt_text = app.browser.get_active_prompt_text()
        if not prompt_text:
            app.set_status("Could not read historical prompt.")
            return
        # Copy historical prompt as the new working prompt, preserving
        # any in-progress dictation so the user can refine into it.
        self.clear_executed_prompt()
        app.current_prompt = prompt_text
        app.prompt_version = 1
        app.prompt_saved = False
        app.browser_view = "active"
        app.browser_index = -1
        w = app.stdscr.getmaxyx()[1] // 2
        app.browser.load_browser_prompt(w)
        app.browser.set_dictation_info(w)
        app.set_status("Historical prompt copied as new working prompt. Dictate to refine or press E to execute.")
