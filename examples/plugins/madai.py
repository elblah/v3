"""
madai.py - Memory Archival Dynamic AI

Plugin for AI self-managed context organization through conscious phase transitions.

Tool:
- switch_context_phase: Archive current context, prune noise, start fresh with summary

Commands:
- /madai status - Show current phase and last summary
- /madai list - Show all phase summaries

Tag Pattern:
- Any message starting with [WORD...] is preserved
- [CONTEXT] is created by switch_context_phase tool
- Other tags like [SUMMARY], [SKILLS], [NOTES] are always preserved
"""

import re
from datetime import datetime, timezone
from aicoder.core.config import Config
from aicoder.utils.log import LogUtils

# Module-level state (shared across plugin invocations)
_pending_summary = None  # noqa: F841 - set during tool call, used in hook
_pending_prune_old_contexts = False  # noqa: F841 - set during tool call, used in hook
_pending_context_for_compaction = None  # noqa: F841 - saved before compaction, restored after


def create_plugin(ctx):
    """Create madai plugin"""
    app = ctx.app

    # In-memory phase tracking
    phases = []  # [{phase: 1, "summary": "..."}]

    def _is_tagged_message(content):
        """Check if message starts with [TAG_NAME] pattern.

        Tag rules:
        - Must start with [ and end with ]
        - Only UPPERCASE letters (A-Z), underscores (_), or hyphens (-)
        - Minimum 4 chars (e.g., [TEST]), maximum 50 chars
        """
        return bool(re.match(r"^\[[A-Z_-]{4,50}\]", content))

    def _get_phase_count():
        return len(phases)

    def _get_current_phase():
        return len(phases) + 1

    def _get_last_summary():
        if phases:
            return phases[-1].get("summary", "No summary")
        return None

    def _prune_old_contexts():
        """Remove all [CONTEXT] messages except the last one.
        Used by /madai prune and keep_only_last_context_after option."""
        messages = app.message_history.get_messages()
        context_indices = [
            i for i, msg in enumerate(messages)
            if msg.get("content", "").startswith("[CONTEXT]")
        ]
        if len(context_indices) <= 1:
            return 0  # Nothing to prune
        # Remove old [CONTEXT]s (keep last)
        pruned_count = 0
        for idx in context_indices[:-1]:
            del messages[idx]
            pruned_count += 1
        # Reestimate context size
        app.message_history.estimate_context()
        return pruned_count

    def _cmd_status(args_str):
        """Show current phase status"""
        phase_num = _get_current_phase()
        last_summary = _get_last_summary()

        output = f"Current Phase: {phase_num}\n"

        if last_summary:
            output += f"\nLast Summary:\n{last_summary}\n"

        if phase_num == 1:
            output += "\n[Use switch_context_phase to start Phase 2]"
        else:
            output += f"\n[Use switch_context_phase to start Phase {phase_num + 1}]"

        return output

    def _cmd_list(args_str):
        """Show all phase summaries"""
        phase_count = _get_phase_count()

        if phase_count == 0:
            return "No phases yet. Use switch_context_phase to create your first phase."

        output = []
        for p in phases:
            output.append(f"Phase {p['phase']}: {p['summary']}")

        output.append(f"\nCurrent Phase: {_get_current_phase()} (see /madai status)")
        return "\n".join(output)

    def _cmd_handler(args_str):
        """Handle /madai commands"""
        args = args_str.strip().split(maxsplit=1) if args_str.strip() else []

        if not args:
            return "Use: /madai status | /madai list | /madai prune"

        command = args[0]

        if command == "status":
            return _cmd_status(args[1] if len(args) > 1 else "")
        elif command == "list":
            return _cmd_list(args[1] if len(args) > 1 else "")
        elif command == "prune":
            pruned = _prune_old_contexts()
            if pruned == 0:
                return "Only one [CONTEXT] - nothing to prune"
            return f"Pruned {pruned} old [CONTEXT] message(s)"
        else:
            return f"Unknown command: {command}. Use /madai status, list, or prune"

    def _switch_context_phase(args):
        """Switch to a new context phase"""
        summary = args.get("summary")
        if not summary:
            return {
                "tool": "switch_context_phase",
                "friendly": "Error: summary is required",
                "detailed": "The 'summary' argument is required. Follow the tool description format.",
            }

        # Store phase
        phase_num = _get_current_phase()
        phases.append({"phase": phase_num, "summary": summary})

        # Store summary for hook to use
        global _pending_summary, _pending_prune_old_contexts
        if summary.strip().startswith("[CONTEXT]"):
            _pending_summary = summary.strip()
        else:
            _pending_summary = f"[CONTEXT] {summary}"
        _pending_prune_old_contexts = args.get("keep_only_last_context_after", False)

        # Notify
        return {
            "tool": "switch_context_phase",
            "friendly": f"[✓] Phase {phase_num}: Context switched",
            "detailed": f"Phase {phase_num} started",
        }

    def _after_tool_results_added(message):
        """Hook called after tool results are added to history.
        Apply pending phase switch."""
        global _pending_summary, _pending_prune_old_contexts

        if _pending_summary is None:
            return

        # Collect tagged messages BEFORE clearing
        messages = app.message_history.get_messages()
        tagged_messages = [
            msg for msg in messages
            if _is_tagged_message(msg.get("content", ""))
        ]

        # Clear messages (keeps system prompt)
        app.message_history.clear()

        # Restore all tagged messages (including old [CONTEXT])
        for msg in tagged_messages:
            app.message_history.add_user_message(msg["content"])

        # Append the new [CONTEXT] summary with UTC timestamp for temporal context
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
        app.message_history.add_user_message(f"{_pending_summary} [{timestamp}]")

        # Add instruction message to guide AI behavior
        instruction = (
            "---\n"
            "[SYSTEM REMINDER - internal note, don't reply to this specific message]\n"
            "You ran save_progress. The [CONTEXT] above summarizes what happened.\n"
            "Your task: Continue from where you left off.\n"
            "  - If you were answering a question: Complete your answer\n"
            "  - If implementing something: Continue the task\n"
            "  - If mid tool use: Re-assess and continue\n"
            "DON'T repeat yourself - [CONTEXT] captured continuity.\n"
            "Just proceed naturally with the conversation."
        )
        app.message_history.add_user_message(instruction)

        # Prune old [CONTEXT]s if requested
        if _pending_prune_old_contexts:
            _prune_old_contexts()

        # Reestimate context size after pruning
        app.message_history.estimate_context()

        # Notify other plugins (e.g., madai_watcher) to reset their counters
        app.plugin_system.call_hooks("madai_progress_saved")

        # Clear pending state
        _pending_summary = None
        _pending_prune_old_contexts = False

    def _on_session_change():
        """Hook called before /new or /load clears the session.
        Clear session-specific state to prevent cross-session contamination."""
        global _pending_summary, _pending_prune_old_contexts, phases
        _pending_summary = None
        _pending_prune_old_contexts = False
        phases = []

    def _after_compaction():
        """Hook called after compaction completes.
        When compaction runs, we trust its summary - clear phases."""
        phases.clear()

    def _after_messages_set(messages):
        """Hook called when messages are set (e.g., after load, /m).
        Clear phases since we trust the loaded state."""
        phases.clear()

    # Register commands
    ctx.register_command("madai", _cmd_handler, description="madai context management")

    # Register tool
    ctx.register_tool(
        name="save_progress",
        fn=_switch_context_phase,
        description=(
            "Organize your thoughts and preserve important information.\n\n"
            "Research shows too much context makes AI confused and less effective. This tool gives you the ability to manage context for better performance and comprehension.\n\n"
            "🤖 TRUST YOUR JUDGMENT - This tool serves TWO purposes:\n\n"
            "1. PURE CONTEXT MANAGEMENT (use anytime YOU need it):\n"
            "• Context feels noisy but task continues\n"
            "• Before starting new major phase of work\n"
            "• Subject changing, conversation shifting focus\n"
            "• After extensive exploration when you've found what you need\n"
            "• Anytime YOU need mental clarity for better responses\n\n"
            "2. RESPONSE + PRESERVATION (when responding to user anyway):\n"
            "⚡ CRITICAL: Give your full response AND call save_progress IN THE SAME MESSAGE.\n"
            "Your text response and saved summary should be the same high-quality content.\n"
            "This provides user with rich analysis while preserving that same context.\n"
            "AVOID calling save_progress before responding - this limits your response quality.\n\n"
            "🎯 KEY GUIDELINE: Never artificially separate responding from preserving.\n"
            "But don't let this stop you from using the tool for pure context management anytime.\n\n"
            "Messages starting with [TAG] like [SKILLS], [SUMMARY] are automatically preserved. System messages (your identity, instructions) are also preserved. Focus on information NOT in system or tagged messages.\n\n"
            "The summary you write becomes ALL the context you'll have. Everything not in it will be forgotten.\n\n"
            "Think: 'What mental model, insights, and technical understanding must I preserve to continue effectively?'\n\n"
            "Template:\n"
            "[CONTEXT]\n"
            "Last Round: Brief overview (2-3 sentences max) of what was discovered and decided\n\n"
            "Problems Solved:\n"
            "- Problem #1 that was addressed\n"
            "- Problem #2 that was addressed\n"
            "- Problem #3 that was addressed\n\n"
            "Key Changes:\n"
            "- Change #1 made to files/code\n"
            "- Change #2 made to files/code\n"
            "- Change #3 made to files/code\n\n"
            "Critical Findings:\n"
            "- Most important discovery #1\n"
            "- Most important discovery #2\n"
            "- Most important discovery #3\n\n"
            "Technical Context:\n"
            "- Key files/locations: essential file paths and line numbers\n"
            "- Working understanding: what the AI knows about the system state\n"
            "- Current assumptions: what the AI is assuming to be true\n\n"
            "Task & Status:\n"
            "- Original user request\n"
            "- Current progress toward that request\n"
            "- What still needs to be done\n\n"
            "Next: Immediate next step to continue (be specific and actionable)\n\n"
            "*IMPORTANT:* Don't repeat yourself. Previous [CONTEXT] messages are preserved. If you've already introduced yourself, answered a question, or established something, don't do it again. Continue naturally from where you left off. Only new information needs to be written.\n\n"
            "Optionally set keep_only_last_context_after=true to remove old [CONTEXT] messages after this save, keeping only the new one."
        ),
        parameters={
            "summary": {
                "type": "string",
                "description": "The [CONTEXT] content to preserve: Last Round, Task, Notes, Accomplished, Next",
            },
            "keep_only_last_context_after": {
                "type": "boolean",
                "description": "If true, remove all previous [CONTEXT] messages after this save, keeping only the new one",
            }
        },
        auto_approved=True,
    )

    # Register hook to clear session state before /new or /load
    ctx.register_hook("on_session_change", _on_session_change)

    # Register hook to apply pending replacement after tool results are added
    ctx.register_hook("after_tool_results_added", _after_tool_results_added)

    # Clear phases after compaction - trust the compaction summary
    ctx.register_hook("after_compaction", _after_compaction)

    # Clear phases when messages are set (load, /m) - trust the loaded state
    ctx.register_hook("after_messages_set", _after_messages_set)

    if Config.debug():
        LogUtils.print("[+] madai plugin loaded")
        LogUtils.print("  - save_progress tool (with keep_only_last_context_after option)")
        LogUtils.print("  - /madai status | /madai list | /madai prune commands")
        LogUtils.print("  - on_session_change hook for session cleanup")
        LogUtils.print("  - after_tool_results_added hook for deferred replacement")
