"""LLM-based prompt refinement."""

import os
import subprocess

from voicecode.providers.base import CLIProvider
from voicecode.providers.claude import ClaudeProvider
from voicecode.constants import INITIAL_REFINE_PROMPT, MODIFY_REFINE_PROMPT


def refine_with_llm(fragments: list[str], current_prompt: str | None,
                    status_callback=None, provider: CLIProvider | None = None) -> str:
    if provider is None:
        provider = ClaudeProvider()
    if status_callback:
        status_callback(f"Refining with {provider.name}...")

    fragment_text = "\n".join(f"- {f}" for f in fragments)

    if current_prompt:
        meta_prompt = MODIFY_REFINE_PROMPT.format(
            current_prompt=current_prompt, fragments=fragment_text)
    else:
        meta_prompt = INITIAL_REFINE_PROMPT.format(fragments=fragment_text)

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
