"""Shared constants for VoiceCode BBS."""

from pathlib import Path
from version import __version__

# ─── Audio / STT ─────────────────────────────────────────────────
SAMPLE_RATE = 16000
CHANNELS = 1
BLOCK_SIZE = int(SAMPLE_RATE * 0.03)
VAD_THRESHOLD = 0.5
SILENCE_AFTER_SPEECH_SEC = 1.5
MIN_SPEECH_DURATION_SEC = 0.3

# ─── Settings persistence ────────────────────────────────────────
APP_DIR = Path(__file__).resolve().parent.parent
SETTINGS_DIR = APP_DIR / "settings"
SETTINGS_FILE = SETTINGS_DIR / "settings.json"
SHORTCUTS_FILE = SETTINGS_DIR / "shortcuts.txt"

# ─── TTS ─────────────────────────────────────────────────────────
TTS_PROMPT_SUFFIX = """

IMPORTANT: At the very end of your response, include a brief spoken summary
for text-to-speech. This must be plain text with NO markdown formatting
whatsoever — no asterisks, backticks, hash symbols, bullet points, dashes,
or any other markup. Write it as natural speech that sounds good read aloud.
Keep it concise (1-3 sentences). Wrap it exactly like this:

[TTS_SUMMARY]
Your plain text summary here.
[/TTS_SUMMARY]"""

# ─── UI ──────────────────────────────────────────────────────────
BANNER = f"""
██╗   ██╗ ██████╗ ██╗ ██████╗███████╗ ██████╗ ██████╗ ██████╗ ███████╗
 ██║   ██║██╔═══██╗██║██╔════╝██╔════╝██╔════╝██╔═══██╗██╔══██╗██╔════╝
 ██║   ██║██║   ██║██║██║     █████╗  ██║     ██║   ██║██║  ██║█████╗
 ╚██╗ ██╔╝██║   ██║██║██║     ██╔══╝  ██║     ██║   ██║██║  ██║██╔══╝
  ╚████╔╝ ╚██████╔╝██║╚██████╗███████╗╚██████╗╚██████╔╝██████╔╝███████╗
   ╚═══╝   ╚═════╝ ╚═╝ ╚═════╝╚══════╝ ╚═════╝ ╚═════╝ ╚═════╝ ╚══════╝
                                                            @schiele
                  ╔════════════════════════════════╗
                  ║     B  ·  B  ·  S    v{__version__}      ║
                  ║  Voice-Driven Prompt Workshop  ║
                  ╚════════════════════════════════╝                   """


# ─── Agent states ────────────────────────────────────────────────
class AgentState:
    IDLE = "idle"
    DOWNLOADING = "downloading"  # ZMODEM animation
    RECEIVING = "receiving"      # typewriter output
    DONE = "done"


# ─── ZMODEM download art ────────────────────────────────────────
ZMODEM_FRAMES = [
    "rz waiting to receive.",
    "rz waiting to receive..",
    "rz waiting to receive...",
    "Starting zmodem transfer.",
    "Transferring prompt data...",
]


# ─── Refinement prompts ─────────────────────────────────────────
INITIAL_REFINE_PROMPT = """\
You are a prompt engineer. The user has dictated the following speech fragments \
while thinking about what they want to ask an AI coding assistant. \
Your job is to synthesize these fragments into a single, clear, well-structured prompt \
that faithfully captures their intent, meaning, and all details mentioned.

Rules:
- Be faithful to what they said. Do not add requirements they didn't mention.
- Organize the prompt logically even if they jumped around.
- Use clear, direct language.
- If they mentioned specific files, tools, or technologies, include those.
- Output ONLY the refined prompt, nothing else. No preamble, no explanation.

Speech fragments:
---
{fragments}
---

Refined prompt:"""

MODIFY_REFINE_PROMPT = """\
You are a prompt engineer. The user previously built this prompt through voice dictation:

CURRENT PROMPT:
---
{current_prompt}
---

They have now dictated additional fragments to modify or extend this prompt. \
Apply their changes faithfully. They may want to:
- Add new requirements or details
- Change or clarify existing parts
- Remove something
- Restructure the prompt

New dictation fragments:
---
{fragments}
---

Rules:
- Output ONLY the updated prompt, nothing else.
- Preserve parts of the original that aren't being changed.
- Be faithful to their intent.

Updated prompt:"""
