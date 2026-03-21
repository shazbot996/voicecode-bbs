"""Architecture document publishing agent."""

from voicecode.publish.base import PublishAgent


class ArchAgent(PublishAgent):
    doc_type = "ARCH"

    prompt_template = """\
You are a senior software architect producing an architecture document (ARCH.md).

## Your task

Analyze the codebase at the scope described below, then produce a comprehensive \
architecture document in Markdown. The document should give a reader — whether a \
new team member, an AI agent, or a future maintainer — a clear mental model of \
how this system is structured, why it is structured that way, and how data and \
control flow through it.

## Scope

{scope}

## Destination

The output will be saved to `docs/{dest_folder}ARCH.md`.

## Document structure

Produce the following sections. Omit any section that genuinely does not apply, \
but err on the side of including rather than skipping.

### 1. Overview
- One-paragraph summary of what this system/component does and its primary \
purpose.
- Key design philosophy or architectural style (e.g. event-driven, layered, \
microservices, monolith, pipes-and-filters).

### 2. High-Level Architecture
- Describe the major components/modules and their responsibilities.
- Explain how they relate to each other (dependencies, communication patterns).
- If there are clear layers (e.g. UI → business logic → data), describe them.

### 3. Component Deep-Dive
For each significant component or module:
- **Purpose**: what it does and why it exists
- **Key classes/functions**: the important entry points and their roles
- **Internal structure**: how it is organized internally
- **Dependencies**: what it depends on and what depends on it

### 4. Data Flow
- Describe the primary data flows through the system.
- Cover the happy path for the most important operations.
- Include any important transformations, validations, or side effects.

### 5. Control Flow & Lifecycle
- Application startup and initialization sequence.
- Main event loop or request handling cycle.
- Shutdown and cleanup.
- Background processes, threads, or async patterns.

### 6. State Management
- Where state lives (in-memory, files, databases, external services).
- How state is shared between components.
- Thread safety and concurrency patterns if applicable.

### 7. External Interfaces
- APIs, CLI interfaces, file formats, network protocols.
- Integration points with external systems or services.
- Configuration and environment dependencies.

### 8. Key Design Decisions
- Important architectural choices and the trade-offs behind them.
- Patterns used and why (e.g. observer, strategy, dependency injection).
- Known limitations or technical debt.

### 9. Extension Points
- How to add new features or components.
- Plugin or provider patterns.
- What would need to change for common modifications.

## Guidelines

- **Read the actual code.** Do not guess or hallucinate. Use your tools to \
explore files, grep for patterns, and read implementations.
- **Be specific.** Reference actual file paths, class names, and function names.
- **Use diagrams sparingly** — prefer clear prose with code references. If you \
do include a diagram, use Mermaid syntax.
- **Keep it maintainable.** Write at the right level of abstraction — enough \
detail to be useful, not so much that it goes stale immediately.
- **Focus on "why" not just "what".** The code already shows what; the \
architecture doc should explain why things are structured this way.
- Write the document as a single Markdown file. Use `##` for top-level sections \
and `###` for subsections.
- Start the document with a YAML frontmatter block containing title, scope, and \
date.
"""
