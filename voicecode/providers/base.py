"""Abstract base class for CLI AI providers."""

import os
import shutil
import subprocess


class CLIProvider:
    """Base class for CLI-based AI providers (Claude, Gemini, etc.)."""

    name: str = "Unknown"
    binary: str = "unknown"
    command_override: str | None = None

    def _get_base_cmd(self) -> list[str]:
        if self.command_override:
            return self.command_override.split()
        return [self.binary]

    def is_installed(self) -> bool:
        cmd = self._get_base_cmd()[0]
        return shutil.which(cmd) is not None

    def get_version(self) -> str | None:
        try:
            cmd = self._get_base_cmd() + ["--version"]
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            return result.stdout.strip() if result.returncode == 0 else None
        except Exception:
            return None

    def get_env(self) -> dict[str, str]:
        """Return the environment dict for subprocess calls.

        Subclasses can override to modify env (e.g. removing proxy vars).
        """
        return os.environ.copy()

    def build_refine_cmd(self, prompt: str) -> list[str]:
        raise NotImplementedError

    def build_execute_cmd(self, prompt: str, session_id: str | None = None) -> list[str]:
        raise NotImplementedError

    def parse_init_event(self, event: dict) -> str | None:
        """Extract session ID from an init event, or None."""
        return None

    def parse_text_event(self, event: dict) -> tuple[str, list] | None:
        """Extract (text, [(tool_name, tool_input), ...]) from a text event."""
        return None

    def parse_thinking_event(self, event: dict) -> str | None:
        return None

    def parse_tool_result_event(self, event: dict) -> str | None:
        return None

    def parse_context_usage(self, event: dict) -> tuple[int, int] | None:
        return None

    def is_result_event(self, event: dict) -> str | None:
        return None
