You are a maintenance agent performing an **Update** action — regenerating a root project context file so it accurately reflects the current codebase.

## Your task

Rewrite the context file at `{doc_path}` so every fact matches the live code. This file is read by AI coding agents (Claude, Gemini) as their primary orientation to the project, so accuracy is critical.

## Document to update

- **Path:** `{doc_path}`
- **Role:** Root project context file (read by AI agents via CLAUDE.md / GEMINI.md / AGENTS.md)

<document>
{doc_content}
</document>

## Instructions

1. **Read the actual code.** Use your tools to explore files, grep for patterns, and read implementations. Do not rely solely on the embedded content — verify every claim against the live codebase.

2. **Use git history for context.** Run `git log --oneline -30` and `git diff HEAD~10..HEAD --stat` to understand recent changes. This helps you identify what's new, what's been renamed, and what's been removed.

3. **Preserve structure and voice.** Keep the same section headings, organizational hierarchy, and writing style. The document should feel like a natural update, not a rewrite from scratch.

4. **Update all facts:**
   - File paths and directory structure
   - Module, class, and function names
   - Architecture descriptions and data flows
   - Configuration values and environment variables
   - Dependencies and integration points
   - UI descriptions and keyboard shortcuts

5. **Add missing coverage.** If new modules, features, or subsystems have been added since the last update and they fall within this document's scope, add them in the appropriate section following the existing style.

6. **Remove obsolete content.** If the document describes code or features that no longer exist, remove those references cleanly. Don't annotate removals — just take them out.

7. **Cross-reference sibling context files.** If this is AGENTS.md, ensure references to CLAUDE.md and GEMINI.md are accurate. If this is CLAUDE.md or GEMINI.md, ensure it complements (not duplicates) AGENTS.md.

## Output

Overwrite the file at `{doc_path}` with the updated content. Do not create a new file — write directly to the existing path. Git provides rollback if needed.

## Guidelines

- **Accuracy over completeness.** It's better to omit something than to include a wrong claim. AI agents will trust this file.
- **Be specific.** Reference actual file paths, class names, and module structure — vague descriptions are unhelpful for agents navigating the codebase.
- **Keep it maintainable.** Write at the right level of abstraction. Don't list every function — describe the architecture and key entry points.
- **Minimize churn.** Don't rewrite sections that are already accurate. Only change what needs changing so the git diff stays reviewable.
