"""LLM-based prompt refinement."""

import os
import subprocess

from voicecode.providers.base import CLIProvider
from voicecode.providers.claude import ClaudeProvider
from voicecode.publish.base import PROMPTS_DIR

# Path to the combined refine prompt template on disk
REFINE_PROMPT_PATH = PROMPTS_DIR / "REFINE.md"

# Separator between the initial and modify sections in the template file
_SECTION_SEP = "===MODIFY==="


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
        meta_prompt = modify_tpl.format(
            current_prompt=current_prompt, fragments=fragment_text)
    else:
        meta_prompt = initial_tpl.format(fragments=fragment_text)

    try:
        cmd = provider.build_refine_cmd(meta_prompt)
        result = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120, env=os.environ)
        if result.returncode == 0 and result.stdout.strip():
            return result.stdout.strip()
        else:
            return f"[Error: {result.stderr.strip() or 'empty response'}]"
    except FileNotFoundError:
        return f"[Error: '{provider.binary}' CLI not found]"
    except subprocess.TimeoutExpired:
        return "[Error: timed out after 120s]"
    except Exception as e:
        return f"[Error: {e}]"
