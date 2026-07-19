"""
Reminder Plugin - Periodic system reminders for the AI

Injects <system-reminder> tag into system prompt after every N AI responses.
Prints [reminder] on screen when triggered.

Commands:
  /reminder edit              - Edit reminder message in $EDITOR (multiline)
  /reminder msg <text>        - Set reminder message inline
  /reminder interval <n>      - Remind every n AI responses (default: 30)
  /reminder on                - Enable reminders
  /reminder off               - Disable reminders
  /reminder clear             - Reset to defaults and delete state file
  /reminder status            - Show current settings
  /reminder help              - Show usage

Env vars (override JSON on load, persist to JSON):
  REMINDER_INTERVAL=<n>
  REMINDER_MSG=<text>
  REMINDER_ON=1
"""

import json
import os
import secrets
import subprocess

from aicoder.core.config import Config
from aicoder.utils.log import LogUtils
from aicoder.utils.temp_file_utils import create_temp_file

# --- State ---
_enabled = False
_interval = 30
_message = ""
_counter = 0
_flag_show_reminder = False

_STATE_FILE = os.path.join(os.getcwd(), ".aicoder", "reminder.json")


def _load_state():
    """Load from JSON, then override with env vars, persist env vars to JSON."""
    global _enabled, _interval, _message

    try:
        with open(_STATE_FILE) as f:
            data = json.load(f)
        _enabled = data.get("enabled", False)
        _interval = data.get("interval", 30)
        _message = data.get("message", "")
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    env_interval = os.environ.get("REMINDER_INTERVAL")
    if env_interval is not None:
        try:
            _interval = int(env_interval)
        except ValueError:
            pass

    env_msg = os.environ.get("REMINDER_MSG")
    if env_msg is not None:
        _message = env_msg

    env_on = os.environ.get("REMINDER_ON")
    if env_on is not None:
        _enabled = env_on.lower() in ("1", "true", "yes", "on")

    if any(k in os.environ for k in ("REMINDER_INTERVAL", "REMINDER_MSG", "REMINDER_ON")):
        _save_state()


def _save_state():
    """Persist current state to JSON."""
    os.makedirs(os.path.dirname(_STATE_FILE), exist_ok=True)
    try:
        with open(_STATE_FILE, "w") as f:
            json.dump({
                "enabled": _enabled,
                "interval": _interval,
                "message": _message,
            }, f)
    except OSError:
        pass


def _edit_in_tmux(initial: str) -> str | None:
    """Open $EDITOR in new tmux window, return edited content or None."""
    token = secrets.token_hex(4)
    sync = f"reminder_edit_done_{token}"
    win = f"reminder_{token}"
    editor = os.environ.get("EDITOR", "nano")
    tmp = create_temp_file("aicoder-reminder-", ".md")

    try:
        with open(tmp, "w") as f:
            f.write(initial)

        LogUtils.info(f"Opening {editor} for reminder message...")
        LogUtils.dim("Save and close when done.")

        subprocess.run(
            f'tmux new-window -n "{win}" \'bash -c "{editor} {tmp}; tmux wait-for -S {sync}"\'',
            shell=True, capture_output=True, text=True, check=False,
        )
        subprocess.run(f"tmux wait-for {sync}", shell=True, capture_output=True, text=True, check=False)

        with open(tmp) as f:
            content = f.read().strip()
    except Exception:
        return None
    finally:
        try:
            os.remove(tmp)
        except OSError:
            pass

    return content if content else None


def create_plugin(ctx):
    """Create reminder plugin."""
    global _enabled, _interval, _message, _counter, _flag_show_reminder

    app = ctx.app
    _load_state()

    def _on_system_prompt_append():
        """Passive instruction in system prompt so AI knows reminders exist."""
        if not _enabled or not _message:
            return None
        return (
            "A reminder plugin is active. When you see `<system-reminder>...</system-reminder>` "
            "in a user message, treat its content as a high-priority instruction."
        )

    def _status() -> str:
        c = Config.colors
        on_off = f"{c['green']}ON{c['reset']}" if _enabled else f"{c['red']}OFF{c['reset']}"
        lines = [
            f"{c['bold']}Reminder{c['reset']}",
            f"  State:    {on_off}",
            f"  Interval: {_interval} AI responses",
            f"  Message:  {_message if _message else c['dim'] + '(none)' + c['reset']}",
        ]
        return "\n".join(lines)

    def _handle_command(args_str: str) -> str:
        global _enabled, _interval, _message, _counter, _flag_show_reminder

        args = args_str.strip()

        if args.lower() == "on":
            _enabled = True
            _counter = 0
            _save_state()
            return _status()

        if args.lower() == "off":
            _enabled = False
            _counter = 0
            _save_state()
            return "Reminder disabled."

        if args.lower() in ("help", "?"):
            return (
                "Reminder subcommands:\n"
                "  edit                 - edit message in $EDITOR (multiline)\n"
                "  msg <text>           - set reminder message\n"
                "  interval <n>         - remind every n AI responses\n"
                "  on                   - enable reminders\n"
                "  off                  - disable\n"
                "  clear                - reset to defaults, delete state file\n"
                "  status               - show settings\n"
                "  help                 - this message\n\n"
                "Env vars: REMINDER_INTERVAL, REMINDER_MSG, REMINDER_ON"
            )

        if args.lower() == "edit":
            content = _edit_in_tmux(_message)
            if content is None:
                return "Edit cancelled or failed."
            _message = content
            _save_state()
            return f"Reminder message updated ({len(content)} chars)."

        if args.lower().startswith("msg "):
            new_msg = args[4:].strip()
            if not new_msg:
                return "Usage: /reminder msg <text>"
            _message = new_msg
            _counter = 0
            _save_state()
            return f"Reminder message set ({len(_message)} chars)."

        if args.lower().startswith("interval "):
            rest = args[9:].strip()
            try:
                n = int(rest)
                if n < 1:
                    return "Interval must be >= 1."
                _interval = n
                _counter = 0
                _save_state()
                return f"Reminder interval set to {_interval} AI responses."
            except ValueError:
                return "Usage: /reminder interval <n>"

        if args.lower() == "clear":
            _enabled = False
            _interval = 30
            _message = ""
            _counter = 0
            _flag_show_reminder = False
            try:
                os.remove(_STATE_FILE)
            except FileNotFoundError:
                pass
            return "Reminder state cleared to defaults."

        if args.lower() in ("status", ""):
            return _status()

        return "Unknown subcommand. Use /reminder help"

    def after_ai_processing(has_tool_calls: bool):
        global _counter, _flag_show_reminder
        if not _enabled or not _message:
            return None
        _counter += 1
        if _counter >= _interval:
            _counter = 0
            c = Config.colors
            LogUtils.print(f"\n{c['brightYellow']}[reminder]{c['reset']} {_message}")
            if has_tool_calls:
                app.message_history.add_user_message(
                    f"<system-reminder>\n{_message}\n</system-reminder>"
                )
            else:
                _flag_show_reminder = True
        return None

    def after_user_prompt(user_input: str):
        global _flag_show_reminder
        if not _flag_show_reminder or not _message:
            return user_input
        _flag_show_reminder = False
        return f"{user_input}\n\n<system-reminder>{_message}</system-reminder>"

    ctx.register_hook("on_system_prompt_append", _on_system_prompt_append)
    ctx.register_hook("after_ai_processing", after_ai_processing)
    ctx.register_hook("after_user_prompt", after_user_prompt)
    ctx.register_command("reminder", _handle_command, "Periodic system reminders for the AI")
