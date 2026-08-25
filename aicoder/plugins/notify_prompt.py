"""
Notify Prompt Plugin - Audio notifications for prompts and approvals

Design:
- NOTIFY_PROMPT_CMD env var: shell command run before user prompt
- NOTIFY_APPROVAL_CMD env var: shell command run before tool approval prompt
- /notify-prompt on|off: creates/deletes .aicoder/.notify-prompt gate file
- Commands run fire-and-forget (non-blocking), output discarded
- Fallback: if env var unset, use espeak if installed (checked once, cached);
  otherwise print an on-screen hint telling the user to set the env var
"""

import os
import shutil
import subprocess

from aicoder.core.config import Config
from aicoder.utils.log import LogUtils
from aicoder.utils.bool_utils import TRUTHY, FALSY

GATE_FILE = os.path.join(".aicoder", ".notify-prompt")


def create_plugin(ctx):
    """Audio notifications plugin"""

    def enabled() -> bool:
        """Check if notifications are enabled (gate file exists)"""
        return os.path.exists(GATE_FILE)

    def get_cmd(name: str) -> str:
        """Get notify command from env, stripped"""
        return (os.environ.get(name) or "").strip()

    espeak_checked = False
    has_espeak = False

    def espeak_available() -> bool:
        """Check espeak presence once, cache result"""
        nonlocal espeak_checked, has_espeak
        if not espeak_checked:
            has_espeak = shutil.which("espeak") is not None
            espeak_checked = True
        return has_espeak

    def say(cmd: str) -> None:
        """Run notify command fire-and-forget"""
        subprocess.Popen(
            cmd,
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def fire(env_name: str, message: str) -> None:
        """Run env command if set; else espeak fallback; else on-screen hint"""
        if not enabled():
            return
        cmd = get_cmd(env_name)
        if cmd:
            say(cmd)
            return
        if espeak_available():
            say(f'espeak "{message}"')
            return
        LogUtils.print(
            f'[notify-prompt] Notifications on, but {env_name} not set and '
            f'espeak not found. Set it, e.g.: export {env_name}="say {message}"'
        )

    def on_before_user_prompt():
        fire("NOTIFY_PROMPT_CMD", "prompt available")

    def on_before_approval_prompt(tool_name: str = None, arguments: dict = None):
        fire("NOTIFY_APPROVAL_CMD", "approval available")

    def handle_notify_prompt(args_str: str) -> str:
        """Handle /notify-prompt command"""
        args = (args_str or "").strip().split()
        if args and (args[0] in TRUTHY or args[0] in FALSY):
            if args[0] in TRUTHY:
                os.makedirs(".aicoder", exist_ok=True)
                with open(GATE_FILE, "w"):
                    pass
                return "Notifications enabled (.aicoder/.notify-prompt)"
            try:
                os.remove(GATE_FILE)
            except FileNotFoundError:
                pass
            return "Notifications disabled"

        prompt_cmd = get_cmd("NOTIFY_PROMPT_CMD")
        approval_cmd = get_cmd("NOTIFY_APPROVAL_CMD")
        state = "enabled" if enabled() else "disabled"
        return f"""Notify Prompt Status:

- Notifications: {state} (/notify-prompt on/off)
- NOTIFY_PROMPT_CMD: {prompt_cmd or "(not set)"}
- NOTIFY_APPROVAL_CMD: {approval_cmd or "(not set)"}

Fallback when env vars unset: espeak (if installed).
Otherwise set them, e.g.: export NOTIFY_PROMPT_CMD="say prompt available"
"""

    # Register hooks and command
    ctx.register_hook("before_user_prompt", on_before_user_prompt)
    ctx.register_hook("before_approval_prompt", on_before_approval_prompt)
    ctx.register_command(
        "/notify-prompt", handle_notify_prompt,
        description="Audio notifications for prompts/approvals"
    )

    if Config.debug():
        LogUtils.print("  - before_user_prompt hook")
        LogUtils.print("  - before_approval_prompt hook")
        LogUtils.print("  - /notify-prompt command")
