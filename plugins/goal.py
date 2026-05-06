"""
Goal Plugin - Session goal that persists through compaction and load

Design:
- Single session goal stored in memory
- [GOAL] message injected at conversation start
- Auto-restored after load/compaction via hooks
- No file persistence - relies on session save/load

Commands:
- /goal           - Show current goal
- /goal <text>    - Set session goal
- /goal clear     - Clear goal
"""

from aicoder.core.config import Config
from aicoder.utils.log import LogUtils


def _extract_goal_from_message(content: str) -> str | None:
    """Extract goal text from [GOAL] message content"""
    prefix = "[GOAL] Session goal: "
    if content.startswith(prefix):
        return content[len(prefix):]
    return None


def _generate_goal_message(goal: str | None) -> str:
    """Generate [GOAL] message content"""
    if goal:
        return f"[GOAL] Session goal: {goal}"
    return "[GOAL] No goal set. Use /goal <text> to set one."


def _find_goal_index(messages: list) -> int | None:
    """Find index of [GOAL] message, or None if not found"""
    from aicoder.core.message_history import MessageHistory
    for i, msg in enumerate(messages):
        if msg.get("role") == "user":
            content = MessageHistory._get_content_as_string(msg.get("content", ""))
            if content and content.startswith("[GOAL]"):
                return i
    return None


def create_plugin(ctx):
    """Goal plugin"""

    # Goal stored in memory
    current_goal = None

    def _sync_goal_from_messages(messages: list):
        """Extract and sync goal from loaded messages"""
        nonlocal current_goal
        for msg in messages:
            if msg.get("role") == "user":
                content = msg.get("content", "")
                if isinstance(content, str) and content.startswith("[GOAL]"):
                    current_goal = _extract_goal_from_message(content)
                    return  # Found it, stop

    def _ensure_goal_message(message_history):
        """Ensure [GOAL] message exists, recreate if needed or missing"""
        messages = message_history.messages
        
        # Check if [GOAL] message exists
        idx = _find_goal_index(messages)
        
        if idx is not None:
            # Already exists, ensure it has current goal text
            messages[idx]["content"] = _generate_goal_message(current_goal)
        else:
            # Missing - insert after system message
            messages.insert(1, {
                "role": "user",
                "content": _generate_goal_message(current_goal)
            })

    def _on_after_messages_set(messages: list):
        """Hook: sync goal from loaded messages"""
        _sync_goal_from_messages(messages)

    def _on_before_user_prompt():
        """Hook: ensure [GOAL] message exists"""
        _ensure_goal_message(ctx.app.message_history)

    def _handle_goal_command(args_str: str) -> str:
        """Handle /goal commands"""
        nonlocal current_goal
        args = args_str.strip()

        if not args or args == "show":
            # Show current goal
            if current_goal:
                return f"Current goal: {current_goal}"
            return "No goal set. Use /goal <text> to set one."

        if args == "clear":
            current_goal = None
            _ensure_goal_message(ctx.app.message_history)
            return "Goal cleared."

        if args.startswith("clear "):
            return "Use /goal clear (without arguments) to clear the goal."

        # Set goal
        current_goal = args
        _ensure_goal_message(ctx.app.message_history)
        return f"Goal set: {args}"

    # Register hooks
    ctx.register_hook("after_messages_set", _on_after_messages_set)
    ctx.register_hook("before_user_prompt", _on_before_user_prompt)

    # Register command
    ctx.register_command("goal", _handle_goal_command, description="Manage session goal")

    if Config.debug():
        LogUtils.print(f"[goal] Plugin loaded")

    return {}