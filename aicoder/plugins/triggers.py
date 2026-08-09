"""triggers.py - Run shell commands on counted application events

Configuration file:
  .aicoder/triggers

Each non-comment line has this form:
  INTERVAL EVENT COMMAND

Example:
  10 after_ai_processing ./check-status
  1 after_assistant_message_added ~/bin/log-response
  5 on_blablabla ./script

Events do not need to exist when configured. A rule becomes active when
something emits that event through the plugin system.
"""

import os
import subprocess
import sys

from aicoder.core.config import Config
from aicoder.core.nudges import add_nudge
from aicoder.utils.log import LogUtils

TRIGGERS_FILE = ".aicoder/triggers"


def _read_rules():
    rules = []
    errors = []

    if not os.path.exists(TRIGGERS_FILE):
        return rules, errors

    try:
        with open(TRIGGERS_FILE, "r", encoding="utf-8") as file:
            for line_number, raw_line in enumerate(file, 1):
                line = raw_line.strip()
                if not line or line.startswith("#"):
                    continue

                parts = line.split(None, 2)
                if len(parts) < 3:
                    errors.append(f"line {line_number}: expected INTERVAL EVENT COMMAND")
                    continue

                try:
                    interval = int(parts[0])
                except ValueError:
                    errors.append(f"line {line_number}: interval must be a positive integer")
                    continue

                if interval < 1:
                    errors.append(f"line {line_number}: interval must be a positive integer")
                    continue

                rules.append({
                    "line": line_number,
                    "interval": interval,
                    "event": parts[1],
                    "command": parts[2],
                })
    except OSError as error:
        errors.append(f"cannot read {TRIGGERS_FILE}: {error}")

    return rules, errors


def create_plugin(ctx):
    """Register configured shell commands against application events."""
    state = {
        "rules": [],
        "errors": [],
        "event_counts": {},
        "registered_events": set(),
    }

    def _run_rule(rule):
        tag = f"{Config.colors['yellow']}[triggers]{Config.colors['reset']}"
        LogUtils.print(
            f"\n{tag} {rule['interval']} {rule['event']} {rule['command']}"
        )
        try:
            result = subprocess.run(
                rule["command"],
                shell=True,
                capture_output=True,
                text=True,
                check=False,
            )
        except OSError as error:
            output = f"trigger command failed to start: {error}"
            print(output, file=sys.stderr)
            add_nudge(
                ctx.app,
                "TRIGGERS",
                f"[TRIGGERS:{rule['event']}]\n{output}",
            )
            return

        if result.stdout:
            print(result.stdout, end="")
        if result.stderr:
            print(result.stderr, end="", file=sys.stderr)

        output_parts = []
        if result.stdout:
            output_parts.append(result.stdout.rstrip("\n"))
        if result.stderr:
            output_parts.append(result.stderr.rstrip("\n"))
        if result.returncode != 0:
            output_parts.append(f"command exited with status {result.returncode}")

        if output_parts:
            add_nudge(
                ctx.app,
                "TRIGGERS",
                f"[TRIGGERS:{rule['event']}]\n" + "\n".join(output_parts),
            )

    def _event_handler(event_name, *_args, **_kwargs):
        count = state["event_counts"].get(event_name, 0) + 1
        state["event_counts"][event_name] = count

        for rule in state["rules"]:
            if rule["event"] == event_name and count % rule["interval"] == 0:
                _run_rule(rule)

    def _load_rules(show_errors=False):
        rules, errors = _read_rules()
        state["rules"] = rules
        state["errors"] = errors

        for event_name in {rule["event"] for rule in rules}:
            if event_name in state["registered_events"]:
                continue
            ctx.register_hook(
                event_name,
                lambda *args, _event=event_name, **kwargs: _event_handler(
                    _event, *args, **kwargs
                ),
            )
            state["registered_events"].add(event_name)

        if show_errors:
            for error in errors:
                LogUtils.error(f"[triggers] {error}")

    def _show():
        if not os.path.exists(TRIGGERS_FILE):
            return f"No {TRIGGERS_FILE} file found."
        try:
            with open(TRIGGERS_FILE, "r", encoding="utf-8") as file:
                content = file.read().rstrip()
        except OSError as error:
            return f"Read error: {error}"
        return content or f"{TRIGGERS_FILE} is empty."

    def _edit():
        if not os.environ.get("TMUX"):
            return "This command only works inside a tmux environment."

        os.makedirs(os.path.dirname(TRIGGERS_FILE), exist_ok=True)
        if not os.path.exists(TRIGGERS_FILE):
            open(TRIGGERS_FILE, "a").close()

        from aicoder.utils.tmux_edit_utils import tmux_open_editor

        if not tmux_open_editor(TRIGGERS_FILE, window_name_prefix="triggers"):
            return "Failed to open editor."
        _load_rules(show_errors=True)
        return "Triggers file saved and reloaded."

    def _command(args):
        subcommand = args.strip().split(maxsplit=1)[0] if args.strip() else "show"
        if subcommand == "show":
            return _show()
        if subcommand == "edit":
            return _edit()
        if subcommand == "reload":
            _load_rules(show_errors=True)
            return f"Loaded {len(state['rules'])} trigger(s)."
        if subcommand == "help":
            return (
                "Usage: /triggers <show|edit|reload>\n"
                "  show    Display .aicoder/triggers\n"
                "  edit    Edit and reload the triggers file\n"
                "  reload  Reload the triggers file"
            )
        return "Unknown subcommand. Use /triggers help"

    _load_rules()
    ctx.register_command("triggers", _command, "Run commands on counted events")
    return {"name": "triggers"}
