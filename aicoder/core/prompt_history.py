"""
Simple JSONL prompt history
Module-based implementation for simplicity and clarity
"""

import os
import json
import re
from typing import List, Dict

# Module state - set once at import time
_HISTORY_PATH: str | None = None
_MAX_HISTORY_LINES = int(os.environ.get("AICODER_HISTORY_MAX", 30))
_SAVE_COUNT = 0
_TRUNCATE_INTERVAL = 10  # truncate every 10 saves


def _init_history_path() -> str | None:
    """Initialize history path - called once at module import"""
    aicoder_dir = ".aicoder"
    history_path = os.path.join(aicoder_dir, "history")

    # Ensure .aicoder directory exists - fail silently if unable to create
    try:
        if not os.path.exists(aicoder_dir):
            os.makedirs(aicoder_dir, exist_ok=True)
        return history_path
    except Exception:
        # Silent fail - history functionality will be disabled
        return None


# Initialize at module import time
_HISTORY_PATH = _init_history_path()


def _truncate_if_needed() -> None:
    """Truncate history file to keep only last N lines"""
    if not _HISTORY_PATH:
        return

    try:
        if not os.path.exists(_HISTORY_PATH):
            return

        with open(_HISTORY_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()

        if len(lines) <= _MAX_HISTORY_LINES:
            return

        # Keep only last N lines
        trimmed_lines = lines[-_MAX_HISTORY_LINES:]

        with open(_HISTORY_PATH, "w", encoding="utf-8") as f:
            f.writelines(trimmed_lines)
    except Exception:
        pass


def save_prompt(prompt: str) -> None:
    """
    Save a prompt to history (JSONL format)
    """
    # Skip empty prompts and approval responses
    if not prompt.strip() or re.match(r"^[Yn]$", prompt.strip()):
        return

    # If history is disabled, return silently
    if not _HISTORY_PATH:
        return

    # Only save prompt attribute for backward compatibility
    entry = {"prompt": prompt}
    line = json.dumps(entry) + "\n"

    try:
        with open(_HISTORY_PATH, "a", encoding="utf-8") as f:
            f.write(line)

        # Truncate on first save or every N saves
        global _SAVE_COUNT
        _SAVE_COUNT += 1
        if _SAVE_COUNT == 1 or _SAVE_COUNT % _TRUNCATE_INTERVAL == 0:
            _truncate_if_needed()
    except Exception:
        # Silent fail for history errors
        pass


def read_history() -> List[Dict[str, str]]:
    """
    Read all prompts from history
    """
    # If history is disabled, return empty list
    if not _HISTORY_PATH:
        return []

    try:
        if not os.path.exists(_HISTORY_PATH):
            return []

        with open(_HISTORY_PATH, "r", encoding="utf-8") as f:
            content = f.read()

        lines = content.strip().split("\n")
        lines = [line for line in lines if line.strip()]

        result = []
        for line in lines:
            try:
                entry = json.loads(line)
                # Only return prompt attribute for backward compatibility
                result.append({"prompt": entry.get("prompt", "")})
            except json.JSONDecodeError:
                result.append({"prompt": ""})

        # Filter out empty prompts
        return [entry for entry in result if entry["prompt"] != ""]
    except Exception:
        return []
