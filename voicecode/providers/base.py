"""Abstract base class for CLI AI providers."""

import os
import shlex
import shutil
import subprocess
from pathlib import Path

# Shared across providers (one constant for both -- see the migration plan).
# Claude reports a real contextWindow in modelUsage and uses this only as a
# fallback; Antigravity reports none and always uses it.
DEFAULT_CONTEXT_WINDOW = 1_000_000

# Execution modes, mapped to per-provider flags by each subclass.
MODE_BUILD = "build"
MODE_PLAN = "plan"


class CLIProvider:
    """Base class for CLI-based AI providers (Claude, Antigravity)."""

    name: str = "Unknown"
    binary: str = "unknown"

    # Full base invocation string, e.g. "claude" or "claude --effort high".
    # None means "use `binary` as-is".
    command_override: str | None = None

    # Explicitly selected model id/alias; None means "let the CLI decide".
    model: str | None = None

    # Working directory to ground the agent in; set by the app at startup
    # and whenever the working_dir setting changes.
    workspace_dir: str | None = None

    # [(id_or_None, display_label), ...] -- the first entry is always the
    # "let the CLI decide" option.
    MODELS: list[tuple[str | None, str]] = [(None, "Default")]

    # Model applied when no choice has been persisted yet.
    DEFAULT_MODEL: str | None = None

    def _get_base_cmd(self) -> list[str]:
        if self.command_override:
            return shlex.split(self.command_override)
        return [self.binary]

    def base_command_string(self) -> str:
        """The editable execution string shown in Settings."""
        return self.command_override or self.binary

    def _binary_path(self) -> str:
        """Just the executable, without any user-appended flags."""
        cmd = self._get_base_cmd()
        return cmd[0] if cmd else self.binary

    def is_installed(self) -> bool:
        return shutil.which(self._binary_path()) is not None

    def get_version(self) -> str | None:
        try:
            result = subprocess.run([self._binary_path(), "--version"],
                                    capture_output=True, text=True, timeout=10,
                                    stdin=subprocess.DEVNULL)
            return result.stdout.strip() if result.returncode == 0 else None
        except Exception:
            return None

    def get_env(self) -> dict[str, str]:
        """Return the environment dict for subprocess calls.

        Subclasses can override to modify env.
        """
        env = os.environ.copy()
        # Ensure commands are non-interactive to prevent terminal corruption
        env["TERM"] = "dumb"
        env["GIT_TERMINAL_PROMPT"] = "0"
        env["GIT_EDITOR"] = "true"
        env["EDITOR"] = "true"
        return env

    # ─── Workspace ──────────────────────────────────────────────────

    def set_workspace_dir(self, path: str | None):
        """Set the directory the agent should be grounded in."""
        self.workspace_dir = path

    def resolved_workspace_dir(self) -> str | None:
        """The workspace as an existing absolute path, or None.

        Passed as the subprocess `cwd`. Load-bearing for two reasons: it is
        the only thing that grounds Claude in the configured project (unlike
        `agy` it gets no --add-dir), and each CLI resolves its own settings
        files -- including the user's permission deny rules -- relative to
        the working directory, so a stale cwd silently applies the wrong
        project's rules. Returns None for an unset or missing directory so
        the subprocess inherits ours instead of failing to spawn.
        """
        if not self.workspace_dir:
            return None
        path = Path(self.workspace_dir).expanduser()
        return str(path) if path.is_dir() else None

    # ─── Model selection ────────────────────────────────────────────

    def list_models(self) -> list[tuple[str | None, str]]:
        """Return selectable models. Subclasses may query the CLI."""
        return self.MODELS

    def model_label(self) -> str:
        """Human label for the active model, for the header ribbon."""
        for mid, label in self.list_models():
            if mid == self.model:
                return label
        return self.model or "Default"

    def set_model(self, model_id: str | None):
        self.model = model_id

    # ─── Command building ───────────────────────────────────────────

    def build_refine_cmd(self, prompt: str) -> list[str]:
        raise NotImplementedError

    def build_execute_cmd(self, prompt: str, session_id: str | None = None,
                          run_mode: str = MODE_BUILD) -> list[str]:
        raise NotImplementedError

    def describe_execute_cmd(self, run_mode: str = MODE_BUILD) -> str:
        """Rendered execution string for the Settings preview row."""
        try:
            return " ".join(self.build_execute_cmd("<prompt>", None, run_mode))
        except Exception:
            return self.base_command_string()

    # ─── Event parsing ──────────────────────────────────────────────

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
