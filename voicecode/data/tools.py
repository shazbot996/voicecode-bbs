"""Built-in tool definitions for the Tools browser tab.

Provides separate tool libraries for Claude Code and Gemini CLI,
selected at runtime based on the active provider.
"""

# Each tool entry has:
#   name        — display name in the browser list
#   category    — grouping label (Files, Search, Execution, AI)
#   summary     — one-line description shown in list
#   detail      — multi-line reference card shown in the detail viewer

# ─── Claude Code tools ────────────────────────────────────────────

CLAUDE_TOOLS: list[dict] = [
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


# ─── Gemini CLI tools ─────────────────────────────────────────────

GEMINI_TOOLS: list[dict] = [
    # ── Files ──────────────────────────────────────────────────
    {
        "name": "ReadFile",
        "category": "Files",
        "summary": "Read file contents by path",
        "detail": """\
# ReadFile — Read file contents

Reads a file from the local filesystem and returns its contents.

## Parameters
  file_path       (required) Path to the file to read
  should_read_all (optional) Read entire file without truncation

## Prompt syntax

  Read the file src/main.py

  Show me the contents of config.yaml

  Read the entire README.md without truncation

## Notes
- Supports text files, images, and common document formats
- Large files are truncated by default; use should_read_all to override
- Paths can be absolute or relative to working directory
""",
    },
    {
        "name": "ReadManyFiles",
        "category": "Files",
        "summary": "Read multiple files at once",
        "detail": """\
# ReadManyFiles — Read multiple files at once

Reads several files in a single operation.

## Parameters
  file_paths   (required) List of file paths to read

## Prompt syntax

  Read src/app.py and src/utils.py

  Show me all three config files: dev.yaml, staging.yaml, prod.yaml

## Notes
- More efficient than reading files one at a time
- Same truncation behavior as ReadFile
""",
    },
    {
        "name": "WriteFile",
        "category": "Files",
        "summary": "Create or overwrite a file",
        "detail": """\
# WriteFile — Create or overwrite a file

Writes content to a file, creating directories as needed.

## Parameters
  file_path    (required) Path to write to
  content      (required) The full file content

## Prompt syntax

  Create a new file src/utils/logger.py with a Logger class

  Write a .gitignore that excludes node_modules and .env

## Notes
- Creates parent directories if they don't exist
- Prefer EditFile for modifying existing files
""",
    },
    {
        "name": "EditFile",
        "category": "Files",
        "summary": "Apply targeted edits to a file",
        "detail": """\
# EditFile — Apply targeted edits to a file

Modifies specific parts of a file using find-and-replace
or line-range operations.

## Parameters
  file_path    (required) Path to the file to edit
  edits        (required) List of edit operations

## Prompt syntax

  In src/app.py, rename the variable old_name to new_name

  Replace the import statement in utils.py

  Update the database URL in config.py

## Notes
- Supports multiple edits in a single operation
- More efficient than WriteFile for small changes
- File should be read first to understand current content
""",
    },
    # ── Search ─────────────────────────────────────────────────
    {
        "name": "GrepSearch",
        "category": "Search",
        "summary": "Search file contents with regex",
        "detail": """\
# GrepSearch — Search file contents

Searches file contents using regex patterns.

## Parameters
  query         (required) Regex pattern to search for
  path          (optional) Directory or file to search in
  include       (optional) File pattern filter (e.g. "*.py")
  case_sensitive (optional) Case sensitive search (default true)

## Prompt syntax

  Search for all uses of "database_url" in the project

  Find all TODO comments in Python files

  Search for the function definition of process_data

## Notes
- Returns matching lines with file paths and line numbers
- Use include to narrow search to specific file types
- Supports full regex syntax
""",
    },
    {
        "name": "FindFiles",
        "category": "Search",
        "summary": "Find files by name pattern",
        "detail": """\
# FindFiles — Find files by name or path pattern

Searches for files matching a name or glob pattern.

## Parameters
  pattern      (required) File name or glob pattern
  path         (optional) Directory to search in

## Prompt syntax

  Find all Python files in the src directory

  List all test files matching test_*.py

  Find all YAML config files in the project

## Notes
- Searches file names and paths, not file contents
- Supports glob patterns: *, **, ?
- Use GrepSearch to search inside files
""",
    },
    {
        "name": "ListDirectory",
        "category": "Search",
        "summary": "List directory contents",
        "detail": """\
# ListDirectory — List directory contents

Lists files and subdirectories at a given path.

## Parameters
  dir_path     (required) Directory path to list

## Prompt syntax

  List the contents of the src directory

  Show me what's in the project root

  What files are in src/components/?

## Notes
- Shows files and directories at the specified level
- Does not recurse into subdirectories
- Use FindFiles for recursive file discovery
""",
    },
    # ── Execution ──────────────────────────────────────────────
    {
        "name": "Shell",
        "category": "Execution",
        "summary": "Run shell commands",
        "detail": """\
# Shell — Execute shell commands

Runs a shell command and returns stdout/stderr.

## Parameters
  command      (required) The shell command to run

## Prompt syntax

  Run the test suite with pytest

  Install the requests package with pip

  Run git log --oneline -10 to show recent commits

  Build the project and show any errors

## Notes
- Working directory persists across calls
- Use for system commands that need shell execution
- Prefer dedicated tools (ReadFile, GrepSearch) when available
""",
    },
    # ── Web ────────────────────────────────────────────────────
    {
        "name": "GoogleSearch",
        "category": "Web",
        "summary": "Search Google for information",
        "detail": """\
# GoogleSearch — Search Google

Performs a Google search and returns results.

## Prompt syntax

  Search for the latest Python 3.13 release notes

  Look up the documentation for the asyncio.TaskGroup API

  Find examples of implementing OAuth2 with FastAPI

## Notes
- Powered by Google Search
- Results include titles, URLs, and snippets
- Follow up with FetchWebPage to read specific pages
""",
    },
    {
        "name": "FetchWebPage",
        "category": "Web",
        "summary": "Fetch and read a web page",
        "detail": """\
# FetchWebPage — Fetch a web page

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
- Use GoogleSearch first to find relevant URLs
""",
    },
    # ── Memory & Context ──────────────────────────────────────
    {
        "name": "SaveMemory",
        "category": "Memory",
        "summary": "Save information for future sessions",
        "detail": """\
# SaveMemory — Save information for future sessions

Stores a key-value memory that persists across conversations.

## Parameters
  key          (required) Memory key/name
  value        (required) Information to remember

## Prompt syntax

  Remember that this project uses PostgreSQL 15

  Save that the deploy command is ./scripts/deploy.sh

## Notes
- Memories persist across Gemini CLI sessions
- Use for project conventions, preferences, and context
- Memories are stored in ~/.gemini/memory/
""",
    },
    {
        "name": "MemorySearch",
        "category": "Memory",
        "summary": "Search saved memories",
        "detail": """\
# MemorySearch — Search saved memories

Retrieves previously saved memories matching a query.

## Parameters
  query        (required) Search query for memories

## Prompt syntax

  What do you remember about the deploy process?

  Search your memory for database configuration

## Notes
- Searches across all saved key-value memories
- Returns matching memories with their keys and values
""",
    },
]


# ─── Provider-keyed registry ──────────────────────────────────────

_LIBRARIES: dict[str, list[dict]] = {
    "Claude": CLAUDE_TOOLS,
    "Gemini": GEMINI_TOOLS,
}


def get_tool_names(provider: str = "Claude") -> list[str]:
    """Return display strings for the browser list: 'Name — Summary'."""
    lib = _LIBRARIES.get(provider, CLAUDE_TOOLS)
    return [f"{t['name']} — {t['summary']}" for t in lib]


def get_tool_detail(index: int, provider: str = "Claude") -> tuple[str, list[str]]:
    """Return (title, lines) for the detail viewer at the given index."""
    lib = _LIBRARIES.get(provider, CLAUDE_TOOLS)
    tool = lib[index]
    title = f"{tool['name']} ({tool['category']})"
    lines = tool["detail"].splitlines()
    return title, lines
