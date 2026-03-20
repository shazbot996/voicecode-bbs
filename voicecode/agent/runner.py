"""Agent execution — stream processing, event parsing, stall detection."""

import json
import os
import time
import select
import subprocess
import threading

from voicecode.constants import AgentState, TTS_PROMPT_SUFFIX
from voicecode.ui.colors import *
from voicecode.tts.engine import extract_tts_summary, speak_text, stop_speaking
from voicecode.tts.cast import cast_tts_to_devices


class RunnerHelper:
    def __init__(self, app):
        self.app = app

    def emit_typewriter(self, text):
        """Queue text for typewriter display in the agent pane.

        Detects [TTS_SUMMARY] / [/TTS_SUMMARY] markers and switches
        typewriter color to white for the TTS summary block.
        """
        app = self.app
        app._tts_detect_buf = getattr(app, '_tts_detect_buf', '')
        app._tts_in_summary = getattr(app, '_tts_in_summary', False)

        app._tts_detect_buf += text

        while app._tts_detect_buf:
            if not app._tts_in_summary:
                idx = app._tts_detect_buf.find('[TTS_SUMMARY]')
                if idx == -1:
                    # Flush all but last 13 chars (tag length) in case tag spans chunks
                    safe = max(0, len(app._tts_detect_buf) - 13)
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
                    safe = max(0, len(app._tts_detect_buf) - 14)
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
        """Format a tool_use input dict into a concise display string."""
        if name == "Read":
            path = inp.get("file_path", "")
            parts = []
            if path:
                parts.append(path.split("/")[-1] if "/" in path else path)
            if inp.get("offset"):
                parts.append(f"L{inp['offset']}")
            if inp.get("limit"):
                parts.append(f"+{inp['limit']}")
            return " ".join(parts) if parts else ""
        elif name == "Edit":
            path = inp.get("file_path", "")
            short = path.split("/")[-1] if "/" in path else path
            old = inp.get("old_string", "")
            preview = old[:60].replace("\n", "\\n") + ("..." if len(old) > 60 else "")
            return f"{short}: {preview}" if preview else short
        elif name == "Write":
            path = inp.get("file_path", "")
            return path.split("/")[-1] if "/" in path else path
        elif name in ("Bash", "Task"):
            cmd = inp.get("command", inp.get("prompt", ""))
            return cmd[:80] + ("..." if len(cmd) > 80 else "")
        elif name in ("Grep", "Glob"):
            pat = inp.get("pattern", "")
            path = inp.get("path", "")
            return f"{pat}" + (f" in {path}" if path else "")
        elif name == "Agent":
            desc = inp.get("description", "")
            return desc
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
        self.emit_typewriter(f"\n>> REQUEST RECEIVED... ROUTING TO [{model_tag}] <<\n")
        self.emit_typewriter(">> INCOMING TRANSMISSION <<\n\n")

        # Add the "incoming transmission" header via typewriter
        self.emit_typewriter("═══ INCOMING TRANSMISSION ═══\n\n")

        try:
            prompt_with_tts = app.xfer_prompt_text + TTS_PROMPT_SUFFIX
            cmd = provider.build_execute_cmd(prompt_with_tts, app.session_id)
            app.agent_process = subprocess.Popen(
                cmd,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                bufsize=1,
                env=os.environ,
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
                stall_warned = False
                if not app.agent_first_output:
                    app.agent_first_output = True

                line = line.strip()
                if not line:
                    continue

                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    # Non-JSON output (e.g. stderr), show as-is
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
            app.ui_queue.put(("status", "Agent complete. Ready for next prompt.", CP_STATUS))

            # Speak the summary via TTS
            full_response = result_text or "".join(response_text_parts)
            summary = extract_tts_summary(full_response)
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
