---
type: spec
title: "Document Type Styling & Maintenance Agents"
scope: "voicecode/publish/, voicecode/ui/overlays.py, voicecode/ui/publish_overlay.py, voicecode/ui/colors.py"
date: 2026-03-24
---

## 1. Problem Statement

VoiceCode's publish system generates structured documents (ARCH, SPEC, PLAN, GLOSSARY, etc.) with a `type` field in YAML front matter. Today that field is **write-only** — agents emit it, but neither the document viewer nor the folder browser reads it back. All documents look identical in the UI regardless of type.

More critically, published documents become stale as the codebase evolves. A GLOSSARY written last week may reference classes that have been renamed. A SPEC may describe behavior that has since changed. There is no way to check or fix this from within the app — the user must manually re-read documents and mentally diff them against current code.

This spec addresses both problems:

1. **Visual differentiation** — Parse the `type` field and use it to style documents distinctly in the viewer and browser.
2. **Maintenance agents** — Provide agent-powered actions that can be triggered from the document viewer to verify, refresh, or augment a published document against the current codebase.

## 2. Goals & Non-Goals

### Goals

- Parse YAML front matter from published documents to extract the `type` field.
- Assign each document type a distinct color or visual indicator in the document viewer title bar and the folder browser listing (Tab overlay, Documents category).
- Build a maintenance action overlay accessible from the document viewer that offers type-appropriate agent actions.
- Implement three initial maintenance agents: **Reconcile**, **Refresh**, and **Coverage Check**.
- Reuse the existing `PublishAgent` base class and agent execution pipeline (`_execute_publish` pattern) so maintenance actions stream output identically to publish actions.

### Non-Goals

- Automatic/scheduled maintenance — all actions are user-initiated.
- Structural document transformations (split, merge, promote/demote) — deferred to a future iteration.
- Changing how publish agents write the `type` field — the current front matter format is stable.
- Adding new document types — this spec works with the existing nine types.

## 3. Proposed Solution

### 3.1 Front Matter Parsing

Add a small utility function that extracts YAML front matter fields from a document's first lines. This avoids a PyYAML dependency by doing simple key-value extraction on the `---`-delimited block. The parser returns a dict with at minimum `type`, `title`, `scope`, and `date`.

### 3.2 Type-Based Styling

Map each document type to a color pair for use in:

- **Document viewer title bar** — The border/title color reflects the document type instead of always using `CP_HEADER`.
- **Folder browser (Tab overlay, Documents category)** — Each document entry gets a type badge (e.g., `[SPEC]`, `[ARCH]`) rendered in the type's color, prepended to the filename.

The color mapping groups related types:

| Group | Types | Color | Rationale |
|-------|-------|-------|-----------|
| Architecture | ARCH, ADR | Cyan (`CP_BANNER`) | Structural/foundational |
| Planning | PLAN, SPEC | Green (`CP_AGENT`) | Forward-looking |
| Reference | GLOSSARY, SCHEMA, CONSTRAINTS, CONVENTIONS | Magenta (`CP_PUBLISH`) | Living reference material |
| Entry point | README | Yellow (`CP_XFER`) | Singular, high-visibility |

New color pair constants are not required — reuse existing pairs. If the type is unrecognized or missing, fall back to `CP_HEADER` (current behavior).

### 3.3 Maintenance Agents

Maintenance agents are a new subclass family alongside publish agents. They share the same execution pipeline but differ in input: a publish agent receives a scope description and produces a new document, while a maintenance agent receives an **existing document path** and produces either a report or a revised document.

#### Base Class: `MaintenanceAgent`

```
voicecode/publish/maintenance/base.py
```

Extends the pattern from `PublishAgent`:

- `action_name: str` — e.g., "RECONCILE", "REFRESH", "COVERAGE"
- `prompt_path` — loads from `voicecode/publish/maintenance/prompts/<ACTION>.md`
- `build_prompt(doc_path, doc_content, doc_type)` — injects the document text and its type into the prompt template

#### Three Initial Agents

**Reconcile** (`maintenance/reconcile.py`)
- **Purpose**: Compare the document against current code and produce a drift report.
- **Output**: A structured report listing stale sections, inaccurate claims, missing elements, and suggested corrections. Displayed as agent streaming output in the agent pane — not written to disk.
- **Applicable to**: All document types.

**Refresh** (`maintenance/refresh.py`)
- **Purpose**: Rewrite stale sections in-place to match current code.
- **Output**: A revised version of the document written to the same file path. Preserves the document's structure, voice, and front matter while updating facts.
- **Applicable to**: All document types. Most valuable for ARCH, SPEC, GLOSSARY, SCHEMA.

**Coverage Check** (`maintenance/coverage.py`)
- **Purpose**: Scan the codebase for items that should be in the document but aren't.
- **Output**: A report listing gaps — undefined terms (GLOSSARY), undocumented entities (SCHEMA), uncaptured constraints (CONSTRAINTS), missing components (ARCH).
- **Applicable to**: GLOSSARY, SCHEMA, CONSTRAINTS, CONVENTIONS, ARCH.

### 3.4 Maintenance Overlay

When the user presses `M` while viewing a document in the doc reader, a small selection overlay appears listing the maintenance actions available for that document's type. Selecting an action closes the overlay and executes the maintenance agent through the standard pipeline.

## 4. Technical Design

### 4.1 Front Matter Parser

New utility module:

```
voicecode/publish/frontmatter.py
```

```python
def parse_frontmatter(text: str) -> dict[str, str]:
    """Extract YAML front matter from a markdown document.

    Returns a dict of key-value pairs. Returns empty dict if no
    front matter block is found.
    """
```

Implementation: find the opening `---` at line 0, find the closing `---`, split intervening lines on first `:`, strip values. No external dependency needed — the front matter format is simple key-value pairs without nesting.

### 4.2 Document Viewer Styling Changes

**File**: `voicecode/ui/overlays.py`, method `draw_doc_reader` (line 638)

Currently, the viewer sets:
```python
border_attr = curses.color_pair(CP_HEADER) | curses.A_BOLD
title_attr = curses.color_pair(CP_HEADER) | curses.A_BOLD
```

Change to: after opening a document in `open_doc_reader`, parse its front matter and store the type on `app.doc_reader_doc_type`. In `draw_doc_reader`, look up the color pair from a `DOC_TYPE_COLORS` mapping and use it for the border and title attributes.

### 4.3 Folder Browser Styling Changes

**File**: `voicecode/ui/overlays.py`, method `draw_folder_slug` (Documents category rendering)

When rendering document entries in category 2 (Documents), read the front matter of each file to extract its type. Cache results in a dict keyed by file path (cleared on each `scan_folder_slugs` call). Prepend a colored `[TYPE]` badge to each entry.

For performance: front matter parsing only reads the first ~10 lines of each file, so even scanning 50+ documents is negligible.

### 4.4 Maintenance Agent Base Class

**File**: `voicecode/publish/maintenance/base.py`

```python
class MaintenanceAgent:
    action_name: str = ""

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
        """Document types this action applies to. Empty = all types."""
        return []
```

### 4.5 Maintenance Prompt Templates

Stored in `voicecode/publish/maintenance/prompts/`:

- `RECONCILE.md` — Instructs the agent to read the provided document and the actual codebase, then produce a structured drift report with sections: Accurate, Stale, Missing, Recommendations.
- `REFRESH.md` — Instructs the agent to rewrite the document at `{doc_path}`, preserving structure and front matter, updating all facts to match current code. Includes `{doc_content}` as reference.
- `COVERAGE.md` — Instructs the agent to scan the codebase for items that should appear in a document of type `{doc_type}` at `{doc_path}` but don't. Report format: list of missing items with brief justification.

Each template receives three placeholders: `{doc_path}`, `{doc_content}`, `{doc_type}`.

### 4.6 Maintenance Overlay UI

**File**: `voicecode/ui/overlays.py` (new method on `OverlayRenderer`)

Small centered overlay (similar to save-confirm dialog) listing available actions:

```
┌─ Maintain: GLOSSARY ─────────┐
│                               │
│  ▸ Reconcile — check drift    │
│    Refresh  — update in-place │
│    Coverage — find gaps       │
│                               │
│  [Enter]Select  [ESC]Cancel   │
└───────────────────────────────┘
```

State fields on `app`:
- `show_maint_overlay: bool`
- `maint_cursor: int`
- `maint_actions: list[tuple[str, str]]` — (action_name, description) filtered by applicable types

### 4.7 Execution Flow

When the user selects a maintenance action:

1. Close the maintenance overlay and the document viewer.
2. Read the document content from `app.doc_reader_path`.
3. Parse front matter to get `doc_type`.
4. Build the maintenance prompt via `agent.build_prompt(doc_path, doc_content, doc_type)`.
5. Feed into the same execution pipeline as `_execute_publish`: set `app.executed_prompt_text` to `[MAINTAIN RECONCILE → docs/context/GLOSSARY.md]`, trigger ZMODEM animation, spawn `run_agent` thread.

This reuses the existing `_execute_publish` machinery from `publish_overlay.py` lines 263-330. Extract the shared execution logic into a helper (e.g., `execute_agent_prompt(prompt_text, label)`) that both publish and maintenance can call.

### 4.8 Maintenance Agent Registry

**File**: `voicecode/publish/maintenance/__init__.py`

```python
_MAINT_REGISTRY: dict[str, MaintenanceAgent] = {}

def get_maintenance_agent(action_name: str) -> MaintenanceAgent | None:
    ...

def get_available_actions(doc_type: str) -> list[tuple[str, str]]:
    """Return (action_name, description) pairs applicable to doc_type."""
    ...
```

### 4.9 Input Handling

**File**: `voicecode/ui/input.py`

In the doc reader input section, add handling for `M` key:
- Parse front matter from `app.doc_reader_lines` to determine document type.
- Call `get_available_actions(doc_type)` to populate the overlay.
- Set `app.show_maint_overlay = True`.

In the maintenance overlay input section (new block):
- `↑↓` — cursor movement
- `Enter` — execute selected action
- `ESC` — close overlay, return to doc reader

## 5. UI / UX

### Document Viewer Changes

- Title bar border color matches document type (cyan for ARCH, green for SPEC, etc.).
- Type badge appears in the title: `── [SPEC] Speech-to-Text Subsystem ──`.
- New help text line adds `[M]Maintain` to the existing `[Enter]Edit [Ins]Inject [ESC]Close`.

### Folder Browser Changes

- Each document in the Documents tab gets a colored type badge: `[ARCH] ARCH.md`, `[SPEC] SPEC.md`.
- Documents without parseable front matter show no badge (graceful degradation).

### Maintenance Overlay

- Small centered modal (approx 35 chars wide) appears over the doc reader.
- Lists only actions applicable to the current document type.
- Cursor-based selection with Enter to confirm, ESC to cancel.
- After selection, the doc reader closes and the agent pane shows streaming output with the standard ZMODEM transfer animation and typewriter effect.
- Status bar shows: `Maintaining RECONCILE → docs/context/GLOSSARY.md ...`

## 6. Integration Points

- **Agent execution pipeline** (`voicecode/agent/runner.py`): Maintenance agents use the identical `run_agent()` flow. No changes needed to the runner.
- **CLI providers** (`voicecode/providers/`): Maintenance prompts are plain text — no provider changes needed.
- **Publish overlay** (`voicecode/ui/publish_overlay.py`): The shared execution logic in `_execute_publish` should be extracted into a reusable helper so maintenance doesn't duplicate it.
- **Document viewer** (`voicecode/ui/overlays.py`): Modified to parse front matter, apply type-based colors, and host the maintenance overlay.
- **Input handler** (`voicecode/ui/input.py`): New key binding (`M`) in doc reader mode, plus new input block for maintenance overlay navigation.
- **Color system** (`voicecode/ui/colors.py`): No new color pairs needed — reuse existing pairs via a type-to-color mapping.

## 7. Edge Cases & Error Handling

- **No front matter**: Document has no `---` block. Parser returns empty dict; UI falls back to default styling; maintenance overlay still opens but uses "unknown" as type (all actions shown).
- **Unrecognized type value**: Front matter has `type: custom`. Treat as unknown — default color, all maintenance actions available.
- **Document read failure**: File was deleted between opening viewer and triggering maintenance. Show status error, do not launch agent.
- **Empty document**: File exists but is empty or has only front matter. Reconcile and coverage check still work (they scan the codebase). Refresh produces a new document body.
- **Concurrent execution**: User triggers maintenance while another agent is running. Same guard as publish — if `agent_state != IDLE`, show status message "Agent already running" and do not launch.
- **Large documents**: The `{doc_content}` placeholder embeds the full document in the prompt. For very large documents this could approach context limits. Mitigation: the maintenance prompt template should instruct the agent to focus on structure and key sections rather than reproducing the full document.
- **Thread safety**: All state mutations happen on the main thread (overlay selection, state field writes). The background agent thread communicates via `app.ui_queue` only. No new concurrency concerns.

## 8. Scope & Milestones

### Milestone 1: Front Matter Parsing + Type Styling

- Implement `voicecode/publish/frontmatter.py`.
- Add type-based color to doc viewer title bar.
- Add type badges to folder browser Documents category.

### Milestone 2: Maintenance Agent Framework

- Create `voicecode/publish/maintenance/` package with `MaintenanceAgent` base class and registry.
- Extract shared execution logic from `_execute_publish` into a reusable helper.
- Add maintenance overlay UI and `M` keybinding in doc reader.

### Milestone 3: Initial Maintenance Agents

- Implement Reconcile agent with prompt template.
- Implement Refresh agent with prompt template.
- Implement Coverage Check agent with prompt template.

### Future Iterations

- **Prune** agent — remove references to deleted code/features.
- **Backfill** agent — add missing entries to reference docs (GLOSSARY, SCHEMA).
- **Staleness indicators** — show document age or last-reconciled date in the browser.
- **Batch maintenance** — run reconcile across all documents and produce a summary dashboard.

## 9. Success Criteria

- Documents in the viewer and folder browser are visually distinguishable by type without reading the filename.
- Pressing `M` on a document in the viewer opens the maintenance overlay with type-appropriate actions.
- Selecting Reconcile on a GLOSSARY document produces a streaming drift report in the agent pane identifying terms that no longer match code.
- Selecting Refresh on an ARCH document produces an updated ARCH.md written to disk with current codebase facts.
- Selecting Coverage Check on a GLOSSARY produces a report of codebase terms not yet in the glossary.
- Maintenance actions reuse the existing ZMODEM animation, typewriter streaming, and TTS summary pipeline with no regressions.
- Documents without front matter degrade gracefully — default styling, full action list.

## 10. Open Questions

1. **Report destination for Reconcile/Coverage**: Should reports be displayed only as streaming agent output, or also saved to a file (e.g., `docs/reports/RECONCILE-GLOSSARY-2026-03-24.md`)? Streaming-only is simpler and avoids file clutter; saving enables later review.

2. **Color mapping granularity**: The proposed mapping groups types into 4 color families. Should each of the 9 types get its own unique color pair instead? This would require 4-5 new `CP_*` constants but give maximum differentiation.

3. **Maintenance on non-published docs**: Should the `M` key work on any markdown file opened in the viewer, or only on files with recognized front matter `type` fields? Supporting arbitrary files is more flexible but the prompts are designed around typed documents.

4. **Refresh conflict handling**: When Refresh rewrites a document, should it create a backup first (e.g., `GLOSSARY.md.bak`)? Or rely on git for rollback? Git is the cleaner approach but requires the user to know to check `git diff`.
