"""
Sections Plugin - AI-Controlled Context Segmentation

Allows AI to mark sections of conversation and selectively replace them with summaries,
giving AI fine-grained control over context management.

Concept: SQL-like transactions for context
- <begin-section>TAG_NAME</begin-section> - Mark section start
- replace_context_section tool - Replace section with summary

Example workflow:
1. AI marks: <begin-section>file_search</begin-section>
2. AI searches many files (30+ tool calls)
3. AI finds the answer
4. AI calls: replace_context_section("file_search", "Found function in utils.py line 42")
5. Section is replaced with summary, rest of history preserved

Tool:
- replace_context_section: Replace a tagged section or entire session with a summary

Commands:
- /sections list - List all active section tags in conversation
"""

import re
from aicoder.core.config import Config
from aicoder.utils.log import LogUtils


def create_plugin(ctx):
    """Sections plugin - AI-controlled context segmentation"""

    app = ctx.app
    tag_pattern = re.compile(r'<begin-section>([^<]+)</begin-section>')

    def _get_sections_message_index():
        """Find the [SECTIONS] message index."""
        messages = app.message_history.get_messages()
        for i, msg in enumerate(messages):
            content = msg.get("content", "")
            if isinstance(content, list):
                continue
            if content.startswith("[SECTIONS]"):
                return i
        return None

    def _find_all_sections():
        """
        Find all section tags and their indices.

        Returns:
            list of tuples: [(index, tag_name), ...] sorted by index
        """
        messages = app.message_history.get_messages()
        sections_index = _get_sections_message_index()
        if sections_index is None:
            return []

        sections = []
        for i, msg in enumerate(messages):
            # Only assistant messages can create sections
            if msg.get("role") != "assistant":
                continue

            content = msg.get("content", "")
            if isinstance(content, list):
                continue
            if not content:
                continue

            lines = content.split('\n')
            if not lines:
                continue

            first_line = lines[0].strip()
            match = tag_pattern.match(first_line)
            if match:
                tag_name = match.group(1).strip()
                sections.append((i, tag_name))

        return sections

    def _find_last_tool_call_index():
        """
        Find the index of the last assistant message with tool_calls.

        Returns:
            int: Index of last assistant with tool_calls, or -1 if not found
        """
        messages = app.message_history.get_messages()
        for i in range(len(messages) - 1, -1, -1):
            msg = messages[i]
            if msg.get("role") == "assistant":
                tool_calls = msg.get("tool_calls", [])
                if tool_calls and len(tool_calls) > 0:
                    return i
        return -1

    def _replace_range_with_summary(start_index, end_index, tag_name, summary):
        """
        Replace a range of messages with a summary.

        Keeps messages before start_index and after end_index.
        """
        messages = app.message_history.get_messages()

        before = messages[:start_index]
        after = messages[end_index:]

        summary_msg = {
            "role": "user",
            "content": f"[SECTION_SUMMARY] {tag_name}: {summary}"
        }

        new_messages = before + [summary_msg] + after
        removed_count = end_index - start_index

        app.message_history.replace_messages(new_messages)
        app.message_history.estimate_context()

        return removed_count

    def _replace_section_with_summary(args):
        """
        Replace a tagged section of message history with a summary.

        Special case: tag='ENTIRE_SESSION' replaces everything after [SECTIONS].
        Normal case: replaces from section start to next section start (or tool call).
        """
        tag_name = args.get("tag")
        summary = args.get("summary")

        if not tag_name or not summary:
            return {
                "tool": "replace_context_section",
                "friendly": "[!] Error: tag and summary are required",
                "detailed": "Both 'tag' and 'summary' parameters are required."
            }

        messages = app.message_history.get_messages()

        if len(messages) < 2:
            return {
                "tool": "replace_context_section",
                "friendly": "[!] Not enough messages to replace",
                "detailed": "Need at least 2 messages in history.",
            }

        # Special case: ENTIRE_SESSION
        if tag_name == "ENTIRE_SESSION":
            sections_index = _get_sections_message_index()
            if sections_index is None:
                return {
                    "tool": "replace_context_section",
                    "friendly": "[!] Could not find [SECTIONS] message",
                    "detailed": "Could not find [SECTIONS] marker in message history.",
                }

            last_tool_call_index = _find_last_tool_call_index()
            if last_tool_call_index == -1:
                return {
                    "tool": "replace_context_section",
                    "friendly": "[!] Could not find tool call message",
                    "detailed": "Could not find the assistant message with tool_calls.",
                }

            start_index = sections_index + 1
            end_index = last_tool_call_index

            if start_index >= end_index:
                return {
                    "tool": "replace_context_section",
                    "friendly": "[!] Nothing to replace",
                    "detailed": "No messages between [SECTIONS] and current message.",
                }

            removed_count = _replace_range_with_summary(
                start_index, end_index, "***ENTIRE_SESSION***", summary
            )

            return {
                "tool": "replace_context_section",
                "friendly": f"[✓] ***ENTIRE_SESSION*** replaced (removed {removed_count} messages)",
                "detailed": f"Replaced entire session context with summary. Removed {removed_count} messages.",
            }

        # Normal case: find and replace tagged section
        all_sections = _find_all_sections()

        # Find the section to replace
        section_start = None
        section_index_in_list = None
        for idx, (msg_idx, tag) in enumerate(all_sections):
            if tag == tag_name:
                section_start = msg_idx
                section_index_in_list = idx
                break

        if section_start is None:
            return {
                "tool": "replace_context_section",
                "friendly": f"[!] Section '{tag_name}' not found",
                "detailed": f"No section with tag '{tag_name}' found in message history. "
                           f"Make sure you used <begin-section>{tag_name}</begin-section> "
                           f"to mark the section before calling replace_context_section.",
            }

        # Find end: either next section start or last tool call
        last_tool_call_index = _find_last_tool_call_index()
        if last_tool_call_index == -1:
            return {
                "tool": "replace_context_section",
                "friendly": "[!] Could not find tool call message",
                "detailed": "Could not find the assistant message with tool_calls.",
            }

        # Check if there's a next section
        if section_index_in_list + 1 < len(all_sections):
            next_section_start = all_sections[section_index_in_list + 1][0]
            end_index = min(next_section_start, last_tool_call_index)
        else:
            # No next section - use last tool call
            end_index = last_tool_call_index

        if section_start >= end_index:
            return {
                "tool": "replace_context_section",
                "friendly": "[!] Nothing to replace",
                "detailed": f"Section '{tag_name}' has no content to replace.",
            }

        removed_count = _replace_range_with_summary(section_start, end_index, tag_name, summary)

        return {
            "tool": "replace_context_section",
            "friendly": f"[✓] Section '{tag_name}' replaced (removed {removed_count} messages)",
            "detailed": f"Replaced section '{tag_name}' with summary. Removed {removed_count} messages.",
        }

    def _list_sections(args_str):
        """List all active section tags in conversation."""
        all_sections = _find_all_sections()

        if not all_sections:
            return "No active section tags found in conversation."

        output = "Active section tags:\n"
        for i, (_, tag_name) in enumerate(all_sections, 1):
            output += f"  {i}. {tag_name}\n"
        output += f"\nTotal: {len(all_sections)} active section(s)\n"

        return output

    def _cmd_handler(args_str):
        """Handle /sections commands"""
        args = args_str.strip().split(maxsplit=1) if args_str.strip() else []

        if not args:
            return "Use: /sections list"

        command = args[0]

        if command == "list":
            return _list_sections(args[1] if len(args) > 1 else "")
        else:
            return f"Unknown command: {command}. Use: /sections list"

    # Register tool
    ctx.register_tool(
        name="replace_context_section",
        fn=_replace_section_with_summary,
        description=(
            "Replace a tagged section of message history with a summary.\n\n"
            "⚠️ IMPORTANT: You must have marked a section FIRST with <begin-section>YOUR_TAG</begin-section> on the FIRST LINE of a message (only thing on that line). Add an empty line after for readability. You can write any content after the first line.\n\n"
            "⚠️ CRITICAL: You CANNOT create and replace a section in the same message. Send the section marker in one message, do work (or send another message), THEN call this tool.\n\n"
            "=== SPECIAL CASE: ENTIRE_SESSION ===\n"
            "Use tag='ENTIRE_SESSION' to replace EVERYTHING after [SECTIONS] message with a summary.\n"
            "This gives you a clean slate. No <begin-section> needed. Use this to fresh start when conversation is\n"
            "messy or you want to restart.\n\n"
            "=== NORMAL SECTIONS ===\n"
            "Workflow:\n"
            "1. Message 1: <begin-section>your_tag</begin-section> on first line, empty line, then your content\n"
            "2. Message 2+: Do your work (file searches, debugging, exploration)\n"
            "3. Later message: replace_context_section(tag='your_tag', summary='key findings')\n\n"
            "The section (from <begin-section> to next section or end) will be replaced with your summary.\n"
            "All other messages are preserved.\n\n"
            "Args:\n"
            "- tag (required): The section tag name (e.g., 'file_search', 'exploration') or 'ENTIRE_SESSION' for clean slate\n"
            "- summary (required): What to replace the section with (key findings, conclusion)\n\n"
            "When to use:\n"
            "- After finding what you were looking for\n"
            "- Before starting a new phase of work\n"
            "- After debugging and finding root cause\n"
            "- Anytime you want to reduce context noise without losing findings\n"
            "- Use ENTIRE_SESSION when you want a completely fresh start"
        ),
        parameters={
            "type": "object",
            "properties": {
                "tag": {"type": "string", "description": "Section tag name (e.g., 'file_search', 'exploration')"},
                "summary": {"type": "string", "description": "Summary of what was accomplished/found in this section"}
            },
            "required": ["tag", "summary"]
        },
        auto_approved=True
    )

    # Register command
    ctx.register_command("sections", _cmd_handler, description="List sections: /sections list")

    # Register hook
    def _ensure_sections_message():
        """Ensure [SECTIONS] message exists in message history."""
        sections_text = """[SECTIONS] Collaborative Context Segmentation

Both AI and user can organize conversation through section tagging and selective replacement.

=== HOW TO USE ===

**STEP 1 - START A SECTION (before doing work):**

AI writes: <begin-section>SECTION_TAG</begin-section>

I'll now search the files...

Use any descriptive tag name (e.g., "file_search", "exploration", "debug_session").
⚠️ IMPORTANT: Mark the section BEFORE starting work you want to summarize later.

⚠️ CRITICAL: The <begin-section>TAG_NAME</begin-section> MUST be the FIRST LINE of the message
with ONLY the tag on that line. Add an empty line after the tag for readability. You can write any content after the first line.

Valid:
<begin-section>exploring_file_search</begin-section>

I'll explore the file search now...

Invalid (tag embedded in text):
I was exploring and found: <begin-section>exploring_file_search</begin-section>
I'll explore more...

Invalid (tag not on first line):
I was exploring and found:

<begin-section>exploring_file_search</begin-section>
I'll explore more...

**STEP 2 - DO YOUR WORK:**
Use tools, read files, grep, etc. within the section.

**STEP 3 - REPLACE THE SECTION (when done):**
replace_context_section(tag='SECTION_TAG', summary='key findings here')

=== SPECIAL: ENTIRE_SESSION ===

Use tag='ENTIRE_SESSION' to replace EVERYTHING after [SECTIONS] message with a summary.
This gives you a clean slate. No <begin-section> needed.

Example: replace_context_section(tag='ENTIRE_SESSION', summary='Clean slate - continuing with new approach')

=== WHEN TO USE ===

✓ Before starting exploratory work (file searches, debugging, investigations)
✓ After you find what you were looking for
✓ Before starting a new phase of work
✓ Anytime you want to reduce context noise without losing findings
✓ Use ENTIRE_SESSION when conversation is messy or you want to restart from scratch

=== KEY POINTS ===

- Section tags are NOT parsed or treated specially - they just mark ranges
- ENTIRE_SESSION replaces everything after [SECTIONS] message
- /sections list shows all active sections
- IMPORTANT: Tags MUST be the FIRST LINE of a message (only thing on that line)
- CRITICAL: You CANNOT create and replace a section in the same message.
  - You must send one message with <begin-section>TAG</begin-section>
  - Then do some work (or at least send another message)
  - THEN call replace_context_section in a separate message
"""

        messages = app.message_history.messages

        # Find and replace existing [SECTIONS] message
        for idx, msg in enumerate(messages):
            content = msg.get("content", "")
            if msg.get("role") == "user" and content.startswith("[SECTIONS]"):
                messages[idx]["content"] = sections_text
                return

        # Add if missing (after system message at index 0)
        messages.insert(1, {
            "role": "user",
            "content": sections_text
        })

    ctx.register_hook("before_user_prompt", _ensure_sections_message)

    if Config.debug():
        LogUtils.print("[+] sections plugin loaded")
        LogUtils.print("  - replace_context_section tool")
        LogUtils.print("  - /sections list command")
