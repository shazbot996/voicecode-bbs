from typing import Any


def parse_frontmatter(text: str) -> dict[str, Any]:
    """Extract YAML front matter from a markdown document.

    Finds the opening ``---`` at the start of the text and the closing
    ``---``, then splits intervening lines on the first ``:`` to build
    a dict.  Supports scalar strings and simple YAML lists (- item).
    Returns an empty dict if no front matter block is found.
    """
    lines = text.lstrip("\r\n").splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    result: dict[str, Any] = {}
    current_list_key: str | None = None
    for line in lines[1:]:
        if line.strip() == "---":
            break
        stripped = line.strip()
        if stripped.startswith("- ") and current_list_key:
            item = stripped[2:].strip().strip('"').strip("'")
            if isinstance(result.get(current_list_key), list):
                result[current_list_key].append(item)
            else:
                result[current_list_key] = [item]
        elif ":" in line:
            key, _, value = line.partition(":")
            k = key.strip()
            v = value.strip().strip('"').strip("'")
            if not v:
                result[k] = []
                current_list_key = k
            else:
                result[k] = v
                current_list_key = None
        else:
            current_list_key = None
    return result


def strip_frontmatter(text: str) -> str:
    """Strip YAML front matter block (--- ... ---) from document if present."""
    text_stripped = text.lstrip("\r\n")
    lines = text_stripped.splitlines()
    if not lines or lines[0].strip() != "---":
        return text
    closing_idx = -1
    for i, line in enumerate(lines[1:], start=1):
        if line.strip() == "---":
            closing_idx = i
            break
    if closing_idx != -1:
        return "\n".join(lines[closing_idx + 1:]).strip()
    return text


def extract_prompt_metadata(text: str) -> dict[str, Any]:
    """Extract metadata (such as executed timestamp and artifacts) from prompt text.

    Supports both `# Key: Value` header comments and `---` YAML frontmatter.
    Returns a dictionary of normalized metadata fields.
    """
    metadata: dict[str, Any] = {}
    artifacts: list[str] = []

    # 1. Try YAML front matter first
    fm = parse_frontmatter(text)
    if fm:
        for k, v in fm.items():
            k_lower = k.lower().replace("-", "_").replace(" ", "_")
            if k_lower in ("artifacts", "artifact", "generated_files", "output_files"):
                if isinstance(v, list):
                    for p in v:
                        if p and p not in artifacts:
                            artifacts.append(p)
                elif isinstance(v, str):
                    for part in v.split(","):
                        p = part.strip()
                        if p and p not in artifacts:
                            artifacts.append(p)
            else:
                metadata[k_lower] = v

    # 2. Extract `# Key: Value` comment lines
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        if not line.startswith("#"):
            # Stop parsing comments once we hit non-comment content
            break
        comment = line.lstrip("#").strip()
        if ":" in comment:
            key, _, val = comment.partition(":")
            key_clean = key.strip().lower().replace("-", "_").replace(" ", "_")
            val_clean = val.strip()
            if key_clean in ("artifacts", "artifact", "generated_files", "output_files"):
                for part in val_clean.split(","):
                    p = part.strip()
                    if p and p not in artifacts:
                        artifacts.append(p)
            elif key_clean in ("prompt_version", "version"):
                metadata["version"] = val_clean
            else:
                metadata[key_clean] = val_clean
        elif comment.lower().startswith("prompt v"):
            metadata["version"] = comment

    if artifacts:
        metadata["artifacts"] = artifacts

    return metadata


def strip_prompt_metadata(text: str) -> str:
    """Strip comment headers (# ...) and YAML frontmatter (--- ... ---) to get pure prompt text."""
    # First strip leading comment lines (and blank lines)
    lines = text.splitlines()
    start_idx = 0
    while start_idx < len(lines):
        line = lines[start_idx].strip()
        if line.startswith("#") or not line:
            start_idx += 1
        else:
            break
    remaining = "\n".join(lines[start_idx:])
    # Then strip front matter if present at the start of remaining
    return strip_frontmatter(remaining).strip()


