"""Shared fixtures for VoiceCode smoke tests."""

import pytest
from voicecode.providers.claude import ClaudeProvider
from voicecode.providers.antigravity import AntigravityProvider


@pytest.fixture
def claude():
    return ClaudeProvider()


@pytest.fixture
def antigravity():
    return AntigravityProvider()
