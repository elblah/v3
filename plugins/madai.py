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
- [CONTEXT] is special: controlled by new_context parameter
- Other tags like [SUMMARY], [SKILLS], [NOTES] are always preserved
"""

import re
from aicoder.core.config import Config

# Module-level state (shared across plugin invocations)
_pending_new_messages = None  # noqa: F841 - set during tool call, used in hook


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
        return bool(re.match(r'^\[[A-Z_-]{4,50}\]', content))

    def _is_context_message(content):
        """Check if message is a [CONTEXT] tag"""
        return content.strip().startswith("[CONTEXT]")

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
                "detailed": "The 'summary' argument is required. Example: {\"summary\": \"Implementing OAuth2...\"}"
            }

        new_context = args.get("new_context", False)

        # Store phase
        phase_num = _get_current_phase()
        phases.append({"phase": phase_num, "summary": summary})

        # Get all messages
        messages = app.message_history.get_messages()

        # Build new message list
        new_messages = []

        for msg in messages:
            content = msg.get("content", "")
            role = msg.get("role")

            # Always preserve tagged messages (any [TAG_NAME] pattern)
            if _is_tagged_message(content):
                if _is_context_message(content):
                    # Keep context only if NOT new_context mode
                    if not new_context:
                        new_messages.append(msg)
                else:
                    # Other tags like [SUMMARY], [SKILLS], [NOTES] - always keep
                    new_messages.append(msg)
            elif role == "system":
                # Always preserve system messages
                new_messages.append(msg)

        # Add new [CONTEXT] message with AI summary
        context_msg = {
            "role": "user",
            "content": f"[CONTEXT] Phase {phase_num}: {summary}"
        }
        new_messages.append(context_msg)

        # Store pending messages for replacement after tool response is added
        global _pending_new_messages
        _pending_new_messages = new_messages

        # Notify
        action = "new notebook started" if new_context else "cumulative notebook continued"

        return {
            "tool": "switch_context_phase",
            "friendly": f"[✓] Phase {phase_num} started - {action}",
            "detailed": f"Phase {phase_num} ready with {len(new_messages)} messages.\n"
                       f"Summary: {summary}\n"
                       f"Mode: {'Fresh start (new_context=true)' if new_context else 'Cumulative (new_context=false)'}"
        }

    def _after_tool_results_added(message):
        """Hook called after tool results are added to history.
        Apply pending context phase replacement."""
        global _pending_new_messages
        if _pending_new_messages is not None:
            app.message_history.replace_messages(_pending_new_messages)
            _pending_new_messages = None

    def _on_session_change():
        """Hook called before /new or /load clears the session.
        Clear session-specific state to prevent cross-session contamination."""
        global _pending_new_messages, phases
        _pending_new_messages = None
        phases = []

    # Register commands
    ctx.register_command("madai", _cmd_handler, description="madai context management")

    # Register tool
    ctx.register_tool(
        name="switch_context_phase",
        fn=_switch_context_phase,
        description=(
            "Archive current context and start a new phase with a summary. "
            "Use when you've completed a logical chunk of work and want a clean slate. "
            "All non-tagged messages are pruned. "
            "Tags preserved: any [TAG_NAME] pattern like [SUMMARY], [SKILLS]. "
            "[CONTEXT] tags preserved based on new_context parameter."
        ),
        parameters={
            "summary": {
                "type": "string",
                "description": "What you need to remember for the next phase (required)"
            },
            "new_context": {
                "type": "boolean",
                "description": "If true, prune old [CONTEXT] messages (fresh start). If false, keep cumulative (default: false)"
            }
        },
        auto_approved=True
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
