"""Antigravity CLI (`agy`) provider for VoiceCode BBS."""

import subprocess
from pathlib import Path

from voicecode.providers.base import (
    CLIProvider, DEFAULT_CONTEXT_WINDOW, MODE_BUILD, MODE_PLAN,
)

# Fallback list, mirroring `agy models` at CLI v1.1.22. Used when the
# subprocess query fails (offline, auth expired, CLI missing).
_FALLBACK_MODELS: list[tuple[str | None, str]] = [
    (None, "Default"),
    ("gemini-3.1-pro-high", "Gemini 3.1 Pro (High)"),
    ("gemini-3.1-pro-low", "Gemini 3.1 Pro (Low)"),
    ("gemini-3.7-flash-high", "Gemini 3.7 Flash (High)"),
    ("gemini-3.7-flash-medium", "Gemini 3.7 Flash (Medium)"),
    ("gemini-3.7-flash-low", "Gemini 3.7 Flash (Low)"),
    ("gemini-3.6-flash-high", "Gemini 3.6 Flash (High)"),
    ("gemini-3.6-flash-medium", "Gemini 3.6 Flash (Medium)"),
    ("gemini-3.6-flash-low", "Gemini 3.6 Flash (Low)"),
    ("gemini-3.5-flash-high", "Gemini 3.5 Flash (High)"),
    ("gemini-3.5-flash-medium", "Gemini 3.5 Flash (Medium)"),
    ("gemini-3.5-flash-low", "Gemini 3.5 Flash (Low)"),
]


class AntigravityProvider(CLIProvider):
    name = "Antigravity"
    binary = "agy"

    MODELS = _FALLBACK_MODELS
    DEFAULT_MODEL = "gemini-3.1-pro-high"

    def __init__(self):
        # Per-instance so the singleton caches once per process run.
        self._model_cache: list[tuple[str | None, str]] | None = None

    # ─── Model discovery ────────────────────────────────────────────

    def list_models(self) -> list[tuple[str | None, str]]:
        """Query `agy models`, cached for the process lifetime.

        Called from the settings overlay on the UI thread, so it must never
        block indefinitely: 10s timeout, cached result, static fallback.
        """
        if self._model_cache is not None:
            return self._model_cache
        models: list[tuple[str | None, str]] | None = [(None, "Default")]
        try:
            r = subprocess.run([self._binary_path(), "models"],
                               capture_output=True, text=True, timeout=10)
            for line in r.stdout.splitlines():
                # Skips the "Fetching available models..." preamble line.
                if "\t" not in line:
                    continue
                mid, label = line.split("\t", 1)
                mid, label = mid.strip(), label.strip()
                if mid:
                    models.append((mid, label or mid))
        except Exception:
            models = None
        self._model_cache = models if models and len(models) > 1 else _FALLBACK_MODELS
        return self._model_cache

    # ─── Command building ───────────────────────────────────────────

    def _common_flags(self, run_mode: str) -> list[str]:
        # Unlike Claude, --dangerously-skip-permissions does NOT defeat
        # --mode plan on `agy` (verified: plan mode still refused to write to
        # the workspace with both flags present), so it is kept in both modes
        # to keep read tools auto-approved.
        flags = ["--dangerously-skip-permissions"]
        if self.workspace_dir:
            # Without --add-dir, `agy` uses its own scratch directory as the
            # workspace and silently edits the wrong files while reporting
            # success. This flag is load-bearing.
            flags += ["--add-dir", str(Path(self.workspace_dir).expanduser())]
        flags += ["--mode", "plan" if run_mode == MODE_PLAN else "accept-edits"]
        if self.model:
            flags += ["--model", self.model]
        return flags

    def build_refine_cmd(self, prompt: str) -> list[str]:
        # Default --output-format is `text`, matching what refine_with_llm()
        # expects on stdout. --print MUST be fused and last (see below).
        return (self._get_base_cmd() + self._common_flags(MODE_BUILD)
                + [f"--print={prompt}"])

    def build_execute_cmd(self, prompt: str, session_id: str | None = None,
                          run_mode: str = MODE_BUILD) -> list[str]:
        cmd = self._get_base_cmd() + self._common_flags(run_mode)
        cmd += ["--output-format", "stream-json"]
        if session_id:
            # Note: --conversation, NOT --resume.
            cmd += ["--conversation", session_id]
        # `agy` uses Go-style flags and --print takes an OPTIONAL value, so a
        # bare `--print` swallows the next token ("--print took --output-format
        # as its prompt"). The prompt must be a single fused argv element and
        # must be last. Do not "clean this up" into ["--print", prompt].
        cmd.append(f"--print={prompt}")
        return cmd

    # ─── Event parsing ──────────────────────────────────────────────
    #
    # Every stream-json line is {"event": "<name>", "<name>": {...}} -- a
    # discriminator plus a same-named payload object.

    @staticmethod
    def _step(event: dict) -> dict | None:
        if event.get("event") == "step_update":
            return event.get("step_update") or {}
        return None

    def parse_init_event(self, event: dict) -> str | None:
        if event.get("event") == "init":
            # conversation_id sits at the TOP level, not inside "init".
            sid = event.get("conversation_id")
            return sid if isinstance(sid, str) and sid else None
        return None

    def parse_text_event(self, event: dict) -> tuple[str, list] | None:
        step = self._step(event)
        if not step:
            return None
        st = step.get("step_type")
        if st == "agent_response":
            # text_delta is incremental -- concatenate every delta, including
            # the one on the final DONE step. Do not dedupe.
            delta = step.get("text_delta", "")
            return (delta, []) if delta else None
        if st == "tool" and step.get("state") == "ACTIVE":
            # Tool steps fire twice (ACTIVE then DONE) with identical params.
            # Rendering only ACTIVE is what prevents double-printing.
            info = step.get("tool_info") or {}
            return ("", [(step.get("tool_name", "?"), info.get("parameters", {}))])
        return None

    def parse_thinking_event(self, event: dict) -> str | None:
        # stream-json exposes thinking_tokens counters but no thinking text,
        # so the ".. " thinking lines never appear under Antigravity. This is
        # a CLI limitation -- do not synthesize text from the token count.
        return None

    def parse_tool_result_event(self, event: dict) -> str | None:
        step = self._step(event)
        if not step or step.get("step_type") != "tool":
            return None
        if step.get("state") != "DONE":
            return None
        # `output` is absent/None for some tools (e.g. write_to_file).
        out = (step.get("tool_info") or {}).get("output")
        if not out:
            return None
        out = str(out)
        preview = out[:200].replace("\n", " ")
        if len(out) > 200:
            preview += f"... ({len(out)} chars)"
        return preview

    def parse_context_usage(self, event: dict) -> tuple[int, int] | None:
        # Per-step usage is per-turn, not cumulative occupancy. The best proxy
        # for "context in play" is input_tokens + cache_read_tokens. `agy`
        # reports no context window, so the shared constant is used.
        usage = None
        if event.get("event") == "result":
            usage = (event.get("result") or {}).get("usage")
        else:
            step = self._step(event)
            if step and step.get("step_type") == "agent_response":
                usage = step.get("usage")
        if not usage:
            return None
        used = usage.get("input_tokens", 0) + usage.get("cache_read_tokens", 0)
        return (used, DEFAULT_CONTEXT_WINDOW) if used else None

    def is_result_event(self, event: dict) -> str | None:
        if event.get("event") == "result":
            # Return "" rather than None on a missing response so run_agent()
            # falls back to accumulated deltas, same as Claude. Deliberately
            # not gated on status -- verified that `status` reports whether the
            # RUN completed, not whether the task succeeded (a task the agent
            # explicitly failed still reported "SUCCESS"), so it carries no
            # error signal worth surfacing.
            return (event.get("result") or {}).get("response", "")
        return None
