# VoiceCode Document Workflow

A practical guide to building and maintaining a structured documentation library
using VoiceCode's voice-driven publishing system. This covers the full lifecycle:
dictating ideas, publishing documents, browsing your library, and keeping
everything current with maintenance agents.

---

## The Target File Structure

VoiceCode expects a working directory (typically a repo root) with two key
folders alongside your root context files:

```
repo-root/
  AGENTS.md                    ← shared project context (root context)
  CLAUDE.md                    ← Claude-specific instructions (root context)
  GEMINI.md                    ← Gemini-specific instructions (root context)
  README.md                    ← project entry point (root context)
  prompts/
    history/                   ← auto-saved prompt/response pairs
      001_slug_prompt.md
      001_slug_response.md
  docs/
    context/                   ← singleton reference docs (always current)
      CONVENTIONS.md           ← coding patterns, naming rules, style
      CONSTRAINTS.md           ← hard boundaries and safety rails
      GLOSSARY.md              ← domain vocabulary
      SCHEMA.md                ← data models, types, API shapes
    decisions/                 ← ADRs, numbered sequentially
      0001-*.md
    specs/                     ← feature specifications
    plans/                     ← implementation plans
```

**Two tiers of context:**
- **Root context** — AGENTS.md, CLAUDE.md, GEMINI.md, README.md. These are
  always loaded by the AI agent and act as project maps. Shown at the top of
  the Documents tab with `[CONTEXT]` badges.
- **docs/** — Published documents with YAML frontmatter. Browsable in the
  Documents tab with color-coded `[TYPE]` badges.

---

## Frontmatter

Every published document carries YAML frontmatter parsed by the system:

```yaml
---
type: spec
status: active
last-updated: 2026-03
---
```

The `type` field drives the UI: color-coded badges in the document browser,
border colors in the document reader, and filtering of applicable maintenance
actions. Types match the 9 publish agents: `adr`, `arch`, `plan`, `spec`,
`glossary`, `constraints`, `conventions`, `schema`, `readme`. Root context
files use the special type `root-context`.

---

## The Voice-Driven Pipeline

VoiceCode's core loop is: **dictate → refine → execute**. Three keys drive it.

### Dictate (SPACE)

Press SPACE to toggle recording. Voice is captured at 16kHz mono, processed
through Silero VAD for voice activity detection, and transcribed by
faster-whisper. Transcribed fragments accumulate in the **Dictation Buffer**
pane. You can also press Enter to type text directly.

### Refine (R)

Press R to send accumulated fragments to the LLM for refinement. The refine
agent uses the `REFINE.md` prompt template to synthesize raw fragments into a
coherent, structured prompt. The result appears in the **Prompt Browser** pane.

Refinement has two modes:
- **Initial** — no existing prompt; fragments are synthesized from scratch
- **Modify** — existing prompt present; new fragments are applied as edits

This means you can iteratively dictate changes and press R again to update the
prompt. Each refinement increments the prompt version number.

### Execute (E) or Direct Execute (D)

- **E** — Executes the refined prompt in the Prompt Browser
- **D** — Joins raw fragments with spaces and executes immediately, skipping
  refinement entirely

Both trigger the same execution pipeline: the prompt is saved to history,
a ZMODEM transfer animation plays, and the agent response streams into the
**Agent Terminal** pane with a typewriter effect. A `[TTS_SUMMARY]` block in the
response is extracted and spoken aloud via piper TTS (or Google Cast).

### Prompt History (← →)

Every executed prompt and its response are saved as numbered pairs in
`prompts/history/`. Browse them with the arrow keys. Press S to save the
current prompt without executing. Press F to add a prompt to one of 10
favorites slots (quick-load with 1-9, 0).

---

## Publishing Documents (P)

Press P to open the **Publish Overlay** — a two-step modal for generating
structured documents.

### Step 1: Choose Document Type

Select from the 9 publish agents, each backed by a `PublishAgent` subclass
with its own prompt template in `publish/prompts/`:

| Agent | Type | Description |
|-------|------|-------------|
| **AdrAgent** | ADR | Architecture Decision Records — capture decisions with context, alternatives, consequences |
| **ArchAgent** | ARCH | Architecture documents — comprehensive codebase analysis |
| **PlanAgent** | PLAN | Implementation plans — milestones, task breakdown, dependencies |
| **SpecAgent** | SPEC | Feature specifications — requirements, design, acceptance criteria |
| **GlossaryAgent** | GLOSSARY | Domain vocabulary — shared terms and definitions |
| **ConstraintsAgent** | CONSTRAINTS | Hard boundaries — safety rails, regulatory, compatibility |
| **ConventionsAgent** | CONVENTIONS | Team practices — naming, style, git workflow, testing |
| **SchemaAgent** | SCHEMA | Data model reference — entities, relationships, constraints |
| **ReadmeAgent** | README | Project entry point — overview, setup, usage |

### Step 2: Choose Destination Folder

For ADR, ARCH, PLAN, and SPEC, you pick a destination folder under `docs/`
(context/, decisions/, plans/, specs/).

Five agents have **fixed destinations** and skip this step:
- GLOSSARY, CONSTRAINTS, CONVENTIONS, SCHEMA → `docs/context/`
- README → project root

The publish overlay shows a reference tree on the left with the folder
structure and agent descriptions, making it easy to understand where documents
will land.

### What Happens

The selected agent's prompt template is populated with the scope (your current
prompt text or dictation) and destination folder, then executed through the
same pipeline as any other prompt. The agent analyzes the codebase and writes
the document with proper frontmatter.

---

## Browsing & Reading Documents (Tab)

Press Tab to open the **Browser Overlay** with four tabs. The **Documents** tab
lists all published docs in `docs/` with color-coded type badges:

- Cyan: ARCH, ADR
- Green: PLAN, SPEC
- Magenta: GLOSSARY, SCHEMA, CONSTRAINTS, CONVENTIONS
- Yellow: README, root-context, drift/coverage reports

Root context files (AGENTS.md, CLAUDE.md, GEMINI.md, README.md) appear at the
top of the list.

Press Enter on any document to open the **Document Reader** — a full-screen
view with scroll controls (arrows, PgUp/PgDn, Home/End) and word/line count.
Press Enter again to enter **edit mode** for in-place modifications.

---

## Maintaining Documents (M)

Press M while viewing a document in the reader to open the **Maintenance
Actions** overlay. The system filters available actions based on the document's
type.

### Maintenance Agents

Five agents handle document upkeep, each subclassing `MaintenanceAgent` with
templates in `publish/maintenance/prompts/`:

| Agent | Action | Applies To | Description |
|-------|--------|------------|-------------|
| **ReconcileAgent** | RECONCILE | All published docs | Compares document against current codebase; produces a drift report |
| **RefreshAgent** | REFRESH | All published docs | Rewrites document in-place to match current code; preserves structure |
| **CoverageAgent** | COVERAGE | GLOSSARY, SCHEMA, CONSTRAINTS, CONVENTIONS, ARCH | Scans codebase for undocumented items; produces a coverage report |
| **CtxDriftAgent** | CTX_DRIFT | Root context only | Checks AGENTS.md/CLAUDE.md for drift against codebase |
| **CtxUpdateAgent** | CTX_UPDATE | Root context only | Regenerates root context files from codebase and git history |

### The Split: Published Docs vs Root Context

The maintenance system treats these two categories separately:

- **Published docs** (in `docs/`): Use RECONCILE, REFRESH, and COVERAGE.
  These agents receive the document path, content, and type, then analyze the
  codebase to produce reports or updated files.
- **Root context files** (AGENTS.md, CLAUDE.md, etc.): Use CTX_DRIFT and
  CTX_UPDATE. These are the files that AI agents load every session, so
  keeping them current is critical.

### Drift Reports and Coverage Reports

RECONCILE and COVERAGE produce report files saved alongside the source
document (with `-DRIFT` or `-COVERAGE` suffixes). These reports appear in the
Documents tab with yellow badges and are view-only — you can browse them but
maintenance actions are not offered on reports themselves.

---

## Recommended Document Creation Order

When taking a new idea through the system, follow this sequence to build up
context progressively:

### 1. Foundation (do these first)

Start with the context-tier singleton documents. These establish the shared
vocabulary and rules that all subsequent documents build on.

1. **CONVENTIONS** — How the team writes code: naming, style, patterns
2. **CONSTRAINTS** — What must never happen: safety rails, hard limits
3. **GLOSSARY** — Domain terms so everyone (including the AI) speaks the same
   language
4. **SCHEMA** — Data models, entity relationships

These all live in `docs/context/` and use fixed destinations, so you just
select the agent type and go.

### 2. Architecture (do this next)

5. **ARCH** — Comprehensive codebase analysis. This gives the AI (and new
   team members) a structural map of the project. Place in `docs/context/` or
   a subfolder.

### 3. Working Documents (create as needed)

These are created iteratively as features and decisions arise:

6. **SPEC** — When you have a feature to design. Dictate the idea, refine it,
   then publish as a spec.
7. **PLAN** — When you need an implementation roadmap for a spec or initiative.
8. **ADR** — When you make a significant technical decision. Capture the
   context while it's fresh.

### 4. Entry Point

9. **README** — Generate or refresh once you have enough context docs for the
   agent to work with. The README agent synthesizes from the entire project.

### 5. Root Context

After publishing documents, use **CTX_UPDATE** on AGENTS.md and CLAUDE.md to
regenerate them from the codebase. This ensures the AI's always-on context
reflects your latest documentation.

---

## The Ongoing Maintenance Cycle

Once your document library is established, keep it healthy:

1. **After code changes** — Open affected documents in the reader, press M,
   run RECONCILE to check for drift. If drift is found, run REFRESH to update
   the document in-place.

2. **Periodically** — Run COVERAGE on context-tier docs (GLOSSARY, SCHEMA,
   CONVENTIONS, CONSTRAINTS, ARCH) to find undocumented code items.

3. **After major changes** — Run CTX_DRIFT on root context files (AGENTS.md,
   CLAUDE.md) to see if they've fallen behind. Follow up with CTX_UPDATE to
   regenerate them.

4. **When documents accumulate** — Browse the Documents tab to review your
   library. Drift and coverage reports appear with yellow badges so you can
   spot documents that need attention.

---

## Workflow Summary

```
┌─────────────┐     ┌──────────┐     ┌─────────────┐
│  DICTATE     │     │  REFINE  │     │  EXECUTE    │
│  (SPACE)     │────>│  (R)     │────>│  (E)        │
│  voice/type  │     │  LLM     │     │  agent runs │
└─────────────┘     └──────────┘     └──────┬──────┘
      │                                      │
      │  ┌───────────────────────────────────┘
      │  │
      v  v
┌─────────────┐     ┌──────────┐     ┌─────────────┐
│  PUBLISH    │     │  BROWSE  │     │  MAINTAIN   │
│  (P)        │     │  (Tab)   │     │  (M)        │
│  9 agents   │────>│  docs    │────>│  5 agents   │
└─────────────┘     └──────────┘     └─────────────┘
```

- **Dictate** ideas with your voice or keyboard
- **Refine** fragments into structured prompts via LLM
- **Execute** prompts to get agent responses, or **Direct Execute** (D) to skip refinement
- **Publish** structured documents with specialized agents
- **Browse** your document library with type-aware filtering
- **Maintain** documents with drift checks, refreshes, and coverage analysis
