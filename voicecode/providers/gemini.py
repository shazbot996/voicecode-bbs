"""Gemini CLI provider for VoiceCode BBS."""

import os

from voicecode.providers.base import CLIProvider


class GeminiProvider(CLIProvider):
    name = "Gemini"
    binary = "gemini"
    disable_proxy: bool = False

    def _common_flags(self) -> list[str]:
        flags = ["--yolo"]
        if self.disable_proxy:
            flags.append("--proxy=false")
        return flags

    def get_env(self) -> dict[str, str]:
        """Return env dict, stripping proxy vars if disable_proxy is set."""
        env = os.environ.copy()
        # Never pass GEMINI_API_KEY — corporate auth does not use it, and
        # its presence causes the CLI to print a distracting banner message.
        env.pop("GEMINI_API_KEY", None)
        if self.disable_proxy:
            for key in ("HTTPS_PROXY", "https_proxy", "HTTP_PROXY", "http_proxy"):
                env.pop(key, None)
        return env

    def build_refine_cmd(self, prompt: str) -> list[str]:
        return self._get_base_cmd() + self._common_flags() + ["-p", prompt]

    def build_execute_cmd(self, prompt: str, session_id: str | None = None) -> list[str]:
        cmd = self._get_base_cmd() + self._common_flags() + ["-o", "stream-json"]
        if session_id:
            cmd += ["--resume", session_id]
        cmd += ["-p", prompt]
        return cmd

    def parse_init_event(self, event: dict) -> str | None:
        # Only capture session_id from init events to avoid
        # misinterpreting session fields on regular message events.
        etype = event.get("type", "")
        if etype != "init":
            return None
        sid = event.get("session_id") or event.get("sessionId") or event.get("session")
        if sid and isinstance(sid, str):
            return sid
        return None

    def parse_text_event(self, event: dict) -> tuple[str, list] | None:
        etype = event.get("type", "")

        # Assistant message events carry streamed text content
        if etype == "message" and event.get("role") == "assistant":
            text = event.get("content", "")
            return (text, []) if text else None

        # Tool use events are separate from message events in Gemini CLI
        if etype == "tool_use":
            tool_name = event.get("tool_name", "?")
            tool_params = event.get("parameters", {})
            return ("", [(tool_name, tool_params)])

        return None

    def parse_thinking_event(self, event: dict) -> str | None:
        if event.get("type") != "message" or event.get("role") != "assistant":
            return None
        thinking = event.get("thinking", "")
        return thinking if thinking else None

    def parse_tool_result_event(self, event: dict) -> str | None:
        if event.get("type") != "tool_result":
            return None
        # Successful tool results have an "output" field
        content = event.get("output", "")
        # Error tool results have an "error" dict
        error = event.get("error")
        if error and isinstance(error, dict):
            content = content or f"ERROR ({error.get('type', '?')}): {error.get('message', '')}"
        if content:
            preview = str(content)[:200].replace("\n", " ")
            if len(str(content)) > 200:
                preview += f"... ({len(str(content))} chars)"
            return preview
        return None

    def parse_context_usage(self, event: dict) -> tuple[int, int] | None:
        if event.get("type") != "result":
            return None
        stats = event.get("stats", {})
        total_tokens = stats.get("total_tokens", 0)
        # Gemini CLI stats are flat: total_tokens, input_tokens, output_tokens
        if total_tokens:
            # Gemini 2.5 Pro context window is 1M tokens
            ctx_window = 1_000_000
            return (total_tokens, ctx_window)
        return None

    def is_result_event(self, event: dict) -> str | None:
        if event.get("type") == "result":
            return event.get("status", "")
        return None
