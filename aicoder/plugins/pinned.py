"""
Pinned Plugin - Show last AI text message above context bar

Solves the problem of tool output flooding making it hard to follow
what the AI said last.

Commands:
  /pinned default  - Auto mode (on when details on, off when details off)
  /pinned on       - Always show
  /pinned off      - Never show
  /pinned len <n>  - Set max characters (default: 300)
  /pinned pwd on   - Also show current working directory
  /pinned pwd off  - Hide PWD (default)
  /pinned status   - Show current settings
"""

import os
from aicoder.core.config import Config


def create_plugin(ctx):
    """Pinned plugin - show last AI text message"""

    # Settings
    _mode = "default"  # "default", "on", "off"
    _max_len = 300
    _pwd_enabled = False
    _last_text = ""
    _last_reasoning = ""

    def _is_enabled():
        """Check if pinned should be shown based on mode and details setting"""
        if _mode == "on":
            return True
        if _mode == "off":
            return False
        # default: on when details is on
        return Config.detail_mode()

    def _get_msg_reasoning(msg):
        """Extract reasoning from message"""
        override = Config.get_reasoning_field()
        if override:
            val = msg.get(override)
            if val and isinstance(val, str) and val.strip():
                return val.strip()
        else:
            for field in Config.get_possible_reasoning_fields():
                val = msg.get(field)
                if val and isinstance(val, str) and val.strip():
                    return val.strip()
        return ""

    def after_ai_processing(has_tool_calls: bool):
        """Capture last text message from AI"""
        nonlocal _last_text, _last_reasoning

        messages = ctx.app.message_history.get_messages()
        if not messages:
            return

        # Get last assistant message
        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                # Capture reasoning if present
                reasoning = _get_msg_reasoning(msg)
                if reasoning:
                    _last_reasoning = reasoning
                # Capture text content
                content = msg.get("content", "")
                if isinstance(content, str):
                    text = content.strip()
                    if text:
                        _last_text = text
                break

    # Heuristic: if last msg had no text and reasoning is concise (fits _max_len),
    # use reasoning. Otherwise fall back to _last_text.
    def _get_display_text():
        """Get the text to display — prefers concise reasoning, else last text"""
        # Try reasoning if it fits
        if _last_reasoning and len(_last_reasoning) <= _max_len:
            return _last_reasoning
        # Fall back to last text
        if _last_text:
            return _last_text
        return None

    def on_before_context_bar(context="ai"):
        """Show pinned message before context bar"""
        nonlocal _last_text, _last_reasoning
        if context != "ai":
            # New file/context — clear pinned history
            _last_text = ""
            _last_reasoning = ""
            return
        if not _is_enabled():
            return

        display_text = _get_display_text()
        if not display_text:
            return

        # Truncate if needed (safety - reasoning already checked but text might be long)
        if len(display_text) > _max_len:
            display_text = display_text[:_max_len] + "..."

        # Replace newlines with spaces for single line display
        display_text = " ".join(display_text.split())

        from aicoder.utils.log import LogUtils

        # Core behavior:
        # - AI path: no \n before context bar
        # - User path: \n before context bar
        # Plugin must adapt spacing based on context
        if context == "user":
            # User path: context bar adds \n before, add \n before Pinned
            LogUtils.print(f"\n{Config.colors['yellow']}Pinned: {display_text}{Config.colors['reset']}")
        else:
            # AI path: no \n from context bar, add \n after Pinned
            LogUtils.print(f"{Config.colors['yellow']}Pinned: {display_text}{Config.colors['reset']}\n")

        if _pwd_enabled:
            pwd = os.getcwd()
            LogUtils.print(f"{Config.colors['dim']}PWD: {pwd}{Config.colors['reset']}")

    def pinned_command(args):
        """Handle /pinned commands"""
        nonlocal _mode, _max_len, _pwd_enabled

        if not args:
            return _show_status()

        parts = args.strip().split(maxsplit=1)
        cmd = parts[0].lower()

        if cmd == "default":
            _mode = "default"
            return f"Pinned mode: default (auto)"
        elif cmd == "on":
            _mode = "on"
            return f"Pinned mode: on (always)"
        elif cmd == "off":
            _mode = "off"
            return f"Pinned mode: off (never)"
        elif cmd == "len":
            if len(parts) < 2:
                return f"Current max length: {_max_len} chars"
            try:
                new_len = int(parts[1])
                if new_len < 10:
                    return "Length must be at least 10"
                if new_len > 2000:
                    return "Length must be at most 2000"
                _max_len = new_len
                return f"Max length set to {_max_len} chars"
            except ValueError:
                return "Invalid number. Usage: /pinned len <number>"
        elif cmd == "status":
            return _show_status()
        elif cmd == "pwd":
            if len(parts) < 2:
                return f"PWD display: {'on' if _pwd_enabled else 'off'}"
            sub = parts[1].lower()
            if sub == "on":
                _pwd_enabled = True
                return "PWD display: on"
            elif sub == "off":
                _pwd_enabled = False
                return "PWD display: off"
            return "Usage: /pinned pwd on|off"
        else:
            return "Usage: /pinned [default|on|off|len <n>|pwd on|off|status]"

    def _show_status():
        """Show current pinned settings"""
        return f"Pinned: mode={_mode}, max_len={_max_len}, enabled={_is_enabled()}, pwd={'on' if _pwd_enabled else 'off'}, text={len(_last_text)} chars, reasoning={len(_last_reasoning)} chars"

    # Register hooks
    ctx.register_hook("after_ai_processing", after_ai_processing)
    ctx.register_hook("on_before_context_bar", on_before_context_bar)

    # Register command
    ctx.register_command("pinned", pinned_command, "Show/controls pinned message display")

    if Config.debug():
        print("[+] Pinned plugin loaded")