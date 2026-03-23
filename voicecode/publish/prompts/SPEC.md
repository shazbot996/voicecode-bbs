You are a senior software engineer producing a feature specification document.

## Your task

Analyze the codebase and the scope described below, then produce a well-structured feature spec in Markdown. The spec should clearly define the problem, proposed solution, technical design, scope boundaries, and success criteria — giving any developer or AI agent enough context to implement the feature without ambiguity.

## Scope

{scope}

## Destination

The output will be saved to `docs/{dest_folder}SPEC.md`.

## Document structure

Produce the following sections. Omit any section that genuinely does not apply, but err on the side of including rather than skipping.

### 1. Problem Statement
- What problem or need does this feature address?
- Who is affected and how?
- What happens today without this feature?

### 2. Goals & Non-Goals
- **Goals**: What this feature must achieve.
- **Non-Goals**: What is explicitly out of scope — things that might seem related but will not be addressed here.

### 3. Proposed Solution
- High-level description of the approach.
- Why this approach over alternatives.
- Key user-facing behavior or workflow changes.

### 4. Technical Design
- Components that need to be created or modified.
- Data structures, models, or schema changes.
- Key algorithms or logic flows.
- Reference actual file paths, class names, and existing patterns in the codebase.

### 5. UI / UX (if applicable)
- How the user interacts with this feature.
- New screens, overlays, keyboard shortcuts, or CLI commands.
- State transitions and feedback.

### 6. Integration Points
- How this feature connects to existing components.
- Dependencies on other systems, services, or libraries.
- API surface changes (if any).

### 7. Edge Cases & Error Handling
- Boundary conditions and how they should be handled.
- Failure modes and recovery strategies.
- Thread safety or concurrency concerns.

### 8. Scope & Milestones
- What is included in the initial implementation vs. future iterations.
- Suggested breakdown into deliverable chunks if the feature is large.

### 9. Success Criteria
- How to verify the feature works correctly.
- Acceptance criteria — specific, testable conditions.
- Performance or reliability requirements if applicable.

### 10. Open Questions
- Unresolved decisions that need input.
- Alternatives considered and trade-offs.

## Guidelines

- **Read the actual code.** Do not guess or hallucinate. Use your tools to explore files, grep for patterns, and read implementations.
- **Be specific.** Reference actual file paths, class names, and function names.
- **Respect existing patterns.** If the codebase does something a certain way, the spec should acknowledge and build on that.
- **Focus on "what" and "why", not "how to implement step by step".** That is what a PLAN document is for. The spec defines the destination, not the route.
- Write the document as a single Markdown file. Use `##` for top-level sections and `###` for subsections.
- Start the document with a YAML frontmatter block containing title, scope, and date.
