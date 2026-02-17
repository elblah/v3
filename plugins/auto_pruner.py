"""
Auto Pruner Plugin - Minimalist tool result pruning before AI compaction

Intercepts auto-compaction and prunes old tool results first.
If pruning reduces context below threshold, AI compaction is skipped.
This preserves context while still managing memory usage.
"""

from aicoder.core.config import Config


def create_plugin(ctx):
    """Create the auto pruner plugin"""

    def before_auto_compaction_hook():
        """
        Hook called before AI compaction.

        Strategy:
        1. Count tool results in the last round (most recent)
        2. Prune all tool results except those in the last round
        3. If pruning reduces context below threshold, skip AI compaction
        4. Return True to skip compaction, False to continue
        """
        message_history = ctx.app.message_history

        # Count tool results in the last round
        last_round_tool_count = _count_tool_results_in_last_round(message_history)

        if last_round_tool_count == 0:
            return False  # No tool results, proceed with AI compaction

        # Prune all tool results except those in the last round
        from aicoder.utils.log import LogUtils
        from aicoder.core.message_history import PRUNED_TOOL_MESSAGE

        pruned = message_history.prune_keep_newest_tool_results(last_round_tool_count)

        if pruned > 0:
            LogUtils.success(f"[*] Pruned {pruned} old tool results")

        # Check if still need compaction after pruning
        if not message_history.should_auto_compact():
            # Pruning was effective - skip AI compaction
            return True

        # Still over threshold - need AI compaction
        return False

    def _count_tool_results_in_last_round(message_history) -> int:
        """Count tool result messages in the last conversation round"""
        chat_messages = message_history.get_chat_messages()
        if not chat_messages:
            return 0

        # Start from end and count tool results until we hit a user message
        tool_count = 0
        for i in range(len(chat_messages) - 1, -1, -1):
            msg = chat_messages[i]
            if msg.get("role") == "tool":
                tool_count += 1
            elif msg.get("role") == "user":
                # Found start of last round
                break

        return tool_count

    # Register the hook
    ctx.register_hook("before_auto_compaction", before_auto_compaction_hook)

    if Config.debug():
        print("[+] Auto pruner plugin loaded")
        print("    - before_auto_compaction hook")
