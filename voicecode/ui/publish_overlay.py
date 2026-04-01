"""Publish overlay — document type and destination folder selection."""

import curses
import textwrap

from voicecode.ui.colors import (
    CP_PUBLISH, CP_PUBLISH_TITLE, CP_ACCENT, CP_VOICE, CP_AGENT, CP_PROMPT,
    CP_SELECTION,
)


# Document types with a publishing agent implemented
IMPLEMENTED_TYPES = [
    "ADR",
    "ARCH",
    "PLAN",
    "SPEC",
    "GLOSSARY",
    "CONSTRAINTS",
    "CONVENTIONS",
    "SCHEMA",
    "README",
]

ALL_DOC_TYPES = IMPLEMENTED_TYPES

# Short agent descriptions for the info panel (shown when agent is highlighted)
AGENT_INFO = {
    "ADR": {
        "title": "ADR Agent — Architecture Decision Records",
        "description": "Captures a single significant technical decision: the context that prompted it, alternatives considered, the choice made, and its consequences. Use ADRs for hard-to-reverse decisions like choosing a framework, adopting a pattern, or establishing a convention. Each ADR is numbered sequentially (0001, 0002, ...) and lives in decisions/.",
    },
    "ARCH": {
        "title": "Architecture Agent",
        "description": "Analyzes your codebase and produces a comprehensive architecture document covering components, data flow, state management, and design decisions. Reads actual code — does not hallucinate.",
    },
    "PLAN": {
        "title": "Plan Agent",
        "description": "Produces a stepwise implementation plan with scope, milestones, task breakdown, and dependencies. Ideal for planning features or initiatives before writing code.",
    },
    "SPEC": {
        "title": "Spec Agent",
        "description": "Generates a detailed feature specification with requirements, API contracts, edge cases, and acceptance criteria. The authoritative reference for reviewers.",
    },
    "GLOSSARY": {
        "title": "Glossary Agent",
        "description": "Maintains a single glossary at docs/context/GLOSSARY.md. Can add, edit, or remove terms. Request a full codebase scan in your prompt to auto-generate definitions.",
    },
    "CONSTRAINTS": {
        "title": "Constraints Agent",
        "description": "Maintains docs/context/CONSTRAINTS.md with hard boundaries and safety rails. Describe constraints in plain language and the agent adds them to the file. Ask for the questionnaire reference to see what kinds of constraints you can define.",
    },
    "CONVENTIONS": {
        "title": "Conventions Agent",
        "description": "Maintains docs/context/CONVENTIONS.md with agreed-upon team practices: naming, file layout, code style, git workflow, testing, and documentation patterns. Describe conventions in plain language and the agent adds them. Unlike constraints, conventions guide rather than block.",
    },
    "SCHEMA": {
        "title": "Schema Agent — Data Layer Reference",
        "description": "Derives and maintains docs/context/SCHEMA.md by scanning the codebase for models, tables, data classes, and relationships. Does not require specific items — it reads the code and produces the schema. Point it at reference materials or ask for a full scan.",
    },
    "README": {
        "title": "README Agent — Repository Entry Point",
        "description": "Curates and maintains README.md at the project root. Keeps the GitHub landing page accurate with project overview, setup instructions, features, and usage. Ask for a full scan to generate from scratch, or describe specific updates.",
    },
}

DOC_TYPE_DESCRIPTIONS = {
    "ARCH": "High-level system architecture overview — components, boundaries, data flow, and deployment topology. The single document an unfamiliar engineer reads first. File: docs/context/ARCH.md",
    "PLAN": "Time-boxed implementation plan for a feature or initiative — scope, milestones, task breakdown, and dependencies. Lives in plans/active/ while in progress. File: docs/plans/active/<name>.md",
    "SPEC": "Detailed feature specification — requirements, API contracts, edge cases, and acceptance criteria. The authoritative reference designers and reviewers check against. File: docs/specs/active/<name>.md",
    "BRIEF": "Concise project or product brief — problem statement, goals, success metrics, and stakeholders. Frames the 'why' before any technical work begins. File: docs/context/BRIEF.md",
    "SCHEMA": "Data model and schema reference — entity definitions, relationships, constraints, and migration strategy. Keeps backend and frontend aligned on shape of data. File: docs/context/SCHEMA.md",
    "ADR": "Architecture Decision Record — captures a single significant technical decision, its context, alternatives considered, and consequences. Numbered sequentially in decisions/. File: docs/decisions/<nnnn>-<slug>.md",
    "CONVENTIONS": "Coding and workflow conventions — naming, file layout, PR etiquette, and style rules the team has agreed on. Reduces review friction and onboarding time. File: docs/context/CONVENTIONS.md",
    "CONSTRAINTS": "Hard boundaries the project must respect — regulatory requirements, performance budgets, compatibility targets, and non-negotiable dependencies. File: docs/context/CONSTRAINTS.md",
    "GLOSSARY": "Shared vocabulary — domain terms, acronyms, and project-specific jargon with precise definitions. Eliminates ambiguity in specs, tickets, and conversations. File: docs/context/GLOSSARY.md",
    "README": "Repository entry point — what the project does, how to set it up, and where to find deeper documentation. The first file every visitor and contributor sees. File: README.md",
}

DEST_FOLDERS = [
    "context/",
    "decisions/",
    "plans/",
    "specs/",
]

# Reference tree shown in the tutorial section
REFERENCE_TREE = [
    "docs/",
    "  context/          — what Claude reads every session (or on demand)",
    "    BRIEF.md",
    "    ARCH.md",
    "    CONVENTIONS.md",
    "    CONSTRAINTS.md",
    "    GLOSSARY.md",
    "    SCHEMA.md",
    "  decisions/        — ADRs, numbered sequentially",
    "    0001-use-gcp-tree-architecture.md",
    "    0002-typescript-react-frontend.md",
    "  plans/            — active and archived plans",
    "    active/",
    "    archive/",
    "  specs/            — feature specs",
    "    active/",
    "    archive/",
]

# Registry of publishing agents by doc type
_AGENT_REGISTRY = {}


def get_publish_agent(doc_type: str):
    """Return a publishing agent instance for the given doc type, or None."""
    if not _AGENT_REGISTRY:
        # Lazy import to avoid circular deps
        from voicecode.publish.adr import AdrAgent
        from voicecode.publish.arch import ArchAgent
        from voicecode.publish.plan import PlanAgent
        from voicecode.publish.spec import SpecAgent
        from voicecode.publish.glossary import GlossaryAgent
        from voicecode.publish.constraints import ConstraintsAgent
        from voicecode.publish.conventions import ConventionsAgent
        from voicecode.publish.schema import SchemaAgent
        from voicecode.publish.readme import ReadmeAgent
        _AGENT_REGISTRY["ADR"] = AdrAgent()
        _AGENT_REGISTRY["ARCH"] = ArchAgent()
        _AGENT_REGISTRY["PLAN"] = PlanAgent()
        _AGENT_REGISTRY["SPEC"] = SpecAgent()
        _AGENT_REGISTRY["GLOSSARY"] = GlossaryAgent()
        _AGENT_REGISTRY["CONSTRAINTS"] = ConstraintsAgent()
        _AGENT_REGISTRY["CONVENTIONS"] = ConventionsAgent()
        _AGENT_REGISTRY["SCHEMA"] = SchemaAgent()
        _AGENT_REGISTRY["README"] = ReadmeAgent()
    return _AGENT_REGISTRY.get(doc_type)


def execute_agent_prompt(app, prompt_text: str, label: str):
    """Feed a prompt into the agent execution pipeline.

    Shared by publish and maintenance workflows.  Sets up the ZMODEM
    animation, saves to history, and spawns the background agent thread.
    """
    import time
    import threading
    from voicecode.constants import AgentState
    from voicecode.ui.colors import CP_XFER

    app.executed_prompt_text = label
    if app._prompt_pane_original_color is None:
        app._prompt_pane_original_color = app.prompt_pane.color_pair
    app.prompt_pane.color_pair = CP_XFER
    app.browser_view = "active"
    app.browser_index = -1
    w = app.stdscr.getmaxyx()[1] // 2
    app.browser.load_browser_prompt(w)

    # Clear prompt state
    app.fragments.clear()
    app.input_handler.clear_buffer_file()
    app.current_prompt = None
    app.prompt_version = 0
    app.prompt_saved = True
    app.dictation_pane.lines.clear()
    app.dictation_pane.scroll_offset = 0

    app._last_history_prompt_path = app.execution.save_to_history(prompt_text)

    app.xfer_prompt_text = prompt_text
    app.xfer_bytes = len(prompt_text.encode())
    app.xfer_progress = 0.0
    app.xfer_frame = 0
    app.xfer_start_time = time.time()
    app.agent_state = AgentState.DOWNLOADING
    app.typewriter_queue.clear()
    app._typewriter_budget = 0.0
    app._typewriter_last_ts = 0.0
    app.agent_first_output = False
    app.agent_last_activity = 0.0
    app._typewriter_line_color = None
    app._tts_detect_buf = ''
    app._tts_in_summary = False

    app.browser.set_agent_welcome(40)
    app.set_status(f"{label} ...")

    app._agent_cancel.clear()
    threading.Thread(target=app.runner.run_agent, daemon=True).start()


class PublishOverlay:
    """Near-full-screen modal for the Publish workflow.

    Two-step selection:
      Step 0 — pick a document type (only implemented types selectable)
      Step 1 — pick a destination folder
    """

    def __init__(self, app):
        self.app = app

    # ── state helpers ────────────────────────────────────────────

    def open(self):
        app = self.app
        app.show_publish_overlay = True
        app.publish_step = 0
        app.publish_cursor = 0
        app.publish_selected_type = None
        app.publish_selected_folder = None
        app.publish_info_scroll = 0

    def close(self):
        self.app.show_publish_overlay = False

    def go_back(self):
        """Go back one step, or close if at step 0."""
        app = self.app
        if app.publish_step == 0:
            self.close()
        else:
            app.publish_step = 0
            # Return cursor to previously selected type
            items = self._type_display_items()
            for i, (name, _) in enumerate(items):
                if name == app.publish_selected_type:
                    app.publish_cursor = i
                    break
            else:
                app.publish_cursor = 0

    def select(self):
        """Confirm the current selection and advance."""
        app = self.app
        if app.publish_step == 0:
            if app.publish_cursor == -1:
                self.edit_refine_prompt()
                return
            items = self._type_display_items()
            name, enabled = items[app.publish_cursor]
            if not enabled:
                app.set_status(f"{name} agent not yet implemented.")
                return
            app.publish_selected_type = name
            if name in ("GLOSSARY", "CONSTRAINTS", "CONVENTIONS", "SCHEMA", "README"):
                # Fixed-destination agents always target context/
                app.publish_step = 1
                app.publish_cursor = 0  # context/ is index 0
            else:
                app.publish_step = 1
                app.publish_cursor = 0
        else:
            if app.publish_selected_type == "README":
                app.publish_selected_folder = ""
            elif app.publish_selected_type in ("GLOSSARY", "CONSTRAINTS", "CONVENTIONS", "SCHEMA"):
                app.publish_selected_folder = "context/"
            else:
                app.publish_selected_folder = DEST_FOLDERS[app.publish_cursor]
            self.close()
            self._execute_publish()

    def cursor_move(self, direction: int):
        app = self.app
        if app.publish_step == 0:
            count = len(self._type_display_items())
            # Allow -1 to select the "Edit Refine Agent Prompt" line
            app.publish_cursor = max(-1, min(count - 1, app.publish_cursor + direction))
        else:
            if app.publish_selected_type in ("GLOSSARY", "CONSTRAINTS", "CONVENTIONS", "SCHEMA", "README"):
                return  # fixed destination, no cursor movement
            count = len(DEST_FOLDERS)
            app.publish_cursor = max(0, min(count - 1, app.publish_cursor + direction))

    def info_scroll(self, direction: int, page_size: int = 5):
        """Scroll the left informational panel by page_size lines."""
        app = self.app
        app.publish_info_scroll = max(0, app.publish_info_scroll + direction * page_size)

    def _type_display_items(self):
        """Return list of (name, enabled) tuples for the type selector."""
        return [(t, True) for t in IMPLEMENTED_TYPES]

    def edit_prompt(self):
        """Open the highlighted agent's prompt template in the doc reader/editor."""
        app = self.app
        if app.publish_step == 0:
            if app.publish_cursor == -1:
                # Cursor is on the refine line — E edits refine prompt too
                self.edit_refine_prompt()
                return
            items = self._type_display_items()
            name, enabled = items[app.publish_cursor]
            if not enabled:
                app.set_status(f"{name} agent not yet implemented — no prompt to edit.")
                return
        else:
            name = app.publish_selected_type

        agent = get_publish_agent(name)
        if not agent:
            app.set_status(f"No agent for {name}.")
            return

        prompt_path = str(agent.prompt_path)
        self.close()
        app.overlays.open_doc_reader(prompt_path, f"{name} Prompt Template",
                                     on_close=self.open)

    def edit_refine_prompt(self):
        """Open the Refine Agent's prompt template in the doc reader/editor."""
        from voicecode.agent.refine import REFINE_PROMPT_PATH
        app = self.app
        prompt_path = str(REFINE_PROMPT_PATH)
        self.close()
        app.overlays.open_doc_reader(prompt_path, "Refine Agent Prompt",
                                     on_close=self.open)

    def _execute_publish(self):
        """Build the publish prompt and send it through the agent pipeline."""
        app = self.app
        doc_type = app.publish_selected_type
        dest_folder = app.publish_selected_folder

        agent = get_publish_agent(doc_type)
        if not agent:
            app.set_status(f"No agent for {doc_type} — this shouldn't happen.")
            return

        # Use current prompt as scope; if prompt window is in initial state,
        # use dictation buffer fragments instead; fall back to default scope.
        # Check fragments first so the dictation buffer isn't shadowed by a
        # stale executed_prompt_text from a previous run.
        if app.fragments and not app.current_prompt and app.browser_index < 0:
            scope = " ".join(app.fragments)
        else:
            scope = app.browser.get_active_prompt_text() or app.current_prompt
        if not scope:
            scope = "the entire repository (all top-level folders and files)"

        prompt_text = agent.build_prompt(scope, dest_folder)
        dest_label = f"docs/{dest_folder}" if dest_folder else "README.md"
        label = f"[PUBLISH {doc_type} → {dest_label}]"

        execute_agent_prompt(app, prompt_text, label)

    # ── drawing ──────────────────────────────────────────────────

    def draw(self):
        app = self.app
        h, w = app.stdscr.getmaxyx()

        # Modal dimensions — near full screen with margin
        margin_x = 2
        margin_top = 3
        margin_bot = 2
        box_x = margin_x
        box_y = margin_top
        box_w = w - margin_x * 2
        box_h = h - margin_top - margin_bot

        if box_w < 40 or box_h < 16:
            return

        purple = curses.color_pair(CP_PUBLISH) | curses.A_BOLD
        title_attr = curses.color_pair(CP_PUBLISH_TITLE) | curses.A_BOLD
        dim = curses.color_pair(CP_ACCENT)
        body = curses.color_pair(CP_PROMPT)  # white for readable body text
        bright = curses.color_pair(CP_AGENT) | curses.A_BOLD
        sel_attr = curses.color_pair(CP_SELECTION) | curses.A_BOLD
        disabled_attr = curses.color_pair(CP_ACCENT)  # dim for unimplemented

        # Clear background
        blank = " " * box_w
        for y in range(box_y, box_y + box_h):
            try:
                app.stdscr.addnstr(y, box_x, blank, box_w)
            except curses.error:
                pass

        # Top border + title
        title = " PUBLISH DOCUMENT "
        border_top = "╔" + "═" * (box_w - 2) + "╗"
        try:
            app.stdscr.addnstr(box_y, box_x, border_top, box_w, purple)
            tx = box_x + (box_w - len(title)) // 2
            app.stdscr.addstr(box_y, tx, title, title_attr)
        except curses.error:
            pass

        # Side borders
        for y in range(box_y + 1, box_y + box_h - 1):
            try:
                app.stdscr.addstr(y, box_x, "║", purple)
                app.stdscr.addstr(y, box_x + box_w - 1, "║", purple)
            except curses.error:
                pass

        # Bottom border
        step_label = " Step 1: Document Type " if app.publish_step == 0 else " Step 2: Destination Folder "
        if app.publish_step == 0 and getattr(app, 'publish_cursor', 0) == -1:
            help_text = " Edit publish/prompts/REFINE.md — the LLM prompt that refines your input into agent instructions "
        else:
            help_text = " [↑↓]Select [E]Edit Prompt [PgUp/Dn]Info [Enter]Confirm [ESC]Back "
        border_bot = "╚" + "═" * (box_w - 2) + "╝"
        try:
            app.stdscr.addnstr(box_y + box_h - 1, box_x, border_bot, box_w, purple)
            # Step label on left
            app.stdscr.addstr(box_y + box_h - 1, box_x + 2, step_label, title_attr)
            # Help on right
            hx = box_x + box_w - len(help_text) - 2
            if hx > box_x + len(step_label) + 4:
                app.stdscr.addstr(box_y + box_h - 1, hx, help_text, purple)
        except curses.error:
            pass

        # Content area
        inner_x = box_x + 2
        inner_w = box_w - 4
        cy = box_y + 2  # current y for content

        # ── Left column: reference tree  |  Right column: selection list ──
        # Use a two-column layout: reference on left, selection on right
        divider_x = box_x + box_w // 2
        left_w = divider_x - inner_x - 1
        right_x = divider_x + 2
        right_w = box_x + box_w - 2 - right_x

        # Draw vertical divider
        for y in range(box_y + 1, box_y + box_h - 1):
            try:
                app.stdscr.addstr(y, divider_x, "│", purple)
            except curses.error:
                pass

        # ── LEFT: Scrollable info panel ──
        # Build all lines for the left panel, then render with scroll offset
        info_lines = []  # list of (text, attr)

        # Panel title
        panel_title = "Voicecode Agent Docs Guidelines"
        info_lines.append((panel_title, title_attr))
        info_lines.append(("═" * min(len(panel_title), left_w), purple))
        info_lines.append(("", body))  # blank separator

        # Introductory guidance text
        intro_text = (
            "Each publication agent has a unique job to deliver your "
            "prompt into an agent that has specific expectations of "
            "context, and specific document goals to accomplish for "
            "each type. Make sure to give instructions in your prompt "
            "specific for the task, and reference any related folders "
            "or other markdown sources as additional context for "
            "these agents."
        )
        for wline in textwrap.wrap(intro_text, width=max(left_w, 20)):
            info_lines.append((wline, body))
        info_lines.append(("", body))  # blank separator

        # Section: Docs Folder Structure
        ref_title = "Docs Folder Structure"
        info_lines.append((ref_title, purple))
        info_lines.append(("─" * min(len(ref_title), left_w), purple))
        for line in REFERENCE_TREE:
            info_lines.append((line, body))

        info_lines.append(("", body))  # blank separator

        # Section: Document Types
        types_title = "Document Types"
        info_lines.append((types_title, purple))
        info_lines.append(("─" * min(len(types_title), left_w), purple))

        for doc_type in ALL_DOC_TYPES:
            desc = DOC_TYPE_DESCRIPTIONS.get(doc_type, "")
            implemented = doc_type in IMPLEMENTED_TYPES
            name_attr = bright if implemented else disabled_attr
            info_lines.append((doc_type, name_attr))
            # Word-wrap description to left_w with 2-space indent
            if desc:
                wrapped = textwrap.wrap(desc, width=max(left_w - 2, 20))
                for wline in wrapped:
                    info_lines.append(("  " + wline, body))
            info_lines.append(("", body))  # blank line between entries

        # Clamp scroll offset
        visible_rows = box_y + box_h - 2 - cy
        max_scroll = max(0, len(info_lines) - visible_rows)
        if not hasattr(app, 'publish_info_scroll'):
            app.publish_info_scroll = 0
        app.publish_info_scroll = max(0, min(app.publish_info_scroll, max_scroll))

        # Render visible portion
        ref_y = cy
        for i in range(app.publish_info_scroll, len(info_lines)):
            if ref_y >= box_y + box_h - 2:
                break
            text, attr = info_lines[i]
            try:
                app.stdscr.addnstr(ref_y, inner_x, text[:left_w], left_w, attr)
            except curses.error:
                pass
            ref_y += 1

        # Scroll indicators
        if app.publish_info_scroll > 0:
            try:
                app.stdscr.addstr(cy, inner_x + left_w - 3, " ▲ ", body)
            except curses.error:
                pass
        if app.publish_info_scroll < max_scroll:
            try:
                ind_y = min(ref_y, box_y + box_h - 3)
                app.stdscr.addstr(ind_y, inner_x + left_w - 3, " ▼ ", body)
            except curses.error:
                pass

        # ── RIGHT: Selection list ──
        sel_y = cy
        if app.publish_step == 0:
            sel_title = "Select Document Type"
            self._draw_type_selector(app, right_x, right_w, sel_y, box_y + box_h,
                                     purple, bright, sel_attr, disabled_attr, dim, body)
        else:
            is_fixed_dest = app.publish_selected_type in ("GLOSSARY", "CONSTRAINTS", "CONVENTIONS", "SCHEMA", "README")
            sel_title = f"Destination for {app.publish_selected_type}"
            try:
                app.stdscr.addnstr(sel_y, right_x, sel_title, right_w, purple)
            except curses.error:
                pass
            sel_y += 1
            try:
                app.stdscr.addnstr(sel_y, right_x, "─" * min(len(sel_title), right_w), right_w, purple)
            except curses.error:
                pass
            sel_y += 1

            if is_fixed_dest:
                # Fixed-destination agent — show path, don't allow changing
                if app.publish_selected_type == "README":
                    fixed_label = "▸ ./  (project root, fixed)"
                    note = "This document is always at README.md in the project root"
                else:
                    fixed_label = "▸ context/  (fixed)"
                    note = f"This document is always at docs/context/{app.publish_selected_type}.md"
                try:
                    app.stdscr.addnstr(sel_y, right_x, fixed_label[:right_w], right_w, sel_attr)
                except curses.error:
                    pass
                sel_y += 2
                for wline in textwrap.wrap(note, width=max(right_w, 20)):
                    if sel_y >= box_y + box_h - 2:
                        break
                    try:
                        note_attr = curses.color_pair(CP_VOICE) | curses.A_BOLD
                        app.stdscr.addnstr(sel_y, right_x, wline[:right_w], right_w, note_attr)
                    except curses.error:
                        pass
                    sel_y += 1
            else:
                items = DEST_FOLDERS
                visible_rows = box_y + box_h - 2 - sel_y
                scroll = 0
                if app.publish_cursor >= visible_rows:
                    scroll = app.publish_cursor - visible_rows + 1

                for i, item in enumerate(items):
                    if i < scroll:
                        continue
                    if sel_y >= box_y + box_h - 2:
                        break
                    if i == app.publish_cursor:
                        attr = sel_attr
                        label = f"▸ {item}"
                    else:
                        attr = curses.color_pair(CP_VOICE) | curses.A_BOLD
                        label = f"  {item}"
                    try:
                        app.stdscr.addnstr(sel_y, right_x, label[:right_w], right_w, attr)
                    except curses.error:
                        pass
                    sel_y += 1

            # Show agent instruction below folder list
            sel_y += 1
            agent_info = AGENT_INFO.get(app.publish_selected_type)
            if agent_info and sel_y < box_y + box_h - 2:
                yellow_attr = curses.color_pair(CP_VOICE) | curses.A_BOLD
                try:
                    app.stdscr.addnstr(sel_y, right_x, agent_info["title"], right_w, yellow_attr)
                except curses.error:
                    pass
                sel_y += 1
                for wline in textwrap.wrap(agent_info["description"], width=max(right_w, 20)):
                    if sel_y >= box_y + box_h - 2:
                        break
                    try:
                        app.stdscr.addnstr(sel_y, right_x, wline[:right_w], right_w, body)
                    except curses.error:
                        pass
                    sel_y += 1

    def _draw_type_selector(self, app, right_x, right_w, start_y, max_y,
                            purple, bright, sel_attr, disabled_attr, dim, body):
        """Draw the type selector."""
        sel_y = start_y
        items = self._type_display_items()
        white_attr = curses.color_pair(CP_PROMPT) | curses.A_BOLD

        # Refine agent prompt editor link
        yellow_attr = curses.color_pair(CP_VOICE) | curses.A_BOLD
        refine_selected = (app.publish_cursor == -1)
        try:
            part1 = "Edit "
            part2 = "[R]efine"
            part3 = " Agent Prompt"
            if refine_selected:
                full_label = f"▸ {part1}{part2}{part3}"
                app.stdscr.addnstr(sel_y, right_x, full_label[:right_w], right_w, sel_attr)
            else:
                x = right_x
                prefix = "  "
                app.stdscr.addnstr(sel_y, x, prefix, right_w, yellow_attr)
                x += len(prefix)
                app.stdscr.addnstr(sel_y, x, part1, right_w - len(prefix), yellow_attr)
                x += len(part1)
                app.stdscr.addnstr(sel_y, x, part2, right_w - len(prefix) - len(part1), white_attr)
                x += len(part2)
                app.stdscr.addnstr(sel_y, x, part3, right_w - len(prefix) - len(part1) - len(part2), yellow_attr)
        except curses.error:
            pass
        sel_y += 2

        # Section header: Available
        header = "Available"
        try:
            app.stdscr.addnstr(sel_y, right_x, header, right_w, purple)
        except curses.error:
            pass
        sel_y += 1
        try:
            app.stdscr.addnstr(sel_y, right_x, "─" * min(len(header), right_w), right_w, purple)
        except curses.error:
            pass
        sel_y += 1

        # Draw implemented types
        idx = 0
        for name, enabled in items:
            if not enabled:
                break
            if sel_y >= max_y - 2:
                break
            if idx == app.publish_cursor:
                attr = sel_attr
                label = f"▸ {name}"
            else:
                attr = bright
                label = f"  {name}"
            try:
                app.stdscr.addnstr(sel_y, right_x, label[:right_w], right_w, attr)
            except curses.error:
                pass
            sel_y += 1
            idx += 1

        # ── Agent info panel at the bottom ──
        # Determine which agent is highlighted
        highlighted_name = None
        if app.publish_cursor >= 0:
            cur_items = self._type_display_items()
            if app.publish_cursor < len(cur_items):
                highlighted_name = cur_items[app.publish_cursor][0]

        agent_info = AGENT_INFO.get(highlighted_name) if highlighted_name else None
        if app.publish_cursor == -1:
            # Show refine agent description when the refine entry is highlighted
            sel_y += 1
            if sel_y < max_y - 2:
                try:
                    app.stdscr.addnstr(sel_y, right_x, "─" * min(right_w, right_w), right_w, purple)
                except curses.error:
                    pass
                sel_y += 1
            yellow_attr = curses.color_pair(CP_VOICE) | curses.A_BOLD
            if sel_y < max_y - 2:
                try:
                    app.stdscr.addnstr(sel_y, right_x, "Refine Agent Prompt Editor", right_w, yellow_attr)
                except curses.error:
                    pass
                sel_y += 1
            refine_desc = (
                "Opens publish/prompts/REFINE.md for editing. "
                "This file contains the LLM prompt template that transforms "
                "your free-form input into structured agent instructions "
                "before a publish agent runs. Customise it to control how "
                "the refine step interprets your intent."
            )
            for wline in textwrap.wrap(refine_desc, width=max(right_w, 20)):
                if sel_y >= max_y - 2:
                    break
                try:
                    app.stdscr.addnstr(sel_y, right_x, wline[:right_w], right_w, body)
                except curses.error:
                    pass
                sel_y += 1
        elif agent_info:
            sel_y += 1
            if sel_y < max_y - 2:
                # Separator
                try:
                    app.stdscr.addnstr(sel_y, right_x, "─" * min(right_w, right_w), right_w, purple)
                except curses.error:
                    pass
                sel_y += 1
            if sel_y < max_y - 2:
                yellow_attr = curses.color_pair(CP_VOICE) | curses.A_BOLD
                try:
                    app.stdscr.addnstr(sel_y, right_x, agent_info["title"], right_w, yellow_attr)
                except curses.error:
                    pass
                sel_y += 1
                for wline in textwrap.wrap(agent_info["description"], width=max(right_w, 20)):
                    if sel_y >= max_y - 2:
                        break
                    try:
                        app.stdscr.addnstr(sel_y, right_x, wline[:right_w], right_w, body)
                    except curses.error:
                        pass
                    sel_y += 1
