"""
Compact command implementation
"""

from typing import List, Dict, Any
from .base import BaseCommand, CommandResult
from aicoder.core.config import Config
from aicoder.utils.log import info, LogUtils


class CompactCommand(BaseCommand):
    """Compact conversation history"""

    def __init__(self, context):
        super().__init__(context)
        self._name = "compact"
        self._description = "Compact conversation history"
        self.usage = "/compact [force <N> | force-messages <N> | prune [all|stats|<N>] | highlander | hm]"
        self._help_text = """Compact conversation history.

Usage:
  /compact                 - Auto-compact if needed
  /compact force <N>       - Compact N oldest rounds (positive) or keep only |N| newest (negative)
  /compact force -1        - Keep only newest round, compact all others
  /compact force 3         - Compact 3 oldest rounds
  /compact force-messages <N> - Compact N oldest messages (positive) or keep only |N| newest (negative)
  /compact force-messages -15 - Keep only 15 newest messages, compact rest
  /compact prune all       - Remove all pruned tool results
  /compact prune stats     - Remove only tool=stats results
  /compact prune <N>       - Remove N oldest (positive) or keep only |N| newest (negative) tool results
  /compact prune -10       - Keep only 10 newest tool results, prune all others
  /compact highlander      - Keep only the most recent [SUMMARY] message
  /compact hm              - Keep only the last message (highlight-message mode, inserts placeholder if last message is not a user message)
  /compact stats           - Show conversation statistics"""

    def get_name(self) -> str:
        """Command name"""
        return self._name

    def get_description(self) -> str:
        """Command description"""
        return self._description

    def get_aliases(self) -> List[str]:
        return ["c"]

    def execute(self, args: List[str] = None) -> CommandResult:
        """Execute compact command"""
        if args is None:
            args = []

        # Check for stats command first since it returns CommandResult
        if len(args) >= 1 and args[0].lower() == "stats":
            return self._show_stats()

        parsed = self._parse_args(args)

        # Check if help was requested or there was an error (these cases don't require compaction)
        if parsed.get("help") or parsed.get("error"):
            # Help was shown or error occurred, no further action needed
            return CommandResult(should_quit=False, run_api_call=False)

        # Check if this is a prune operation
        if parsed.get("is_prune_operation"):
            return self._handle_prune(parsed)

        self._handle_compact(parsed)

        return CommandResult(should_quit=False, run_api_call=False)

    def _parse_args(self, args: List[str]) -> Dict[str, Any]:
        """Parse command arguments"""
        parsed = {}

        if not args:
            return parsed  # Normal auto-compact

        command = args[0].lower()

        if command == "force" and len(args) > 1:
            parsed["force"] = True
            try:
                parsed["count"] = int(args[1]) if args[1] else 1
            except ValueError:
                parsed["count"] = 1
        elif command == "force-messages" and len(args) > 1:
            parsed["force_messages"] = True
            try:
                parsed["count"] = int(args[1]) if args[1] else 1
            except ValueError:
                parsed["count"] = 1
        elif command == "prune":
            parsed["prune"] = args[1].lower() if len(args) > 1 else "all"
            if parsed["prune"] not in ["all", "stats"]:
                try:
                    parsed["count"] = int(parsed["prune"])
                    if parsed["count"] == 0:
                        LogUtils.error(f"[X] Invalid prune count: {parsed['prune']}")
                        LogUtils.error(f"[i] Usage: {self.usage}")
                        return {"error": True}
                except ValueError:
                    LogUtils.error(f"[X] Invalid prune count: {parsed['prune']}")
                    LogUtils.error(f"[i] Usage: {self.usage}")
                    return {"error": True}
            # Mark this as a prune operation that should be handled separately
            parsed["is_prune_operation"] = True
        elif command == "stats":
            # Stats is handled in execute() method to avoid type issues
            parsed["stats"] = True
        elif command == "highlander":
            parsed["highlander"] = True
        elif command == "hm":
            parsed["hm"] = True
        elif command == "help":
            self._show_help()
            return {"help": True}  # Return special flag to indicate help was shown
        else:
            LogUtils.error(f"[X] Unknown compact command: {command}")
            LogUtils.error(f"[i] Usage: {self.usage}")
            return {"error": True}  # Return error flag

        return parsed

    def _handle_compact(self, args: Dict[str, Any]) -> None:
        """Handle compaction operations"""
        # Check for special flags first
        if args.get("help") or args.get("error"):
            # Help was already displayed or there was an error, so don't proceed with compaction
            return

        message_history = self.context.message_history
        message_history.estimate_context()  # Update token estimate
        current_tokens = self.context.stats.current_prompt_size or 0
        threshold = Config.auto_compact_threshold()
        rounds = message_history.get_round_count()

        if args.get("force"):
            message_history.force_compact_rounds(args.get("count", 1))
            return

        if args.get("force_messages"):
            message_history.force_compact_messages(args.get("count", 1))
            return

        if args.get("highlander"):
            pruned = message_history.prune_old_summaries()
            if pruned > 0:
                LogUtils.success(f"[✓] Highlander: removed {pruned} old [SUMMARY] message(s)")
                LogUtils.print("    Only the last [SUMMARY] remains")
            else:
                LogUtils.warn("[i] Highlander: 0 or 1 [SUMMARY] messages found - nothing to prune")
            return

        if args.get("hm"):
            pruned = message_history.keep_last_message()
            if pruned > 0:
                LogUtils.success(f"[✓] Highlight-message: removed {pruned} message(s), keeping only last")
            else:
                LogUtils.warn("[i] Highlight-message: only 0 or 1 message(s) found - nothing to remove")
            return

        # Normal auto-compaction
        if not Config.auto_compact_enabled():
            LogUtils.warn("[i] Auto-compaction is disabled")
            return

        if rounds == 0:
            LogUtils.warn("[i] No messages available to compact")
            return

        percentage = (current_tokens / threshold * 100) if threshold > 0 else 0
        if percentage < 80:
            LogUtils.warn(
                f"[i] Auto-compaction not needed ({percentage:.1f}% of {threshold:,} tokens)"
            )
            LogUtils.warn(
                f"[i] Current conversation: {rounds} rounds (user + assistant exchanges)"
            )
            return

        try:
            message_history.compact_memory()
        except Exception as e:
            LogUtils.error(f"[X] Compaction failed: {e}")

    def _show_stats(self) -> CommandResult:
        """Show conversation statistics"""
        message_history = self.context.message_history
        message_history.estimate_context()  # Update token estimate
        current_tokens = self.context.stats.current_prompt_size or 0
        threshold = Config.auto_compact_threshold()
        rounds = message_history.get_round_count()
        percentage = (current_tokens / threshold * 100) if threshold > 0 else 0

        info("Conversation Statistics:")
        LogUtils.print(f"  Rounds (user+assistant): {rounds}")
        LogUtils.print(f"  Messages (total): {message_history.get_message_count()}")
        LogUtils.print(
            f"  Token usage: {current_tokens:,} / {threshold:,} ({percentage:.1f}%)"
        )
        LogUtils.print(
            f"  Auto-compaction: {'enabled' if Config.auto_compact_enabled() else 'disabled'}"
        )
        LogUtils.print(f"  Total compactions: {message_history.get_compaction_count()}")

        return CommandResult(should_quit=False, run_api_call=False)

    def _handle_prune(self, args: Dict[str, Any]) -> CommandResult:
        """Handle prune operations"""
        message_history = self.context.message_history
        stats = message_history.get_tool_call_stats()

        if args.get("prune") == "stats":
            info("Tool Call Statistics:")
            LogUtils.print(f"  Tool results: {stats['count']}")
            LogUtils.print(f"  Estimated tokens: {stats['tokens']:,}")
            LogUtils.print(f"  Total bytes: {stats['bytes']:,}")

            if stats['count'] > 0:
                avg_bytes = round(stats['bytes'] / stats['count'])
                avg_tokens = round(stats['tokens'] / stats['count'])
                LogUtils.print(
                    f"  Average per result: {avg_bytes} bytes, {avg_tokens} tokens"
                )

            return CommandResult(should_quit=False, run_api_call=False)

        prune_all = args.get("prune") == "all"
        prune_count = 0 if prune_all else args.get("count", 1)

        if stats['count'] == 0:
            LogUtils.warn("[i] No tool results to prune")
            return CommandResult(should_quit=False, run_api_call=False)

        if prune_all:
            pruned_count = message_history.prune_all_tool_results()
            LogUtils.success(f"[✓] Pruned {pruned_count} tool result(s)")
        else:
            if prune_count < 0:
                # Negative count: keep only |prune_count| newest results
                keep_count = abs(prune_count)
                pruned_count = message_history.prune_keep_newest_tool_results(keep_count)
                if pruned_count > 0:
                    LogUtils.success(f"[✓] Kept {keep_count} newest tool result(s), pruned {pruned_count} older result(s)")
                else:
                    LogUtils.warn(f"[i] Keeping all {stats['count']} tool result(s) (already ≤ {keep_count})")
            else:
                # Positive count: prune prune_count oldest results
                to_prune = min(prune_count, stats['count'])
                pruned_count = message_history.prune_oldest_tool_results(to_prune)
                LogUtils.success(f"[✓] Pruned {pruned_count} oldest tool result(s)")

        return CommandResult(should_quit=False, run_api_call=False)

    def _show_help(self) -> Dict[str, Any]:
        """Show help for compact command"""
        info("Compact Command Help:")
        LogUtils.print(f"  {self.usage}")
        LogUtils.print("  ")
        LogUtils.print("  Commands:")
        LogUtils.print("    /compact                    Try auto-compaction")
        LogUtils.print("    /compact force <N>           Force compact N oldest rounds")
        LogUtils.print("    /compact force -<N>          Keep only N newest rounds, compact rest")
        LogUtils.print(
            "    /compact force-messages <N>   Force compact N oldest messages"
        )
        LogUtils.print("    /compact force-messages -<N> Keep only N newest messages, compact rest")
        LogUtils.print("    /compact prune all           Prune all tool call results")
        LogUtils.print("    /compact prune stats         Show tool call statistics")
        LogUtils.print(
            "    /compact prune <N>           Prune N oldest (positive) or keep only |N| newest (negative)"
        )
        LogUtils.print(
            "    /compact prune -<N>          Keep only N newest tool results, prune all others"
        )
        LogUtils.print("    /compact stats               Show conversation statistics")
        LogUtils.print("    /compact highlander          Keep only last [SUMMARY] (there can be only one)")
        LogUtils.print("    /compact hm                  Keep only last message (inserts placeholder if last is not user)")
        LogUtils.print("    /compact help                Show this help")
        LogUtils.print("  ")
        LogUtils.print("  Examples:")
        LogUtils.print("    /compact force 3            Compact 3 oldest rounds")
        LogUtils.print("    /compact force -1            Keep only newest round, compact rest")
        LogUtils.print("    /compact force -3            Keep 3 newest rounds, compact rest")
        LogUtils.print("    /compact force-messages 15   Compact 15 oldest messages")
        LogUtils.print("    /compact force-messages -5   Keep 5 newest messages, compact rest")
        LogUtils.print("    /compact prune all           Clear all tool results")
        LogUtils.print("    /compact prune 5             Clear 5 oldest tool results")
        LogUtils.print("    /compact prune -10           Keep only 10 newest tool results")
        LogUtils.print("    /compact prune stats         Show tool call stats")
        LogUtils.print("    /compact highlander          Keep only last [SUMMARY]")
        LogUtils.print("    /compact hm                  Keep only last message")
        LogUtils.print("  ")
        LogUtils.print("  Definitions:")
        LogUtils.print("    Round = User + Assistant response (with tool calls)")
        LogUtils.print("    Message = Individual message (user, assistant, or tool)")
        LogUtils.print(
            '    Prune = Replace tool result content with "[Tool result pruned]"'
        )

        return {}
