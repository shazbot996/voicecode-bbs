"""Claude Code built-in tool definitions for the Tools browser tab."""

# Each tool entry has:
#   name        — display name in the browser list
#   category    — grouping label (Files, Search, Execution, AI)
#   summary     — one-line description shown in list
#   detail      — multi-line reference card shown in the detail viewer

TOOL_LIBRARY: list[dict] = [
    # ── Files ──────────────────────────────────────────────────
    {
        "name": "Read",
        "category": "Files",
        "summary": "Read file contents by path",
        "detail": """\
# Read — Read file contents

Reads a file and returns its contents with line numbers.

## Parameters
  file_path    (required) Absolute path to the file
  offset       (optional) Line number to start from
  limit        (optional) Max lines to return

## Prompt syntax

  Read the file src/main.py

  Read lines 50-100 of src/main.py

  Show me the first 20 lines of config.yaml

## Notes
- Works with text, images, PDFs, and Jupyter notebooks
- For large files, specify offset/limit to read a section
- PDF files support a pages parameter (e.g. pages 1-5)
""",
    },
    {
        "name": "Edit",
        "category": "Files",
        "summary": "Replace exact strings in a file",
        "detail": """\
# Edit — Replace text in a file

Performs exact string replacement in a file. The old string
must appear exactly once (unless replacing all occurrences).

## Parameters
  file_path    (required) Absolute path to the file
  old_string   (required) Exact text to find
  new_string   (required) Replacement text
  replace_all  (optional) Replace every occurrence

## Prompt syntax

  In src/app.py, rename the variable old_name to new_name

  Replace "TODO: fix this" with the actual implementation
  in utils/helpers.py

  Change all occurrences of 'http://' to 'https://' in config.py

## Notes
- The file must be read first before editing
- Whitespace and indentation must match exactly
- If old_string is not unique, provide more surrounding context
""",
    },
    {
        "name": "Write",
        "category": "Files",
        "summary": "Create or overwrite a file",
        "detail": """\
# Write — Create or overwrite a file

Writes content to a file, creating it if needed or
overwriting existing content.

## Parameters
  file_path    (required) Absolute path to write
  content      (required) The full file content

## Prompt syntax

  Create a new file src/utils/logger.py with a Logger class
  that supports debug, info, warn, and error levels

  Write a .gitignore that excludes node_modules, .env,
  and build artifacts

## Notes
- Prefer Edit for modifying existing files (sends only the diff)
- Use Write for new files or complete rewrites
- Existing files must be Read first
""",
    },
    # ── Search ─────────────────────────────────────────────────
    {
        "name": "Grep",
        "category": "Search",
        "summary": "Search file contents with regex",
        "detail": """\
# Grep — Search file contents

Searches file contents using regex patterns. Built on ripgrep.

## Parameters
  pattern      (required) Regex pattern to search for
  path         (optional) Directory or file to search in
  glob         (optional) File pattern filter (e.g. "*.py")
  type         (optional) File type (e.g. "py", "js", "rust")
  output_mode  (optional) "content", "files_with_matches", "count"
  -A / -B / -C (optional) Context lines after/before/around
  -i           (optional) Case insensitive

## Prompt syntax

  Search for all uses of "database_url" in the project

  Find all TODO comments in Python files

  Search for the function definition of process_data
  with 3 lines of context

  Find all files that import the requests library

## Notes
- Default output is file paths only (files_with_matches)
- Use output_mode "content" to see matching lines
- Supports full regex: "log.*Error", "def\\s+\\w+"
""",
    },
    {
        "name": "Glob",
        "category": "Search",
        "summary": "Find files by name pattern",
        "detail": """\
# Glob — Find files by name pattern

Fast file pattern matching across the codebase.
Returns paths sorted by modification time.

## Parameters
  pattern      (required) Glob pattern (e.g. "**/*.py")
  path         (optional) Directory to search in

## Prompt syntax

  Find all Python files in the src directory

  List all test files matching test_*.py

  Find all TypeScript components: src/components/**/*.tsx

  Show me all YAML config files in the project

## Notes
- Supports standard glob: *, **, ?, [abc]
- Results sorted by modification time (newest first)
- Use for finding files; use Grep for searching contents
""",
    },
    # ── Execution ──────────────────────────────────────────────
    {
        "name": "Bash",
        "category": "Execution",
        "summary": "Run shell commands",
        "detail": """\
# Bash — Execute shell commands

Runs a bash command and returns stdout/stderr.
Working directory persists between calls.

## Parameters
  command      (required) The shell command to run
  timeout      (optional) Timeout in ms (max 600000)

## Prompt syntax

  Run the test suite with pytest

  Install the requests package with pip

  Run git log --oneline -10 to show recent commits

  Build the project with make and show any errors

  Start the dev server on port 3000

## Notes
- Working directory persists across calls
- Default timeout is 120 seconds (max 10 minutes)
- Use for system commands that need shell execution
- Prefer dedicated tools (Read, Grep, Glob) when available
""",
    },
    {
        "name": "NotebookEdit",
        "category": "Execution",
        "summary": "Edit Jupyter notebook cells",
        "detail": """\
# NotebookEdit — Edit Jupyter notebook cells

Modify cells in .ipynb Jupyter notebook files.

## Parameters
  notebook_path  (required) Path to the .ipynb file
  cell_number    (required) Which cell to edit (0-indexed)
  new_source     (required) New cell content
  cell_type      (optional) "code" or "markdown"

## Prompt syntax

  In analysis.ipynb, update cell 3 to use pandas
  instead of raw CSV parsing

  Add a markdown header cell at position 0 in the notebook

## Notes
- Cell numbers are 0-indexed
- Can change both content and cell type
- Read the notebook first to see current cell contents
""",
    },
    # ── AI & Agents ────────────────────────────────────────────
    {
        "name": "Agent",
        "category": "AI",
        "summary": "Launch a sub-agent for complex tasks",
        "detail": """\
# Agent — Launch a specialized sub-agent

Spawns an autonomous sub-agent to handle complex,
multi-step tasks. Sub-agents have their own context
and tool access.

## Parameters
  prompt         (required) Task description for the agent
  description    (required) Short 3-5 word summary
  subagent_type  (optional) "Explore", "Plan", or default
  model          (optional) "sonnet", "opus", "haiku"

## Prompt syntax

  Use a sub-agent to explore the codebase and find all
  API endpoint definitions

  Launch an Explore agent to understand how authentication
  works in this project

  Use a Plan agent to design an implementation strategy
  for adding WebSocket support

## Notes
- Explore agents are fast for codebase research
- Plan agents design implementation strategies
- Sub-agents run independently and return results
- Use for parallelizing research or protecting context
""",
    },
    # ── Web ────────────────────────────────────────────────────
    {
        "name": "WebSearch",
        "category": "Web",
        "summary": "Search the web for information",
        "detail": """\
# WebSearch — Search the web

Performs a web search and returns results.

## Prompt syntax

  Search the web for the latest Python 3.13 release notes

  Look up the documentation for the asyncio.TaskGroup API

  Find examples of implementing OAuth2 with FastAPI

## Notes
- Useful for finding documentation and examples
- Results include titles, URLs, and snippets
- Follow up with WebFetch to read specific pages
""",
    },
    {
        "name": "WebFetch",
        "category": "Web",
        "summary": "Fetch and read a web page",
        "detail": """\
# WebFetch — Fetch a web page

Downloads and reads the content of a specific URL.

## Parameters
  url          (required) The URL to fetch

## Prompt syntax

  Fetch the contents of https://docs.python.org/3/library/asyncio.html

  Read this page and summarize the API:
  https://example.com/api/docs

## Notes
- Returns page content as text
- Works with documentation, API references, etc.
- Use WebSearch first to find relevant URLs
""",
    },
    # ── MCP Tools ──────────────────────────────────────────────
    {
        "name": "MCP Tools",
        "category": "MCP",
        "summary": "Custom tools via Model Context Protocol",
        "detail": """\
# MCP — Model Context Protocol tools

MCP lets you add custom tool servers that Claude can invoke.
Tools are configured in .claude/settings.json.

## Configuration

  Add to .claude/settings.json:

  {
    "mcpServers": {
      "my-server": {
        "command": "python",
        "args": ["path/to/mcp_server.py"],
        "env": {}
      }
    }
  }

## Popular MCP servers
  - Database: Query PostgreSQL, SQLite, MySQL directly
  - GitHub: Create issues, PRs, manage repos
  - Slack: Send messages, read channels
  - Filesystem: Extended file operations
  - Docker: Manage containers and images
  - Puppeteer: Browser automation and scraping

## Prompt syntax

  Use the database tool to query all users created today

  Use the GitHub tool to create an issue titled "Bug: login fails"

## Notes
- Each MCP server exposes its own set of tools
- Claude discovers available tools automatically
- Server must implement the MCP protocol
- See modelcontextprotocol.io for the full spec
""",
    },
]


def get_tool_names() -> list[str]:
    """Return display strings for the browser list: 'Name — Summary'."""
    return [f"{t['name']} — {t['summary']}" for t in TOOL_LIBRARY]


def get_tool_detail(index: int) -> tuple[str, list[str]]:
    """Return (title, lines) for the detail viewer at the given index."""
    tool = TOOL_LIBRARY[index]
    title = f"{tool['name']} ({tool['category']})"
    lines = tool["detail"].splitlines()
    return title, lines
