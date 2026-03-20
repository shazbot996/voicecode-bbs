"""Entry point for python -m voicecode."""

import argparse
import curses
import os
import sys
import textwrap

from version import __version__
from voicecode.app import BBSApp
from voicecode.audio.utils import restore_stderr


def main():
    parser = argparse.ArgumentParser(
        description=f"VoiceCode BBS v{__version__} - Voice-Driven Prompt Workshop & Agent Terminal",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            ╔═══════════════════════════════════════════════════════╗
            ║  Three-Pane Layout:                                   ║
            ║    Top-Left:    Prompt Browser / Editor               ║
            ║    Bottom-Left: Dictation Buffer                      ║
            ║    Right:       Agent Terminal (full height)          ║
            ║                                                       ║
            ║  Controls:                                            ║
            ║    SPACE    Toggle voice recording                    ║
            ║    R        Refine fragments into prompt              ║
            ║    N        New prompt (prompts save if unsaved)      ║
            ║    E        Execute prompt (send to agent)            ║
            ║    U        Undo last dictation entry                 ║
            ║    C        Clear dictation buffer                    ║
            ║    ←→       Browse prompt history                     ║
            ║    ↑↓       Scroll prompt pane                        ║
            ║    PgUp/Dn  Scroll agent pane                         ║
            ║    K        Kill running agent                        ║
            ║    W        New session (clear context)               ║
            ║    X        Restart application                       ║
            ║    Q        Quit                                      ║
            ╚═══════════════════════════════════════════════════════╝
        """),
    )
    parser.parse_args()  # exits on --help, otherwise no args expected

    app = BBSApp()
    try:
        curses.wrapper(lambda stdscr: app.run(stdscr))
    finally:
        restore_stderr()

    if app.restart:
        os.execv(sys.executable, [sys.executable] + sys.argv)


if __name__ == "__main__":
    main()
