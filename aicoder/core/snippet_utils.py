"""
Snippet utilities for AI Coder
Ported exactly from TypeScript version
"""

import os
from pathlib import Path


SNIPPETS_DIR = Path(os.path.expanduser("~")) / ".config/aicoder-mini/snippets"


def ensure_snippets_dir() -> None:
    """Ensure snippets directory exists"""
    SNIPPETS_DIR.mkdir(parents=True, exist_ok=True)


def load_snippet(name: str) -> str:
    """Load a snippet by name"""
    ensure_snippets_dir()
    # Try no-ext first, then .txt
    paths = [SNIPPETS_DIR / name, SNIPPETS_DIR / f"{name}.txt"]

    for file_path in paths:
        if file_path.exists():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    return f.read().strip()
            except Exception as error:
                # File exists but can't read - continue to next option
                print(f"Warning: Cannot read snippet file {file_path}: {error}")

    return ""


def expand_snippets(input_text: str) -> str:
    """Expand snippets in input text"""
    result = input_text
    changed = False

    while True:
        changed = False

        def replace_snippet(match):
            nonlocal changed
            name = match.group(1)
            content = load_snippet(name)
            if content:
                changed = True
                return content
            else:
                print(f"[Snippet missing: @@{name} → skipped]")
                return match.group(0)  # Keep original

        # Use re.sub with callback
        import re

        result = re.sub(r"@@([a-zA-Z0-9_-]+)", replace_snippet, result)

        if not changed:
            break

    return result


def get_snippet_names() -> list:
    """Get all snippet names"""
    ensure_snippets_dir()
    try:
        files = [f for f in SNIPPETS_DIR.iterdir() if not f.name.startswith(".")]
        names = []
        for f in files:
            name = Path(f.stem)
            if name:  # Filter out empty names
                names.append(str(name))
        # Dedup if both name and name.txt exist and sort once
        return sorted(list(set(names)))
    except Exception as error:
        print(f"Warning: Cannot read snippets directory: {error}")
        return []
