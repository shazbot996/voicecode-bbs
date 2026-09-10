---
type: spec
id: context-refinery
title: Context Refinery — Framework Specification
authority: prescriptive
status: draft
version: 0.2
created: 2026-09-10
last-updated: 2026-09-10
derives-from: [voicecode-bbs]
code-refs:
  - voicecode/publish/**
  - voicecode/publish/maintenance/**
  - voicecode/publish/frontmatter.py
---

# Context Refinery

**An opinionated framework for context creation, execution, and change
management in agent-built software — anchored on provenance.**

> Build from context. Refine well.

Distilled from the publish/maintain subsystem of `voicecode-bbs` and generalized
so that any host can implement it: a TUI, a web application, a CI job, or a
plain CLI. This document is the root of the standard. The tooling that consumes
it is a separate concern and a separate repository.

---

## 0. What this document is

Context Refinery specifies five things and nothing else:

1. **The repository contract** — what a conformant repo contains, and where.
2. **The frontmatter and lineage schema** — the metadata layer that records
   which prompt produced which document, against which commit, having consumed
   which context.
3. **The document type registry** — every document type, its authority, its
   cardinality, its lifecycle, and which agents may touch it.
4. **The execution contract** — how context is selected for an agent run, what
   is recorded about that run, and how the resulting change is attributed.
5. **The change-management rules** — how drift is detected cheaply, reported,
   triaged, and repaired.

It deliberately does **not** specify a UI, a keybinding, a voice pipeline, a
model, or a provider. A host application implements this spec; it is not
described by it.

Keywords MUST, MUST NOT, SHOULD, SHOULD NOT, MAY are used in the RFC-2119 sense.

### 0.1 The premise

An agent's output quality is bounded by the precision of the context it was
given, and an agent pipeline's cost is dominated by context it was given
needlessly. Those two pressures point in opposite directions, and most teams
resolve the conflict by guessing — loading everything, or loading nothing and
letting the model infer.

Context Refinery resolves it with records instead of guesses. Every document
declares what it describes and what it depends on. Every run records what it
consumed and what it changed. Once those records exist, context selection stops
being a heuristic and becomes a query, and the expensive question — *what is
stale now?* — is answered by a git diff rather than a model call.

### 0.2 The three phases

```
   ┌─────────────┐      ┌──────────────┐      ┌────────────────────┐
   │  CREATION   │ ───→ │  EXECUTION   │ ───→ │ CHANGE MANAGEMENT  │
   │  §3 §4 §5   │      │      §6      │      │        §7          │
   │ produce the │      │ spend context│      │ detect what the    │
   │ context     │      │ to change    │      │ change invalidated │
   │ layer       │      │ the code     │      │ and repair it      │
   └─────────────┘      └──────────────┘      └─────────┬──────────┘
          ▲                                              │
          └──────────────────────────────────────────────┘
                         provenance closes the loop
```

Most document tooling implements creation and stops. The loop only closes — and
the library only stays worth reading — if execution is recorded and change is
managed. Provenance is the thread that runs through all three.

---

## 1. Core model

### 1.1 The authority model

Every document type has exactly one **authority** — the answer to "when this
document and the code disagree, which one is wrong?" This is the most
load-bearing concept in the spec. Every maintenance rule derives from it.

| Authority | Source of truth | Disagreement means | Repair action |
|---|---|---|---|
| **Descriptive** | The code | The *document* is wrong | Rewrite the document from code |
| **Prescriptive** | The document | The *code* is wrong | Open a violation; change code, or amend the doc by explicit human decision |
| **Historical** | Neither — a record of a past moment | Nothing. Records don't drift | Never edit. Supersede with a new record |

A refinery that runs one uniform "reconcile then refresh" loop over all document
types **will silently destroy its own guardrails**. Pointed at a prescriptive
document, "rewrite so every fact matches the live code" deletes the constraint
the moment the code violates it, and the violation quietly becomes the new
standard. Pointed at a historical document, it is falsification of the record.

> **Rule A-1.** A maintenance agent MUST NOT be offered for, or executed
> against, a document whose authority does not admit that action. Action
> eligibility is a property of the document type, not a user choice.

### 1.2 Tiers

Tier governs load order, dependency direction, and how expensive drift is.

| Tier | Name | Contents | Loaded |
|---|---|---|---|
| **T0** | Root context | `AGENTS.md` (canonical), provider stubs, `README.md` | Every agent session, automatically |
| **T1** | Foundation | `GLOSSARY`, `CONVENTIONS`, `CONSTRAINTS`, `SCHEMA` | On demand; referenced by everything above |
| **T2** | Structural | `ARCH` | On demand; assumes T1 vocabulary |
| **T3** | Working | `SPEC`, `PLAN`, `ADR` | Per task; assumes T1 + T2 |
| **T4** | Derived | drift, coverage, violation reports | Never loaded as context; consumed and discarded |

> **Rule T-1.** A document MUST NOT declare `derives-from` a document in a
> higher tier. Dependencies point downward only. This keeps the context graph
> acyclic and makes "what breaks if I change this?" a computable query.

> **Rule T-2.** T4 artifacts MUST NOT be treated as context. They are work
> orders with a lifecycle, not documents.

### 1.3 Cardinality

| Cardinality | Meaning | Write semantics |
|---|---|---|
| **Singleton** | Exactly one per repo, at a fixed path | Mutated in place; version increments |
| **Serial** | Numbered sequence, append-only | New file per entry; existing entries immutable |
| **Multiple** | Many, one per subject | Created, lifecycled, archived independently |

---

## 2. Repository contract

```
repo-root/
  AGENTS.md                    T0  canonical root context
  CLAUDE.md                    T0  import stub only — @AGENTS.md, no content
  GEMINI.md                    T0  import stub only
  README.md                    T0  human / landing-page entry point
  .refinery/
    registry.yaml                  type + agent registry (§8)
    state.json                     host-managed run ledger
    runs/
      NNNN.yaml                    execution records (§6.3)
  prompts/
    history/
      NNNN_slug_prompt.md          the prompt as executed
      NNNN_slug_response.md        the agent response
  docs/
    context/                   T1/T2  always-current singletons
      GLOSSARY.md
      CONVENTIONS.md
      CONSTRAINTS.md
      SCHEMA.md
      ARCH.md
    decisions/                 T3  ADRs, serial, immutable
      NNNN-slug-ADR.md
    specs/                     T3  one per feature
      <feature>-SPEC.md
    plans/                     T3  one per initiative
      <initiative>-PLAN.md
```

> **Rule R-1.** Exactly one T0 file is canonical and maintained. All other
> provider-specific root files MUST be single-line import stubs. Content that
> accumulates in a stub is drift by construction, because nothing maintains it.

> **Rule R-2.** Every file under `docs/` MUST carry valid frontmatter (§3). A
> markdown file under `docs/` without frontmatter is *unmanaged* and MUST be
> reported by the validator, not silently ignored.

> **Rule R-3.** `.refinery/` is the framework's namespace. A repo adopts Context
> Refinery by adding `.refinery/registry.yaml`; conformance level is computed
> from the repo, not asserted in the registry.

---

## 3. Frontmatter — the provenance layer

Frontmatter is not decoration and not merely UI colour-coding. It is the **only**
durable record of how a document came to exist, what it was true about, and what
it depends on. Prose is written for humans; frontmatter is the machine-readable
claim about provenance that every other feature in the framework reads.

The design goal: **from any document, reconstruct the prompt that produced it;
from any prompt, find every document it consumed and every document it touched;
from any code change, compute which documents are now suspect — all without
invoking a model.**

### 3.1 Document frontmatter (normative)

```yaml
---
# ── Identity ─────────────────────────────────────────────
type: spec                     # REQUIRED  enum, see §4
id: publish-overlay            # REQUIRED  stable slug, immutable for life
title: Publish Overlay         # REQUIRED  human title
authority: prescriptive        # REQUIRED  descriptive|prescriptive|historical
cardinality: multiple          # REQUIRED  singleton|serial|multiple
status: active                 # REQUIRED  see §5.1

# ── Versioning ───────────────────────────────────────────
version: 4                     # REQUIRED  integer; +1 on every write
created: 2026-08-14
last-updated: 2026-09-10
last-agent-write: 2026-09-10T14:22:11Z
last-human-edit: 2026-09-02T09:11:00Z   # null if never hand-edited

# ── Provenance ───────────────────────────────────────────
provenance:                    # REQUIRED  append-only, newest last
  - run: 0147                  #   index into prompts/history/ and .refinery/runs/
    prompt: prompts/history/0147_publish_overlay_prompt.md
    agent: SPEC
    action: publish            #   publish|refresh|repair|amend|manual
    model: claude-opus-5
    commit: a3f9c21            #   repo HEAD when the write occurred
    date: 2026-09-10T14:22:11Z
  - run: 0151
    prompt: prompts/history/0151_overlay_two_step_prompt.md
    agent: REFRESH
    action: refresh
    model: claude-opus-5
    commit: 7be0d43
    date: 2026-09-10T16:40:02Z

# ── Graph edges ──────────────────────────────────────────
derives-from: [glossary, conventions]     # doc ids, equal or lower tier
informs: [publish-overlay-PLAN]           # doc ids, equal or higher tier
code-refs:                                # globs this doc claims to describe
  - voicecode/ui/publish_overlay.py
  - voicecode/publish/**
supersedes: null
superseded-by: null

# ── Verification ─────────────────────────────────────────
verified:                      # last CLEAN audit; null if never verified
  commit: 7be0d43
  date: 2026-09-10T16:44:00Z
  by: RECONCILE
---
```

### 3.2 Field rules

> **Rule F-1.** `id` is assigned once and is immutable. Filenames may change;
> `id` may not. All graph edges reference `id`, never paths.

> **Rule F-2.** `provenance` is **append-only**. An agent MUST append exactly one
> entry per write and MUST NOT rewrite or prune prior entries. Any truncation
> policy is a host concern and MUST preserve the first and last entries.

> **Rule F-3.** Every provenance entry MUST carry `commit`. An entry without the
> repo HEAD it was written against is worthless for drift detection (§7.1) and
> MUST be rejected by the validator.

> **Rule F-4.** Lineage is **bidirectional and verifiable**. If document `X`
> lists run `0147`, then run `0147` MUST list `X` in its `artifacts`. The
> validator checks both ends resolve; a one-sided edge is a lint error.

> **Rule F-5.** `derives-from` edges MUST resolve to an existing document `id`
> and MUST point to an equal or lower tier. Unresolvable or upward edges are
> lint errors.

> **Rule F-6.** If `last-human-edit` is later than `last-agent-write`, the
> document carries **unreconciled human intent**. A repairer MUST NOT
> blind-overwrite such a document; it MUST reconcile first and surface the
> conflict. This is the rule that stops the refinery from eating hand-written
> nuance.

> **Rule F-7.** `code-refs` is the document's claim about its own subject
> matter. It is what makes §7.1 possible and what makes §6.1 selective. A
> non-empty `code-refs` is REQUIRED for every T1, T2, and T3 document.

### 3.3 Prompt frontmatter

The prompt half of the lineage pair. The existing `voicecode` parser already
accepts `artifacts` / `generated_files` / `output_files`; this normalizes it and
adds the consumption side.

```yaml
---
run: 0147
date: 2026-09-10T14:22:11Z
agent: SPEC                    # null for a free-form execute
action: publish
provider: claude
model: claude-opus-5
commit: a3f9c21                # HEAD at execution
session: 8f21-…                # provider session/conversation id
scope-docs: [glossary, conventions, arch]   # context the agent was handed
artifacts:                                  # documents created or modified
  - docs/specs/publish-overlay-SPEC.md
code-touched:                               # source files created or modified
  - voicecode/ui/publish_overlay.py
refined: true                  # went through the refine loop vs. direct execute
refine-cycles: 3
---
```

`scope-docs` is the field that turns the prompt archive into a genuine **context
contribution ledger**. It records not only what a run produced but what it was
permitted to see. Two runs producing contradictory documents are almost always
explained by differing `scope-docs`, and without the field that diagnosis is
guesswork. It is also the raw material for the cost model in §9 — you cannot
tune context spend you do not measure.

### 3.4 What provenance buys you

Once F-1..F-7 hold, all of these are deterministic queries over frontmatter with
no model call:

- *Which documents are suspect after this merge?* — any doc whose `code-refs`
  match a path changed between `verified.commit` and `HEAD`.
- *Where did this claim come from?* — walk `provenance` to the prompt and read
  the dictation as executed.
- *What breaks if I rewrite the glossary?* — transitive closure of `informs`.
- *Which documents actually earn their keep?* — documents that appear frequently
  in `scope-docs` across runs. Documents that never appear are dead weight.
- *Which prompts contributed to shipped context?* — prompts whose `artifacts`
  are non-empty and still resolve.
- *Is this a hand-edit or an agent artifact?* — compare the two timestamps.
- *Has this document ever been checked against code?* — `verified == null`.

---

## 4. Document type registry

| Type | Tier | Authority | Cardinality | Destination | Filename | Depends on |
|---|---|---|---|---|---|---|
| `agents` | T0 | descriptive | singleton | root | `AGENTS.md` | all |
| `readme` | T0 | descriptive | singleton | root | `README.md` | arch |
| `glossary` | T1 | prescriptive | singleton | `docs/context/` | `GLOSSARY.md` | — |
| `conventions` | T1 | prescriptive | singleton | `docs/context/` | `CONVENTIONS.md` | glossary |
| `constraints` | T1 | prescriptive | singleton | `docs/context/` | `CONSTRAINTS.md` | glossary |
| `schema` | T1 | descriptive | singleton | `docs/context/` | `SCHEMA.md` | glossary |
| `arch` | T2 | descriptive | singleton | `docs/context/` | `ARCH.md` | T1 |
| `spec` | T3 | prescriptive | multiple | `docs/specs/` | `<slug>-SPEC.md` | T1, arch |
| `plan` | T3 | prescriptive → historical | multiple | `docs/plans/` | `<slug>-PLAN.md` | spec |
| `adr` | T3 | historical | serial | `docs/decisions/` | `NNNN-<slug>-ADR.md` | T1 |
| `drift-report` | T4 | derived | multiple | sibling of source | `<source>-DRIFT.md` | — |
| `coverage-report` | T4 | derived | multiple | sibling of source | `<source>-COVERAGE.md` | — |
| `violation-report` | T4 | derived | multiple | sibling of source | `<source>-VIOLATION.md` | — |

### 4.1 Notes on the awkward types

**`plan` changes authority mid-life.** While `status: active` it is
prescriptive — the code should come to match it. Once `status: complete` it is
historical and MUST become immutable. Refreshing a completed plan against the
code produces a tautology: the plan matches the code because it was rewritten
from the code, and the record of what was actually intended is gone.

> **Rule P-1.** A `plan` MUST transition `active → complete | abandoned` and
> MUST NOT accept a repairer after that transition.

**`adr` is immutable from birth.** The only legal mutation is setting
`superseded-by` on an existing ADR when a newer one replaces it.

**`spec` is prescriptive, which inverts its drift semantics.** A spec that
disagrees with the code usually means the feature is unfinished or the
implementation diverged — not that the spec is stale. The correct output is a
violation report, not a rewritten spec.

**`glossary` / `conventions` / `constraints` are prescriptive.** COVERAGE is the
right maintenance action for them — find undocumented terms and patterns to
*add*. A refresher is not.

**`schema` is descriptive** despite sitting beside prescriptive siblings in
`docs/context/`. It is derived from models in code. Folder is not authority.

---

## 5. Agents

### 5.1 Document lifecycle

```
        ┌──────────┐  publish   ┌──────────┐
absent →│  draft   │──────────→ │  active  │
        └──────────┘            └────┬─────┘
                                     │
              audit finds a problem  ▼
                                ┌──────────┐  repair   ┌──────────┐
                                │ suspect  │─────────→ │  active  │
                                └────┬─────┘           └──────────┘
                                     │ superseded / obsolete
                                     ▼
                              ┌─────────────┐        ┌──────────┐
                              │ superseded  │  ────→ │ archived │
                              └─────────────┘        └──────────┘
```

`status` enum: `draft | active | suspect | superseded | archived | complete |
abandoned | blocked`.

> **Rule S-1.** `suspect` MAY be set by a deterministic check (§7.1) with no
> model call. Only an audit run may clear it back to `active`, and only by
> writing `verified`.

### 5.2 Agent kinds

| Kind | Writes | Model call | Purpose |
|---|---|---|---|
| **Producer** | the document | yes (build mode) | Creates or replaces a document from prompt scope + code |
| **Auditor** | a T4 report only | yes (read-only mode) | Compares document to reality, writes findings |
| **Repairer** | the document | yes (build mode) | Consumes a T4 report and applies it |
| **Validator** | nothing | **no** | Deterministic lint over frontmatter and the graph |
| **Curator** | frontmatter only | **no** | Lifecycle transitions, supersession, archival, report reaping |

Validator and Curator are the two kinds missing from the current
implementation, and they are the cheapest and most frequently useful. A large
share of what is currently spent on audit runs is answerable by lint.

> **Rule S-2.** An Auditor MUST run read-only and MUST NOT write to the
> workspace other than its report. A Producer or Repairer MUST run in build
> mode. An agent whose prompt template ends by saving a file MUST NOT be
> configured read-only — it will report success and write nothing.

### 5.3 Agent contract

Every agent, of any kind, is fully described by:

```yaml
id: SPEC
kind: producer
doc-type: spec
run-mode: build                 # build | read-only
template: prompts/SPEC.md
inputs: [scope, dest_folder]
requires-context: [glossary, conventions, arch]   # injected, and recorded
                                                  # as scope-docs on the prompt
write-scope:                    # the ONLY paths this agent may write
  - docs/specs/*-SPEC.md
emits-provenance: true
applies-to-authority: [prescriptive]
```

> **Rule S-3.** `write-scope` is enforced by the host, not requested of the
> model. An agent that writes outside its declared scope has failed the run, and
> the run MUST be reported as failed even if the model reports success.

> **Rule S-4.** Every write by any agent MUST append a provenance entry. A write
> without provenance is a spec violation, not a stylistic lapse — it breaks
> every query in §3.4.

### 5.4 Required agent set

**Producers**, one per non-derived type — 10: `AGENTS`, `README`, `GLOSSARY`,
`CONVENTIONS`, `CONSTRAINTS`, `SCHEMA`, `ARCH`, `SPEC`, `PLAN`, `ADR`.

**Auditors** — 4:

| Agent | Applies to | Finds | Emits |
|---|---|---|---|
| `RECONCILE` | descriptive | Document claims the code no longer supports | drift-report |
| `COVERAGE` | glossary, conventions, constraints, schema, arch | Code items with no documentation | coverage-report |
| `CONFORMANCE` *(new)* | prescriptive | Code that violates the document | violation-report |
| `COHERENCE` *(new)* | any with `derives-from` | Documents that contradict each other, independent of code | drift-report |

`CONFORMANCE` is the inverse of `RECONCILE` and the agent the current
implementation is missing entirely; without it, prescriptive documents have no
maintenance path at all. `COHERENCE` catches the failure where ARCH and SCHEMA
describe two different systems and each individually matches the code.

**Repairers** — 2:
- `REFRESH` — descriptive only. Consumes a drift-report, rewrites in place.
- `AMEND` — prescriptive only. Consumes a violation-report and applies an
  explicit human decision to change the document. MUST require confirmation and
  MUST record the decision as an ADR.

**Validator** — 1, no model: `LINT`. Checks R-2, F-1..F-7, T-1, orphan and stale
reports, missing required sections, unresolvable `code-refs` globs.

**Curator** — 1, no model: `CURATE`. Lifecycle transitions, supersession chains,
archival, report reaping (§7.2).

Total: **18 agents**, two of which never call a model.

---

## 6. Execution

Creation produces context. Execution spends it. This is the phase where cost is
actually incurred and where most frameworks record nothing at all.

### 6.1 Context selection

> **Rule X-1.** An execution MUST declare its `scope-docs` before the run, and
> the host MUST inject exactly those documents. Implicit or ambient context —
> whatever the provider happens to have cached from a prior turn — is not
> context; it is contamination, and it makes the run unreproducible.

Selection policy, in order of preference:

1. **Declared.** The task names its documents (a plan names its spec; a spec
   names its glossary). Use them.
2. **Derived.** Walk `derives-from` from the named documents, downward only,
   and include the closure. This is why T-1 exists.
3. **Matched.** For a code-modifying task, include documents whose `code-refs`
   match the files in scope.
4. **Never blanket.** Loading all of `docs/` is not a selection policy. It is
   the failure mode this framework exists to replace.

> **Rule X-2.** T0 is always injected. T4 is never injected. T1 is injected for
> any run that writes code or documents. T2 and T3 are injected by policy above.

### 6.2 Session hygiene

> **Rule X-3.** A run's recorded `scope-docs` MUST be complete. If the host uses
> provider session continuity (`--resume`, `--conversation`), then either each
> refinery run starts a fresh session, or the run record MUST include the
> session id and the ordered list of prior runs in that session, so the true
> context set remains reconstructible.

This is a real hole in the current implementation: publish runs share a session,
so document N+1 can be shaped by context that appears nowhere in its lineage.

### 6.3 The execution record

Every run writes one record to `.refinery/runs/NNNN.yaml`, whether it produced a
document, changed code, or failed.

```yaml
run: 0152
date: 2026-09-10T17:02:00Z
kind: code-change          # code-change | publish | audit | repair | query
agent: null                # null for a free-form code-change run
provider: claude
model: claude-opus-5
run-mode: build
commit-before: 7be0d43
commit-after: c11a904
session: 8f21-…
scope-docs: [agents, constraints, conventions, publish-overlay]
context-tokens: 18400      # what selection actually cost
output-tokens: 6200
duration-s: 214
code-touched:
  - voicecode/ui/publish_overlay.py
  - voicecode/publish/base.py
artifacts: []              # documents written by this run
implicates:                # computed post-run from code-refs (§7.1)
  - arch
  - publish-overlay
outcome: success           # success | failed | scope-violation | killed
```

> **Rule X-4.** After any run that changes code, the host MUST compute
> `implicates` by matching `code-touched` against every document's `code-refs`,
> and MUST mark those documents `suspect`. This is the moment the loop closes:
> execution automatically schedules its own change management, with no model
> call and no human remembering to do it.

> **Rule X-5.** A run that ends `scope-violation` (S-3) MUST NOT write
> provenance and MUST NOT mark documents suspect. Failed runs stay out of the
> lineage graph.

---

## 7. Change management

### 7.1 Two-stage drift detection

Stage 1 is free and MUST run first.

**Stage 1 — deterministic suspicion.** For each document, diff `verified.commit`
(or the last provenance `commit`) against `HEAD`. If any changed path matches
the document's `code-refs`, set `status: suspect` and record the implicating
commits. No model call. This is what makes continuous drift tracking affordable
across a whole repo, and it is the same computation as X-4 run on a range
instead of a single commit.

**Stage 2 — agent audit.** Only for suspect documents, and only the audit
matching the document's authority:

| Authority | Stage-2 agent | Output |
|---|---|---|
| descriptive | `RECONCILE` | drift-report |
| prescriptive | `CONFORMANCE` | violation-report |
| historical | *(none — skip)* | — |

> **Rule D-1.** Stage 2 MUST NOT run on a document that Stage 1 did not mark
> suspect, unless explicitly forced. Auditing unchanged documents is the single
> largest source of wasted spend in this workflow.

> **Rule D-2.** A document with empty `code-refs` can never be marked suspect and
> MUST be flagged by LINT (see F-7). Empty `code-refs` means the document has
> opted out of change management entirely.

### 7.2 Report lifecycle

Reports are work orders. They rot faster than the documents they describe, and
an unreaped report becomes its own source of drift.

```yaml
---
type: drift-report
source: publish-overlay          # doc id
source-version: 4                # version of the source when generated
against-commit: 7be0d43
generated-by-run: 0153
generated: 2026-09-10T17:20:00Z
status: open                     # open | resolved | dismissed | stale
severity: moderate               # minor | moderate | major
resolved-by-run: null
---
```

> **Rule D-3.** A report is **automatically stale** the moment its
> `source-version` no longer matches the source document's `version`. Stale
> reports MUST NOT be presented as actionable and SHOULD be reaped by CURATE.

> **Rule D-4.** A repair run MUST set the consuming report to `resolved` and
> record the run id. A repair that leaves a report `open` will be re-offered
> forever.

> **Rule D-5.** At most one `open` report of a given kind may exist per source
> document. Re-running an audit supersedes the previous report.

### 7.3 The repair loop

```
 code change (X-4)  ──┐
                      ├──→ suspect ──→ audit ──→ report ──→ human triage
 Stage 1 sweep (D-1) ─┘                                          │
                    ┌────────────────────────┬───────────────────┤
                    ▼                        ▼                   ▼
             REFRESH                  change the code       AMEND + ADR
             (descriptive)            (prescriptive)        (prescriptive,
                    │                        │               explicit decision)
                    ▼                        ▼                   │
             verified updated         CONFORMANCE re-run         │
                    │                        │                   │
                    └────────→ report resolved ◄─────────────────┘
```

> **Rule D-6.** Triage is a human decision for prescriptive findings. An agent
> MUST NOT choose between "change the code" and "change the document" — that
> choice is the whole point of having a prescriptive document.

---

## 8. The registry

`.refinery/registry.yaml` is the machine-readable expression of §4 and §5.3. It
exists so that the type list, folder map, authority rules, and agent contracts
are **data, not code** — which is what lets a TUI host and a web host implement
identical behaviour, and lets a repo override defaults without forking tooling.

```yaml
refinery-version: 0.2
extends: org-baseline            # optional; see open decision 5
paths:
  docs: docs/
  context: docs/context/
  decisions: docs/decisions/
  plans: docs/plans/
  specs: docs/specs/
  history: prompts/history/
  runs: .refinery/runs/
types:
  - id: spec
    tier: 3
    authority: prescriptive
    cardinality: multiple
    dest: docs/specs/
    filename: "{slug}-SPEC.md"
    required-sections: [Problem Statement, Goals & Non-Goals,
                        Technical Design, Success Criteria]
    derives-from: [glossary, conventions, arch]
agents:
  - id: SPEC
    kind: producer
    doc-type: spec
    run-mode: build
    write-scope: ["docs/specs/*-SPEC.md"]
gates:
  L1: [glossary, conventions, constraints]
  L2: [schema, arch]
  L3: [agents, readme]
budgets:
  context-tokens-warn: 40000
  audit-runs-per-day: 25
```

> **Rule G-1.** The host MUST read the registry rather than hardcode the type
> list. Adding a document type MUST be a registry edit plus a prompt template,
> with no host code change.

### 8.1 Readiness gates

A repo's readiness level is a deterministic function of which documents exist,
are `active`, and are `verified`.

| Level | Requires | Meaning |
|---|---|---|
| **L0** | nothing | Unmanaged repo |
| **L1** | glossary, conventions, constraints active | Agents have vocabulary and rails |
| **L2** | + schema, arch active and verified | Agents have a structural map |
| **L3** | + agents, readme active and verified | Fully grounded; new sessions start oriented |
| **L4** | L3 and zero open major reports | Maintained |

> **Rule G-2.** A producer for a T3 document SHOULD warn below L1. A spec
> written before the glossary exists will invent its own vocabulary, and that
> vocabulary then propagates into plans, into code, and into every document
> that derives from it.

---

## 9. Cost model

Effectiveness and cost efficiency are the same problem viewed from two sides:
both are governed by how precisely context is selected and how rarely
expensive checks are run.

### 9.1 The escalation ladder

> **Rule C-1.** A question MUST be answered at the cheapest rung that can answer
> it. Escalate only on failure.

| Rung | Mechanism | Cost | Answers |
|---|---|---|---|
| 0 | Frontmatter query | free | What exists, what depends on what, what is unverified |
| 1 | `LINT` | free | Schema validity, broken edges, orphan and stale reports |
| 2 | Git diff vs `code-refs` | free | What is *suspect* |
| 3 | Auditor on suspect docs only | one model run each | What has *actually* drifted |
| 4 | Repairer on open reports only | one model run each | Fix it |

Rungs 0–2 cover most day-to-day questions. The current implementation starts at
rung 3 for everything, which is why drift checking stays manual: it is too
expensive to run continuously, so it is run rarely, so documents rot between
checks.

### 9.2 Selection discipline

> **Rule C-2.** Every run MUST record `context-tokens`. Unmeasured context spend
> cannot be tuned, and `scope-docs` plus token counts across the run ledger is
> the dataset that tells you which documents are worth their weight.

> **Rule C-3.** A document that has never appeared in any run's `scope-docs`
> after N runs is a candidate for archival. Documents nobody loads are cost
> without benefit, and they still incur audit spend.

> **Rule C-4.** Batch audits by commit range, not by document. One sweep after a
> merge that audits five suspect documents is cheaper and more coherent than
> five sweeps triggered ad hoc, because the auditors share a code reality.

### 9.3 Mode discipline

> **Rule C-5.** Auditors run read-only. Beyond safety (S-2), read-only runs are
> cheaper and faster, and an audit that cannot write cannot accidentally become
> an unreviewed repair.

---

## 10. Open decisions

Genuinely undecided; needed before v1.0.

1. **Report location.** Sibling files (current behaviour, preserves the
   parent-child affordance in a browser) vs. `docs/reports/` (keeps `docs/`
   clean, breaks nesting). Sibling is assumed above.

2. **Provenance depth.** Full append-only history forever, or first entry plus
   last N? Full history is more honest, but frontmatter on a long-lived
   singleton like `ARCH.md` grows without bound.

3. **`id` assignment.** Agent-chosen slug or host-assigned? Agent-chosen is
   simpler but risks collisions and non-determinism across runs.

4. **Does `AMEND` always require an ADR?** Principled — you changed a rule, that
   is a decision — but adds friction to every constraint tweak. Middle ground:
   ADR required only for `severity: major`.

5. **Registry inheritance.** Is `registry.yaml` per-repo, or does it `extends` an
   org-level baseline? A shareable standard across your org implies the latter,
   and that implies an inheritance and override mechanism this draft only
   gestures at.

6. **Who computes `implicates`?** Host at run end (assumed, X-4), or a git hook,
   or CI? Host-side is immediate but only covers changes made through the
   refinery; a hook covers hand edits too.

7. **Does the run ledger belong in git?** Committing `.refinery/runs/` makes
   lineage shareable and reviewable; it also adds a file per run to history.

---

## 11. Gap summary vs. the current `voicecode-bbs` implementation

Present and working:
- 10 publish agents with fixed vs. chosen destinations
- 5 maintenance agents (RECONCILE, REFRESH, COVERAGE, CTX_DRIFT, CTX_UPDATE)
- Frontmatter parsing with `type`-driven UI treatment
- Drift and coverage reports as nested view-only children
- `artifacts` extraction on the prompt side — the first half of lineage

Missing, in priority order:

| # | Gap | Rule | Why it matters |
|---|---|---|---|
| 1 | Authority model | A-1 | Refresh is currently offered where it is destructive |
| 2 | Document-side provenance | F-4 | Lineage is one-directional today |
| 3 | `commit` on every write | F-3 | Without it, all drift detection costs a model run |
| 4 | `code-refs` on documents | F-7 | "Which docs does this commit affect?" is unanswerable |
| 5 | `LINT` | S-4, C-1 | Every check currently costs tokens |
| 6 | `CONFORMANCE` | A-1 | Prescriptive documents have no maintenance path |
| 7 | Execution records | X-4 | Execution is invisible; the loop never closes |
| 8 | Report lifecycle | D-3..D-5 | Reports are write-once, never resolved or reaped |
| 9 | Registry file | G-1 | TUI and web hosts cannot share definitions |
| 10 | Human-edit detection | F-6 | Repairers can silently overwrite hand-written content |
| 11 | Session hygiene | X-3 | Shared sessions leak context outside recorded lineage |
| 12 | Graph edges / `COHERENCE` | T-1 | No doc-to-doc dependency tracking |

Items 3, 4, and 7 are the cheapest to add and unlock the most: together they are
what turns change management from a manual, per-document, model-priced chore
into a continuous free sweep.
