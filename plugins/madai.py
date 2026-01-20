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
from aicoder.core.config import Config

# Module-level state (shared across plugin invocations)
_pending_summary = None  # noqa: F841 - set during tool call, used in hook


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
            return "Use: /madai status | /madai list"

        command = args[0]

        if command == "status":
            return _cmd_status(args[1] if len(args) > 1 else "")
        elif command == "list":
            return _cmd_list(args[1] if len(args) > 1 else "")
        else:
            return f"Unknown command: {command}. Use /madai status or /madai list"

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
        global _pending_summary
        if summary.strip().startswith("[CONTEXT]"):
            _pending_summary = summary.strip()
        else:
            _pending_summary = f"[CONTEXT] {summary}"

        # Notify
        return {
            "tool": "switch_context_phase",
            "friendly": f"[✓] Phase {phase_num}: Context switched",
            "detailed": f"Phase {phase_num} started",
        }

    def _after_tool_results_added(message):
        """Hook called after tool results are added to history.
        Apply pending phase switch."""
        global _pending_summary

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

        # Append the new [CONTEXT] summary
        app.message_history.add_user_message(_pending_summary)

        # Reestimate context size after pruning
        app.message_history.estimate_context()

        # Notify other plugins (e.g., madai_watcher) to reset their counters
        app.plugin_system.call_hooks("madai_progress_saved")

        # Clear pending state
        _pending_summary = None

    def _on_session_change():
        """Hook called before /new or /load clears the session.
        Clear session-specific state to prevent cross-session contamination."""
        global _pending_summary, phases
        _pending_summary = None
        phases = []

    # Register commands
    ctx.register_command("madai", _cmd_handler, description="madai context management")

    # Register tool
    ctx.register_tool(
        name="save_progress",
        fn=_switch_context_phase,
        description=(
            "Organize your thoughts and preserve important information.\n\n"
            "Research shows too much context makes AI confused and less effective. This tool solves that by letting you write a summary that REPLACES all current context.\n\n"
            "Messages starting with [TAG] like [SKILLS], [SUMMARY] are automatically preserved. System messages (your identity, instructions) are also preserved. Focus on information NOT in system or tagged messages.\n\n"
            "The summary you write becomes ALL the context you'll have. Everything not in it will be forgotten.\n\n"
            "Think: 'What do I need to remember? Names, preferences, important paths, file locations, key findings, where to find useful info...'\n\n"
            "Template:\n"
            "[CONTEXT]\n"
            "Task: What the user asked for\n"
            "Notes:\n"
            "- Names, preferences, important paths\n"
            "- File locations and line numbers\n"
            "Accomplished:\n"
            "- Key finding 1\n"
            "- Key finding 2\n"
            "- Key finding <N>\n"
            "Next: What is the last thing that happened? What needs to happen next? Be SPECIFIC.\n"
            "  - If user asked something: 'Answer user's question about X'\n"
            "  - If you were doing something: 'Continue implementing feature X'\n"
            "  - If user made a statement: 'Respond to user's point about X'\n"
            "  - Only say 'Wait for user' if conversation is genuinely finished\n\n"
            "*IMPORTANT:* Only what you write in the summary survives. Everything else is lost."
        ),
        parameters={
            "summary": {
                "type": "string",
                "description": "The [CONTEXT] content to preserve: Task, Notes, Accomplished, Next",
            }
        },
        auto_approved=True,
    )

    # Register hook to clear session state before /new or /load
    ctx.register_hook("on_session_change", _on_session_change)

    # Register hook to apply pending replacement after tool results are added
    ctx.register_hook("after_tool_results_added", _after_tool_results_added)

    if Config.debug():
        print("[+] madai plugin loaded")
        print("  - switch_context_phase tool")
        print("  - /madai status | /madai list commands")
        print("  - on_session_change hook for session cleanup")
        print("  - after_tool_results_added hook for deferred replacement")
