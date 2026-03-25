"""Lightweight YAML front-matter parser for published documents."""


def parse_frontmatter(text: str) -> dict[str, str]:
    """Extract YAML front matter from a markdown document.

    Finds the opening ``---`` at the start of the text and the closing
    ``---``, then splits intervening lines on the first ``:`` to build
    a dict.  Returns an empty dict if no front matter block is found.
    """
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return {}
    result: dict[str, str] = {}
    for line in lines[1:]:
        if line.strip() == "---":
            break
        if ":" in line:
            key, _, value = line.partition(":")
            result[key.strip()] = value.strip().strip('"').strip("'")
    return result
