"""
Shutdown Recovery Plugin

Saves timestamped recovery snapshots on SIGTERM/SIGHUP.
Provides /lr command to list, load, and clean recovery files.
"""

import os
import glob
from datetime import datetime

from aicoder.utils.json_utils import write_file


def create_plugin(ctx):
    RECOVERY_DIR = ".aicoder"
    _saved = False

    # ── helpers ──────────────────────────────────────────────────────────

    def _recovery_files():
        """Return sorted list of recovery json files in RECOVERY_DIR"""
        pattern = os.path.join(RECOVERY_DIR, "session_recovery_*.json")
        return sorted(glob.glob(pattern))

    def _load_by_path(path):
        """Load a session file via /load command"""
        ctx.app.command_handler.handle_command(f"/load {path}")

    def _save_recovery():
        """Save recovery session (only once)"""
        nonlocal _saved
        if _saved:
            return
        _saved = True
        try:
            ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            path = os.path.join(RECOVERY_DIR, f"session_recovery_{ts}.json")
            os.makedirs(RECOVERY_DIR, exist_ok=True)
            msgs = ctx.app.message_history.get_messages()
            write_file(path, msgs)
        except Exception:
            pass

    # ── hooks ───────────────────────────────────────────────────────────

    def on_sigterm(signum):
        _save_recovery()

    def on_sighup(signum):
        _save_recovery()

    def on_eof_error_readline(signum):
        _save_recovery()

    ctx.register_hook("on_sigterm", on_sigterm)
    ctx.register_hook("on_sighup", on_sighup)
    ctx.register_hook("on_eof_error_readline", on_eof_error_readline)

    # ── /load-recovery command (alias /lr) ───────────────────────────────

    def cmd_load_recovery(args_str):
        """Handle /lr and /load-recovery command"""
        parts = args_str.strip().split()
        sub = parts[0] if parts else ""

        files = _recovery_files()

        if sub == "list" or not sub:
            if not files:
                return "No recovery files found."
            lines = [f"Recovery files in {RECOVERY_DIR}/:"]
            for i, f in enumerate(files, 1):
                name = os.path.basename(f)
                lines.append(f"  [{i}] {name}")
            return "\n".join(lines)

        elif sub == "load":
            if len(parts) < 2:
                return "Usage: /load-recovery load <number|filename>"
            target = parts[1]
            # Try as numeric index
            if target.isdigit():
                n = int(target)
                if n < 1 or n > len(files):
                    return f"Invalid index {n}. Use /load-recovery list to see available files."
                _load_by_path(files[n - 1])
                return f"Loaded: {os.path.basename(files[n - 1])}"
            # Treat as filename (exact or partial)
            matches = [f for f in files if target in f]
            if len(matches) == 0:
                return f"No recovery file matching '{target}'."
            if len(matches) > 1:
                lines = [f"Multiple matches for '{target}':"]
                for i, m in enumerate(matches, 1):
                    lines.append(f"  [{i}] {os.path.basename(m)}")
                return "\n".join(lines)
            _load_by_path(matches[0])
            return f"Loaded: {os.path.basename(matches[0])}"

        elif sub == "rm-all":
            if not files:
                return "No recovery files to delete."
            count = len(files)
            for f in files:
                try:
                    os.remove(f)
                except OSError:
                    pass
            return f"Deleted {count} recovery file(s)."

        else:
            # Try bare number as shortcut: "/load-recovery 3" → load #3 (also /lr 3)
            if sub.isdigit():
                n = int(sub)
                if n < 1 or n > len(files):
                    return f"Invalid index {n}. Use /load-recovery list to see available files."
                _load_by_path(files[n - 1])
                return f"Loaded: {os.path.basename(files[n - 1])}"
            return f"Unknown subcommand: {sub}\nUsage: /load-recovery list | load <n|name> | rm-all"

    ctx.register_command("load-recovery", cmd_load_recovery, "Load recovery session")
    ctx.register_command("lr", cmd_load_recovery, "Alias for /load-recovery")
