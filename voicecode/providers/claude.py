"""Claude CLI provider for VoiceCode BBS."""

import shlex

from voicecode.providers.base import CLIProvider


class ClaudeProvider(CLIProvider):
    name = "Claude"
    binary = "claude"

    def build_refine_cmd(self, prompt: str) -> list[str]:
        return self._get_base_cmd() + ["--print", "-p", prompt]

    def build_execute_cmd(self, prompt: str, session_id: str | None = None) -> list[str]:
        cmd = self._get_base_cmd() + ["--print", "--verbose", "--output-format",
               "stream-json", "--dangerously-skip-permissions"]
        if session_id:
            cmd += ["--resume", session_id]
        cmd += ["-p", prompt]
        return cmd

    def parse_init_event(self, event: dict) -> str | None:
        if event.get("type") == "system" and event.get("subtype") == "init":
            return event.get("session_id") or None
        return None

    def parse_text_event(self, event: dict) -> tuple[str, list] | None:
        if event.get("type") != "assistant":
            return None
        text_parts = []
        tool_uses = []
        msg = event.get("message", {})
        for block in msg.get("content", []):
            bt = block.get("type", "")
            if bt == "text":
                text_parts.append(block.get("text", ""))
            elif bt == "tool_use":
                tool_uses.append((block.get("name", "?"), block.get("input", {})))
        return ("".join(text_parts), tool_uses) if text_parts or tool_uses else None

    def parse_thinking_event(self, event: dict) -> str | None:
        if event.get("type") != "assistant":
            return None
        msg = event.get("message", {})
        thinking_parts = []
        for block in msg.get("content", []):
            if block.get("type") == "thinking":
                t = block.get("thinking", "")
                if t:
                    thinking_parts.append(t)
        return "\n".join(thinking_parts) if thinking_parts else None

    def parse_tool_result_event(self, event: dict) -> str | None:
        if event.get("type") != "user":
            return None
        content = event.get("content", [])
        if not isinstance(content, list):
            return None
        previews = []
        for item in content:
            if item.get("type") == "tool_result":
                tool_text = item.get("content", "")
                if isinstance(tool_text, list):
                    tool_text = " ".join(
                        c.get("text", "") for c in tool_text if c.get("type") == "text")
                if tool_text:
                    preview = tool_text[:200].replace("\n", " ")
                    if len(tool_text) > 200:
                        preview += f"... ({len(tool_text)} chars)"
                    previews.append(preview)
        return "\n".join(previews) if previews else None

    def parse_context_usage(self, event: dict) -> tuple[int, int] | None:
        if event.get("type") != "result":
            return None
        model_usage = event.get("modelUsage", {})
        for _model, usage_data in model_usage.items():
            ctx_window = usage_data.get("contextWindow", 0)
            input_t = usage_data.get("inputTokens", 0)
            output_t = usage_data.get("outputTokens", 0)
            cache_read = usage_data.get("cacheReadInputTokens", 0)
            cache_create = usage_data.get("cacheCreationInputTokens", 0)
            total = input_t + output_t + cache_read + cache_create
            return (total, ctx_window)
        return None

    def is_result_event(self, event: dict) -> str | None:
        if event.get("type") == "result":
            return event.get("result", "")
        return None
