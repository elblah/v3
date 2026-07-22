"""
autoexec.py - Execute .aicoder/autoexec line by line at startup

Each line is fed as the next prompt. The main loop handles commands/prompts.

Example .aicoder/autoexec:
  /cs 100k
  /detail on
  hello my name is Blah

Commands:
  /autoexec help       - Show usage
  /autoexec show       - Show current autoexec contents
  /autoexec edit       - Open $EDITOR to edit .aicoder/autoexec
"""

import os
import secrets
import subprocess
from aicoder.core.config import Config
from aicoder.utils.log import LogUtils

_AUTOEXEC_FILE = ".aicoder/autoexec"


def _read_autoexec():
    """Return list of non-comment, non-empty lines from autoexec file."""
    if not os.path.exists(_AUTOEXEC_FILE):
        return []
    lines = []
    try:
        with open(_AUTOEXEC_FILE, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    if ' #' in line:
                        line = line[:line.index(' #')].strip()
                    if line:
                        lines.append(line)
    except Exception:
        return []
    return lines


def _show_autoexec():
    """Print autoexec file contents."""
    if not os.path.exists(_AUTOEXEC_FILE):
        LogUtils.info("No .aicoder/autoexec file found.")
        return
    try:
        with open(_AUTOEXEC_FILE, 'r') as f:
            content = f.read()
    except Exception as e:
        LogUtils.error(f"Read error: {e}")
        return
    if not content.strip():
        LogUtils.info("autoexec file is empty.")
        return
    c = Config.colors
    print(f"\n{c['cyan']}── .aicoder/autoexec ──{c['reset']}")
    print(content.rstrip())
    print(f"{c['cyan']}─────────────────────{c['reset']}")


def _edit_autoexec():
    """Open .aicoder/autoexec in $EDITOR via tmux."""
    if not os.environ.get("TMUX"):
        LogUtils.error("This command only works inside a tmux environment.")
        return
    if not os.path.exists(_AUTOEXEC_FILE):
        LogUtils.error(f"{_AUTOEXEC_FILE} not found.")
        return

    editor = os.environ.get("EDITOR", "nano")
    token = secrets.token_hex(4)
    sync_point = f"autoexec_done_{token}"

    tmux_cmd = (
        f'tmux new-window -n "autoexec_{token}" '
        f'\'bash -c "{editor} {_AUTOEXEC_FILE}; tmux wait-for -S {sync_point}"\''
    )

    result = subprocess.run(tmux_cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        LogUtils.error(f"tmux command failed: {result.stderr}")
        return

    result = subprocess.run(
        f"tmux wait-for {sync_point}", shell=True, capture_output=True, text=True
    )
    if result.returncode != 0:
        LogUtils.error(f"tmux wait failed: {result.stderr}")
        return

    LogUtils.success("autoexec file saved.")


def create_plugin(ctx):
    """Load .aicoder/autoexec and feed lines one by one via hook"""
    app = ctx.app
    lines = []
    started = False

    def feed_next():
        nonlocal lines, started

        if not started:
            # First call: read file and set first prompt
            started = True
            lines.extend(_read_autoexec())
            if not lines:
                return

            c = Config.colors
            print(f"\n{c['cyan']}[autoexec] {len(lines)} line(s){c['reset']}")

            next_line = lines.pop(0)
            print(f"\n{c['cyan']}[autoexec] {next_line}{c['reset']}")
            app.set_next_prompt(next_line)
            return

        # Subsequent calls: feed next line if any
        if not lines:
            return

        c = Config.colors
        next_line = lines.pop(0)
        print(f"\n{c['cyan']}[autoexec] {next_line}{c['reset']}")
        app.set_next_prompt(next_line)

    def cmd_autoexec(args: str) -> str:
        """Handle /autoexec subcommands"""
        parts = args.strip().split()
        sub = parts[0] if parts else "show"

        if sub == "help":
            return (
                "Usage: /autoexec <subcommand>\n"
                "  help       Show this help\n"
                "  show       Display .aicoder/autoexec contents\n"
                "  edit       Open $EDITOR in tmux to edit .aicoder/autoexec"
            )
        elif sub == "edit":
            _edit_autoexec()
            return ""
        elif sub == "show":
            _show_autoexec()
            return ""
        else:
            return f"Unknown subcommand: {sub}\nUsage: /autoexec help"

    ctx.register_hook("before_user_prompt", feed_next)
    ctx.register_command("autoexec", cmd_autoexec, "Manage autoexec commands")
    ctx.register_command("ae", cmd_autoexec, "Alias for /autoexec")
