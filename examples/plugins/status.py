"""
Status Plugin - Show AI's current task in context bar

The AI uses <status> tags to indicate what it's currently doing.
Status is displayed before the context bar.

Usage: AI outputs <status>Reading codebase</status> in its response.
Status must be 3-5 words max.
"""

import re
from typing import Optional
from aicoder.core.config import Config


def create_plugin(ctx):
    """Status plugin - show AI's current task"""

    _current_status = ""
    _status_pattern = re.compile(r"<status>(.*?)</status>", re.IGNORECASE)

    def get_system_prompt_addition():
        """Return status instructions for system prompt"""
        return """Status Tags:
Before EVERY tool call or significant action, output <status>current task</status> tags.
Status must be 3-5 words max. ALWAYS use status tags. Examples:
- Before list_directory: <status>Listing files</status>
- Before grep: <status>Searching codebase</status>
- Before run_shell_command: <status>Running command</status>
- Before write_file: <status>Writing file</status>
- Before read_file: <status>Reading file</status>
- When thinking: <status>Analyzing</status>
- When done: <status></status>

You MUST output status tags before EVERY tool call. This is required."""

    def after_ai_processing(has_tool_calls: bool):
        """Parse status from AI response"""
        nonlocal _current_status

        messages = ctx.app.message_history.get_messages()
        if not messages:
            return

        # Get last assistant message
        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                if content:
                    # Find last status tag
                    matches = _status_pattern.findall(content)
                    if matches:
                        last_status = matches[-1].strip()
                        _current_status = last_status if last_status else ""
                    else:
                        _current_status = ""
                break

    def on_before_context_bar(context="ai"):
        """Show status before context bar"""
        if _current_status:
            # Print status line with separator
            from aicoder.utils.log import LogUtils
            print()  # Empty line before status
            LogUtils.print(f"{Config.colors['cyan']}Status: {_current_status}{Config.colors['reset']}")

    # Register hooks
    ctx.register_hook("on_system_prompt_append", get_system_prompt_addition)
    ctx.register_hook("after_ai_processing", after_ai_processing)
    ctx.register_hook("on_before_context_bar", on_before_context_bar)

    if Config.debug():
        print("[+] Status plugin loaded")
