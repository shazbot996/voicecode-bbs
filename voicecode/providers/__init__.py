"""CLI provider registry for VoiceCode BBS."""

from voicecode.providers.base import CLIProvider
from voicecode.providers.claude import ClaudeProvider
from voicecode.providers.gemini import GeminiProvider

# Singleton instances so command_override and other state persist.
_PROVIDERS: list[CLIProvider] = [ClaudeProvider(), GeminiProvider()]


def detect_providers() -> list[CLIProvider]:
    """Return list of installed CLI providers."""
    return [p for p in _PROVIDERS if p.is_installed()]


def get_provider_by_name(name: str) -> CLIProvider | None:
    """Return a provider instance by display name, or None."""
    for p in _PROVIDERS:
        if p.name.lower() == name.lower():
            return p
    return None
