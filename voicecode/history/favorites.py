"""Favorites slot management."""

import datetime
from pathlib import Path

from voicecode.settings import load_settings, save_settings, next_seq, slug_from_text
from voicecode.ui.colors import *


class FavoritesHelper:
    def __init__(self, app):
        self.app = app

    def load_favorites_slots(self):
        """Load 10-slot favorites from settings."""
        app = self.app
        saved = load_settings()
        slots = saved.get("favorites_slots", [None] * 10)
        # Ensure exactly 10 slots
        app.favorites_slots = (slots + [None] * 10)[:10]
        # Validate paths still exist
        for i, p in enumerate(app.favorites_slots):
            if p and not Path(p).exists():
                app.favorites_slots[i] = None

    def save_favorites_slots(self):
        """Persist 10-slot favorites to settings."""
        app = self.app
        settings = load_settings()
        settings["favorites_slots"] = app.favorites_slots
        save_settings(settings)

    def favorites_as_paths(self) -> list[Path]:
        """Return list of Path objects for occupied favorites slots, in slot order."""
        app = self.app
        return [Path(p) for p in app.favorites_slots if p]

    def favorites_slot_count(self) -> int:
        """Return number of occupied favorites slots."""
        app = self.app
        return sum(1 for p in app.favorites_slots if p)

    def key_to_fav_slot(self, ch: int) -> int:
        """Convert a key code to a favorites slot index (0-9), or -1 if invalid."""
        if ord("1") <= ch <= ord("9"):
            return ch - ord("1")  # keys 1-9 -> slots 0-8
        if ch == ord("0"):
            return 9  # key 0 -> slot 9 (10th)
        return -1

    def format_favorites_slots(self) -> str:
        """Format the 10 favorites slots for display."""
        app = self.app
        lines = []
        for i in range(10):
            key = str((i + 1) % 10)  # 1,2,...,9,0
            path = app.favorites_slots[i]
            if path:
                p = Path(path)
                try:
                    content = p.read_text()
                    # Get first non-comment, non-empty line as preview
                    preview = ""
                    for line in content.split("\n"):
                        stripped = line.strip()
                        if stripped and not stripped.startswith("#"):
                            preview = stripped[:50]
                            if len(stripped) > 50:
                                preview += "\u2026"
                            break
                    if not preview:
                        preview = p.name
                except Exception:
                    preview = p.name
                lines.append(f"  [{key}] \u2605 {preview}")
            else:
                lines.append(f"  [{key}]   (empty)")
        return "\n".join(lines)

    def add_to_favorites(self, slot_idx: int | None):
        """Start favorites assignment: prompt user for slot if not given."""
        app = self.app
        # Determine the source path to favorite
        prompt_list = app.browser.current_browser_list()
        source_path = None
        if app.browser_index >= 0 and app.browser_index < len(prompt_list):
            source_path = prompt_list[app.browser_index]

        if source_path and source_path.exists():
            # Source is a file on disk — store its path directly
            pass
        else:
            # No source file — need to save current prompt text first
            prompt_text = app.browser.get_active_prompt_text()
            if not prompt_text and app.current_prompt:
                prompt_text = app.current_prompt
            if not prompt_text:
                app.set_status("No prompt to favorite. Browse or refine one first!")
                return
            # Write to a file in history
            now = datetime.datetime.now()
            app.history_base.mkdir(parents=True, exist_ok=True)
            seq = next_seq(app.history_base)
            slug = slug_from_text(prompt_text)
            dest = app.history_base / f"{seq:03d}_{slug}_prompt.md"
            with open(dest, "w") as f:
                f.write(f"# Favorited: {now.isoformat()}\n\n")
                f.write(prompt_text)
                f.write("\n")
            source_path = dest
            app.browser.scan_history_prompts()

        app._pending_fav_path = str(source_path)

        if slot_idx is not None:
            self.assign_to_fav_slot(slot_idx)
        else:
            app.choosing_fav_slot = True
            app.set_status("Choose favorites slot [1-9, 0] or any other key to cancel")

    def assign_to_fav_slot(self, slot_idx: int):
        """Assign to slot, with overwrite confirmation if occupied."""
        app = self.app
        if app.favorites_slots[slot_idx]:
            app._pending_fav_slot = slot_idx
            app.confirming_fav_overwrite = True
            slot_num = slot_idx + 1
            app.set_status(f"Slot {slot_num} already has a favorite. Overwrite? [Y/other]")
        else:
            self.do_assign_fav_slot(slot_idx)

    def do_assign_fav_slot(self, slot_idx: int):
        """Actually assign the pending path to the given slot."""
        app = self.app
        app.favorites_slots[slot_idx] = app._pending_fav_path
        self.save_favorites_slots()
        app._pending_fav_slot = -1
        slot_num = slot_idx + 1
        key = str(slot_num % 10)
        app.set_status(f"\u2605 Saved to favorites slot {slot_num} [key {key}]! ({self.favorites_slot_count()}/10)")

    def remove_from_favorites(self):
        """Remove the currently browsed favorite from its slot."""
        app = self.app
        if app.browser_view != "favorites" or app.browser_index < 0:
            app.set_status("No favorite selected to remove.")
            return
        # Find which slot corresponds to this browser index
        fav_paths = self.favorites_as_paths()
        if app.browser_index >= len(fav_paths):
            app.set_status("No favorite selected to remove.")
            return
        target = fav_paths[app.browser_index]
        # Find and clear the slot
        for i, p in enumerate(app.favorites_slots):
            if p and Path(p) == target:
                app.favorites_slots[i] = None
                break
        self.save_favorites_slots()
        # Adjust browser index
        remaining = self.favorites_as_paths()
        if remaining:
            app.browser_index = min(app.browser_index, len(remaining) - 1)
        else:
            app.browser_index = -1
        app.browser.load_browser_prompt(app.stdscr.getmaxyx()[1] // 2)
        app.set_status(f"Removed from favorites. ({self.favorites_slot_count()}/10 remaining)")

    def quick_load_favorite(self, ch: int):
        """Quick-load a favorite by number key."""
        app = self.app
        slot_idx = self.key_to_fav_slot(ch)
        if slot_idx < 0:
            return
        path_str = app.favorites_slots[slot_idx]
        slot_num = slot_idx + 1
        if not path_str:
            app.set_status(f"Favorites slot {slot_num} is empty.")
            return
        path = Path(path_str)
        if not path.exists():
            app.favorites_slots[slot_idx] = None
            self.save_favorites_slots()
            app.set_status(f"Favorites slot {slot_num}: file no longer exists (cleared).")
            return
        # Switch to favorites view and select this item
        app.browser_view = "favorites"
        fav_paths = self.favorites_as_paths()
        try:
            app.browser_index = fav_paths.index(path)
        except ValueError:
            app.browser_index = -1
        app.browser.load_browser_prompt(app.stdscr.getmaxyx()[1] // 2)
        app.set_status(f"\u2605 Loaded favorites slot {slot_num}. Press E to execute.")
