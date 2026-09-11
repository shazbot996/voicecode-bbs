---
type: spec
id: context-refinery-app
title: Context Refinery — Application Specification
authority: prescriptive
status: draft
version: 0.1
created: 2026-09-11
derives-from: [context-refinery]
code-refs:
  - app/**
  - lib/refinery/**
  - .refinery/**
---

# Context Refinery — Application Specification

**The application that ships inside the repository it manages.**

> Build from context. Refine well.

This document specifies the application. The framework it implements is
specified separately in `CONTEXT-REFINERY-SPEC` (the standard). The standard is
the shareable asset; other teams may adopt it with no application at all. This
application exists to make the standard cheap to follow and impossible to drift
from silently.

---

## 0. Relationship to the standard

| | Standard | Application |
|---|---|---|
| Artifact | `CONTEXT-REFINERY-SPEC.md`, registry defaults, prompt templates | Next.js app + runner |
| Answers | *What must a conformant repo contain and record?* | *How do I do that without thinking about it?* |
| Adoption | Copy `.refinery/`, follow the rules by hand or with any agent CLI | `npx create-refinery` into a repo |
| Repo | `context-refinery` | `context-refinery-app` |

The full division of responsibility is tabulated in §0.1 of the standard and is
not restated here. In short: the standard defines *what is required*, this
document defines *how it is delivered*. Where this document names a rule from the
standard it cites it (`Rule A-1`, `Rule X-4`) rather than reproducing it, and
rules numbered `N-M` are this document's own.

> **Rule 0-1.** The application MUST NOT be required to achieve conformance. Any
> behaviour the app enforces MUST be expressible as a rule in the standard and
> checkable by `LINT` without the app running. The app is an accelerator, not a
> runtime dependency.

---

## 1. Product thesis

Context Refinery installs into a project and gives you a browser over the
project's own context layer, a set of configurable agents that produce and
maintain that layer, and an execution engine that spends the layer to change
code. It runs where the repository is, reads and writes ordinary markdown, and
records everything it does to a git-committed ledger.

Three properties distinguish it:

1. **It lives inside the repo it manages.** Not a SaaS pointed at your code, not
   an IDE you must adopt. A route in your own app, or a standalone dev server in
   the same working tree. The context layer, the prompts, the agent config, and
   the run ledger are all files in your repository, under your version control.
2. **Every document has an authority.** Descriptive documents get repaired from
   code; prescriptive documents raise violations against code; historical
   documents are never touched. No other tool in this space makes this
   distinction, and without it automated maintenance erodes the standard it was
   installed to protect.
3. **Every run is recorded.** What context it consumed, what it changed, what it
   invalidated, what it cost. This is the substrate for everything else — cheap
   drift detection, context tuning, and the transposition proof in §2.

### 1.1 Position against prior art

Spec-driven development is a crowded category — Spec Kit, Kiro, OpenSpec, BMAD,
Tessl, Antigravity. Doc-drift linting is a real category too — Fiberplane's
`drift`, `staledocs`, `docpin`, Swimm. Both categories are worth learning from
and neither is the same product.

| Concern | Prior art | Context Refinery |
|---|---|---|
| Spec authoring workflow | Spec Kit, Kiro, OpenSpec | Same idea; we adopt it rather than reinvent it |
| Doc↔code binding, staleness | `drift`, `docpin`, `staledocs` | Same mechanism (commit/fingerprint anchoring). We add authority, so repair direction is correct |
| Spec as long-term memory | Tessl | Same, plus a run ledger that makes the memory auditable |
| Prompt→document lineage | *none found* | Bidirectional, lint-enforced |
| Context spend measurement | *none found* | `scope-docs` + token accounting per run |
| Stack transposition | *none found* | §2, the primary goal |

> **Rule 1-1.** Where prior art has a working convention, adopt it rather than
> invent. Specifically: `AGENTS.md` as the canonical root context file, EARS-style
> acceptance criteria in specs, and a CI gate that fails on stale documents.
> Novelty is reserved for the authority model, the provenance ledger, and stack
> scoping.

---

## 2. Primary goal: the stack transposition proof

**Take a working Next.js application, change one line of configuration, and have
the agents regenerate it in Go — passing the same acceptance tests.**

This is the first milestone the application should be able to demonstrate, and
it is the goal the rest of the design serves. It is chosen not because
transposition is a common need but because it is the only honest test of whether
the context layer actually captured the application. If the specs are complete,
the port is mechanical. If the port fails, the specs were prose.

### 2.1 Why this is the right proof

Every other demonstration of context quality is subjective. "The agent built my
feature correctly" is unfalsifiable — the agent may have inferred from code it
could see. Transposition removes that escape: the target runtime shares no code
with the source. Whatever survives the port came from the documents, and
whatever breaks identifies precisely which document was incomplete.

It also produces a diagnostic, not just a verdict. A failing acceptance test
after transposition points at exactly one gap in exactly one spec.

### 2.2 What must be true for it to work

**Acceptance criteria must be stack-independent and executable.** A spec whose
success criteria are prose cannot gate a port. Criteria must be expressed at a
boundary both stacks share — HTTP request/response, CLI in/out, database state,
rendered DOM.

> **Rule 2-1.** Every `spec` MUST carry a `Success Criteria` section written as
> black-box assertions at a stack-neutral boundary. Criteria referencing
> framework internals (a React hook, a Go struct) are a lint error.

**The document set must be partitioned by stack dependence.** This is the
central new concept the app introduces, and it is what makes transposition a
configuration change rather than a rewrite.

**There must be a frozen, stack-neutral acceptance suite.** See §2.3.

### 2.3 The acceptance suite

The acceptance suite is the only artifact shared by both stacks and the only
thing that can render a verdict on a port. It deserves its own rules.

#### 2.3.1 What it is, and what it is not

An acceptance test **never imports application code**. It starts the system and
interacts with it across an external boundary, the way a user or a peer service
would. A unit test calls a function and asserts on its return value; it is welded
to the implementation and becomes worthless the moment the implementation is
replaced in another language. An acceptance test is a conversation over a wire.

```
POST /api/links   {"url": "https://example.com", "title": "Example"}
  → 201, body contains an id
GET  /api/links
  → 200, list contains that id
POST /api/links   {"url": "not-a-url"}
  → 400, body names the offending field
GET  /api/links   (no auth header)
  → 401
```

Nothing in that is TypeScript or Go. The same file runs unchanged against both
implementations, which is what makes the port verifiable at all. The equivalent
boundary for a CLI is argv, stdout, and exit code; for a batch job, seeded input
state and resulting output state.

> **Rule 2-4.** The acceptance suite MUST NOT import, link, or otherwise
> reference the application under test. It MUST address the system only through
> an interface declared identically by every stack profile. A suite that reaches
> inside is a unit suite wearing a costume, and it will not survive a port.

#### 2.3.2 Where the suite comes from

Generated by an agent from the specs, then **validated against the working
source application and frozen.** The validation step is what matters.

```
 1. An agent reads each invariant spec and emits acceptance tests
 2. The suite runs against the source stack — the app you have used
    and confirmed behaves correctly
 3. Every disagreement is resolved BY HAND, deciding case by case
    whether the test was wrong or the application was
 4. The suite passes against a verified system → freeze it
```

Without step 3 the exercise is circular. An agent that reads `SPEC.md`, writes
the code, then reads the same `SPEC.md` and writes the tests will produce an
artifact that agrees with itself: both halves inherit the same misreading of the
same ambiguous sentence, the suite passes, and nothing has been proven. Tests
generated from the *code* are worse — they assert whatever the code currently
does, defects included, and then defend them.

Step 3 breaks the circle by inserting reality. Once the suite has been reconciled
against a system a human has actually verified, it is no longer derived from the
specs; it is an empirical record of how a working system behaved. The Go
implementation is then graded by an artifact that predates it and that it had no
hand in shaping.

> **Rule 2-5.** An acceptance suite MUST be reconciled against a running,
> human-verified implementation before it is used as a transposition gate. A
> suite that has never been run against a working system is a hypothesis, not a
> gate.

> **Rule 2-6.** The suite carries its own provenance: the run that generated it,
> the commit and stack it was reconciled against, and the date it was frozen.
> A suite whose reconciliation commit is unknown MUST NOT gate a port.

#### 2.3.3 The freeze

> **Rule 2-7.** During a transposition run the acceptance suite is **read-only**.
> Any write to the acceptance path is a scope violation under Rule S-3 and fails
> the run, regardless of the outcome of the tests themselves.

This rule exists because an agent asked to make tests pass will sometimes weaken
the assertion rather than fix the code. `expect(status).toBe(201)` becomes
`expect(status).toBeLessThan(500)`, everything goes green, and the gate has been
quietly disarmed. The failure is invisible in a passing test report and obvious
in a diff, so the enforcement belongs at the diff.

When the target implementation fails a test, exactly two resolutions are legal:

1. **Fix the target implementation.** The usual case.
2. **Fix the spec, then regenerate and re-freeze the suite.** Legal only when the
   original behaviour was genuinely wrong, and it MUST be recorded as an ADR
   explaining why. Re-freezing requires reconciliation against the source stack
   again (Rule 2-5).

Editing the test to accommodate the implementation is never legal.

#### 2.3.4 Test generation as spec lint

Deciding what to assert is the hard part of testing, and it is the same work as
writing a `Success Criteria` section. This makes the generator useful well
before any port:

> **Rule 2-8.** `LINT --criteria` runs the acceptance generator against a spec in
> read-only mode and reports any criterion from which no concrete assertion could
> be derived. Such criteria are prose, not requirements, and MUST be rewritten.

"The system should handle errors gracefully" yields nothing testable. "An invalid
URL returns 400 and names the offending field" yields a test. One cheap run turns
the first into the second, and the document is permanently better whether or not
a transposition ever happens.

### 2.4 Stack scope in practice

The `stack-scope` field, its values, and the per-document rule are defined in the
standard (§1.6, Rule K-1). What matters here is what transposition *does* with
each value:

| Scope | On transposition |
|---|---|
| **invariant** | Carried over unchanged |
| **bound** | Regenerated against the new stack profile |
| **mixed** | Blocks the port; must be split first |

Default classification, and the reasoning behind each:

| Document | Scope | Rationale |
|---|---|---|
| `glossary` | invariant | Domain vocabulary does not change with runtime |
| `constraints` | mostly invariant | Business and security rules survive; "no client-side secrets" is invariant, "use Server Actions" is bound |
| `spec` | invariant | Behaviour, not implementation — enforced by Rule 2-1 |
| `adr` | mixed | Some decisions are domain, some are runtime. Runtime ADRs are superseded by the port, not carried |
| `schema` | mixed | The data model is invariant; ORM mapping is bound |
| `arch` | bound | Component structure is a property of the runtime |
| `conventions` | bound | Naming, file layout, lint rules are per-language |
| `plan` | bound | Plans are implementation sequences |

> **Rule 2-2.** `LINT --transposition` MUST report every `mixed` document as a
> blocker and MUST name the split it implies — `CONSTRAINTS.md` beside
> `CONSTRAINTS-nextjs-15.md`, a domain `SCHEMA.md` beside a persistence-mapping
> document. Rule K-1 of the standard says a mixed document should be split; this
> is where that becomes actionable, because a port cannot proceed past it.

Forcing the split costs one awkward afternoon per repository and makes the
invariant set something you can point at.

### 2.5 Stack profiles

A stack profile is a registry fragment describing a target runtime: language,
frameworks, layout conventions, test runner, build and run commands, and the
prompt fragments that teach agents its idioms.

```yaml
# .refinery/stacks/nextjs-15.yaml
id: nextjs-15
language: typescript
runtime: node-22
frameworks: [next@15, react@19, tailwind@4]
layout:
  routes: app/
  components: components/
  server: app/api/
tests:
  runner: vitest
  e2e: playwright
  acceptance: tests/acceptance/**        # the stack-neutral gate
commands:
  install: npm ci
  build: npm run build
  test: npm test
  dev: npm run dev
regenerates: [arch, conventions, plan]   # bound doc types
prompt-fragments:
  conventions: stacks/nextjs-15/CONVENTIONS.md
  arch: stacks/nextjs-15/ARCH.md
```

```yaml
# .refinery/stacks/go-1.24.yaml
id: go-1.24
language: go
runtime: go1.24
frameworks: [chi, templ, sqlc]
layout:
  routes: internal/http/
  components: internal/view/
  server: cmd/server/
tests:
  runner: go test
  acceptance: tests/acceptance/**
commands:
  install: go mod download
  build: go build ./...
  test: go test ./...
  dev: go run ./cmd/server
regenerates: [arch, conventions, plan]
```

> **Rule 2-9.** The acceptance suite MUST live at a path declared identically by
> every stack profile and MUST NOT import from the application under test. It
> speaks to the running system over its external boundary only. This is the one
> artifact both stacks share, and it is what makes the port verifiable.

### 2.6 Transposition modes

Two modes, and the distinction is what the run is allowed to look at.

| | **Regenerate** (default) | **Translate** |
|---|---|---|
| Agent sees | Invariant docs + new stack profile only | The above, plus the source implementation |
| Proves | The context layer captured the application | That an agent can port code |
| Likely outcome | Lower first-pass success; precise diagnostics | Higher first-pass success; weaker evidence |
| Use for | The proof, and for measuring context quality over time | Getting a real port done once the proof has been made |

> **Rule 2-12.** In regenerate mode the source implementation MUST NOT be
> readable from the transposition worktree. This is enforced by workspace
> construction — the worktree contains the context layer, the acceptance suite,
> and nothing else — not by instructing the agent to ignore it. An agent that can
> read the source will read the source, and the run's evidentiary value
> evaporates without any signal that it did.

> **Rule 2-13.** The mode MUST be recorded on every transposition run. A
> regenerate result and a translate result are not comparable, and a ledger that
> conflates them cannot answer whether context quality is improving.

Regenerate is the default because reliable regeneration is the thesis. Translate
exists because a failed proof should not also mean a failed port — when
regeneration falls short, translate mode finishes the job while the diff between
the two runs identifies exactly which documents were carrying less than they
appeared to.

### 2.7 The transposition procedure

```
 1. LINT --transposition        invariant/bound partition is clean,
                                every spec has stack-neutral criteria,
                                acceptance suite is frozen and reconciled
 2. Snapshot                    record acceptance suite results on source stack
 3. Set target                  registry: stack: go-1.24, mode: regenerate
 4. Construct worktree          context layer + acceptance suite only
                                (regenerate mode: source code excluded)
 5. CURATE                      supersede bound docs; invariant docs untouched
 6. Regenerate bound docs       ARCH, CONVENTIONS against new stack profile
                                (producers, informed by invariant docs)
 7. PLAN                        generate an implementation plan for the port
 8. Execute                     execution engine runs the plan, per-task
                                checkpointing, acceptance path read-only
 9. Gate                        run the acceptance suite unchanged
10. Verdict                     per spec: passed | failed | never exercised
11. Diff report                 per failing assertion, the spec that owns it
```

> **Rule 2-10.** Transposition MUST run in a separate git worktree or branch and
> MUST NOT modify the source stack's working tree. The source remains the
> reference implementation until the gate passes.

> **Rule 2-11.** The output of a transposition run MUST include a **coverage
> verdict**: for each invariant spec, whether its criteria passed, failed, or
> were never exercised. "Never exercised" is the most valuable result — it
> identifies specs that describe nothing testable.

---

## 3. Deployment model

Context Refinery is installed *beside* a project, not into it.

| Mode | Shape | Status |
|---|---|---|
| **Sidecar** | Standalone Next.js app on its own port, pointed at a working tree | **Foundational** — the reference mode for every stack |
| **CLI** | Headless runner, no UI | Required — CI, scripted sweeps, the LINT/CURATE gate |
| **Embedded** | Mounted at `/_refinery` inside a host Next.js app, dev-only | Optional convenience, Next.js hosts only |

> **Rule 3-1.** Sidecar is the foundational mode. Every feature MUST work in
> sidecar before it works anywhere else, and no feature may depend on the host
> application being Node, Next.js, or running at all.

This is the decision that keeps the target set open. The app is a development
tool that happens to be written in Next.js; it is not part of the application it
manages. Building embedded-first would silently accumulate assumptions about the
host — its module system, its dev server, its config — and every one of those
assumptions is a language Context Refinery could never target. Sidecar has no
such assumptions: it reads a directory and shells to a CLI, which is all it needs
for Go, Rust, Python, or anything else.

> **Rule 3-2.** All modes MUST share one implementation of the runner and one
> registry reader. The UI is a client of the same API the CLI calls.

> **Rule 3-3.** Embedded mode MUST be unreachable in a production build. It
> mounts only when `NODE_ENV !== 'production'` or an explicit opt-in flag is set,
> and the route MUST refuse to serve when neither holds.

### 3.1 Configuration portability

The registry, stack profiles, prompt templates, and skills are the portable
core. They are plain files with no executable content and no dependency on the
host language, which is what makes a template ecosystem possible: a starting
template is a `.refinery/` directory plus a skill or two, and adopting one is a
copy.

> **Rule 3-4.** Configuration MUST remain declarative and language-neutral. A
> stack profile MUST NOT contain executable code, and anything a profile needs to
> run MUST be expressed as a declared command the runner invokes. The moment a
> profile can execute, profiles stop being shareable and start being a supply
> chain problem.

> **Rule 3-5.** A starting template MUST be installable without the application —
> copy the directory, and the repo is conformant against the standard's Core set
> (§10 there). The app accelerates adoption; it is never the distribution
> mechanism (Rule 0-1).

### 3.2 Self-hosting

The application manages its own repository. This is the best available dogfood
and the most dangerous operation the app performs.

> **Rule 3-6.** When the target repository is the application's own repository,
> the app MUST operate through a separate worktree and MUST NOT hot-modify the
> running instance. Self-directed changes land as a branch for review.

---

## 4. Surfaces

### 4.1 Document browser (centerpiece)

A tree of **every document the registry says could exist**, not merely the ones
present. This inversion is the single most important UI decision in the product:
absence is information, and a browser that only lists files can never show you
what you are missing.

```
 docs/
 ├── context/
 │   ├── ● GLOSSARY.md          active · verified · 2d ago
 │   ├── ● CONVENTIONS.md       active · suspect ⚠ 3 commits
 │   ├── ○ CONSTRAINTS.md       template · never edited
 │   ├── ● SCHEMA.md            active · verified · 5h ago
 │   └── ● ARCH.md              active · unverified
 ├── specs/
 │   ├── ● publish-overlay      active · 1 open report
 │   └── ● voice-capture        active · verified
 ├── decisions/                 4 ADRs · 1 superseded
 └── plans/
     └── ◐ go-transposition     active · 3/11 tasks
```

Per-document state shown at a glance: status, authority, verification age,
suspect flag with the implicating commit count, open report count, stack scope.

**Required documents are always present.** Per your standard, a conformant repo
has `CONSTRAINTS.md` and `CONVENTIONS.md` even when empty.

> **Rule 4-1.** On init, the app MUST write template stubs for every document the
> registry marks required. A stub carries valid frontmatter, `status: template`,
> and body comments explaining what belongs there and why it matters.

> **Rule 4-2.** A `template` document MUST be visually distinct from an `active`
> one and MUST NOT be injected as context by the execution engine. An empty
> constraints file teaches an agent nothing; injecting it teaches it that
> constraints are empty.

Per-document actions, gated by authority per Rule A-1 of the standard:

| Action | Availability |
|---|---|
| View / edit (markdown + frontmatter form) | always |
| Publish / regenerate | when absent, template, or explicitly forced |
| Drift check | descriptive only |
| Conformance check | prescriptive only |
| Coverage check | T1/T2 only |
| Refresh from report | descriptive, open drift report exists |
| Amend from report | prescriptive, open violation report exists, confirmation required |
| Supersede | historical |
| Run agent on this document | any registered agent whose `applies-to` matches |
| History | provenance timeline → prompt, response, diff, commit |

The history view is where the ledger pays off: for any paragraph in any
document, you can reach the dictation that produced it and the commit it was
true about.

### 4.2 Agent console

Lists every configured agent with kind, doc-type, run mode, write scope, and
model. Each agent's prompt template is editable in place, with a diff against
the shipped default and a one-click revert.

> **Rule 4-3.** Agent prompt templates MUST be files in the repository, not
> database rows or app-internal constants. They are context, they are versioned,
> and they are reviewable in a pull request like anything else.

> **Rule 4-4.** The app MUST distinguish a shipped default template from a
> customized one and MUST NOT silently overwrite a customization on upgrade.
> Upgrades present a three-way merge.

### 4.3 Execution console

Free-form execution against selected context. This is the general-purpose
surface and deliberately unconstrained in what it can be asked to do.

```
┌ Context ─────────────────────────────────────────────┐
│ ☑ AGENTS  ☑ CONSTRAINTS  ☑ CONVENTIONS               │
│ ☑ publish-overlay-SPEC   ☐ ARCH                      │
│ selection: 6 docs · ~18.4k tokens                    │
├ Instruction ─────────────────────────────────────────┤
│ [ voice ▸ ]  or type…                                │
│ "run the security agent on this spec and tighten     │
│  the auth section before we plan it"                 │
├ Mode ────────────────────────────────────────────────┤
│ ◉ build   ○ read-only        provider: claude ▾      │
└──────────────────────────────────────────────────────┘
```

Three execution shapes, one engine (§6):

- **Ad hoc** — instruction plus selected context. Anything.
- **Plan execution** — a `plan` document as the instruction source; the engine
  works its task list.
- **Agent invocation** — a named agent applied to a named document, the
  structured case.

### 4.4 Run ledger

Chronological list of runs with author, scope, cost, outcome, artifacts, and
`implicates`. Filterable by document — "every run that consumed `CONSTRAINTS`" —
which is how you discover that a document nothing loads is costing you audits.

Because the ledger is author-partitioned (Rule L-1 of the standard), it is also a
contribution view. Useful cuts:

| View | Answers |
|---|---|
| By author | Who has been shaping which parts of the context layer |
| By document, across authors | Every prompt that ever read or wrote this file, and who sent it |
| Provenance graph | Prompt → documents read → documents written → code touched |
| Unattributed | Runs by `author-kind: automation` — sweeps, CI, scheduled audits |

> **Rule 4-6.** Author attribution is descriptive, never evaluative. The ledger
> MUST NOT rank, score, or leaderboard authors. It records what happened so the
> team can find the reasoning behind a document; the moment it becomes a
> productivity metric, people stop dictating honestly and the record degrades.

### 4.5 Voice capture

The dictation workflow from `voicecode`, ported. Available anywhere the app
accepts an instruction: execution console, document editor, report triage.

> **Rule 4-5.** Voice is an input method, not a mode. Every action reachable by
> voice MUST be reachable by typing, and the run record MUST NOT distinguish
> them except in the `refined` / `refine-cycles` metadata.

---

## 5. Agent configuration

### 5.1 Layering

```
packaged defaults        shipped with the app
        ↓ overridden by
org baseline             registry `extends:` — the shareable org standard
        ↓ overridden by
repo registry            .refinery/registry.yaml
        ↓ overridden by
stack profile            .refinery/stacks/<id>.yaml — prompt fragments
        ↓ overridden by
local                    .refinery/local.yaml, gitignored, per-developer
```

> **Rule 5-1.** Resolution MUST be deterministic and inspectable. The agent
> console MUST show, for any agent, the effective configuration and which layer
> each field came from.

The registry file format, including `extends` semantics and the deferral of
remote references, is the standard's (§8, Rules G-1..G-3). This document
specifies only the resolution order above and its presentation.

### 5.2 Prompt template composition

A template is assembled from parts so that customization does not mean forking
the whole prompt:

```
[ role preamble        ] ← packaged, rarely customized
[ standard rules       ] ← generated from the registry, never hand-edited
[ stack fragment       ] ← from the active stack profile
[ document contract    ] ← required sections for this doc type
[ org/repo customization] ← where teams actually edit
[ output contract      ] ← packaged; frontmatter and provenance requirements
```

> **Rule 5-2.** The output contract section MUST NOT be customizable. It is what
> guarantees the agent emits valid frontmatter and appends provenance; making it
> editable makes conformance optional.

### 5.3 Provider abstraction

Agents are provider-agnostic. The runner shells to a CLI.

```yaml
providers:
  claude:
    command: claude
    build-mode: ["-p", "{prompt}", "--permission-mode", "acceptEdits"]
    read-only: ["-p", "{prompt}", "--permission-mode", "plan"]
  antigravity:
    command: antigravity
    build-mode: ["run", "--prompt", "{prompt}"]
    read-only: ["run", "--prompt", "{prompt}", "--dry-run"]
```

> **Rule 5-3.** Mode is a provider-level contract, not a prompt instruction.
> Read-only MUST be enforced by the provider invocation. An auditor asked
> politely not to write will eventually write.

### 5.4 Capability model — agents, skills, subagents

The provider harnesses already supply file reading, editing, search, shell, and
git, plus two extension mechanisms: **skills** (packaged knowledge the model
loads when it judges them relevant) and **subagents** (isolated context windows
with restricted tool allowlists). Context Refinery uses all three, and the
allocation matters.

| Mechanism | Owns | Triggering | Used for |
|---|---|---|---|
| **Refinery agent** | Identity, authority, write scope, output contract | **Deterministic** — host invokes | RECONCILE, SPEC, REFRESH — every registry agent |
| **Skill** | Reusable knowledge | Model-judged, or host-pinned | Stack idioms, review heuristics, house style |
| **Subagent** | Isolation and tool restriction | Host selects per agent | Enforcing read-only auditors; keeping long audits out of the main window |

> **Rule 5-4.** A refinery agent MUST NOT be implemented as a skill. Skills are
> model-triggered, and the framework's guarantees depend on invocation being
> certain: when a user asks for a drift check, RECONCILE runs — not probably
> runs. A probabilistically-triggered auditor cannot be gated in CI and cannot be
> audited afterward, because "it didn't fire" and "it fired and found nothing"
> are indistinguishable in the ledger.

> **Rule 5-5.** Auditors SHOULD execute as subagents with an allowlist that
> excludes edit tools. An auditor with no edit tool cannot write regardless of
> what its prompt says. This is stronger than Rule 5-3 and complements it —
> permission mode is the contract, tool restriction is the mechanism.

> **Rule 5-6.** The runner MUST NOT implement capabilities the provider harness
> already supplies. Its job is to assemble context, constrain the workspace,
> invoke, and record. Every file or shell tool reimplemented in the runner is one
> the harness already ships and maintains better.

### 5.5 Skills as the extension surface

Skills are how third parties extend Context Refinery, and stack profiles are the
first and most important case. The knowledge in a stack profile — idiomatic Go
with chi and sqlc, how this shop lays out packages, what never to do — is
exactly skill-shaped: reusable, self-describing, progressively disclosed, and
valuable to someone who never installs this application.

> **Rule 5-7.** A stack profile SHOULD carry its idiom knowledge as a skill
> reference rather than inline prompt text. "Add Rust support" then means
> "contribute a skill," and the contribution has standalone value.

```yaml
# .refinery/stacks/go-1.24.yaml  (excerpt)
skills:
  - id: go-idioms
    path: .refinery/skills/go-idioms/SKILL.md
    pin: always            # always | agents: [...] | discover
  - id: sqlc-patterns
    path: .refinery/skills/sqlc-patterns/SKILL.md
    pin: agents: [ARCH, PLAN]
```

Review heuristics follow the same pattern — a security-review skill, an
accessibility skill, a house-style skill — invoked by an agent or a chain step
that pins them.

### 5.6 Skill provenance

Skills are context. A skill the harness loads mid-run that appears nowhere in
the run record makes the ledger untrue, and the reproducibility claim that the
entire provenance layer rests on quietly stops holding. This is the shared-session
hole of Rule X-3 in a different costume, and it gets the same treatment.

> **Rule 5-8.** Nothing enters an agent's context without appearing in that run's
> record. For any run, `skills` MUST list every skill that contributed, with its
> id, version or content digest, and how it was introduced
> (`pinned` | `discovered`).

Two mechanisms, both required:

**Pinned (structured runs).** For registry agents and chain steps, the host
resolves the skill list from the registry and stack profile, reads each
`SKILL.md`, injects it, and records it. Loading is deterministic and the record
is written before the run starts.

**Discovered (free-form runs).** Where model-judged skill selection is desirable
— ad hoc execution — the host parses the provider transcript for skill
activations and appends them to the run record post-hoc.

> **Rule 5-9.** A run whose skill activations cannot be recovered from the
> provider transcript MUST record `skills: unknown` rather than an empty list. An
> empty list asserts that no skill loaded; silence about it is the honest answer
> when the harness does not report.

> **Rule 5-10.** Adding, removing, or modifying a skill is a context change and
> MUST be versioned in the repository alongside the documents. A skill edited
> outside version control makes every prior run in the ledger unreproducible.

### 5.7 Default actions

Each document type declares the action the browser preselects when the document
is opened, via the registry's `default-action` field. This is registry data, not
application logic.

```yaml
types:
  - id: plan
    default-action: execute
  - id: spec
    default-action: plan
  - id: drift-report
    default-action: repair
  - id: constraints
    default-action: conformance
```

A `template` document always defaults to `publish`, whatever its type says.

> **Rule 5-11.** A default action MUST be preselected, never auto-executed.
> Clicking a plan resolves the context, shows the estimated cost and the
> instruction that will be sent, and waits for confirmation. An interface that
> starts writing code on a single click is delightful twice and alarming
> thereafter.

> **Rule 5-12.** The preselected action is subject to the same authority
> eligibility as any other (Rule A-1). A default action a document's authority
> forbids MUST NOT be offered.

---

## 6. Execution engine

One engine serves all three shapes in §4.3.

### 6.1 Run pipeline

```
resolve context → resolve skills → assemble prompt → preflight → invoke →
  watch → collect → recover discovered skills → enforce write scope →
  stamp provenance → compute implicates → write run record → present diff
```

**Resolve context** applies the selection policy from the standard (§6.1 there):
declared, then derived closure, then code-ref matched. Never blanket.

**Preflight** is deterministic and free: registry valid, target document exists
and is in an eligible state, agent authority matches document authority,
required context resolvable, working tree clean or explicitly overridden,
estimated context within budget.

> **Rule 6-1.** Preflight MUST fail closed. A run that cannot be recorded
> correctly MUST NOT start. The alternative — a successful change with no
> lineage — is worse than no change.

**Enforce write scope** diffs the working tree after the run against the agent's
declared `write-scope`. Out-of-scope writes fail the run per Rule S-3.

> **Rule 6-2.** A scope violation MUST surface the offending paths and offer to
> revert them. It MUST NOT be silently accepted because the model's output looked
> reasonable.

**Compute implicates** matches `code-touched` against every document's
`code-refs` and marks matches suspect, per Rule X-4. This is the step that makes
the system self-maintaining: nobody has to remember that changing the auth
module invalidated the architecture document.

### 6.2 Plan execution

A plan is a task list. The engine works it one task at a time, with a
verification step between tasks.

> **Rule 6-3.** Plan execution MUST checkpoint per task — a commit or a stash —
> so a failing task can be retried or abandoned without discarding preceding
> work. A long plan executed as one opaque run is unreviewable and unrecoverable.

> **Rule 6-4.** Task state MUST be written back to the plan document, so a plan
> interrupted at task 7 of 20 resumes from the document rather than from app
> state. The repository is the database.

### 6.3 Agent chaining

The ad hoc example — "run the security agent on this spec and tighten the auth
section" — is an agent invocation the engine can issue as a step. Agents may be
composed into named chains in the registry:

```yaml
chains:
  spec-hardening:
    - agent: SECURITY-REVIEW
      on: "{target}"
    - agent: CONFORMANCE
      on: "{target}"
    - gate: no-major-violations
```

> **Rule 6-5.** A chain step MUST NOT consume the previous step's provider
> session. Each step resolves its own context and writes its own run record; the
> connection between steps is the artifact on disk, not a conversation. This is
> Rule X-3 of the standard applied to composition, and it is what keeps chained
> runs reproducible.

---

## 7. Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Next.js (App Router) · React · Tailwind                 │
│  browser · console · ledger · voice                      │
└───────────────┬──────────────────────────────────────────┘
                │  REST + SSE
┌───────────────▼──────────────────────────────────────────┐
│  Route handlers (server-only)                            │
│   /api/docs  /api/agents  /api/runs  /api/registry        │
└───────────────┬──────────────────────────────────────────┘
┌───────────────▼──────────────────────────────────────────┐
│  lib/refinery — shared core, also used by the CLI        │
│   registry · frontmatter · graph · selector · runner ·   │
│   scope-enforcer · provenance · implicator · lint        │
└───────────────┬──────────────────────────────────────────┘
       ┌────────┴────────┬──────────────┐
       ▼                 ▼              ▼
  filesystem          git          provider CLIs
  (docs, prompts)  (commits,      (claude,
                    worktrees)     antigravity)
```

> **Rule 7-1.** There is no database. Documents are markdown, configuration is
> YAML, the ledger is files, and history is git. Any state the app needs that
> cannot live in the repository is a design error, because it cannot be
> reviewed, shared, or rolled back with the code it describes.

> **Rule 7-2.** `lib/refinery` MUST have no Next.js or React imports. The CLI
> and CI gate depend on it; coupling it to the UI framework would break sidecar
> and headless modes and would make the app a runtime dependency in violation of
> Rule 0-1.

### 7.1 API surface

| Route | Purpose |
|---|---|
| `GET /api/registry` | Resolved registry, with layer attribution |
| `GET /api/docs` | Expected-vs-present tree with computed state |
| `GET /api/docs/:id` | Content, frontmatter, provenance, reports |
| `PUT /api/docs/:id` | Human edit; stamps `last-human-edit` |
| `GET /api/docs/:id/actions` | Eligible actions for this document's authority |
| `POST /api/runs` | Start a run; returns run id |
| `GET /api/runs/:id/stream` | SSE — output, progress, diff |
| `POST /api/runs/:id/cancel` | Kill the provider process |
| `GET /api/runs` | Ledger, filterable |
| `POST /api/lint` | Deterministic validation; no model |
| `POST /api/sweep` | Stage-1 suspicion pass over the repo |
| `POST /api/transpose` | Start a transposition into a worktree |

> **Rule 7-3.** Every mutating route MUST be idempotent under retry or MUST
> return a conflict. A dropped SSE connection is routine, and a UI reconnect
> must never start a second run.

---

## 8. Permissions and safety

The app runs agent CLIs with write access to a repository, and in self-hosting
mode that repository is its own. That deserves real constraints.

> **Rule 8-1.** The app MUST NOT be exposed on a public interface. Bind to
> loopback by default; any other bind requires explicit configuration and
> authentication.

> **Rule 8-2.** Write scope is enforced post-hoc by diffing the working tree
> (§6.1), not by trusting the provider's own permission flags. Provider flags are
> defense in depth, not the control.

> **Rule 8-3.** Destructive operations — amend a prescriptive document, execute a
> plan, transpose, operate on the app's own repo — MUST require explicit
> confirmation and MUST state what will be written before it is.

> **Rule 8-4.** The app MUST refuse to start a build-mode run on a dirty working
> tree unless explicitly overridden, so that every run's diff is attributable.

> **Rule 8-5.** Secrets MUST NOT be injectable as context. The selector operates
> on registry-declared document paths only; `.env` and credential files are never
> selectable, and the app MUST refuse a `code-refs` glob that would match them.

---

## 9. Milestones

**M0 — Standard is checkable.** `lib/refinery` with registry reader, frontmatter
parser, graph builder, and `LINT` — errors for the standard's Core set (§10
there), warnings for everything else. CLI only, no UI, no model calls. Run it
against `voicecode-bbs` and produce an honest conformance report. Everything
downstream depends on this being right, and none of it costs a token.

**M1 — Browser and producers.** Document tree with expected-vs-present, template
stubs on init, the 10 producers, run ledger, provenance stamping, pinned skill
resolution and recording. Skill accounting belongs here rather than later: every
run recorded before it exists is a run with an incomplete ledger, and those runs
cannot be retrofitted.

**M2 — Maintenance loop.** `code-refs`, Stage-1 sweep, the four auditors, report
lifecycle, two repairers, `CURATE`. The loop from the standard closes. Add the
CI gate here — a stale-doc merge block is what makes the discipline stick, and
it is the one convention the prior art is unanimous about.

**M3 — Execution engine.** Ad hoc runs, plan execution with per-task
checkpointing, agent chaining, write-scope enforcement, `implicates` computation.

**M3.5 — Acceptance suite.** The generator agent, `LINT --criteria`, and the
reconciliation workflow. Produce a frozen suite for the demo app on the Next.js
stack and confirm it passes against the running system. This is a milestone
rather than a step inside M4 because reconciliation is hand work that cannot be
rushed, and because `LINT --criteria` pays for itself on every spec whether or
not a port follows.

**M4 — Transposition.** Stack profiles, `stack-scope` partitioning,
transposition lint, worktree construction with source exclusion, both modes,
coverage verdict. **Demo: port a non-trivial Next.js app to Go in regenerate
mode and pass its frozen acceptance suite unchanged.**

**M5 — Voice.** Port the dictation and refine loop from `voicecode`.

Voice comes last deliberately. It is the feature you already know how to build
and the one with the least bearing on whether the thesis holds. If M4 works, the
project is proven; if it doesn't, voice would not have saved it.

### 9.1 The M4 target application

Choose the demo app carefully. It should be small enough to port in a day and
rich enough that porting it is not trivial: persistence, auth, a background job,
at least one third-party integration, and a UI with real state. A to-do app
proves nothing. Something like a link-sharing service with accounts, a feed, and
a scheduled digest email is about right.

---

## 10. Open questions

1. ~~**Does transposition regenerate or translate?**~~ **Resolved** — both, as
   explicit modes (§2.6). Regenerate is the default and the one the project
   exists to validate; translate is the fallback that finishes a port when the
   proof falls short. Enforcement is by workspace construction, not instruction.

2. ~~**Where do acceptance tests come from?**~~ **Resolved** — agent-generated
   from the specs, reconciled by hand against the running source application,
   then frozen and read-only during transposition (§2.3). The reconciliation step
   is what breaks the circularity; the freeze is what stops an agent from
   weakening assertions to reach green.

3. ~~**Embedded mode in non-Node stacks.**~~ **Resolved** — sidecar is the
   foundational mode for every stack (§3), embedded is an optional Next.js-only
   convenience. Configuration stays declarative and language-neutral so that
   stack profiles and starting templates are portable artifacts (Rules 3-4, 3-5).

4. **How much does a full sweep cost on a large repo?** Open — and deliberately
   not designed for yet. Stage 2 on a repo with 40 documents after a large merge
   could mean dozens of audit runs, but the right policy (severity thresholds,
   commit-range batching, a daily cap) cannot be chosen without data. **Decision
   for now: instrument, don't throttle.** Rule C-6 of the standard requires
   capturing token counts, cached tokens, reported cost, and the rate table on
   every run from M1 onward. Revisit once there are a few hundred runs to
   analyze. A budget policy chosen today would be a guess wearing a rule number.

5. ~~**Is `stack-scope` per-document or per-section?**~~ **Resolved** —
   per-document (Rule 2-2). Documents carrying both invariant and bound content
   are split before a port; `mixed` is a transitional state that blocks
   transposition rather than a supported configuration.

6. ~~**Multi-repo.**~~ **Resolved in schema, deferred in function** — `extends`
   is a list of references that may be local or remote (Rule G-3). v1 resolves
   local references only and fails remote ones with an explicit unsupported-scheme
   error. The distribution and versioning mechanism for an org baseline remains
   genuinely open; the schema no longer forecloses it.

7. ~~**Does the run ledger get committed?**~~ **Resolved** — yes (Rule R-4), and
   author-partitioned (§2.1 of the standard). Runs are identified by the
   composite id `<author>/<sequence>`, which keeps sequences collision-free
   across concurrent branches and makes the ledger a team contribution view
   (§4.4). `CURATE` rolls old runs into dated summaries to bound history growth.

   Still open underneath this: whether a shared sequence should exist *alongside*
   the per-author one for stable cross-team ordering, and how to handle a handle
   change — Rule L-2 makes the frontmatter authoritative so files can relocate,
   but the migration path is unspecified.
