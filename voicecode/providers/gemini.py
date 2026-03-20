"""Gemini CLI provider for VoiceCode BBS."""

import shlex

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

    def build_refine_cmd(self, prompt: str) -> list[str]:
        return self._get_base_cmd() + self._common_flags() + ["-p", prompt]

    def build_execute_cmd(self, prompt: str, session_id: str | None = None) -> list[str]:
        cmd = self._get_base_cmd() + self._common_flags() + ["-o", "stream-json"]
        if session_id:
            cmd += ["--resume", session_id]
        cmd += ["-p", prompt]
        return cmd

    def parse_init_event(self, event: dict) -> str | None:
        # Only capture session_id from init/system events to avoid
        # misinterpreting session fields on regular message events.
        etype = event.get("type", "")
        if etype not in ("init", "system", "session"):
            return None
        sid = event.get("session_id") or event.get("sessionId") or event.get("session")
        if sid and isinstance(sid, str):
            return sid
        return None

    def parse_text_event(self, event: dict) -> tuple[str, list] | None:
        if event.get("type") != "message":
            return None
        if event.get("role") != "assistant":
            return None
        text = event.get("content", "")
        tool_uses = []
        # Gemini may include tool_calls in the event
        for tc in event.get("tool_calls", []):
            tool_uses.append((tc.get("name", "?"), tc.get("args", {})))
        return (text, tool_uses) if text or tool_uses else None

    def parse_thinking_event(self, event: dict) -> str | None:
        if event.get("type") != "message" or event.get("role") != "assistant":
            return None
        thinking = event.get("thinking", "")
        return thinking if thinking else None

    def parse_tool_result_event(self, event: dict) -> str | None:
        if event.get("type") != "message" or event.get("role") != "tool":
            return None
        content = event.get("content", "")
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
        total_tokens = 0
        ctx_window = 1_000_000
        for _model, model_data in stats.get("models", {}).items():
            tokens = model_data.get("tokens", {})
            total_tokens += tokens.get("total", 0)
            ctx_window = tokens.get("contextWindow", ctx_window)
        return (total_tokens, ctx_window) if total_tokens else None

    def is_result_event(self, event: dict) -> str | None:
        if event.get("type") == "result":
            return event.get("result", "")
        return None
