"""LLM-based prompt refinement."""

import re
import subprocess

from voicecode.providers.base import CLIProvider
from voicecode.providers.claude import ClaudeProvider
from voicecode.publish.base import PROMPTS_DIR

# Path to the combined refine prompt template on disk
REFINE_PROMPT_PATH = PROMPTS_DIR / "REFINE.md"

# Separator between the initial and modify sections in the template file
_SECTION_SEP = "===MODIFY==="


def strip_tts_summary(text: str) -> str:
    """Remove any [TTS_SUMMARY] blocks or tags from text.

    Refinement runs should not generate or include [TTS_SUMMARY] tags; TTS
    summaries belong only on agent responses in the agent terminal.
    """
    if not text:
        return ""
    # Strip complete or unclosed [TTS_SUMMARY] blocks
    cleaned = re.sub(r'\[TTS_SUMMARY\].*?(?:\[/TTS_SUMMARY\]|$)', '', text,
                     flags=re.DOTALL | re.IGNORECASE)
    # Also strip any isolated closing tags
    cleaned = re.sub(r'\[/TTS_SUMMARY\]', '', cleaned, flags=re.IGNORECASE)
    return cleaned.strip()


def _load_refine_prompts() -> tuple[str, str]:
    """Load and split the refine prompt template from disk."""
    raw = REFINE_PROMPT_PATH.read_text(encoding="utf-8")
    parts = raw.split(_SECTION_SEP, 1)
    initial = parts[0].rstrip("\n")
    modify = parts[1].lstrip("\n") if len(parts) > 1 else initial
    return initial, modify


def refine_with_llm(fragments: list[str], current_prompt: str | None,
                    status_callback=None, provider: CLIProvider | None = None) -> str:
    if provider is None:
        provider = ClaudeProvider()
    if status_callback:
        status_callback(f"Refining with {provider.name}...")

    fragment_text = "\n".join(f"- {f}" for f in fragments)
    initial_tpl, modify_tpl = _load_refine_prompts()

    if current_prompt:
        clean_current = strip_tts_summary(current_prompt)
        meta_prompt = modify_tpl.format(
            current_prompt=clean_current, fragments=fragment_text)
    else:
        meta_prompt = initial_tpl.format(fragments=fragment_text)

    try:
        cmd = provider.build_refine_cmd(meta_prompt)
        # stdin=DEVNULL: capture_output only redirects stdout/stderr, so
        # without this the CLI inherits the curses app's TTY and any prompt
        # (auth, trust-folder) steals keystrokes from the UI until timeout.
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
            stdin=subprocess.DEVNULL, env=provider.get_env(),
            cwd=provider.resolved_workspace_dir())
        if result.returncode == 0 and result.stdout.strip():
            cleaned_output = strip_tts_summary(result.stdout.strip())
            return cleaned_output if cleaned_output else result.stdout.strip()
        else:
            return f"[Error: {result.stderr.strip() or 'empty response'}]"
    except FileNotFoundError:
        return f"[Error: '{provider.binary}' CLI not found]"
    except subprocess.TimeoutExpired:
        return "[Error: timed out after 120s]"
    except Exception as e:
        return f"[Error: {e}]"
