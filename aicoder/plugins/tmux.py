"""
tmux.py - Tmux session management for AI Coder

Session markers for pane scrollback, restore-session, and wintitle.
"""

import os
import subprocess
from datetime import datetime

MARKER_PREFIX = "[tmux]"
MARKER_TEXT = "session-start"
WINTITLE_FILE = ".aicoder/tmux-wintitle"
WINTITLE_FILE_DISABLED = ".aicoder/_tmux-wintitle"

_MARKER_LOADED = False


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

    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    LogUtils.print(f"{dim}{MARKER_PREFIX} {MARKER_TEXT} {ts}{reset}")

    def _wintitle_filepath():
        return os.path.join(os.getcwd(), WINTITLE_FILE)

    def _wintitle_filepath_disabled():
        return os.path.join(os.getcwd(), WINTITLE_FILE_DISABLED)

    def _apply_title(name):
        """Rename window if single pane and name differs. Fully async."""
        script = (
            f'read cur_name cur_count <<< $(tmux display-message -p '
            f'"#{{window_name}} #{{window_panes}}" 2>/dev/null); '
            f'if [ -n "$cur_count" ] && [ "$cur_count" -le 1 ] '
            f'&& [ "$cur_name" != "{name}" ]; then '
            f'tmux rename-window "{name}"; '
            f'fi'
        )
        subprocess.Popen(script, shell=True,
                         stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)

    def _read_title_file(path):
        """Read title from file, or None if missing/empty"""
        try:
            with open(path, "r") as f:
                content = f.read().strip()
            return content if content else None
        except (FileNotFoundError, IOError, OSError):
            return None

    def _write_title_file(path, name):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as f:
            f.write(name + "\n")

    def _set_wintitle_from_file():
        """Check active file, derive name, apply async. Called on startup."""
        active = _wintitle_filepath()
        name = _read_title_file(active)
        if name is None:
            # File may be empty — use dir name
            name = os.path.basename(os.path.abspath(os.getcwd()))
        _apply_title(name)

    def _handle_wintitle(parts):
        active = _wintitle_filepath()
        disabled = _wintitle_filepath_disabled()

        if not parts or parts[0] == "show":
            # Show current window name
            try:
                r = subprocess.run(["tmux", "display-message", "-p", "#W"],
                                   capture_output=True, text=True, timeout=3)
                cur = r.stdout.strip()
            except Exception:
                cur = "(unknown)"
            exists = "active" if os.path.isfile(active) else (
                "saved (off)" if os.path.isfile(disabled) else "off (no file)"
            )
            return f"Window: {cur}\nWintitle state: {exists}"

        cmd = parts[0]

        if cmd == "on":
            # Restore disabled file if exists, otherwise create
            if os.path.isfile(disabled):
                os.rename(disabled, active)
            if not os.path.isfile(active):
                name = os.path.basename(os.path.abspath(os.getcwd()))
                _write_title_file(active, name)
            _set_wintitle_from_file()
            return "Wintitle on."

        elif cmd == "reset":
            name = os.path.basename(os.path.abspath(os.getcwd()))
            _write_title_file(active, name)
            _apply_title(name)
            return f"Wintitle reset to: {name}"

        elif cmd == "off":
            if os.path.isfile(active):
                os.rename(active, disabled)
            _apply_title(os.path.basename(os.path.abspath(os.getcwd())))
            return "Wintitle off (name saved)."

        else:
            # Custom name
            name = " ".join(parts)
            _write_title_file(active, name)
            # Ensure it's active (rename disabled -> active if exists)
            if os.path.isfile(disabled):
                os.rename(disabled, active)
            _apply_title(name)
            return f"Wintitle set to: {name}"

    def handle_tmux(args_str):
        """Handle /tmux command"""
        parts = args_str.strip().split()
        cmd = parts[0] if parts else ""

        if cmd in ("rs", "restore", "restore-session"):
            return _restore_session(ctx)
        elif cmd == "wintitle":
            return _handle_wintitle(parts[1:])
        elif cmd in ("help", ""):
            return (
                "Usage: /tmux <subcommand>\n"
                "  rs / restore-session     - Recover context from previous session\n"
                "  wintitle                 - Show current window name & state\n"
                "  wintitle on              - Enable wintitle (restore saved name)\n"
                "  wintitle off             - Disable wintitle (saves name)\n"
                "  wintitle reset           - Reset to current directory name\n"
                "  wintitle <custom name>   - Set custom window title\n"
                "  help                     - Show this help"
            )
        else:
            return f"Unknown subcommand: {cmd}. Try /tmux help"

    ctx.register_command("tmux", handle_tmux, "Tmux session management (restore-session, wintitle)")

    # Apply wintitle on startup if active file exists — fire-and-forget
    if os.path.isfile(_wintitle_filepath()) or os.path.isfile(_wintitle_filepath_disabled()):
        LogUtils.info("[tmux] wintitle file exists, will apply on session init")
    ctx.register_hook("after_session_initialized", lambda *_: _set_wintitle_from_file()
                       if os.path.isfile(_wintitle_filepath()) else None)

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
