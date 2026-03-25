---
type: coverage-report
source: "docs/context/ARCH.md"
date: 2026-03-25
---

# ARCH.md Coverage Report

## Summary

The architecture document provides strong coverage of the core runtime layers (audio pipeline, agent execution, TTS, providers, settings) and the foundational UI rendering/input system. However, it significantly under-documents the **publish/maintenance subsystem** (describing only 1 of 9 implemented publish agents and omitting the entire 5-agent maintenance layer), the **document reader/editor overlay**, the **4-category browser system**, and several UI subsystems added since the document was written. The document covers approximately 18 of 28 identifiable architectural components. **10 gaps found.**

## Gaps Found

### 1. Publish System — All 9 Document Types Are Implemented (not "only ARCH")

- **Item**: Section 3.8 states "currently ARCH.md" and section 8 lists "only ARCH document type is implemented; 12 others are stubbed" under Known Limitations. In reality, all 9 document types (ADR, ARCH, PLAN, SPEC, GLOSSARY, CONSTRAINTS, CONVENTIONS, SCHEMA, README) are fully implemented with dedicated agents and prompt templates.
- **Found in**: `voicecode/publish/adr.py`, `voicecode/publish/plan.py`, `voicecode/publish/spec.py`, `voicecode/publish/glossary.py`, `voicecode/publish/constraints.py`, `voicecode/publish/conventions.py`, `voicecode/publish/schema.py`, `voicecode/publish/readme.py`; `voicecode/ui/publish_overlay.py:12-22` (`IMPLEMENTED_TYPES` lists all 9)
- **Suggested entry** (replace Section 3.8):

> **`base.py` — `PublishAgent`**: Abstract base with `doc_type` property and a `prompt_path` that resolves to `publish/prompts/<DOC_TYPE>.md`. Templates are loaded from disk at runtime (editable via the publish overlay's `E` key). `build_prompt(scope, dest_folder)` fills `{scope}` and `{dest_folder}` placeholders.
>
> **Concrete agents (9 implemented)**:
>
> | Agent | `doc_type` | Fixed destination | Notes |
> |-------|-----------|-------------------|-------|
> | `ArchAgent` | ARCH | — | Flexible folder selection |
> | `AdrAgent` | ADR | — | Flexible folder selection |
> | `PlanAgent` | PLAN | — | Flexible folder selection |
> | `SpecAgent` | SPEC | — | Flexible folder selection |
> | `GlossaryAgent` | GLOSSARY | `context/` | Single file per project |
> | `ConstraintsAgent` | CONSTRAINTS | `context/` | Single file per project |
> | `ConventionsAgent` | CONVENTIONS | `context/` | Single file per project |
> | `SchemaAgent` | SCHEMA | `context/` | Derived from code, single file |
> | `ReadmeAgent` | README | project root | Single file per project |
>
> Agents with `FIXED_DEST_FOLDER` override `build_prompt()` to bypass folder selection. Prompt templates live in `voicecode/publish/prompts/*.md` (one per agent).

---

### 2. Maintenance Agent Subsystem (`voicecode/publish/maintenance/`)

- **Item**: The entire document maintenance layer — 5 agents that audit and update published documents — is absent from the architecture document.
- **Found in**: `voicecode/publish/maintenance/base.py` (`MaintenanceAgent` base class), `voicecode/publish/maintenance/reconcile.py`, `refresh.py`, `coverage.py`, `ctx_drift.py`, `ctx_update.py`; registry in `voicecode/publish/maintenance/__init__.py`; prompt templates in `voicecode/publish/maintenance/prompts/`
- **Suggested entry** (new subsection under 3.8 or as 3.8b):

> ### 3.8b Maintenance Agents (`voicecode/publish/maintenance/`)
>
> **`base.py` — `MaintenanceAgent`**: Abstract base with `action_name`, `description`, `applicable_types` (empty = all), and `excluded_types`. Prompt templates live in `publish/maintenance/prompts/<ACTION>.md` and accept `{doc_path}`, `{doc_content}`, and `{doc_type}` placeholders.
>
> **`__init__.py`**: Lazy-initialized registry. `get_maintenance_agent(action_name)` returns an agent instance; `get_available_actions(doc_type)` returns actions applicable to a given document type (respecting inclusion/exclusion lists).
>
> | Agent | Action | Purpose | Scope |
> |-------|--------|---------|-------|
> | `ReconcileAgent` | RECONCILE | Read-only drift audit → `*-DRIFT.md` report | All except root-context |
> | `RefreshAgent` | REFRESH | Rewrite document in-place to match codebase | All except root-context |
> | `CoverageAgent` | COVERAGE | Find undocumented items → `*-COVERAGE.md` report | glossary, schema, constraints, conventions, arch |
> | `CtxDriftAgent` | CTX_DRIFT | Drift audit for root context files (CLAUDE.md, AGENTS.md) | root-context only |
> | `CtxUpdateAgent` | CTX_UPDATE | Rewrite root context file in-place | root-context only |
>
> Maintenance actions are triggered from the **document actions overlay** (Enter on a doc in the browser) or the **maintenance overlay** (M key in the document reader). The selected action's prompt is assembled and fed into the standard `runner.run_agent()` pipeline.

---

### 3. Document Reader/Editor Overlay

- **Item**: A full-featured document reader with an embedded text editor is not mentioned anywhere in the architecture document. This is a major overlay that supports viewing, editing, and saving published documents, plus launching maintenance actions.
- **Found in**: `voicecode/ui/overlays.py:794` (`draw_doc_reader`); state in `voicecode/app.py:200-214` (`show_doc_reader`, `doc_edit_mode`, `doc_edit_lines`, `doc_edit_cursor_row/col`, `doc_edit_scroll`, `doc_edit_save_confirm`, `doc_reader_on_close`)
- **Suggested entry** (add to Section 3.2 under overlays):

> **`overlays.py` — `draw_doc_reader()`**: A dual-mode document overlay. **Viewer mode** renders markdown with scrolling (Up/Down, PgUp/PgDn, Home/End), allows injecting the document title into the dictation buffer (Insert), and opens the maintenance overlay (M). **Editor mode** (Enter from viewer) provides a full text editor with cursor navigation, line insertion/deletion, Tab indentation, bracketed-paste support, and a Save/Discard confirmation dialog. The reader also hosts two nested modals: the maintenance action selector and the document actions menu.

---

### 4. Document Actions Overlay and Browser Delete Confirmation

- **Item**: Two modal overlays within the browser — document actions (View + maintenance actions context menu) and delete confirmation — are undocumented.
- **Found in**: `voicecode/ui/overlays.py:973` (`draw_doc_actions`), `voicecode/ui/overlays.py:1041` (`draw_browser_delete_confirm`); state in `voicecode/app.py:222-232`
- **Suggested entry**:

> **`overlays.py` — `draw_doc_actions()`**: A context menu shown when pressing Enter on a document in the browser's Documents tab. Lists "View" plus all applicable maintenance actions for the document's type (via `get_available_actions()`). Drift-report documents show only "View".
>
> **`overlays.py` — `draw_browser_delete_confirm()`**: A Y/N confirmation modal for deleting a file from the Documents browser tab (triggered by the Delete key).

---

### 5. Four-Category Browser System

- **Item**: The browser is documented as a prompt history scanner, but it actually has 4 switchable categories: Shortcuts, Project Folders, Documents, and Tools. Each category has its own item list and behavior.
- **Found in**: `voicecode/app.py:195-198` (`_browser_category`, `_browser_categories = ["Shortcuts", "Project Folders", "Documents", "Tools"]`, `_browser_cat_lists`); category-specific rendering in `voicecode/ui/drawing.py`; input routing in `voicecode/ui/input.py`
- **Suggested entry** (expand Section 3.7 or `BrowserHelper` description):

> **Browser categories**: The browser pane (top-left) has four tabs navigable with Left/Right arrows:
>
> | Category | Content | Key actions |
> |----------|---------|-------------|
> | **Shortcuts** | User-defined text shortcuts from `shortcuts.txt` | Insert to inject, E to edit, Enter to inject |
> | **Project Folders** | Subdirectories of the working directory | Insert to inject path, Enter to inject |
> | **Documents** | Published docs (`docs/**/*.md`) + root context files (CLAUDE.md, AGENTS.md, GEMINI.md) at top | Enter for actions menu, Delete to remove, Insert to inject title |
> | **Tools** | AI tool reference cards (provider-specific) | Enter to view detail |
>
> Root context files (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`) are pinned at the top of the Documents tab with special handling for maintenance actions.

---

### 6. `voicecode/data/tools.py` — Tool Reference Data Module

- **Item**: The `voicecode/data/` package providing built-in tool reference libraries for Claude and Gemini is not mentioned in the architecture document.
- **Found in**: `voicecode/data/tools.py` (706 lines) — defines `CLAUDE_TOOLS` and `GEMINI_TOOLS` lists with structured tool entries (name, category, summary, detail), plus `get_tool_names()` and `get_tool_detail()` accessors; `voicecode/data/__init__.py`
- **Suggested entry**:

> **`voicecode/data/tools.py`**: Static reference library of AI tool definitions for the browser's Tools tab. Maintains separate `CLAUDE_TOOLS` and `GEMINI_TOOLS` lists, each containing structured entries (name, category, summary, multi-line detail card). `get_tool_names(provider)` returns display strings; `get_tool_detail(index, provider)` returns a title and detail lines for the document reader. The active provider determines which tool library is shown.

---

### 7. `voicecode/publish/frontmatter.py` — YAML Front-Matter Parser

- **Item**: A lightweight YAML front-matter parser used by the publish/maintenance system is undocumented.
- **Found in**: `voicecode/publish/frontmatter.py` — `parse_frontmatter(text)` extracts `---`-delimited YAML into a dict by splitting on `:`. Used to determine document type for maintenance action filtering.
- **Suggested entry** (add to Section 3.8):

> **`frontmatter.py` — `parse_frontmatter()`**: A minimal YAML front-matter parser that extracts the `---`-delimited header block from published documents into a `dict[str, str]`. Used by the browser and maintenance system to determine `doc_type` for action filtering and badge coloring.

---

### 8. Typing Mode (Direct Text Entry)

- **Item**: The document mentions dictation via speech but does not describe the direct typing mode where users can type text directly into the dictation buffer.
- **Found in**: `voicecode/app.py:246-248` (`typing_mode`, `typing_buffer`, `typing_cursor`); input handling in `voicecode/ui/input.py`; rendering in `voicecode/ui/drawing.py` (typing input line overlaid on dictation pane)
- **Suggested entry** (add to Section 4.1 or 3.2):

> **Typing mode**: Pressing Enter when not recording activates direct text input in the dictation pane. A cursor-enabled input line overlays the bottom of the pane. Typed text is appended as a fragment on Enter, equivalent to a dictated speech fragment. This provides a keyboard-only workflow without requiring a microphone.

---

### 9. Tips System

- **Item**: A tips cycling system that shows contextual tips in the agent pane welcome screen is undocumented.
- **Found in**: `voicecode/app.py:98-100` (`_all_tips`, `_tip_index`), `voicecode/app.py:370-399` (`_load_all_tips()`, `get_tip()`, `get_random_tip()`, `cycle_tip()`); tips loaded from `tips.txt` at project root
- **Suggested entry**:

> **Tips system**: On startup, `BBSApp._load_all_tips()` reads `tips.txt` (one tip per line) and selects a random starting index. Tips are displayed in the agent pane welcome art. The T key cycles to the next tip. Tips provide usage guidance and keyboard shortcut reminders.

---

### 10. `version.py` — Version Module

- **Item**: The standalone `version.py` module at the project root (imported by `constants.py` for the banner) is not mentioned.
- **Found in**: `version.py:1` (`__version__ = "3.9"`); imported in `voicecode/constants.py:4` (`from version import __version__`)
- **Suggested entry** (add to Section 5 Startup or Section 6 File State):

> **`version.py`**: Single-line module at the project root defining `__version__`. Imported by `constants.py` to embed the version string in the BBS banner. Updated manually on each release.

---

## Coverage Map

| Area | Coverage | Notes |
|------|----------|-------|
| **Entry points / lifecycle** | Good | Startup, main loop, shutdown, restart well-covered |
| **Agent execution pipeline** | Good | Runner, execution, refine all documented |
| **Provider abstraction** | Good | Claude and Gemini fully covered |
| **Audio pipeline** | Good | Capture, VAD, Whisper, injection merging all covered |
| **TTS layer** | Good | Engine, voices, Cast all covered |
| **Core UI rendering** | Good | Panes, drawing, colors, animation covered |
| **Settings overlay** | Good | Data-driven panel documented |
| **History & favorites** | Adequate | Core mechanics covered; browser categories missing |
| **Input handling** | Adequate | Normal/recording modes covered; typing mode, doc editor, browser categories missing |
| **Overlays** | Partial | Help/about/escape/shortcuts covered; doc reader/editor, doc actions, delete confirm, maint overlay missing |
| **Publish system** | **Under-covered** | Only ARCH agent described; all 9 agents are implemented; fixed-destination pattern undocumented |
| **Maintenance system** | **Missing** | Entire 5-agent maintenance layer absent |
| **Data module** | **Missing** | Tool reference libraries not mentioned |
| **Typing mode** | **Missing** | Direct keyboard input alternative to speech |
| **Tips system** | **Missing** | Welcome screen tips from tips.txt |
| **Front-matter parsing** | **Missing** | Used by browser and maintenance for doc-type detection |
| **Known Limitations (§8)** | **Stale** | Claims "no tests" (tests/ exists with 8 test files) and "only ARCH implemented" (all 9 agents done) |
