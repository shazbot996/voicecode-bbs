---
type: spec
id: context-refinery
title: Context Refinery — Framework Specification
authority: prescriptive
status: active
version: 1.0
created: 2026-09-10
last-updated: 2026-09-11
stack-scope: invariant
derives-from: [voicecode-bbs]
informs: [context-refinery-app]
code-refs:
  - lib/refinery/**
drift-sensitivity: structural
---

# Context Refinery

**An opinionated framework for context creation, execution, and change
management in agent-built software — anchored on provenance.**

> Build from context. Refine well.

This is the standard. It defines what a conformant repository contains and
records. It is implementable by hand, by any agent CLI, by a CI job, or by the
Context Refinery application — and adopting it requires none of those in
particular.

---

## 0. Scope

### 0.1 What this document owns

| Owned here | Owned by `context-refinery-app` |
|---|---|
| Repository contract — what files exist, where | Deployment modes, UI surfaces |
| Frontmatter schema and all field semantics | Editing, browsing, presenting documents |
| Document type registry — types, authority, lifecycle | Default actions, per-document affordances |
| Agent contract — kinds, required set, write scope | Prompt composition, provider invocation, skills, subagents |
| Execution record and run identity | The run pipeline, preflight, chaining |
| Drift model and report lifecycle | Triage UI, sweep scheduling |
| Registry file format | Registry layering and resolution |
| Cost accounting requirements | Budget enforcement, if any |
| `stack-scope` as a frontmatter field | Stack profiles, transposition, acceptance suites |

> **Rule 0-1.** Where both documents touch a subject, this one defines *what is
> required* and the application spec defines *how it is delivered*. A behaviour
> the application enforces MUST be expressible as a rule here and checkable by
> `LINT` without the application running.

### 0.2 Conformance levels

Keywords MUST, MUST NOT, SHOULD, SHOULD NOT, MAY are used in the RFC-2119 sense,
and they map to two conformance levels.

**Core** — the small set that makes the ledger true. A repository either meets
these or its provenance claims are unreliable, so every Core rule is a MUST and
`LINT` reports violations as errors.

**Recommended** — everything else. These are SHOULD, `LINT` reports them as
warnings, and a repository may adopt them progressively. They are recommendations
in v1 because the framework has not yet earned the right to be rigid about them;
several will likely become Core later, once there is evidence about which ones
actually pay.

The complete Core set is enumerated in §10. Nothing outside §10 blocks
conformance in v1.

---

## 1. Core model

### 1.1 The premise

An agent's output quality is bounded by the precision of the context it was
given, and an agent pipeline's cost is dominated by context it was given
needlessly. Those pressures point in opposite directions, and most teams resolve
the conflict by guessing — loading everything, or loading nothing and letting the
model infer.

Context Refinery resolves it with records instead of guesses. Every document
declares what it describes and what it depends on. Every run records what it
consumed and what it changed. Once those records exist, context selection stops
being a heuristic and becomes a query, and the expensive question — *what is
stale now?* — is answered by a git diff rather than a model call.

### 1.2 The three phases

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
managed.

### 1.3 Authority

Every document type has exactly one **authority** — the answer to "when this
document and the code disagree, which one is wrong?" Every maintenance rule
derives from it.

| Authority | Source of truth | Disagreement means | Repair |
|---|---|---|---|
| **Descriptive** | The code | The *document* is wrong | Rewrite the document from code |
| **Prescriptive** | The document | The *code* is wrong | Raise a violation; change code, or amend the doc by explicit human decision |
| **Historical** | Neither — a record of a past moment | Nothing. Records don't drift | Never edit. Supersede with a new record |

A refinery that runs one uniform "reconcile then refresh" loop over all types
**will silently destroy its own guardrails**. Pointed at a prescriptive document,
"rewrite so every fact matches the live code" deletes the constraint the moment
the code violates it, and the violation becomes the new standard. Pointed at a
historical document, it is falsification.

> **Rule A-1.** *(Core)* A maintenance agent MUST NOT be offered for, or executed
> against, a document whose authority does not admit that action. Action
> eligibility is a property of the document type, not a user choice.

### 1.4 Tiers

| Tier | Name | Contents | Loaded |
|---|---|---|---|
| **T0** | Root context | `AGENTS.md` (canonical), provider stubs, `README.md` | Every session, automatically |
| **T1** | Foundation | `GLOSSARY`, `CONVENTIONS`, `CONSTRAINTS`, `SCHEMA` | On demand; referenced by everything above |
| **T2** | Structural | `ARCH` | On demand; assumes T1 vocabulary |
| **T3** | Working | `SPEC`, `PLAN`, `ADR` | Per task; assumes T1 + T2 |
| **T4** | Derived | drift, coverage, violation reports | Never loaded as context |

> **Rule T-1.** A document SHOULD NOT declare `derives-from` a higher tier.
> Dependencies point downward only, which keeps the context graph acyclic and
> makes "what breaks if I change this?" computable.

> **Rule T-2.** *(Core)* T4 artifacts MUST NOT be injected as context. They are
> work orders with a lifecycle, not documents.

### 1.5 Cardinality

| Cardinality | Meaning | Write semantics |
|---|---|---|
| **Singleton** | Exactly one per repo, at a fixed path | Mutated in place; version increments |
| **Serial** | Numbered sequence, append-only | New file per entry; existing entries immutable |
| **Multiple** | Many, one per subject | Created, lifecycled, archived independently |

### 1.6 Stack scope

Every document declares how it relates to the runtime. The field is defined here
because it is frontmatter; what is *done* with it — stack profiles, transposition
— belongs to the application spec.

```yaml
stack-scope: invariant     # invariant | bound | mixed
stack: nextjs-15           # required when scope is bound
```

| Scope | Meaning |
|---|---|
| **invariant** | True regardless of runtime — domain vocabulary, behaviour, business rules |
| **bound** | Describes or prescribes this runtime specifically — layout, idiom, sequencing |
| **mixed** | Contains both. A transitional state, not a supported configuration |

> **Rule K-1.** `stack-scope` is declared per document. A document containing both
> invariant and bound content SHOULD be split into two. Per-section annotation is
> not supported: it would make the unit of regeneration a fragment rather than a
> file, complicate every producer's write scope, and hide the partition inside a
> document instead of exposing it in the file tree.

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
    stacks/<id>.yaml               target runtime profiles (app spec §2.5)
    runs/
      <author>/NNNN.yaml           execution records (§6.3)
  prompts/
    history/
      <author>/
        NNNN_slug_prompt.md        the prompt as executed
        NNNN_slug_response.md      the agent response
  docs/
    context/                   T1/T2  always-current singletons
      GLOSSARY.md  CONVENTIONS.md  CONSTRAINTS.md  SCHEMA.md  ARCH.md
    decisions/                 T3  ADRs, serial, immutable
      NNNN-slug-ADR.md
    specs/                     T3  <feature>-SPEC.md
    plans/                     T3  <initiative>-PLAN.md
```

> **Rule R-1.** Exactly one T0 file is canonical and maintained. All other
> provider-specific root files MUST be single-line import stubs. Content that
> accumulates in a stub is drift by construction, because nothing maintains it.

> **Rule R-2.** *(Core)* Every file under `docs/` MUST carry valid frontmatter
> (§3). A markdown file under `docs/` without frontmatter is *unmanaged* and MUST
> be reported by the validator, not silently ignored.

> **Rule R-3.** `.refinery/` is the framework's namespace. A repo adopts Context
> Refinery by adding `.refinery/registry.yaml`; conformance level is computed
> from the repo, not asserted in the registry.

> **Rule R-4.** *(Core)* The ledger — `prompts/history/` and `.refinery/runs/` —
> MUST be committed. Lineage outside version control cannot be reviewed in a pull
> request, shared across a team, or rolled back with the code it explains.

### 2.1 Reports

Reports are siblings of the document they describe: a drift report on
`docs/context/ARCH.md` is written to `docs/context/ARCH-DRIFT.md`.

> **Rule R-5.** A report MUST be a sibling of its source. This keeps the
> parent-child relationship visible in any file browser, in a pull request diff,
> and in the application's tree without a lookup. The cost is a slightly noisier
> `docs/` directory, which `CURATE` reaping (§7.2) keeps bounded.

### 2.2 Identity

Two identifiers matter, and both are host-assigned. Neither is chosen by an
agent, because an agent choosing an identifier is a source of collisions and of
non-determinism between otherwise identical runs.

**Document `id`** — host-assigned, derived deterministically from the destination
filename slug at creation, unique across the repository.

> **Rule I-1.** *(Core)* `id` is assigned by the host at creation and is
> immutable for the life of the document. Filenames may change; `id` may not. All
> graph edges reference `id`, never paths.

> **Rule I-2.** A producer MUST NOT invent an `id`. If a generated document
> arrives without the host-assigned `id`, the host sets it; it does not accept
> the agent's.

**Author** — the VCS identity, the git handle, of whoever initiated the run.

> **Rule L-1.** *(Core)* A run is identified by the composite id
> `<author>/<sequence>`, where `sequence` is monotonic **within that author**.
> Provenance entries, reports, and run records MUST reference runs by composite
> id, never by path.

Per-author sequences are not merely organizational. A sequence shared across a
team collides on every concurrent branch, and the resulting merge conflicts land
on exactly the files that are supposed to be an immutable record. Partitioning by
author makes collisions structurally impossible, and it turns the ledger into a
contribution view for free.

> **Rule L-2.** The author is recorded in the run record as well as in the path.
> The directory is a storage convention; the frontmatter is the fact. A changed
> handle relocates files without invalidating the ledger.

> **Rule L-3.** Automation MUST be distinguishable from human authors
> (`author-kind: automation`), so that contribution views do not attribute
> scheduled sweeps to people.

---

## 3. Frontmatter — the provenance layer

Frontmatter is not decoration and not UI colour-coding. It is the only durable
record of how a document came to exist, what it was true about, and what it
depends on. Prose is written for humans; frontmatter is the machine-readable
claim about provenance that every other feature reads.

The design goal: **from any document, reconstruct the prompt that produced it;
from any prompt, find everything it consumed and touched; from any code change,
compute which documents are now suspect — all without invoking a model.**

### 3.1 Document frontmatter

```yaml
---
# ── Identity ─────────────────────────────────────────────
type: spec                     # REQUIRED  enum, §4
id: publish-overlay            # REQUIRED  host-assigned, immutable
title: Publish Overlay         # REQUIRED
authority: prescriptive        # REQUIRED  descriptive|prescriptive|historical
cardinality: multiple          # REQUIRED  singleton|serial|multiple
status: active                 # REQUIRED  §5.1

# ── Versioning ───────────────────────────────────────────
version: 4                     # REQUIRED  integer; +1 on every write
created: 2026-08-14
last-updated: 2026-09-10
last-agent-write: 2026-09-10T14:22:11Z
last-human-edit: 2026-09-02T09:11:00Z   # null if never hand-edited

# ── Provenance ───────────────────────────────────────────
provenance:                    # REQUIRED  append-only, newest last
  - run: charles/0147          #   composite id (Rule L-1)
    agent: SPEC
    action: publish            #   publish|refresh|repair|amend|manual
    model: claude-opus-5
    commit: a3f9c21            #   repo HEAD when the write occurred
    date: 2026-09-10T14:22:11Z
  - run: charles/0151
    agent: REFRESH
    action: refresh
    model: claude-opus-5
    commit: 7be0d43
    date: 2026-09-10T16:40:02Z

# ── Graph edges ──────────────────────────────────────────
derives-from: [glossary, conventions]
informs: [publish-overlay-PLAN]
code-refs:
  - voicecode/ui/publish_overlay.py
  - voicecode/publish/**
drift-sensitivity: content     # content | structural  (§3.4)
stack-scope: invariant         # §1.6
supersedes: null
superseded-by: null

# ── Verification ─────────────────────────────────────────
verified:                      # last CLEAN audit; null if never verified
  commit: 7be0d43
  date: 2026-09-10T16:44:00Z
  by: RECONCILE
---
```

The prompt path is not stored. It is derived from the composite run id and the
registry's history path; storing both would create two sources of truth for one
fact, and they would diverge the first time a directory moved.

### 3.2 Provenance rules

> **Rule F-1.** *(Core)* `provenance` is **append-only and complete**. An agent
> MUST append exactly one entry per write and MUST NOT rewrite, prune, or
> truncate prior entries. Full history is kept indefinitely.

Unbounded growth is the obvious objection and in practice it does not bite: an
entry is six short lines, and documents written hundreds of times are rare enough
to handle individually. The alternative — truncating to the last N — destroys
exactly the entries most worth having, which are the early ones explaining why a
document exists at all.

> **Rule F-2.** *(Core)* Every provenance entry MUST carry `commit`. An entry
> without the repo HEAD it was written against is worthless for drift detection
> (§7.1) and MUST be rejected.

> **Rule F-3.** Lineage SHOULD be bidirectional and verifiable. If document `X`
> lists run `charles/0147`, that run's record SHOULD list `X` in its `artifacts`.
> `LINT` checks both ends resolve and warns on a one-sided edge.

> **Rule F-4.** `derives-from` edges SHOULD resolve to an existing `id` and point
> to an equal or lower tier.

> **Rule F-5.** If `last-human-edit` is later than `last-agent-write`, the
> document carries **unreconciled human intent**. A repairer SHOULD reconcile
> rather than blind-overwrite, and SHOULD surface the conflict. This is what
> stops the refinery from eating hand-written nuance.

### 3.3 `code-refs` — what a document claims

`code-refs` is the document's claim about its own subject matter. It makes drift
detection free (§7.1) and context selection selective (§6.1).

> **Rule F-6.** A T1, T2, or T3 document SHOULD declare `code-refs`. A document
> with none can never be marked suspect and has opted out of change management;
> `LINT` warns.

**`code-refs` is not an inventory.** A core singleton like `ARCH.md` describes the
shape of a system, not a list of files, and enumerating every file it touches
would be unmaintainable and wrong the moment a file is added. Coarse globs are the
intended usage:

```yaml
# ARCH.md
code-refs: ["src/**", "cmd/**"]
drift-sensitivity: structural
```

### 3.4 `drift-sensitivity`

A coarse glob would leave a document permanently suspect if every edit counted,
so documents declare *what kind* of change invalidates them.

| Value | Suspect when a matching path is | Suits |
|---|---|---|
| **content** *(default)* | modified, added, deleted, or renamed | Documents describing specific behaviour — specs, schema detail |
| **structural** | added, deleted, renamed, or moved — **not** edited in place | Documents describing shape — `ARCH`, `CONVENTIONS`, `README` |

An architecture document is invalidated by a new package, a deleted module, or a
directory reorganization. It is not invalidated by a one-line change inside an
existing file. Declaring that distinction is what lets the core singletons carry
a two-line `code-refs` and still produce a meaningful signal rather than constant
noise.

> **Rule F-7.** A document using globs broader than a single directory SHOULD
> declare `drift-sensitivity: structural`. `LINT` warns when a broad glob is
> paired with content sensitivity, because the result is a document that is
> always suspect and therefore never informative.

### 3.5 Prompt frontmatter

```yaml
---
run: charles/0147
author: charles
date: 2026-09-10T14:22:11Z
agent: SPEC                    # null for a free-form execute
action: publish
provider: claude
model: claude-opus-5
commit: a3f9c21
session: 8f21-…
scope-docs: [glossary, conventions, arch]
artifacts: [docs/specs/publish-overlay-SPEC.md]
code-touched: [voicecode/ui/publish_overlay.py]
refined: true
refine-cycles: 3
---
```

`scope-docs` turns the prompt archive into a **context contribution ledger**: it
records not only what a run produced but what it was permitted to see. Two runs
producing contradictory documents are almost always explained by differing
`scope-docs`, and without the field that diagnosis is guesswork.

### 3.6 What provenance buys

Deterministic queries, no model call:

- *Which documents are suspect after this merge?* — `code-refs` matched against
  the diff since `verified.commit`, filtered by `drift-sensitivity`.
- *Where did this claim come from?* — walk `provenance` to the prompt.
- *What breaks if I rewrite the glossary?* — transitive closure of `informs`.
- *Which documents earn their keep?* — frequency in `scope-docs` across runs.
- *Who has shaped this document?* — authors across its provenance entries.
- *Is this a hand-edit or an agent artifact?* — compare the two timestamps.
- *Has this ever been checked against code?* — `verified == null`.

---

## 4. Document type registry

| Type | Tier | Authority | Cardinality | Destination | Filename | Stack scope |
|---|---|---|---|---|---|---|
| `agents` | T0 | descriptive | singleton | root | `AGENTS.md` | mixed |
| `readme` | T0 | descriptive | singleton | root | `README.md` | mixed |
| `glossary` | T1 | prescriptive | singleton | `docs/context/` | `GLOSSARY.md` | invariant |
| `conventions` | T1 | prescriptive | singleton | `docs/context/` | `CONVENTIONS.md` | bound |
| `constraints` | T1 | prescriptive | singleton | `docs/context/` | `CONSTRAINTS.md` | invariant |
| `schema` | T1 | descriptive | singleton | `docs/context/` | `SCHEMA.md` | invariant |
| `arch` | T2 | descriptive | singleton | `docs/context/` | `ARCH.md` | bound |
| `spec` | T3 | prescriptive | multiple | `docs/specs/` | `<slug>-SPEC.md` | invariant |
| `plan` | T3 | prescriptive → historical | multiple | `docs/plans/` | `<slug>-PLAN.md` | bound |
| `adr` | T3 | historical | serial | `docs/decisions/` | `NNNN-<slug>-ADR.md` | mixed |
| `drift-report` | T4 | derived | multiple | sibling | `<source>-DRIFT.md` | — |
| `coverage-report` | T4 | derived | multiple | sibling | `<source>-COVERAGE.md` | — |
| `violation-report` | T4 | derived | multiple | sibling | `<source>-VIOLATION.md` | — |

### 4.1 Notes on the awkward types

**`plan` changes authority mid-life.** While `active` it is prescriptive — the
code should come to match it. Once `complete` it is historical and immutable.
Refreshing a completed plan against the code produces a tautology: the plan
matches the code because it was rewritten from the code, and the record of what
was intended is gone.

> **Rule P-1.** A `plan` MUST transition `active → complete | abandoned` and MUST
> NOT accept a repairer after that transition.

**`adr` is immutable from birth.** The only legal mutation is setting
`superseded-by` when a newer ADR replaces it.

**`spec` is prescriptive, which inverts its drift semantics.** A spec disagreeing
with code usually means the feature is unfinished or the implementation diverged
— not that the spec is stale. The output is a violation report, not a rewrite.

**`glossary` / `conventions` / `constraints` are prescriptive.** COVERAGE is
their maintenance action: find undocumented terms and patterns to *add*. A
refresher is not.

**`schema` is descriptive** despite its neighbours. Folder is not authority. Its
domain model is invariant; any ORM mapping it carries is bound and should be
split out before a port (Rule K-1).

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

`status`: `template | draft | active | suspect | superseded | archived |
complete | abandoned | blocked`.

`template` is a required-but-unwritten document carrying valid frontmatter and
guidance comments.

> **Rule S-1.** `suspect` MAY be set deterministically (§7.1) with no model call.
> Only an audit run clears it to `active`, and only by writing `verified`.

> **Rule S-2.** *(Core)* A `template` document MUST NOT be injected as context.
> An empty constraints file teaches an agent nothing; injecting it teaches it
> that constraints are empty.

### 5.2 Agent kinds

| Kind | Writes | Model call | Purpose |
|---|---|---|---|
| **Producer** | the document | yes (build) | Creates or replaces a document |
| **Auditor** | a T4 report only | yes (read-only) | Compares document to reality |
| **Repairer** | the document | yes (build) | Consumes a report and applies it |
| **Validator** | nothing | **no** | Deterministic lint over frontmatter and graph |
| **Curator** | frontmatter only | **no** | Lifecycle, supersession, archival, reaping |

> **Rule S-3.** *(Core)* An Auditor MUST run read-only and MUST NOT write to the
> workspace other than its report. A Producer or Repairer MUST run in build mode.
> An agent whose prompt ends by saving a file MUST NOT be configured read-only —
> it will report success and write nothing.

### 5.3 Agent contract

```yaml
id: SPEC
kind: producer
doc-type: spec
run-mode: build                 # build | read-only
template: prompts/SPEC.md
requires-context: [glossary, conventions, arch]
write-scope: ["docs/specs/*-SPEC.md"]
applies-to-authority: [prescriptive]
```

> **Rule S-4.** *(Core)* `write-scope` is enforced by the host, not requested of
> the model. An agent that writes outside its declared scope has failed the run,
> and the run MUST be reported as failed even if the model reports success.

> **Rule S-5.** *(Core)* Every write by any agent MUST append a provenance entry.
> A write without provenance breaks every query in §3.6.

### 5.4 Required agent set

**Producers**, one per non-derived type — 10: `AGENTS`, `README`, `GLOSSARY`,
`CONVENTIONS`, `CONSTRAINTS`, `SCHEMA`, `ARCH`, `SPEC`, `PLAN`, `ADR`.

**Auditors** — 4:

| Agent | Applies to | Finds | Emits |
|---|---|---|---|
| `RECONCILE` | descriptive | Document claims the code no longer supports | drift-report |
| `COVERAGE` | T1, T2 | Code items with no documentation | coverage-report |
| `CONFORMANCE` | prescriptive | Code that violates the document | violation-report |
| `COHERENCE` | any with `derives-from` | Documents contradicting each other, independent of code | drift-report |

`CONFORMANCE` is the inverse of `RECONCILE`; without it, prescriptive documents
have no maintenance path at all. `COHERENCE` catches the case where `ARCH` and
`SCHEMA` describe two different systems and each individually matches the code.

**Repairers** — 2:
- `REFRESH` — descriptive only. Consumes a drift report, rewrites in place.
- `AMEND` — prescriptive only. Consumes a violation report and applies an
  explicit human decision to change the document.

> **Rule S-6.** `AMEND` MUST require confirmation and SHOULD record the decision
> as an ADR. Requiring an ADR for every constraint tweak is more ceremony than v1
> has earned; a host MAY require one above a severity threshold.

**Validator** — 1, no model: `LINT`. Core rules as errors, Recommended as
warnings.

**Curator** — 1, no model: `CURATE`. Lifecycle transitions, supersession chains,
archival, report reaping, and rolling old run records into dated summaries.

Total: **18 agents**, two of which never call a model.

---

## 6. Execution

Creation produces context. Execution spends it.

### 6.1 Context selection

> **Rule X-1.** *(Core)* An execution MUST declare its `scope-docs` before the
> run, and the host MUST inject exactly those documents. Ambient context —
> whatever the provider happens to have cached from a prior turn — is not
> context; it is contamination, and it makes the run unreproducible.

Selection policy, in order of preference:

1. **Declared.** The task names its documents. Use them.
2. **Derived.** Walk `derives-from` downward and include the closure.
3. **Matched.** For a code-modifying task, include documents whose `code-refs`
   match the files in scope.
4. **Never blanket.** Loading all of `docs/` is not a selection policy; it is the
   failure mode this framework exists to replace.

> **Rule X-2.** T0 is always injected. T4 is never injected. T1 is injected for
> any run that writes code or documents. T2 and T3 follow the policy above.

### 6.2 Session hygiene

> **Rule X-3.** A run's recorded `scope-docs` MUST be complete. If the host uses
> provider session continuity, then either each run starts a fresh session, or
> the record MUST include the session id and the ordered prior runs within it, so
> the true context set remains reconstructible.

### 6.3 The execution record

One record per run, at `.refinery/runs/<author>/NNNN.yaml`, written whether the
run produced a document, changed code, or failed.

```yaml
run: charles/0152
author: charles
author-kind: human         # human | automation
date: 2026-09-10T17:02:00Z
kind: code-change          # code-change | publish | audit | repair | query
agent: null
provider: claude
model: claude-opus-5
run-mode: build
commit-before: 7be0d43
commit-after: c11a904
session: 8f21-…
scope-docs: [agents, constraints, conventions, publish-overlay]
skills:
  - id: go-idioms
    digest: sha256:9c1f…
    via: pinned            # pinned | discovered
context-tokens: 18400
output-tokens: 6200
cached-tokens: 12100
cost-usd: 0.41
rate-table: claude-2026-09
duration-s: 214
code-touched: [voicecode/ui/publish_overlay.py, voicecode/publish/base.py]
artifacts: []
implicates: [arch, publish-overlay]
outcome: success           # success | failed | scope-violation | killed
```

> **Rule X-4.** *(Core)* After any run that changes code, the host MUST compute
> `implicates` by matching `code-touched` against every document's `code-refs`,
> filtered by `drift-sensitivity`, and MUST mark those documents suspect. This is
> where the loop closes: execution schedules its own change management, with no
> model call and nobody remembering to do it.

> **Rule X-5.** A run ending `scope-violation` MUST NOT write provenance and MUST
> NOT mark documents suspect. Failed runs stay out of the lineage graph.

> **Rule X-6.** *(Core)* `scope-docs` and `skills` together MUST account for all
> context the run received. Harness-supplied context the host cannot enumerate
> MUST be recorded as `skills: unknown` rather than omitted. A ledger that is
> silently incomplete is worse than one that is honestly partial, because only
> the second kind can be fixed.

---

## 7. Change management

### 7.1 Two-stage drift detection

**Stage 1 — deterministic suspicion.** For each document, diff `verified.commit`
(or the last provenance `commit`) against `HEAD`. If a changed path matches
`code-refs` at the document's `drift-sensitivity`, set `status: suspect` and
record the implicating commits. No model call. This is the same computation as
X-4 over a range rather than a single run, and it is what makes continuous drift
tracking affordable.

**Stage 2 — agent audit.** Only for suspect documents, and only the audit
matching the document's authority:

| Authority | Stage-2 agent | Output |
|---|---|---|
| descriptive | `RECONCILE` | drift-report |
| prescriptive | `CONFORMANCE` | violation-report |
| historical | *(skip)* | — |

> **Rule D-1.** Stage 2 MUST NOT run on a document Stage 1 did not mark suspect,
> unless explicitly forced. Auditing unchanged documents is the largest source of
> wasted spend in this workflow.

### 7.2 Report lifecycle

Reports are work orders. They rot faster than the documents they describe, and an
unreaped report becomes its own source of drift.

```yaml
---
type: drift-report
source: publish-overlay
source-version: 4
against-commit: 7be0d43
generated-by-run: charles/0153
status: open                     # open | resolved | dismissed | stale
severity: moderate               # minor | moderate | major
resolved-by-run: null
---
```

> **Rule D-2.** A report is **stale** the moment its `source-version` no longer
> matches the source document's `version`. Stale reports MUST NOT be presented as
> actionable and SHOULD be reaped by `CURATE`.

> **Rule D-3.** A repair run MUST set the consuming report to `resolved` and
> record the run id. A repair leaving a report `open` will be re-offered forever.

> **Rule D-4.** At most one `open` report of a given kind SHOULD exist per source
> document. Re-running an audit supersedes the previous report.

### 7.3 The repair loop

```
 code change (X-4)  ──┐
                      ├──→ suspect ──→ audit ──→ report ──→ human triage
 Stage 1 sweep (D-1) ─┘                                          │
                    ┌────────────────────────┬───────────────────┤
                    ▼                        ▼                   ▼
             REFRESH                  change the code       AMEND (+ADR)
             (descriptive)            (prescriptive)        (prescriptive)
                    │                        │                   │
                    ▼                        ▼                   │
             verified updated         CONFORMANCE re-run         │
                    │                        │                   │
                    └────────→ report resolved ◄─────────────────┘
```

> **Rule D-5.** *(Core)* Triage is a human decision for prescriptive findings. An
> agent MUST NOT choose between "change the code" and "change the document" —
> that choice is the entire point of having a prescriptive document.

---

## 8. The registry

`.refinery/registry.yaml` expresses §4 and §5.3 as data, so that any host — TUI,
web, CLI, CI — implements identical behaviour, and a repo can override defaults
without forking tooling.

```yaml
refinery-version: 1.0
extends:                         # optional; resolved first to last
  - ./baseline.yaml              #   local path or well-known name
  # - registry:acme/base@2.1     #   reserved: remote, not resolved in v1
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
    stack-scope: invariant
    dest: docs/specs/
    filename: "{slug}-SPEC.md"
    required: false
    default-action: plan
    drift-sensitivity: content
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
```

> **Rule G-1.** *(Core)* The host MUST read the registry rather than hardcode the
> type list. Adding a document type MUST be a registry edit plus a prompt
> template, with no host code change.

> **Rule G-2.** The registry is **per-repository**. v1 resolves local `extends`
> references only. An organization-wide baseline is a distribution problem, not a
> file-format problem, and is deliberately out of scope.

> **Rule G-3.** `extends` MUST be a list, and each entry MUST be parsed as a
> reference that may be local or remote. A remote reference MUST fail with a
> clear unsupported-scheme error rather than a parse error. Accepting what cannot
> yet be resolved costs nothing now and avoids a breaking change later.

### 8.1 Readiness gates

| Level | Requires | Meaning |
|---|---|---|
| **L0** | nothing | Unmanaged repo |
| **L1** | glossary, conventions, constraints active | Agents have vocabulary and rails |
| **L2** | + schema, arch active and verified | Agents have a structural map |
| **L3** | + agents, readme active and verified | Fully grounded |
| **L4** | L3 and zero open major reports | Maintained |

> **Rule G-4.** A producer for a T3 document SHOULD warn below L1. A spec written
> before the glossary exists will invent its own vocabulary, and that vocabulary
> propagates into plans, into code, and into every document derived from it.

---

## 9. Cost model

Effectiveness and cost efficiency are the same problem from two sides: both are
governed by how precisely context is selected and how rarely expensive checks
run.

### 9.1 The escalation ladder

> **Rule C-1.** A question SHOULD be answered at the cheapest rung that can
> answer it. Escalate only on failure.

| Rung | Mechanism | Cost | Answers |
|---|---|---|---|
| 0 | Frontmatter query | free | What exists, what depends on what, what is unverified |
| 1 | `LINT` | free | Schema validity, broken edges, orphan and stale reports |
| 2 | Git diff vs `code-refs` | free | What is *suspect* |
| 3 | Auditor on suspect docs only | one run each | What has *actually* drifted |
| 4 | Repairer on open reports only | one run each | Fix it |

Rungs 0–2 cover most day-to-day questions. Starting at rung 3 for everything is
why drift checking stays manual: too expensive to run continuously, so it runs
rarely, so documents rot in between.

### 9.2 Accounting

> **Rule C-2.** *(Core)* Every run MUST record `context-tokens`. Unmeasured
> context spend cannot be tuned, and `scope-docs` plus token counts across the
> ledger is the dataset that reveals which documents are worth their weight.

> **Rule C-3.** Every run SHOULD record whatever economic metrics the provider
> exposes — output and cached tokens, reported cost, and the `rate-table` used to
> derive it. The rate table matters as much as the number: a cost recorded
> without it is uninterpretable once pricing moves.

No budget or throttling policy is specified. Collection comes first; a policy
chosen before there is data would be a guess wearing a rule number.

> **Rule C-4.** A document never appearing in any run's `scope-docs` after N runs
> is a candidate for archival. Documents nobody loads are cost without benefit,
> and they still incur audit spend.

> **Rule C-5.** Audits SHOULD be batched by commit range rather than by document.
> One sweep auditing five suspect documents is cheaper and more coherent than
> five ad hoc sweeps, because the auditors share a code reality.

---

## 10. Core conformance

A repository is conformant when all of the following hold. `LINT` reports these
as errors and everything else as warnings.

| Rule | Requirement |
|---|---|
| R-2 | Every file under `docs/` carries valid frontmatter |
| R-4 | The ledger is committed |
| I-1 | `id` is host-assigned and immutable |
| F-1 | `provenance` is append-only and complete |
| F-2 | Every provenance entry carries `commit` |
| A-1 | Maintenance actions respect document authority |
| T-2, S-2 | T4 and `template` documents are never injected as context |
| S-3 | Auditors run read-only; producers and repairers run in build mode |
| S-4 | Write scope is host-enforced |
| S-5 | Every agent write appends provenance |
| X-1 | `scope-docs` is declared before the run |
| X-4 | `implicates` is computed after every code-changing run |
| X-6 | `scope-docs` + `skills` account for all context received |
| C-2 | Every run records `context-tokens` |
| D-5 | Prescriptive triage is a human decision |
| G-1 | The host reads the registry rather than hardcoding types |
| L-1 | Runs are identified by `<author>/<sequence>` |

Everything else here is a recommendation in v1. The Core set is deliberately
small: it is exactly what must hold for the ledger to be true, and nothing more.
A framework that requires thirty things on day one gets adopted for none of them.

---

## 11. Design decisions

Recorded so future readers see the reasoning, not just the rule.

| # | Decision | Rationale |
|---|---|---|
| 1 | Reports are siblings of their source | Parent-child stays visible in any browser and in a PR diff, with no lookup. Noise is bounded by `CURATE` reaping |
| 2 | Provenance is kept in full, forever | Truncation destroys the earliest entries, which explain why a document exists. Growth is bounded in practice: entries are short and most documents are written few times |
| 3 | `code-refs` are coarse; `drift-sensitivity` disambiguates | Core singletons describe shape, not files. `structural` sensitivity makes a two-line glob informative instead of permanently noisy |
| 4 | `id` and run sequence are host-assigned | An agent choosing an identifier is a source of collisions and of non-determinism between otherwise identical runs |
| 5 | Run ids are `<author>/<sequence>` | Shared sequences collide on every concurrent branch, and the conflicts land on the immutable record. Per-author partitioning makes collisions structurally impossible and yields a contribution view for free |
| 6 | Most rules are SHOULD in v1 | Too many business rules for a first pass. The Core set is what must hold for the ledger to be true; the rest earns promotion with evidence |
| 7 | Registry is per-repository | An org baseline is a distribution problem, better solved by a service than a file format. The schema still accepts remote references it cannot yet resolve |
| 8 | The ledger is committed and git-attributed | Lineage outside version control cannot be reviewed, shared, or rolled back with the code it explains |
| 9 | `stack-scope` is per document | Per-section annotation would make the unit of regeneration a fragment and hide the partition inside a file |

### 11.1 Remaining open question

**Who computes `implicates`?** Rule X-4 assigns it to the host at run end, which
is immediate but only covers changes made through the refinery. A git hook would
also catch hand edits and agents invoked outside the app. CI would catch
everything but only at push time, by which point suspect flags arrive after
review has already started.

The likely answer is host-at-run-end with a CI sweep as backstop and the hook as
an optional extra — but it is unresolved, and it is the one place where the loop
in §1.2 can currently leak.

---

## 12. Gap summary vs. `voicecode-bbs`

Present and working:
- 10 publish agents with fixed vs. chosen destinations
- 5 maintenance agents (RECONCILE, REFRESH, COVERAGE, CTX_DRIFT, CTX_UPDATE)
- Frontmatter parsing with `type`-driven UI treatment
- Drift and coverage reports as nested view-only children
- `artifacts` extraction on the prompt side — the first half of lineage

Missing, in order of leverage:

| # | Gap | Rule | Why it matters |
|---|---|---|---|
| 1 | Authority model | A-1 | Refresh is currently offered where it is destructive |
| 2 | `commit` on every write | F-2 | Without it, all drift detection costs a model run |
| 3 | `code-refs` + `drift-sensitivity` | F-6, F-7 | "Which docs does this commit affect?" is unanswerable |
| 4 | Execution records | X-4 | Execution is invisible; the loop never closes |
| 5 | Document-side provenance | F-3 | Lineage is one-directional today |
| 6 | `LINT` | §10 | Every check currently costs tokens |
| 7 | `CONFORMANCE` | A-1 | Prescriptive documents have no maintenance path |
| 8 | Report lifecycle | D-2..D-4 | Reports are write-once, never resolved or reaped |
| 9 | Registry file | G-1 | TUI and web hosts cannot share definitions |
| 10 | Author-partitioned ledger | L-1 | Sequences collide the moment a second person joins |
| 11 | Human-edit detection | F-5 | Repairers can silently overwrite hand-written content |
| 12 | Session hygiene | X-3 | Shared sessions leak context outside recorded lineage |

Items 2, 3, and 4 are cheapest to add and unlock the most: together they turn
change management from a manual, per-document, model-priced chore into a
continuous free sweep.
