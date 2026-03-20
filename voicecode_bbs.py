#!/usr/bin/env python3
"""
VoiceCode BBS - A retro BBS-style voice-driven prompt workshop & agent terminal.

This is a thin wrapper that delegates to the voicecode package.
Run directly: python voicecode_bbs.py
Or as module: python -m voicecode
"""

from voicecode.__main__ import main

if __name__ == "__main__":
    main()
