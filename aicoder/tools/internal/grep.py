"""
Grep tool - text search in files

"""

import os
import re
import shlex
import subprocess
from typing import Dict, Any, List, Optional, Tuple
from aicoder.core.config import Config
from aicoder.tools.internal.run_shell_command import resolve_command
from aicoder.utils.file_utils import check_sandbox, sandbox_denial_message
from aicoder.utils.log import LogUtils
from aicoder.utils.num_utils import coerce_int

# Configuration
DEFAULT_MAX_RESULTS = Config.default_grep_max_results()

# Pure-Python fallback settings (used when no external binary can be executed,
# e.g. sandboxed environments where execvp is blocked)
FALLBACK_SKIP_DIRS = {
    ".git", ".hg", ".svn", "node_modules", "__pycache__",
    ".venv", "venv", ".mypy_cache", ".pytest_cache", ".tox",
    ".idea", ".gradle", "target", "dist", "build",
}
FALLBACK_MAX_FILE_BYTES = 2 * 1024 * 1024
FALLBACK_MAX_LINE_CHARS = 500


def _looks_binary(path: str) -> bool:
    """Return True when the first chunk of a file contains NUL bytes."""
    try:
        with open(path, "rb") as handle:
            return b"\0" in handle.read(8192)
    except OSError:
        return True


def _iter_files(root: str):
    """Yield regular file paths below root, skipping known noise directories."""
    if os.path.isfile(root):
        yield root
        return

    for dirpath, dirnames, filenames in os.walk(root, followlinks=False):
        # Prune noise dirs and symlinked dirs (avoids cycles and escapes)
        dirnames[:] = [
            d for d in dirnames
            if d not in FALLBACK_SKIP_DIRS
            and not os.path.islink(os.path.join(dirpath, d))
        ]
        for name in filenames:
            full = os.path.join(dirpath, name)
            if os.path.islink(full) or not os.path.isfile(full):
                continue
            yield full


def _is_exec_failure(stderr: str) -> bool:
    """Detect failures caused by being unable to spawn a process at all."""
    lowered = stderr.lower()
    markers = (
        "execvp",
        "execvpe",
        "cannot execute",
        "failed to execute",
        "command not found",
    )
    return any(marker in lowered for marker in markers)


def python_grep(
    text: str,
    root: str,
    max_results: int,
    context: int,
) -> Tuple[List[str], Optional[str]]:
    """Pure-Python replacement for `rg -n --max-count N -C K`.

    Returns (result_lines, error_message). Result lines mimic ripgrep output:
    "path:lineno:line" for matches, "path-lineno-line" for context lines.
    """
    try:
        pattern = re.compile(text)
    except re.error as exc:
        return [], f"error: {exc}"

    results: List[str] = []
    match_count = 0

    for file_path in _iter_files(root):
        if match_count >= max_results:
            break
        try:
            if os.path.getsize(file_path) > FALLBACK_MAX_FILE_BYTES:
                continue
        except OSError:
            continue
        if _looks_binary(file_path):
            continue

        try:
            with open(file_path, "r", encoding="utf-8", errors="replace") as handle:
                lines = handle.read().splitlines()
        except OSError:
            continue

        hit_indexes = [i for i, line in enumerate(lines) if pattern.search(line)]
        if not hit_indexes:
            continue

        emitted = set()
        for index in hit_indexes:
            if match_count >= max_results:
                break
            match_count += 1
            first = max(0, index - context)
            last = min(len(lines) - 1, index + context)
            for i in range(first, last + 1):
                if i in emitted:
                    continue
                emitted.add(i)
                snippet = lines[i]
                if len(snippet) > FALLBACK_MAX_LINE_CHARS:
                    snippet = snippet[:FALLBACK_MAX_LINE_CHARS] + "..."
                sep = ":" if i == index else "-"
                results.append(f"{file_path}{sep}{i + 1}{sep}{snippet}")

    return results, None


def validateArguments(args: Dict[str, Any]) -> None:
    """Validate grep arguments"""
    pattern = args.get("text")
    if not pattern or not isinstance(pattern, str):
        raise Exception('grep requires "text" argument (string)')


def formatArguments(args: Dict[str, Any]) -> str:
    """Format arguments for approval display"""
    text = args.get("text", "")
    path = args.get("path", ".")
    max_results = coerce_int(args.get("max_results"), "max_results", DEFAULT_MAX_RESULTS)
    context = coerce_int(args.get("context"), "context", 2)

    parts = [f'Text: "{text}"']
    if path and path != ".":
        parts.append(f"Path: {path}")
    if max_results != DEFAULT_MAX_RESULTS:
        parts.append(f"Max results: {max_results}")
    if context != 2:
        parts.append(f"Context: {context} lines")

    return "\n  ".join(parts)


def execute(args: Dict[str, Any]) -> Dict[str, Any]:
    """Search for text in files using ripgrep or grep"""
    text = args.get("text")
    path = args.get("path", ".")
    max_results = coerce_int(args.get("max_results"), "max_results", DEFAULT_MAX_RESULTS)
    context = coerce_int(args.get("context"), "context", 2)

    if not text:
        raise Exception("Text is required")

    try:
        # Check sandbox restrictions, but don't print message (will show in result)
        if not check_sandbox(path, "grep", print_message=False):
            # Create sandbox message in result instead of printing
            sandbox_msg = f'Path: {path}\n[x] Sandbox: {sandbox_denial_message(path)}'
            return {
                "tool": "grep",
                "friendly": sandbox_msg,
                "detailed": sandbox_msg
            }

        # Validate search text
        if not text.strip():
            return {
                "tool": "grep",
                "friendly": f'ERROR: Search text cannot be empty.',
                "detailed": f'Search text "{text}" is invalid - it cannot be empty or whitespace only.'
            }

        # Build command using ripgrep ()
        search_path = os.path.abspath(path)

        cmd = [
            "rg",
            "-n",  # Line numbers
            "--max-count",
            str(max_results),
            "-C",
            str(context),  # Context lines
            "--",  # End of options: text can never be parsed as an rg flag
            text,
            search_path,
        ]

        # Prepend wrapper if configured (e.g. AICODER_SHELL_PREPEND_CMD="rtk")
        prepend = Config.shell_prepend_cmd()
        if prepend:
            cmd = prepend.split() + cmd

        # Route through the same seal hook as run_shell_command/bg_jobs
        # (on_before_run_shell_command). Quoted so bash re-parses faithfully.
        # When no process can be spawned at all (execvp blocked by the sandbox,
        # rg/bash missing), fall back to the pure-Python walker below.
        matches = []
        engine = "ripgrep"
        fallback_reason = None
        result = None

        try:
            quoted = " ".join(shlex.quote(c) for c in cmd)
            sealed_command, argv = resolve_command(quoted)
            result = subprocess.run(
                argv if argv is not None else ["bash", "-c", sealed_command],
                capture_output=True,
                text=True,
                timeout=30,
            )
        except subprocess.TimeoutExpired:
            raise
        except OSError as exc:
            fallback_reason = f"{type(exc).__name__}: {exc}"
            result = None

        if result is not None:
            stderr = (result.stderr or "").strip()
            if result.returncode != 0 and stderr and _is_exec_failure(stderr):
                fallback_reason = stderr.splitlines()[-1]
                result = None

        if result is None:
            engine = "python-fallback"
            matches, fallback_error = python_grep(text, search_path, max_results, context)
            if fallback_error:
                friendly = f"🔍 Search failed: {fallback_error}"
                return {
                    "tool": "grep",
                    "friendly": friendly,
                    "detailed": (
                        f"Search for '{text}' failed: {fallback_error}\n"
                        f"External search unavailable: {fallback_reason}"
                    ),
                }
        else:
            # Surface failures (bad regex, seal block) instead of "no matches"
            if result.returncode != 0 and result.stderr.strip():
                err = result.stderr.strip()
                friendly = f"🔍 Search failed: {err.splitlines()[-1]}"
                return {
                    "tool": "grep",
                    "friendly": friendly,
                    "detailed": f"Command: {' '.join(cmd)}\n\nExit {result.returncode}:\n{err}"
                }

            # Parse results
            stdout = result.stdout or ""
            matches = stdout.strip().split("\n") if stdout.strip() else []

        # Create friendly message
        if not matches:
            friendly = f"🔍 No matches found for '{text}'"
        else:
            friendly = f"🔍 Found {len(matches)} matches for '{text}'"

        if engine == "python-fallback":
            friendly += " [python fallback]"
            detail_lines = [
                f"Search completed: {friendly}",
                f"Engine: pure-Python fallback (external search unavailable: {fallback_reason})",
                "Matches:",
                "\n".join(matches),
            ]
        else:
            detail_lines = [
                f"Search completed: {friendly}",
                f"Command: {' '.join(cmd)}",
                "Matches:",
                "\n".join(matches),
            ]

        return {
            "tool": "grep",
            "friendly": friendly,
            "detailed": "\n\n".join(detail_lines),
        }

    except subprocess.TimeoutExpired:
        return {
            "tool": "grep",
            "friendly": f"⏰ Search timed out",
            "detailed": f"Search for '{text}' timed out. Command: {' '.join(cmd)}"
        }
    except Exception as e:
        return {
            "tool": "grep",
            "friendly": f"❌ Search error: {str(e)}",
            "detailed": f"Search for '{text}' failed with error: {str(e)}"
        }


# Tool definition
TOOL_DEFINITION = {
    "type": "internal",
    "auto_approved": True,
    "approval_excludes_arguments": False,
    "approval_key_exclude_arguments": [],
    "hide_results": False,
    "description": "Search text in files using ripgrep with line numbers. The text is a regular expression (ripgrep syntax) - escape metacharacters like ( ) [ ] | to match them literally. Path defaults to current directory.",
    "parameters": {
        "type": "object",
        "properties": {
            "text": {"type": "string", "description": "Text to search for (regular expression - escape metacharacters to match literally)."},
            "path": {
                "type": "string",
                "description": "Directory path to search in (defaults to current directory).",
            },
            "max_results": {
                "type": "number",
                "description": f"Maximum number of results (defaults to {DEFAULT_MAX_RESULTS}).",
            },
            "context": {
                "type": "number",
                "description": "Number of lines to show before/after match (defaults to 2).",
            },
        },
        "required": ["text"],
        "additionalProperties": False,
    },
    "validateArguments": validateArguments,
    "formatArguments": formatArguments,
}

# Add execute method to the definition
TOOL_DEFINITION["execute"] = execute
