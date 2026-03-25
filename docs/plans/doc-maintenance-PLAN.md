---
type: plan
title: "Document Type Styling & Maintenance Agents"
spec_reference: docs/specs/maintenance-actions-spec.md
scope: "voicecode/publish/, voicecode/ui/overlays.py, voicecode/ui/input.py, voicecode/ui/colors.py, voicecode/app.py"
date: 2026-03-24
---

## 1. Goal

Implement visual differentiation of published documents by type (using the existing `type` front matter field) and build an agent-powered document maintenance system with Reconcile, Refresh, and Coverage Check actions — accessible from the document viewer via a new overlay. See [docs/specs/maintenance-actions-spec.md](../specs/maintenance-actions-spec.md).

**Resolved open questions:**
- Reconcile and Coverage reports are saved as single files (one per action) — git provides history.
- No new color pairs — reuse existing palette, grouped by type family.
- `M` key works on any file. Show a fallback message if no maintenance actions apply.
- No backup on Refresh — rely on git for rollback.

## 2. Context & Prior Art

### Key files that will be touched

| File | Role |
|------|------|
| `voicecode/publish/frontmatter.py` | **New** — front matter parser utility |
| `voicecode/publish/maintenance/__init__.py` | **New** — registry and `get_available_actions()` |
| `voicecode/publish/maintenance/base.py` | **New** — `MaintenanceAgent` base class |
| `voicecode/publish/maintenance/reconcile.py` | **New** — Reconcile agent |
| `voicecode/publish/maintenance/refresh.py` | **New** — Refresh agent |
| `voicecode/publish/maintenance/coverage.py` | **New** — Coverage Check agent |
| `voicecode/publish/maintenance/prompts/RECONCILE.md` | **New** — prompt template |
| `voicecode/publish/maintenance/prompts/REFRESH.md` | **New** — prompt template |
| `voicecode/publish/maintenance/prompts/COVERAGE.md` | **New** — prompt template |
| `voicecode/ui/overlays.py` | Modify — type-based viewer styling, type badges in Documents browser, maintenance overlay modal |
| `voicecode/ui/input.py` | Modify — `M` key in doc reader view mode, maintenance overlay input dispatch |
| `voicecode/ui/publish_overlay.py` | Modify — extract shared execution logic into helper |
| `voicecode/ui/drawing.py` | Modify — render maintenance overlay in draw pipeline |
| `voicecode/app.py` | Modify — add maintenance overlay state fields |

### Patterns to follow

- **PublishAgent** (`voicecode/publish/base.py`): `MaintenanceAgent` mirrors this pattern — `action_name` instead of `doc_type`, prompt loaded from `maintenance/prompts/`, `build_prompt()` with different parameters.
- **Fixed-destination agents** (`voicecode/publish/glossary.py`): Example of overriding `build_prompt()`.
- **Agent registry** (`voicecode/ui/publish_overlay.py:111-133`): Lazy import pattern for `get_publish_agent()` — replicate for `get_maintenance_agent()`.
- **Execution pipeline** (`voicecode/ui/publish_overlay.py:263-330`): The `_execute_publish()` method sets up ZMODEM animation, clears prompt state, saves to history, and spawns `run_agent` thread. Extract the reusable parts.
- **Modal dialog** (`voicecode/ui/overlays.py:887-913`): `_draw_save_confirm()` is the pattern for a small centered modal — box drawing, border attributes, centered text.
- **Overlay state pattern** (`voicecode/app.py:200-213`): Doc reader uses `show_doc_reader`, cursor, scroll, mode flags. Maintenance overlay follows this.
- **Draw pipeline** (`voicecode/ui/drawing.py:454-457`): Overlays draw after base UI; doc reader draws last (line 456). Maintenance modal draws on top of doc reader.
- **Input dispatch** (`voicecode/ui/input.py:398-449`): Doc reader view-mode key handling. Add `M` key after existing handlers, before the final `return` on line 449.

## 3. Implementation Steps

### Phase 1: Front Matter Parsing + Type Styling

#### Step 1. Create `voicecode/publish/frontmatter.py`

**What**: New utility module with a single function to extract front matter key-value pairs from markdown text.

**Where**: `voicecode/publish/frontmatter.py`

**How**:

```python
"""Lightweight YAML front-matter parser for published documents."""


def parse_frontmatter(text: str) -> dict[str, str]:
    """Extract YAML front matter from a markdown document.

    Finds the opening ``---`` at the start of the text and the closing
    ``---``, then splits intervening lines on the first ``:`` to build
    a dict.  Returns an empty dict if no front matter block is found.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    result: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip().strip('"').strip("'")
    return result
```

No external dependencies. Handles the exact front matter format used by all 9 publish agents (simple key: value lines, no nesting).

#### Step 2. Add `DOC_TYPE_COLORS` mapping and parse front matter in `open_doc_reader`

**What**: Store the doc type when a document is opened; define a mapping from type to existing color pair.

**Where**: `voicecode/ui/overlays.py` — imports section and `open_doc_reader()` (line 611)

**How**:

Add import at top:
```python
from voicecode.publish.frontmatter import parse_frontmatter
```

Add mapping constant (near other constants at module level):
```python
DOC_TYPE_COLORS = {
    "arch": CP_BANNER,    # cyan — structural
    "adr": CP_BANNER,     # cyan — structural
    "plan": CP_AGENT,     # green — forward-looking
    "spec": CP_AGENT,     # green — forward-looking
    "glossary": CP_PUBLISH,   # magenta — reference
    "schema": CP_PUBLISH,     # magenta — reference
    "constraints": CP_PUBLISH, # magenta — reference
    "conventions": CP_PUBLISH, # magenta — reference
    "readme": CP_XFER,   # yellow — entry point
}
```

In `open_doc_reader()` (after line 623 where `doc_reader_lines` is set):
```python
fm = parse_frontmatter(content)
app.doc_reader_doc_type = fm.get("type", "")
```

#### Step 3. Add `doc_reader_doc_type` state field

**What**: New state field on the app object.

**Where**: `voicecode/app.py` line 205 (after `doc_reader_scroll`)

**How**: Add `self.doc_reader_doc_type = ""` alongside the other doc reader fields.

#### Step 4. Apply type-based color to doc viewer title bar

**What**: Use `DOC_TYPE_COLORS` to set border and title color in `draw_doc_reader()`.

**Where**: `voicecode/ui/overlays.py`, `draw_doc_reader()` method (lines 655-656)

**How**: Replace the fixed `CP_HEADER` assignments:

```python
# Current (lines 655-656):
border_attr = curses.color_pair(CP_HEADER) | curses.A_BOLD
title_attr = curses.color_pair(CP_HEADER) | curses.A_BOLD

# New:
type_cp = DOC_TYPE_COLORS.get(app.doc_reader_doc_type, CP_HEADER)
border_attr = curses.color_pair(type_cp) | curses.A_BOLD
title_attr = curses.color_pair(type_cp) | curses.A_BOLD
```

Also update the title text in `_draw_doc_viewer()` (line 701) to include a type badge when present:

```python
# Current:
title = f" {app.doc_reader_title} "

# New:
if app.doc_reader_doc_type:
    badge = app.doc_reader_doc_type.upper()
    title = f" [{badge}] {app.doc_reader_title} "
else:
    title = f" {app.doc_reader_title} "
```

#### Step 5. Add type badges to Documents category in folder browser

**What**: Prepend colored `[TYPE]` badge to each document entry in the Documents tab.

**Where**: `voicecode/ui/overlays.py`, `draw_folder_slug()` method (lines 436-452), and `scan_folder_slugs()` (lines 322-336)

**How**:

In `scan_folder_slugs()`, after building the `docs` list (line 336), build a front matter cache:

```python
# After line 336:
app._doc_type_cache = {}
if app.working_dir:
    wd_root = Path(app.working_dir).expanduser()
    for rel_path in docs:
        try:
            full = wd_root / rel_path
            head = full.read_text(encoding="utf-8")[:512]  # First ~10 lines
            fm = parse_frontmatter(head)
            if fm.get("type"):
                app._doc_type_cache[rel_path] = fm["type"]
        except (OSError, UnicodeDecodeError):
            pass
```

In `draw_folder_slug()` (inside the loop at lines 436-449), when rendering category 2 entries, insert the badge:

```python
# Inside the rendering loop, after getting `entry`:
if cat == 2 and entry in app._doc_type_cache:
    doc_type = app._doc_type_cache[entry]
    badge = f"[{doc_type.upper()}] "
else:
    badge = ""
text = f" {icon} {badge}{entry}"
```

To color the badge separately, use `addstr` for the badge portion with the type color pair, then continue with the normal entry text. This requires splitting the single `addnstr` on line 449 into two calls — one for the badge and one for the rest.

#### Step 6. Add `[M]Maintain` to doc viewer help text

**What**: Show the `M` keybinding in the doc viewer's bottom help bar.

**Where**: `voicecode/ui/overlays.py`, `_draw_doc_viewer()` (lines 733-736)

**How**: Update the help text strings:

```python
# Current (line 734):
help_text = " [↑↓/PgUp/PgDn]Scroll [Enter]Edit [Ins]Inject [ESC/Q]Close "

# New:
help_text = " [↑↓/PgUp/PgDn]Scroll [M]Maintain [Enter]Edit [Ins]Inject [ESC/Q]Close "

# Tool detail mode stays unchanged (line 736)
```

---

### Phase 2: Maintenance Agent Framework

#### Step 7. Create maintenance package structure

**What**: New package with base class, registry, and prompt directory.

**Where**: Create these files:
- `voicecode/publish/maintenance/__init__.py`
- `voicecode/publish/maintenance/base.py`
- `voicecode/publish/maintenance/prompts/` (directory)

**How**:

`voicecode/publish/maintenance/base.py`:
```python
"""Base class for document maintenance agents."""

from pathlib import Path

MAINT_PROMPTS_DIR = Path(__file__).parent / "prompts"


class MaintenanceAgent:
    """Base class for maintenance actions on published documents.

    Each subclass sets ``action_name`` (e.g. "RECONCILE").  The prompt
    template is loaded at runtime from ``prompts/<ACTION_NAME>.md``.

    Templates receive three placeholders:
      - {doc_path}    — path to the document being maintained
      - {doc_content} — full text of the document
      - {doc_type}    — the document's front matter type value
    """

    action_name: str = ""
    description: str = ""  # Short label shown in overlay

    @property
    def prompt_path(self) -> Path:
        return MAINT_PROMPTS_DIR / f"{self.action_name}.md"

    @property
    def prompt_template(self) -> str:
        return self.prompt_path.read_text(encoding="utf-8")

    def build_prompt(self, doc_path: str, doc_content: str, doc_type: str) -> str:
        return self.prompt_template.format(
            doc_path=doc_path,
            doc_content=doc_content,
            doc_type=doc_type,
        )

    @property
    def applicable_types(self) -> list[str]:
        """Document types this action applies to. Empty list = all types."""
        return []
```

`voicecode/publish/maintenance/__init__.py`:
```python
"""Maintenance agent registry."""

_MAINT_REGISTRY: dict = {}


def _init_registry():
    from voicecode.publish.maintenance.reconcile import ReconcileAgent
    from voicecode.publish.maintenance.refresh import RefreshAgent
    from voicecode.publish.maintenance.coverage import CoverageAgent
    _MAINT_REGISTRY["RECONCILE"] = ReconcileAgent()
    _MAINT_REGISTRY["REFRESH"] = RefreshAgent()
    _MAINT_REGISTRY["COVERAGE"] = CoverageAgent()


def get_maintenance_agent(action_name: str):
    if not _MAINT_REGISTRY:
        _init_registry()
    return _MAINT_REGISTRY.get(action_name)


def get_available_actions(doc_type: str) -> list[tuple[str, str]]:
    """Return (action_name, description) pairs applicable to doc_type."""
    if not _MAINT_REGISTRY:
        _init_registry()
    result = []
    for name, agent in _MAINT_REGISTRY.items():
        types = agent.applicable_types
        if not types or doc_type.lower() in [t.lower() for t in types]:
            result.append((name, agent.description))
    return result
```

#### Step 8. Create the three maintenance agent subclasses

**What**: Three minimal agent classes mirroring the publish agent pattern.

**Where**:
- `voicecode/publish/maintenance/reconcile.py`
- `voicecode/publish/maintenance/refresh.py`
- `voicecode/publish/maintenance/coverage.py`

**How**: Each follows the same minimal pattern:

`reconcile.py`:
```python
"""Reconcile maintenance agent — checks document drift against codebase."""

from voicecode.publish.maintenance.base import MaintenanceAgent


class ReconcileAgent(MaintenanceAgent):
    action_name = "RECONCILE"
    description = "Reconcile — check drift"
```

`refresh.py`:
```python
"""Refresh maintenance agent — updates document to match current code."""

from voicecode.publish.maintenance.base import MaintenanceAgent


class RefreshAgent(MaintenanceAgent):
    action_name = "REFRESH"
    description = "Refresh — update in-place"
```

`coverage.py`:
```python
"""Coverage Check maintenance agent — finds gaps in document coverage."""

from voicecode.publish.maintenance.base import MaintenanceAgent


class CoverageAgent(MaintenanceAgent):
    action_name = "COVERAGE"
    description = "Coverage — find gaps"

    @property
    def applicable_types(self) -> list[str]:
        return ["glossary", "schema", "constraints", "conventions", "arch"]
```

#### Step 9. Extract shared execution logic from `_execute_publish`

**What**: Move the agent-launch pipeline (lines 288-330 of `publish_overlay.py`) into a reusable helper that both publish and maintenance can call.

**Where**: `voicecode/ui/publish_overlay.py` — add a module-level function `execute_agent_prompt(app, prompt_text, label)` and refactor `_execute_publish()` to call it.

**How**:

Extract into a new function (above the `PublishOverlay` class):

```python
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
```

Then simplify `_execute_publish()` to:

```python
def _execute_publish(self):
    app = self.app
    doc_type = app.publish_selected_type
    dest_folder = app.publish_selected_folder

    agent = get_publish_agent(doc_type)
    if not agent:
        app.set_status(f"No agent for {doc_type} — this shouldn't happen.")
        return

    scope = app.browser.get_active_prompt_text() or app.current_prompt
    if not scope and app.fragments:
        scope = " ".join(app.fragments)
    if not scope:
        scope = "the entire repository (all top-level folders and files)"

    prompt_text = agent.build_prompt(scope, dest_folder)
    dest_label = f"docs/{dest_folder}" if dest_folder else "README.md"
    label = f"[PUBLISH {doc_type} → {dest_label}]"

    execute_agent_prompt(app, prompt_text, label)
```

**Why**: Maintenance needs the same execution pipeline. Duplicating 40 lines of state setup would be fragile.

#### Step 10. Add maintenance overlay state fields to `app.py`

**What**: State for the maintenance action selection overlay.

**Where**: `voicecode/app.py`, after doc reader state (around line 213)

**How**:
```python
# Maintenance overlay state (modal within doc reader)
self.show_maint_overlay = False
self.maint_cursor = 0
self.maint_actions: list[tuple[str, str]] = []  # (action_name, description)
```

#### Step 11. Add maintenance overlay drawing

**What**: A small centered modal that draws on top of the doc reader, listing available maintenance actions with cursor selection.

**Where**: `voicecode/ui/overlays.py` — new method `draw_maint_overlay()` on `OverlayRenderer`

**How**: Follow the `_draw_save_confirm()` pattern (lines 887-913) but with a dynamic action list:

```python
def draw_maint_overlay(self):
    """Draw the maintenance action selection modal over the doc reader."""
    app = self.app
    h, w = app.stdscr.getmaxyx()

    actions = app.maint_actions
    label = app.doc_reader_doc_type.upper() if app.doc_reader_doc_type else "FILE"

    # Dialog sizing
    max_desc_len = max((len(desc) for _, desc in actions), default=20)
    dialog_w = max(36, max_desc_len + 10)
    dialog_h = len(actions) + 4  # border + title + actions + footer
    dx = (w - dialog_w) // 2
    dy = (h - dialog_h) // 2

    border_attr = curses.color_pair(CP_HEADER) | curses.A_BOLD
    text_attr = curses.color_pair(CP_PROMPT) | curses.A_BOLD
    sel_attr = curses.color_pair(CP_AGENT) | curses.A_BOLD
    key_attr = curses.color_pair(CP_AGENT) | curses.A_BOLD

    try:
        # Top border with title
        title = f" Maintain: {label} "
        top_left = "╔═"
        top_right = "═" * (dialog_w - len(top_left) - len(title) - 1) + "╗"
        app.stdscr.addstr(dy, dx, top_left, border_attr)
        app.stdscr.addstr(dy, dx + len(top_left), title, border_attr)
        app.stdscr.addstr(dy, dx + len(top_left) + len(title), top_right, border_attr)

        # Action rows
        for i, (name, desc) in enumerate(actions):
            row_y = dy + 1 + i
            pointer = "▸" if i == app.maint_cursor else " "
            line_text = f" {pointer} {desc}"
            padded = line_text + " " * max(0, dialog_w - 2 - len(line_text))
            attr = sel_attr if i == app.maint_cursor else text_attr
            app.stdscr.addstr(row_y, dx, "║", border_attr)
            app.stdscr.addnstr(row_y, dx + 1, padded, dialog_w - 2, attr)
            app.stdscr.addstr(row_y, dx + dialog_w - 1, "║", border_attr)

        # Empty separator row
        sep_y = dy + 1 + len(actions)
        app.stdscr.addstr(sep_y, dx, "║" + " " * (dialog_w - 2) + "║", border_attr)

        # Footer with help
        foot_y = dy + 2 + len(actions)
        options = "[Enter]Select  [ESC]Cancel"
        app.stdscr.addstr(foot_y, dx, "║", border_attr)
        centered = options.center(dialog_w - 2)
        app.stdscr.addnstr(foot_y, dx + 1, centered, dialog_w - 2, key_attr)
        app.stdscr.addstr(foot_y, dx + dialog_w - 1, "║", border_attr)

        # Bottom border
        bot = "╚" + "═" * (dialog_w - 2) + "╝"
        app.stdscr.addnstr(foot_y + 1, dx, bot, dialog_w, border_attr)
    except curses.error:
        pass
```

#### Step 12. Add maintenance overlay to the draw pipeline

**What**: Render the maintenance overlay when active.

**Where**: `voicecode/ui/drawing.py` (after line 457, after doc reader)

**How**:
```python
if app.show_doc_reader:
    app.overlays.draw_doc_reader()
if app.show_maint_overlay:
    app.overlays.draw_maint_overlay()
```

The maintenance overlay draws after (on top of) the doc reader since it's a modal within it.

#### Step 13. Add `M` key handler in doc reader view mode

**What**: When user presses `M` in the doc reader (view mode), open the maintenance overlay with actions filtered by document type.

**Where**: `voicecode/ui/input.py`, doc reader view-mode section (before line 449's `return`)

**How**: Add a new `elif` block after the Insert key handler (line 448) and before the `return` on line 449:

```python
elif ch in (ord("m"), ord("M")):
    from voicecode.publish.maintenance import get_available_actions
    doc_type = app.doc_reader_doc_type if hasattr(app, 'doc_reader_doc_type') else ""
    actions = get_available_actions(doc_type)
    if actions:
        app.maint_actions = actions
        app.maint_cursor = 0
        app.show_maint_overlay = True
    else:
        app.set_status("No maintenance actions available for this file type.")
```

**Why**: The `M` key is used at the top level for AI provider toggle (line 1206), but inside the doc reader modal it is unbound — the doc reader returns before the top-level dispatch runs (line 449). So there is no conflict.

#### Step 14. Add maintenance overlay input dispatch

**What**: Handle arrow keys, Enter, and ESC in the maintenance overlay.

**Where**: `voicecode/ui/input.py` — add a new block at the top of the doc reader section (before line 256), or just inside the `if app.show_doc_reader:` block, before the edit/view mode dispatch.

**How**: Insert at the beginning of the `if app.show_doc_reader:` block:

```python
if app.show_doc_reader:
    # ── Maintenance overlay (modal within doc reader) ──
    if app.show_maint_overlay:
        if ch in (27,):  # ESC
            app.show_maint_overlay = False
            app.stdscr.nodelay(True)
            app.stdscr.getch()
        elif ch == curses.KEY_UP:
            app.maint_cursor = max(0, app.maint_cursor - 1)
        elif ch == curses.KEY_DOWN:
            app.maint_cursor = min(len(app.maint_actions) - 1, app.maint_cursor + 1)
        elif ch in (10, 13, curses.KEY_ENTER):
            # Execute selected maintenance action
            from voicecode.constants import AgentState
            if app.agent_state not in (AgentState.IDLE, AgentState.DONE):
                app.set_status("Agent is busy. Wait or kill it first.")
                app.show_maint_overlay = False
            elif app.maint_actions:
                action_name, _ = app.maint_actions[app.maint_cursor]
                self._execute_maintenance(action_name)
        return

    # ... existing doc reader code ...
```

#### Step 15. Implement `_execute_maintenance()` on InputHandler

**What**: Build the maintenance prompt and feed it into the shared execution pipeline.

**Where**: `voicecode/ui/input.py` — new method on `InputHandler`

**How**:

```python
def _execute_maintenance(self, action_name: str):
    """Build and execute a maintenance agent prompt on the current document."""
    from voicecode.publish.maintenance import get_maintenance_agent
    from voicecode.ui.publish_overlay import execute_agent_prompt

    app = self.app
    agent = get_maintenance_agent(action_name)
    if not agent:
        app.set_status(f"Unknown maintenance action: {action_name}")
        return

    doc_path = app.doc_reader_path
    doc_content = "\n".join(app.doc_reader_lines)
    doc_type = app.doc_reader_doc_type or "unknown"

    prompt_text = agent.build_prompt(doc_path, doc_content, doc_type)

    # Close overlays before launching agent
    app.show_maint_overlay = False
    self._close_doc_reader()

    label = f"[MAINTAIN {action_name} → {doc_path}]"
    execute_agent_prompt(app, prompt_text, label)
```

---

### Phase 3: Prompt Templates

#### Step 16. Write RECONCILE prompt template

**What**: Prompt that instructs the agent to compare the document against current code and produce a drift report, saved as a single reconcile file alongside the document.

**Where**: `voicecode/publish/maintenance/prompts/RECONCILE.md`

**How**: The prompt should:
- Receive `{doc_path}`, `{doc_content}`, `{doc_type}` placeholders
- Instruct the agent to read the document, scan the codebase, and produce a structured report
- Report sections: Summary, Accurate (still correct), Stale (needs updating), Missing (should be added), Recommendations
- Save the report alongside the source document: if the document is at `docs/context/GLOSSARY.md`, save the reconcile report as `docs/context/GLOSSARY-RECONCILE.md`
- The report file should have front matter with `type: reconcile-report`, `source`, and `date`
- Remind the agent to read actual code, not hallucinate

#### Step 17. Write REFRESH prompt template

**What**: Prompt that instructs the agent to rewrite the document to match current code.

**Where**: `voicecode/publish/maintenance/prompts/REFRESH.md`

**How**: The prompt should:
- Receive `{doc_path}`, `{doc_content}`, `{doc_type}` placeholders
- Instruct the agent to read the current document, scan the codebase, and rewrite the document at `{doc_path}`
- Preserve the document's structure, voice, section headings, and front matter format
- Update the `date` field in front matter to today
- Update facts, code references, file paths, and descriptions to match current codebase
- Do not invent features or describe things that don't exist in code
- The output is the file itself, overwritten in-place (git handles rollback)

#### Step 18. Write COVERAGE prompt template

**What**: Prompt that instructs the agent to find gaps in document coverage.

**Where**: `voicecode/publish/maintenance/prompts/COVERAGE.md`

**How**: The prompt should:
- Receive `{doc_path}`, `{doc_content}`, `{doc_type}` placeholders
- Instruct the agent to scan the codebase and compare against what's documented
- Behavior varies by `{doc_type}`:
  - **glossary**: find terms, acronyms, and domain concepts used in code but missing from the glossary
  - **schema**: find data structures, models, or entities not documented
  - **constraints**: find implicit constraints in code (error checks, assertions, limits) not captured
  - **conventions**: find consistent patterns in code not documented as conventions
  - **arch**: find modules, components, or integrations not covered
- Save the report alongside the source document as `{basename}-COVERAGE.md` (same pattern as reconcile)
- Report format: list of missing items, each with the item name, where it was found in code, and a suggested definition/entry

## 4. Data Model / Schema Changes

### New state fields on `BBSApp` (`app.py`)

```python
self.doc_reader_doc_type = ""              # Parsed from front matter when doc opens
self.show_maint_overlay = False            # Maintenance action selection modal
self.maint_cursor = 0                      # Cursor position in action list
self.maint_actions: list[tuple[str, str]] = []  # (action_name, description)
```

### New cache field on `BBSApp` (`app.py`)

```python
self._doc_type_cache: dict[str, str] = {}  # rel_path → front matter type (for browser badges)
```

### New classes

- `MaintenanceAgent` — base class in `voicecode/publish/maintenance/base.py`
- `ReconcileAgent`, `RefreshAgent`, `CoverageAgent` — subclasses

### New module-level function

- `execute_agent_prompt(app, prompt_text, label)` in `voicecode/ui/publish_overlay.py` — extracted from `_execute_publish()`

## 5. Integration Points

- **Agent runner** (`voicecode/agent/runner.py`): No changes. Maintenance prompts flow through `run_agent()` identically to publish prompts.
- **CLI providers** (`voicecode/providers/`): No changes. Maintenance prompts are plain text.
- **Publish overlay** (`voicecode/ui/publish_overlay.py`): Refactored to use `execute_agent_prompt()`. Publish behavior is unchanged.
- **Document viewer** (`voicecode/ui/overlays.py`): Gets type-based coloring, type badge in title, `[M]Maintain` in help bar, and new `draw_maint_overlay()` method.
- **Folder browser** (`voicecode/ui/overlays.py`): Gets type badges in Documents category via front matter cache.
- **Input handler** (`voicecode/ui/input.py`): Gets `M` key in doc reader, maintenance overlay input dispatch, and `_execute_maintenance()` method.
- **Draw pipeline** (`voicecode/ui/drawing.py`): Adds `draw_maint_overlay()` after `draw_doc_reader()`.

## 6. Edge Cases & Risks

### Edge cases

- **M on non-markdown file**: `get_available_actions("")` returns all actions (empty `applicable_types` = all). This is intentional — let the user try reconcile on any file. The agent will do its best.
- **M on tool detail view**: `doc_reader_path` is empty for tool details (set at `overlays.py:630`). `doc_reader_doc_type` will be `""`. Actions will be shown but `_execute_maintenance` will pass an empty path — the agent prompt will still have the content via `{doc_content}`. This is acceptable.
- **Front matter with special characters**: Quoted values (`title: "foo: bar"`) are handled by stripping quotes. Colons inside quoted values won't break because we partition on the first `:` only.
- **Concurrent agent**: Guarded by the `AgentState` check in step 14 — same as existing publish guard.
- **Empty maint_actions**: The `M` key handler checks `if actions:` and shows a status message if empty.

### Risks

- **Prompt template quality**: The maintenance prompts are the most important part. If the agent instructions are too vague, results will be poor. Iterate on prompt quality after initial implementation.
- **Large doc_content in prompt**: Embedding the full document in `{doc_content}` could consume significant context. Mitigation: the prompt templates should instruct the agent to use the embedded content as a reference but primarily read the file on disk via tools.
- **_execute_publish refactor**: Extracting the shared helper changes a working function. Test carefully that publish still works after the refactor.

## 7. Verification

### Phase 1 (Styling)

1. Open a published document (e.g., `docs/context/GLOSSARY.md`) in the doc viewer — title bar should be magenta with `[GLOSSARY]` badge.
2. Open `docs/context/ARCH.md` — title bar should be cyan with `[ARCH]` badge.
3. Open a file without front matter — should use default yellow/blue `CP_HEADER` styling, no badge.
4. Open the folder browser, navigate to Documents tab — each entry should show a colored type badge.
5. The `[M]Maintain` hint should appear in the doc viewer help bar.

### Phase 2 (Framework)

6. Press `M` in the doc viewer on a GLOSSARY — maintenance overlay should appear with all 3 actions.
7. Press `M` on a PLAN — overlay should show Reconcile and Refresh (not Coverage).
8. Press `M` on a `.txt` file or file without front matter — should show status message "No maintenance actions available for this file type." (or show all if type is empty — depends on `get_available_actions("")` behavior for generic files).
9. ESC in the maintenance overlay returns to doc reader without launching anything.
10. Arrow keys navigate the action list; cursor wraps correctly at boundaries.

### Phase 3 (Agents)

11. Select Reconcile on GLOSSARY — agent streams a drift report and saves `GLOSSARY-RECONCILE.md` alongside.
12. Select Refresh on ARCH — agent rewrites `ARCH.md` in-place with updated content. Verify with `git diff`.
13. Select Coverage on GLOSSARY — agent streams a gap report and saves `GLOSSARY-COVERAGE.md`.
14. Verify the ZMODEM animation plays and TTS summary is spoken, same as a publish action.
15. Try triggering maintenance while an agent is running — should show "Agent is busy" status.

### Regression

16. Publish a new document (e.g., SPEC) — verify `_execute_publish` still works correctly after the refactor to `execute_agent_prompt`.

## 8. Open Questions

All open questions from the spec have been resolved per the user's answers (see Goal section). No remaining open questions.

Implementation order recommendation: Phase 1 → Phase 2 → Phase 3. Each phase is independently shippable. Phase 1 provides immediate visual value with no new agents. Phase 2 builds the framework without needing finished prompt templates (can use placeholder prompts). Phase 3 is pure prompt authoring.
