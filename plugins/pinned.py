"""
Pinned Plugin - Show last AI text message above context bar

Solves the problem of tool output flooding making it hard to follow
what the AI said last.

Commands:
  /pinned default  - Auto mode (on when details on, off when details off)
  /pinned on       - Always show
  /pinned off      - Never show
  /pinned len <n>  - Set max characters (default: 300)
  /pinned status   - Show current settings
"""

from aicoder.core.config import Config


def create_plugin(ctx):
    """Pinned plugin - show last AI text message"""

    # Settings
    _mode = "default"  # "default", "on", "off"
    _max_len = 300
    _last_text = ""

    def _is_enabled():
        """Check if pinned should be shown based on mode and details setting"""
        if _mode == "on":
            return True
        if _mode == "off":
            return False
        # default: on when details is on
        return Config.detail_mode()

    def after_ai_processing(has_tool_calls: bool):
        """Capture last text message from AI"""
        nonlocal _last_text

        messages = ctx.app.message_history.get_messages()
        if not messages:
            return

        # Get last assistant message
        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                if content and isinstance(content, str):
                    text = content.strip()
                    if text:
                        _last_text = text
                break

    def on_before_context_bar(context="ai"):
        """Show pinned message before context bar"""
        if not _is_enabled():
            return

        if not _last_text:
            return

        from aicoder.utils.log import LogUtils

        # Truncate if needed
        display_text = _last_text
        if len(display_text) > _max_len:
            display_text = display_text[:_max_len] + "..."

        # Replace newlines with spaces for single line display
        display_text = " ".join(display_text.split())

        # Core behavior:
        # - AI path: no \n before context bar
        # - User path: \n before context bar
        # Plugin must adapt spacing based on context
        if context == "user":
            # User path: context bar adds \n before, add \n before Last
            LogUtils.print(f"\n{Config.colors['yellow']}Last: {display_text}{Config.colors['reset']}")
        else:
            # AI path: no \n from context bar, add \n after Last
            LogUtils.print(f"{Config.colors['yellow']}Last: {display_text}{Config.colors['reset']}\n")

    def pinned_command(args):
        """Handle /pinned commands"""
        nonlocal _mode, _max_len

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
        else:
            return "Usage: /pinned [default|on|off|len <n>|status]"

    def _show_status():
        """Show current pinned settings"""
        return f"Pinned: mode={_mode}, max_len={_max_len}, enabled={_is_enabled()}, last_text={len(_last_text)} chars"

    # Register hooks
    ctx.register_hook("after_ai_processing", after_ai_processing)
    ctx.register_hook("on_before_context_bar", on_before_context_bar)

    # Register command
    ctx.register_command("pinned", pinned_command, "Show/controls pinned message display")

    if Config.debug():
        print("[+] Pinned plugin loaded")