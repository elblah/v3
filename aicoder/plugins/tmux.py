"""
tmux.py - Tmux session management for AI Coder

Provides session markers for pane scrollback segmentation and a
/tmux restore-session command to recover context from previous sessions.

Each startup in tmux prints a dim marker line. restore-session captures
tmux scrollback, finds the previous session marker, extracts content,
opens editor for review/trimming, then sends as user message.
"""

import os
import subprocess
from datetime import datetime

MARKER_PREFIX = "[tmux]"
MARKER_TEXT = "session-start"

_MARKER_LOADED = False  # module-level guard against double-print


def create_plugin(ctx):
    """Load tmux plugin - only activates inside a tmux session"""
    if not os.environ.get("TMUX"):
        return None

    global _MARKER_LOADED
    if _MARKER_LOADED:
        return {"name": "tmux"}
    _MARKER_LOADED = True

    from aicoder.core.config import Config
    from aicoder.utils.log import LogUtils

    colors = Config.colors
    reset = colors.get("reset", "")
    dim = colors.get("dim", "")

    # Print session marker for future restores
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    LogUtils.print(f"{dim}{MARKER_PREFIX} {MARKER_TEXT} {ts}{reset}")

    def handle_tmux(args_str):
        """Handle /tmux command"""
        parts = args_str.strip().split()
        cmd = parts[0] if parts else ""

        if cmd in ("rs", "restore", "restore-session"):
            return _restore_session(ctx)
        else:
            return (
                "Usage: /tmux <subcommand>\n"
                "  rs / restore-session  - Recover context from previous session\n"
                "  help                  - Show this help"
            )

    ctx.register_command("tmux", handle_tmux, "Tmux session management (restore-session)")
    return {"name": "tmux"}


def _restore_session(ctx):
    """Capture tmux scrollback, find prev marker, open editor, inject as next prompt"""
    from aicoder.core.config import Config
    from aicoder.utils.log import LogUtils
    from aicoder.utils.temp_file_utils import create_temp_file
    colors = Config.colors
    reset = colors.get("reset", "")
    dim = colors.get("dim", "")

    # Capture full tmux pane scrollback
    try:
        result = subprocess.run(
            ["tmux", "capture-pane", "-p", "-S", "-"],
            capture_output=True, text=True, timeout=5,
        )
        if result.returncode != 0:
            LogUtils.error(f"capture-pane failed: {result.stderr}")
            return
        pane_content = result.stdout
    except FileNotFoundError:
        LogUtils.error("tmux not found")
        return
    except subprocess.TimeoutExpired:
        LogUtils.error("tmux capture timed out")
        return

    # Find marker lines (oldest → newest)
    lines = pane_content.splitlines()
    marker_pattern = f"{MARKER_PREFIX} {MARKER_TEXT}"
    marker_indices = [i for i, line in enumerate(lines) if marker_pattern in line]

    if len(marker_indices) >= 2:
        start = marker_indices[-2]
        captured = lines[start:]
        info = f"Found {len(marker_indices)} session markers. Extracting from previous session start (line {start})."
    elif len(marker_indices) == 1:
        captured = lines[marker_indices[0]:]
        info = "Found current session marker only. Extracting from this session start."
    else:
        captured = lines
        info = "No session markers found. Extracting full scrollback."

    content = "\n".join(captured).strip()
    if not content:
        LogUtils.warn("No content captured from tmux scrollback.")
        return

    # Write to temp file with header comments
    header = (
        f"# Recovered from tmux pane ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})\n"
        f"# {info}\n"
        f"# Edit below and save to send. Clear all content (or delete non-comment lines) to cancel.\n"
        f"# Lines starting with # are stripped before sending.\n"
        f"# ─────────────────────────────────────────────────\n\n"
    )
    temp_file = create_temp_file("aicoder-tmux-restore", ".md")
    with open(temp_file, "w", encoding="utf-8") as f:
        f.write(header + content)

    # Open editor in tmux window (same pattern as /e)
    editor = os.environ.get("EDITOR", "nano")
    random_suffix = os.urandom(4).hex()
    sync_point = f"tmux_restore_{random_suffix}"
    window_name = f"tmux-rs_{random_suffix}"

    LogUtils.info(f"Opening {editor} with captured content...")
    LogUtils.dim("Save and close when done. Empty file or all-comment = cancel.")

    tmux_cmd = f'tmux new-window -n "{window_name}" \'bash -c "{editor} {temp_file}; tmux wait-for -S {sync_point}"\''
    proc = subprocess.run(tmux_cmd, shell=True, capture_output=True, text=True)
    if proc.returncode != 0:
        LogUtils.error(f"tmux command failed: {proc.stderr}")
        return

    subprocess.run(f"tmux wait-for {sync_point}", shell=True, capture_output=True, text=True)

    # Read edited content
    try:
        with open(temp_file, "r", encoding="utf-8") as f:
            edited = f.read()
    except FileNotFoundError:
        LogUtils.error("Temp file not found")
        return
    finally:
        try:
            os.remove(temp_file)
        except Exception:
            pass

    # Strip comment lines (starting with # after optional whitespace)
    clean_lines = []
    for line in edited.split("\n"):
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            clean_lines.append(line)
    clean_content = "\n".join(clean_lines).strip()

    if not clean_content:
        LogUtils.warn("Empty content - nothing sent.")
        return

    LogUtils.success("Session content recovered.")
    ctx.app.set_next_prompt(clean_content)
