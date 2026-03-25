---
type: drift-report
source: "/home/schiele/projects/voicecode/docs/specs/maintenance-actions-spec.md"
date: 2026-03-25
---

# Drift Report: Document Type Styling & Maintenance Agents Spec

## Summary

This spec is **largely accurate (~85%)** — all three milestones have been implemented and the core architecture matches the design. The main drift areas are: (1) the color system uses new dedicated `CP_DOC_BADGE_*` color pairs rather than reusing existing pairs as specified, (2) two additional maintenance agents (`CTX_DRIFT`, `CTX_UPDATE`) and a `root-context` document type exist but are not documented, (3) the `MaintenanceAgent` base class has an `excluded_types` property and a `description` field not described in the spec, and (4) a new document-actions overlay in the browser adds an alternative entry point for maintenance beyond the doc reader's `M` key.

## Accurate

- **Front matter parser** — `voicecode/publish/frontmatter.py` exists exactly as specified, with `parse_frontmatter(text) -> dict[str, str]` doing line-based key:value extraction without PyYAML.
- **`DOC_TYPE_COLORS` mapping** — lives in `voicecode/ui/overlays.py:31-42`, groups types into the same four color families (Cyan/Architecture, Green/Planning, Magenta/Reference, Yellow/Entry point).
- **Doc viewer title bar** uses type-based color: `type_cp = DOC_TYPE_COLORS.get(app.doc_reader_doc_type, CP_HEADER)` at line 750, with `[BADGE]` in title at lines 797-799.
- **Folder browser badges** — Documents category renders `[TYPE]` badges with type-colored attributes at lines 510-533, using a front matter type cache.
- **`MaintenanceAgent` base class** at `voicecode/publish/maintenance/base.py` — matches the spec's `action_name`, `prompt_path`, `prompt_template`, `build_prompt(doc_path, doc_content, doc_type)`, and `applicable_types` exactly.
- **Three initial agents** implemented: `ReconcileAgent`, `RefreshAgent`, `CoverageAgent` in their respective modules, each as thin subclasses.
- **Coverage agent `applicable_types`** matches spec: `["glossary", "schema", "constraints", "conventions", "arch"]`.
- **Prompt templates** in `voicecode/publish/maintenance/prompts/` — `RECONCILE.md`, `REFRESH.md`, `COVERAGE.md` all exist with the three placeholders `{doc_path}`, `{doc_content}`, `{doc_type}`.
- **Maintenance overlay UI** — `draw_maint_overlay()` at `overlays.py:853` is a centered modal with cursor-based selection, `▸` pointer, Enter/ESC controls, exactly as described.
- **State fields** `show_maint_overlay`, `maint_cursor`, `maint_actions` are used as specified.
- **`M` keybinding** in doc reader at `input.py:512` — calls `get_available_actions(doc_type)`, populates overlay.
- **Maintenance overlay input handling** at `input.py:300-317` — supports `↑↓`, Enter, ESC as specified.
- **`execute_agent_prompt` helper** extracted to `publish_overlay.py:136` — shared by publish and maintenance as the spec recommended.
- **`_execute_maintenance`** at `input.py:56-78` — builds prompt, closes overlays, calls `execute_agent_prompt` with `[MAINTAIN {action} → {path}]` label.
- **Registry** in `__init__.py` — `get_maintenance_agent()` and `get_available_actions()` match spec signatures.
- **Help text** shows `[M]Maintain` at `overlays.py:834`.
- **Concurrent execution guard** — checked at `input.py:544`: `if app.agent_state not in (AgentState.IDLE, AgentState.DONE)`.
- **Graceful degradation** — missing front matter → empty type → default `CP_HEADER` color, all maintenance actions shown (minus those with `applicable_types` restrictions).

## Stale

1. **Color pair constants**
   - **Spec says**: "New color pair constants are not required — reuse existing pairs" (`CP_BANNER`, `CP_AGENT`, `CP_PUBLISH`, `CP_XFER`).
   - **Actual code**: Four new dedicated color pairs were added to `colors.py:33-36`: `CP_DOC_BADGE_CYAN` (33), `CP_DOC_BADGE_GREEN` (34), `CP_DOC_BADGE_MAGENTA` (35), `CP_DOC_BADGE_YELLOW` (36). These use `curses.COLOR_BLACK` as background (matching the doc list theme) rather than reusing the existing pairs which have different backgrounds.
   - **Severity**: Minor — the grouping and colors are semantically identical; only the constant names and background colors differ.

2. **Doc viewer border/title color source**
   - **Spec says (§4.2)**: "look up the color pair from a `DOC_TYPE_COLORS` mapping" using existing pairs like `CP_BANNER`.
   - **Actual code**: Uses `DOC_TYPE_COLORS` which maps to the new `CP_DOC_BADGE_*` constants, not the spec's proposed reuse of `CP_BANNER`/`CP_AGENT`/etc.
   - **Severity**: Minor — same visual intent, different constants.

3. **`MaintenanceAgent` base class has extra members**
   - **Spec says (§4.4)**: Base class has `action_name`, `prompt_path`, `prompt_template`, `build_prompt()`, `applicable_types`.
   - **Actual code** (`base.py`): Also has `description: str = ""` (line 21) used for overlay labels, and `excluded_types` property (lines 43-46) returning types the action should *never* apply to.
   - **Severity**: Minor — additive, doesn't contradict spec, but the `excluded_types` pattern changes how filtering works in `get_available_actions`.

4. **Registry type annotation**
   - **Spec says (§4.8)**: `_MAINT_REGISTRY: dict[str, MaintenanceAgent] = {}`
   - **Actual code** (`__init__.py:3`): `_MAINT_REGISTRY: dict = {}` — untyped dict.
   - **Severity**: Minor — cosmetic.

5. **`get_available_actions` filtering logic**
   - **Spec implies**: Only `applicable_types` is checked (empty = all types).
   - **Actual code** (`__init__.py:30-36`): Also checks `excluded_types` — if the doc type is in `agent.excluded_types`, the action is skipped regardless of `applicable_types`.
   - **Severity**: Minor — the exclusion mechanism is an additive refinement.

6. **Reconcile/Refresh agents use `excluded_types` instead of being universal**
   - **Spec says**: Reconcile and Refresh are "applicable to all document types".
   - **Actual code**: They exclude `root-context` type via `excluded_types = ["root-context"]`.
   - **Severity**: Minor — the root-context type didn't exist when the spec was written.

7. **`M` key accepts both cases**
   - **Spec says (§4.9)**: "handling for `M` key".
   - **Actual code** (`input.py:512`): `ch in (ord("m"), ord("M"))` — accepts both lowercase and uppercase.
   - **Severity**: Minor — strictly more permissive than described.

## Missing

1. **Two additional maintenance agents: `CTX_DRIFT` and `CTX_UPDATE`**
   - `voicecode/publish/maintenance/ctx_drift.py` — `CtxDriftAgent` with `applicable_types = ["root-context"]`, action `CTX_DRIFT`, description "Drift check — find stale sections".
   - `voicecode/publish/maintenance/ctx_update.py` — `CtxUpdateAgent` with `applicable_types = ["root-context"]`, action `CTX_UPDATE`, description "Update — regenerate from codebase".
   - Corresponding prompt templates: `prompts/CTX_DRIFT.md`, `prompts/CTX_UPDATE.md`.
   - These are registered in the registry alongside the three original agents.
   - The spec lists only three agents; these two are entirely undocumented.

2. **`root-context` document type**
   - `DOC_TYPE_COLORS` includes `"root-context": CP_DOC_BADGE_YELLOW` (overlays.py:41).
   - Root context files (`AGENTS.md`, `CLAUDE.md`, `GEMINI.md`) defined in `ROOT_CONTEXT_FILES` (overlays.py:44-47) get special `[CONTEXT]` badge treatment in the browser (overlays.py:510-514).
   - The spec's type table lists only 9 types across 4 groups; `root-context` is a 10th type.

3. **Document actions overlay in the browser (`draw_doc_actions`)**
   - `overlays.py:912` — a `draw_doc_actions()` method provides a separate actions modal accessible from the folder browser, not just from the doc reader.
   - `input.py:37-54` — `_open_doc_actions()` builds a combined list with "View" as the first action plus applicable maintenance actions.
   - `input.py:524-556` — Full input handling for this overlay (ESC, ↑↓, Enter with routing to View or maintenance execution).
   - This is a significant UX addition not described anywhere in the spec — it means users can trigger maintenance directly from the browser without first opening the doc reader.

4. **`description` field on agents**
   - Each agent subclass sets `description` (e.g., `"Reconcile — check drift"`) used as the label in overlays. The spec's overlay mockup shows similar text but doesn't document `description` as a class attribute.

5. **`_doc_type_cache` on app**
   - `input.py:42` references `app._doc_type_cache` for looking up document types in the browser. The spec mentions caching in §4.3 conceptually ("Cache results in a dict keyed by file path") but doesn't name the attribute.

6. **New `CP_DOC_*` color pairs (beyond badges)**
   - `colors.py:27-32` adds `CP_DOC_BODY`, `CP_DOC_HEADING`, `CP_DOC_DIM`, `CP_DOC_LIST_BG`, `CP_DOC_LIST_SEL`, `CP_DOC_LIST_BORDER` — used by the doc reader and overlays. These are outside the spec's scope statement but are integral to the feature.

## Recommendations

1. **Add CTX_DRIFT and CTX_UPDATE agents to the spec** — These are production agents with prompt templates, registered in the registry. Add a new row to the agents table and describe `root-context` as a document type. *New section needed. Medium effort.*

2. **Document the browser document-actions overlay** — This is a full alternative entry point for maintenance from the folder browser (Enter on a document → actions modal). Add to §3.4 and §4.6. *New subsection needed. Medium effort.*

3. **Update §3.2 color mapping table** — Replace "reuse existing pairs" claim with the actual `CP_DOC_BADGE_*` constants. Add `root-context` to the Yellow row. Note the additional `CP_DOC_*` pairs for the reader UI. *Paragraph rewrite.*

4. **Update §4.4 base class** — Add `description: str` field and `excluded_types` property. Update the filtering description in §4.8 to reflect the exclusion logic. *Paragraph rewrite.*

5. **Update "existing nine types" references** — The codebase now has 10 types including `root-context`. *One-liner fixes in §2 Non-Goals and §3.2.*

6. **Update Open Question #2** — Resolved: the implementation chose dedicated `CP_DOC_BADGE_*` pairs rather than reusing existing ones, giving badge-specific backgrounds. Mark as resolved. *One-liner.*
