"""Agent execution — stream processing, event parsing, stall detection."""

import json
import re
import time
import select
import subprocess
import threading

from voicecode.constants import AgentState, TTS_PROMPT_SUFFIX
from voicecode.providers.base import MODE_PLAN
from voicecode.ui.colors import *
from voicecode.tts.engine import extract_tts_summary, speak_text, stop_speaking
from voicecode.tts.cast import cast_tts_to_devices


# Everything the agent pane displays passes through sanitize_text().  Tool
# output reaches us verbatim -- `agy` runs shell commands on a PTY, so
# run_command results arrive CRLF-terminated and tab-indented (git status,
# git diff, ls -l ...) -- and curses interprets those bytes as cursor
# movement rather than drawing them:
#   \r  returns the cursor to column 0 of the physical screen row, so the
#       next characters paint over the left-hand panes ("output rendered
#       outside the agent terminal").
#   \t  advances to the next 8-column tab stop, overshooting the pane's
#       right border and wrapping onto the following screen row.
#   ESC sequences and other control codes render as multi-column caret
#       escapes (^[), which also overflow the pane's character-based clip.
# The pane wraps by character count, so anything that occupies more columns
# than it has characters breaks the layout.

# ANSI CSI/Fe escape sequences (colors, cursor moves, mode switches).
ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
# OSC sequences (e.g. terminal title: ESC ] 0 ; text BEL/ST), which the CSI
# pattern above only clips the two-byte introducer of.
ANSI_OSC = re.compile(r'\x1B\][^\x07\x1B]*(?:\x07|\x1B\\)?')

# Tab stops are terminal state we cannot track from a streamed chunk, so
# tabs become a fixed indent instead.
TAB_WIDTH = 4


def sanitize_text(text: str) -> str:
    """Strip terminal control codes so agent output cannot corrupt the curses UI.

    Removes ANSI escape sequences and carriage returns, expands tabs to
    spaces, and drops any remaining non-printable characters.  Newlines are
    the only control character preserved -- the pane treats them as line
    breaks rather than passing them to curses.
    """
    if not text:
        return text
    text = ANSI_OSC.sub('', text)
    text = ANSI_ESCAPE.sub('', text)
    text = text.replace('\r', '')
    text = text.replace('\t', ' ' * TAB_WIDTH)
    return "".join(ch for ch in text if ch.isprintable() or ch == '\n')


class RunnerHelper:
    def __init__(self, app):
        self.app = app

    def emit_typewriter(self, text):
        """Queue text for typewriter display in the agent pane.

        Detects [TTS_SUMMARY] / [/TTS_SUMMARY] markers and switches
        typewriter color to white for the TTS summary block.
        """
        text = sanitize_text(text)
        app = self.app
        app._tts_detect_buf = getattr(app, '_tts_detect_buf', '')
        app._tts_in_summary = getattr(app, '_tts_in_summary', False)

        app._tts_detect_buf += text

        while app._tts_detect_buf:
            if not app._tts_in_summary:
                idx = app._tts_detect_buf.find('[TTS_SUMMARY]')
                if idx == -1:
                    # Only hold back chars if a '[' exists in the tail that
                    # could be the start of a partially-received tag.  This
                    # avoids buffering 13 chars on every chunk, which caused
                    # visible mid-word freezes during streaming.
                    bracket = app._tts_detect_buf.rfind('[')
                    if bracket != -1 and bracket >= len(app._tts_detect_buf) - 13:
                        safe = bracket
                    else:
                        safe = len(app._tts_detect_buf)
                    for ch in app._tts_detect_buf[:safe]:
                        app.ui_queue.put(("typewriter_char", ch))
                    app._tts_detect_buf = app._tts_detect_buf[safe:]
                    break
                else:
                    # Flush text before the tag
                    for ch in app._tts_detect_buf[:idx]:
                        app.ui_queue.put(("typewriter_char", ch))
                    # Skip the tag itself, emit color change
                    app._tts_detect_buf = app._tts_detect_buf[idx + 13:]
                    app._tts_in_summary = True
                    app.ui_queue.put(("typewriter_color", CP_TTS))
            else:
                idx = app._tts_detect_buf.find('[/TTS_SUMMARY]')
                if idx == -1:
                    bracket = app._tts_detect_buf.rfind('[')
                    if bracket != -1 and bracket >= len(app._tts_detect_buf) - 14:
                        safe = bracket
                    else:
                        safe = len(app._tts_detect_buf)
                    for ch in app._tts_detect_buf[:safe]:
                        app.ui_queue.put(("typewriter_char", ch))
                    app._tts_detect_buf = app._tts_detect_buf[safe:]
                    break
                else:
                    # Flush text before the closing tag
                    for ch in app._tts_detect_buf[:idx]:
                        app.ui_queue.put(("typewriter_char", ch))
                    # Skip the closing tag, reset color
                    app._tts_detect_buf = app._tts_detect_buf[idx + 14:]
                    app._tts_in_summary = False
                    app.ui_queue.put(("typewriter_color", None))

    def flush_tts_detect_buf(self):
        """Flush any remaining chars in the TTS detection buffer."""
        app = self.app
        buf = getattr(app, '_tts_detect_buf', '')
        if buf:
            for ch in buf:
                app.ui_queue.put(("typewriter_char", ch))
            app._tts_detect_buf = ''

    def format_tool_input(self, name, inp):
        """Format a tool_use input dict into a concise display string.

        Handles both Claude's PascalCase tools with snake_case params and
        Antigravity's snake_case tools with PascalCase params.
        """
        if name in ("Read", "view_file"):
            path = inp.get("file_path", "") or inp.get("AbsolutePath", "")
            parts = []
            if path:
                parts.append(path.split("/")[-1] if "/" in path else path)
            if inp.get("offset"):
                parts.append(f"L{inp['offset']}")
            if inp.get("limit"):
                parts.append(f"+{inp['limit']}")
            return " ".join(parts) if parts else ""
        elif name in ("Edit", "replace_file_content", "multi_replace_file_content",
                      "sed_file"):
            path = inp.get("file_path", "") or inp.get("TargetFile", "")
            short = path.split("/")[-1] if "/" in path else path
            old_str = inp.get("old_string", "")
            preview = (old_str[:60].replace("\n", "\\n")
                       + ("..." if len(old_str) > 60 else ""))
            return f"{short}: {preview}" if preview else short
        elif name in ("Write", "write_to_file"):
            path = inp.get("file_path", "") or inp.get("TargetFile", "")
            return path.split("/")[-1] if "/" in path else path
        elif name in ("Bash", "Task", "run_command", "command_status",
                      "send_command_input"):
            cmd = (inp.get("command", "") or inp.get("CommandLine", "")
                   or inp.get("prompt", ""))
            return cmd[:80] + ("..." if len(cmd) > 80 else "")
        elif name in ("Grep", "Glob", "grep_search", "find_by_name"):
            # grep_search uses Query/SearchPath; find_by_name uses
            # Pattern/SearchDirectory (verified against the CLI).
            pat = (inp.get("pattern", "") or inp.get("query", "")
                   or inp.get("Query", "") or inp.get("Pattern", ""))
            path = (inp.get("path", "") or inp.get("SearchPath", "")
                    or inp.get("SearchDirectory", ""))
            return f"{pat}" + (f" in {path}" if path else "")
        elif name in ("ListDirectory", "list_dir"):
            path = inp.get("dir_path", "") or inp.get("DirectoryPath", "")
            return path.split("/")[-1] if "/" in path else path
        elif name in ("WebSearch", "search_web"):
            q = inp.get("query", "") or inp.get("Query", "")
            return q[:80] + ("..." if len(q) > 80 else "")
        elif name in ("WebFetch", "read_url_content"):
            return inp.get("url", "") or inp.get("Url", "")
        elif name in ("Agent", "invoke_subagent"):
            return inp.get("description", "") or inp.get("Name", "")
        elif name == "manage_task":
            return str(inp.get("Action", ""))[:80]
        else:
            s = json.dumps(inp)
            return s[:80] + ("..." if len(s) > 80 else "")

    def run_agent(self):
        """Run AI agent in background, streaming verbose output."""
        app = self.app

        # Let the download animation play for ~3 seconds (cancellable)
        if app._agent_cancel.wait(3.0):
            return  # cancelled during animation

        app.ui_queue.put(("agent_state", AgentState.RECEIVING))
        app.ui_queue.put(("status", "Agent receiving transmission...", CP_STATUS))

        provider = app.ai_provider

        # BBS-style announcement block before the session header
        model_tag = provider.name.upper()
        if app.agent_run_mode == MODE_PLAN:
            # Plan mode is read-only and writes nothing -- that must be
            # visible in the transcript or the run looks like a failure.
            model_tag += " / PLAN"
        self.emit_typewriter(f"\n>> REQUEST RECEIVED... ROUTING TO [{model_tag}] <<\n")
        self.emit_typewriter(">> INCOMING TRANSMISSION <<\n\n")

        # Add the "incoming transmission" header via typewriter
        self.emit_typewriter("═══ INCOMING TRANSMISSION ═══\n\n")

        try:
            prompt_with_tts = app.xfer_prompt_text + TTS_PROMPT_SUFFIX
            cmd = provider.build_execute_cmd(prompt_with_tts, app.session_id,
                                             app.agent_run_mode)
            app.agent_process = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=provider.get_env(),
                start_new_session=True,
            )

            result_text = ""
            response_text_parts = []
            stdout_fd = app.agent_process.stdout.fileno()
            app.agent_last_activity = time.time()
            stall_warned = False

            while True:
                # Non-blocking poll: check for data every 0.5s so we can
                # update the UI activity indicator and detect stalls.
                ready, _, _ = select.select([stdout_fd], [], [], 0.5)
                if not ready:
                    # No data available — check for stall
                    if app._agent_cancel.is_set() or app.agent_state == AgentState.IDLE:
                        break
                    idle_secs = time.time() - app.agent_last_activity
                    if idle_secs >= 60 and not stall_warned:
                        stall_warned = True
                        app.ui_queue.put(("status",
                            f"No output for {int(idle_secs)}s — agent may be stalled. Press K to kill.",
                            CP_XFER))
                    continue

                line = app.agent_process.stdout.readline()
                if not line:
                    break
                if app.agent_state == AgentState.IDLE:
                    break

                app.agent_last_activity = time.time()
                if stall_warned:
                    stall_warned = False
                    app.ui_queue.put(("status", "", CP_STATUS))
                if not app.agent_first_output:
                    app.agent_first_output = True

                line = line.strip()
                if not line:
                    continue

                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    # Non-JSON output (e.g. stderr) — surface it as-is.
                    self.emit_typewriter(line + "\n")
                    continue

                # Capture session_id from init event
                sid = provider.parse_init_event(event)
                if sid:
                    app.ui_queue.put(("session_id", sid))

                # Assistant text + tool use
                text_result = provider.parse_text_event(event)
                if text_result:
                    text, tool_uses = text_result
                    if text:
                        response_text_parts.append(text)
                        self.emit_typewriter(text)
                    for name, inp in tool_uses:
                        detail = self.format_tool_input(name, inp)
                        self.emit_typewriter(f"\n▶ {name}: {detail}\n")

                # Thinking
                thinking = provider.parse_thinking_event(event)
                if thinking:
                    for tl in thinking.split("\n"):
                        self.emit_typewriter(f"  .. {tl}\n")

                # Tool results
                tool_preview = provider.parse_tool_result_event(event)
                if tool_preview:
                    self.emit_typewriter(f"  ◀ {tool_preview}\n")

                # Result event (final)
                result_check = provider.is_result_event(event)
                if result_check is not None:
                    result_text = result_check
                    # Extract context usage
                    ctx = provider.parse_context_usage(event)
                    if ctx:
                        app.ui_queue.put(("context_usage", ctx[0], ctx[1]))

            # If the agent was killed, don't post completion messages
            if app._agent_cancel.is_set():
                return

            if app.agent_process:
                app.agent_process.wait()

            # Flush any remaining TTS detection buffer
            self.flush_tts_detect_buf()

            # End marker — reset color to default for the transmission footer
            app.ui_queue.put(("typewriter_color", None))
            self.emit_typewriter("\n\n═══ END TRANSMISSION ═══\n")
            self.flush_tts_detect_buf()

            app.ui_queue.put(("agent_state", AgentState.DONE))
            app.ui_queue.put(("clear_dictation_buffer",))
            app.ui_queue.put(("status", "Agent complete. Ready for next prompt.", CP_STATUS))

            # Speak the summary via TTS.  Check the result event first, then
            # the accumulated stream deltas: the two are normally identical,
            # but a provider whose result event carries an abridged response
            # would otherwise lose a summary that did stream through.
            streamed_response = "".join(response_text_parts)
            summary = (extract_tts_summary(result_text)
                       or extract_tts_summary(streamed_response))
            if summary:
                app.last_tts_summary = summary
                app.execution.save_response_to_history(summary)
                stop_speaking()
                mute_local = (app.cast_enabled and app.cast_mute_local_tts
                              and app.cast_selected_devices)
                if not mute_local:
                    speak_text(summary, on_done=lambda: app.ui_queue.put(
                        ("status", "Ready for next prompt.", CP_STATUS)))
                    app.ui_queue.put(("status", "Speaking summary...", CP_STATUS))

                # Cast to Google Cast / Nest speakers if enabled
                if app.cast_enabled and app.cast_selected_devices:
                    cast_tts_to_devices(summary,
                                        app.cast_selected_devices,
                                        ui_queue=app.ui_queue,
                                        volume=app.cast_volume)
            else:
                app.execution.save_response_to_history("(no TTS summary returned)", is_error=True)

        except FileNotFoundError:
            if not app._agent_cancel.is_set():
                app.execution.save_response_to_history(
                    f"ERROR: '{provider.binary}' CLI not found", is_error=True)
                app.ui_queue.put(("agent_state", AgentState.DONE))
                app.ui_queue.put(("status", f"Error: '{provider.binary}' CLI not found!", CP_STATUS))
        except Exception as e:
            if not app._agent_cancel.is_set():
                app.execution.save_response_to_history(
                    f"ERROR: {e}", is_error=True)
                app.ui_queue.put(("agent_state", AgentState.DONE))
                app.ui_queue.put(("status", f"Agent error: {e}", CP_STATUS))

    def kill_agent(self, sync=False):
        app = self.app
        # Signal the cancel event so the animation sleep exits early
        app._agent_cancel.set()
        proc = app.agent_process
        app.agent_process = None
        stop_speaking()
        app.agent_state = AgentState.IDLE
        app.typewriter_queue.clear()
        app._typewriter_budget = 0.0
        app._typewriter_last_ts = 0.0
        if proc:
            def _reap():
                try:
                    proc.terminate()  # SIGTERM for graceful shutdown
                    try:
                        proc.wait(timeout=3.0)
                    except subprocess.TimeoutExpired:
                        proc.kill()  # SIGKILL as last resort
                except Exception:
                    pass
            if sync:
                _reap()
            else:
                # Terminate in background to avoid blocking the UI thread
                threading.Thread(target=_reap, daemon=True).start()
        # Restore source pane if still pending
        if app._agent_source_pane is not None:
            app._agent_source_pane.color_pair = app._agent_source_original_color
            app._agent_source_pane = None
            app._agent_source_original_color = None
        app.set_status("Agent terminated.")

    def clear_session(self):
        """Clear the current session, starting fresh next execution."""
        app = self.app
        app.session_id = None
        app.session_turns = 0
        app.context_tokens_used = 0
        app.context_window_size = 0
        app.set_status("Session cleared. Next prompt starts a new conversation.")
