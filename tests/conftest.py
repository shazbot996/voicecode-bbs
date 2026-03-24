"""Shared fixtures for VoiceCode smoke tests."""

import pytest
from voicecode.providers.claude import ClaudeProvider
from voicecode.providers.gemini import GeminiProvider


@pytest.fixture
def claude():
    return ClaudeProvider()


@pytest.fixture
def gemini():
    return GeminiProvider()
