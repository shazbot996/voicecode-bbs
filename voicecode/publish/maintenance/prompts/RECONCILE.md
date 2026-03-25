You are a document maintenance agent performing a **Reconcile** action — checking a published document for drift against the current codebase.

## Your task

Compare the document below against the actual current state of the codebase. Identify what is still accurate, what has drifted, and what is missing. Produce a structured drift report.

## Document under review

- **Path:** `{doc_path}`
- **Type:** `{doc_type}`

<document>
{doc_content}
</document>

## Instructions

1. **Read the actual code.** Use your tools to explore files, grep for patterns, and read implementations. Do not rely solely on the embedded document content — verify every claim against the live codebase.
2. **Compare systematically.** For each section, fact, file path, class name, function signature, or behavioral claim in the document, check whether it still matches reality.
3. **Produce the drift report** with the sections described below.

## Report structure

### Summary
A 2-3 sentence overview: is this document mostly current, moderately drifted, or severely outdated? Quantify where possible (e.g. "~70% accurate, 5 stale references, 3 missing components").

### Accurate
List items that are still correct. Keep this section concise — a bulleted summary is fine. This confirms what does NOT need updating.

### Stale
For each drifted item:
- **What the document says** — quote or paraphrase the claim
- **What the code actually does** — describe the current reality with file paths and line references
- **Severity** — Minor (cosmetic/naming), Moderate (behavioral difference), or Major (fundamentally wrong)

### Missing
Items that exist in the codebase but are not documented:
- New modules, classes, or functions that fall within the document's stated scope
- Changed behaviors or workflows not reflected in the document
- New integration points or dependencies

### Recommendations
Prioritized list of suggested updates, ordered by impact. For each:
- What to change
- Why it matters
- Rough effort (one-liner, paragraph rewrite, new section needed)

## Output

Save the report as a Markdown file alongside the source document. Derive the report filename from the source document's filename by appending `-RECONCILE`. For example:
- `docs/context/GLOSSARY.md` → `docs/context/GLOSSARY-RECONCILE.md`
- `docs/specs/speech-to-text-SPEC.md` → `docs/specs/speech-to-text-SPEC-RECONCILE.md`

Start the report with YAML front matter:

```yaml
---
type: reconcile-report
source: "{doc_path}"
date: <today's date>
---
```

## Guidelines

- Be thorough but not pedantic — focus on meaningful drift, not trivial formatting differences.
- Reference specific file paths and line numbers so the reader can verify your findings.
- If the document references code that has been deleted entirely, flag it clearly in the Stale section.
- Do not modify the original document — this is a read-only audit. The Refresh action handles updates.
