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

        # Special case: ***ENTIRE_SESSION***
        if tag_name == "***ENTIRE_SESSION***":
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

        # Special case: ***START*** - replace from after [SECTIONS] to first section (or end if no sections)
        if tag_name == "***START***":
            sections_index = _get_sections_message_index()
            if sections_index is None:
                return {
                    "tool": "replace_context_section",
                    "friendly": "[!] Could not find [SECTIONS] message",
                    "detailed": "Could not find [SECTIONS] marker in message history.",
                }

            all_sections = _find_all_sections()
            last_tool_call_index = _find_last_tool_call_index()

            if last_tool_call_index == -1:
                return {
                    "tool": "replace_context_section",
                    "friendly": "[!] Could not find tool call message",
                    "detailed": "Could not find the assistant message with tool_calls.",
                }

            # Start after [SECTIONS]
            start_index = sections_index + 1

            # End at first section (if exists) or last tool call
            if all_sections:
                end_index = all_sections[0][0]  # First section's message index
            else:
                # No sections - same as ENTIRE_SESSION
                end_index = last_tool_call_index

            if start_index >= end_index:
                return {
                    "tool": "replace_context_section",
                    "friendly": "[!] Nothing to replace",
                    "detailed": "No messages between [SECTIONS] and first section (or end of context).",
                }

            removed_count = _replace_range_with_summary(
                start_index, end_index, "***START***", summary
            )

            return {
                "tool": "replace_context_section",
                "friendly": f"[✓] ***START*** replaced (removed {removed_count} messages)",
                "detailed": f"Replaced context from [SECTIONS] to first section (or end) with summary. Removed {removed_count} messages.",
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
                           f"to mark the section before calling replace_context_section. "
                           f"Use '***START***' or '***ENTIRE_SESSION***' for special operations.",
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
            "⚠️ IMPORTANT: Tag must be on FIRST LINE of a message (only thing on that line). Send section marker, do work, THEN call this tool.\n\n"
            "Summary should include: what you did, files/lines modified, decisions, failed approaches.\n"
            "Guidelines: be specific (files, lines), concise (50-200 tokens), assertive (no questions).\n\n"
            "Special tags:\n"
            "- '***START***' - Replace from after [SECTIONS] to first tagged section (or end if no sections)\n"
            "- '***ENTIRE_SESSION***' - Replace everything after [SECTIONS] message (clean slate)\n\n"
            "Args:\n"
            "- tag (required): Section tag name (e.g., 'edit_auth_system', 'debug_crash') or special tag ('***START***', '***ENTIRE_SESSION***')\n"
            "- summary (required): What was accomplished (specific files, lines, outcomes)"
        ),
        parameters={
            "type": "object",
            "properties": {
                "tag": {"type": "string", "description": "Section tag name (e.g., 'file_search', 'exploration') or special tag ('***START***', '***ENTIRE_SESSION***')"},
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

⚠️ NOTE: This message is AUTOMATICALLY INSERTED by aicoder to educate the AI. It is NOT controlled by the user.

AI can organize conversation through section tagging and selective replacement.

This is a helpful tool to keep context tidy - use it when it makes sense.

=== TIMING: CLEAR AT START, NOT END ===
When you do replace sections, do it at the BEGINNING of each interaction (before starting new work), not at the end.
- START: Think about what previous info is still needed → optionally call replace_context_section() to clear old sections
- THEN: Tag new work → Do work → Finish/stop
- This way sections persist for follow-up questions in the next prompt

Only replace when it's clear the information won't be needed anymore. It's perfectly fine to keep sections around if they might be useful.

=== USAGE PATTERN ===
✓ Mark sections BEFORE exploratory work or tool usage (searches, file reads, debugging)
✓ Use descriptive tags to help organize your thoughts
✓ Sections help keep conversations organized when working on complex tasks
✓ Only use sections when there's actual work being done

=== SECTION NAMING ===
Use descriptive tags: `edit_auth_system`, `debug_crash`, `search_database`, `run_tests`
Avoid: `section1`, `task`, `work` (too vague)

=== WHEN TO USE SECTIONS ===
Use sections for: file operations, searches, edits, debugging, multi-step tasks
Skip sections for: single-line answers, simple clarifications, confirmations

=== COMMON MISTAKES ===
- Tag not on first line - must be the ONLY content on line 1
- Trying to replace section in same message - need at least one message between
- Using vague tag names - use descriptive tags like `edit_user_auth` not `task1'
- Using XML syntax for replace_context_section - call it as a FUNCTION, not XML!

=== WRITING EFFECTIVE SUMMARIES ===

**Include:**
- What you did (task completed)
- Key decisions with rationale (if applicable)
- Files modified/created (with paths and line numbers)
- Failed approaches to avoid repeating (if any)

**Guidelines:**
- Be specific: file paths, function names, line numbers
- Be concise: 50-200 tokens depending on complexity
- Be assertive: no questions at the end
- No meta-commentary: the summary IS the output

=== SECTION LIFECYCLE ===

- Sections marked with `<begin-section>` remain in context until you replace them
- If you never replace a section, it will eventually be collected by auto compaction
- Auto compaction replaces old messages (including unreplaced sections) with `[SUMMARY]`
- Use `replace_context_section()` to control what gets summarized and when
- `[SECTION_SUMMARY]` messages from manual replacement are preserved through auto compaction

=== HOW TO USE ===

**STEP 1 - START A SECTION (before doing work):**

AI writes: <begin-section>SECTION_TAG</begin-section>

I'll now search the files...

Use any descriptive tag name (e.g., "file_search", "exploration", "debug_session").
Mark the section BEFORE starting work.

The `<begin-section>TAG_NAME</begin-section>` MUST be the FIRST LINE of the message
with ONLY the tag on that line. Add an empty line after the tag for readability.

Valid:
<begin-section>exploring_file_search</begin-section>

I'll explore the file search now...

**STEP 2 - DO YOUR WORK:**
Use tools, read files, grep, etc. within the section.

**OPTIONAL: LATER - REPLACE OLD SECTIONS:**
When starting a new interaction and it's clear previous info won't be needed, call:
replace_context_section(tag='SECTION_TAG', summary='key findings')

Note: begin-section uses XML tags, but replace_context_section is a FUNCTION CALL.

=== SPECIAL TAGS ===

Use tag='***START***' to replace context from after [SECTIONS] to the first tagged section.
Useful for clearing initial context while preserving later sections.

Use tag='***ENTIRE_SESSION***' to replace EVERYTHING after [SECTIONS] message with a summary.
This gives you a clean slate. No <begin-section> needed.

Examples:
- replace_context_section(tag='***START***', summary='Cleared initial exploration')
- replace_context_section(tag='***ENTIRE_SESSION***', summary='Clean slate - continuing with new approach')

=== WHEN TO USE ===

- Before starting exploratory work (file searches, debugging, investigations)
- Before starting a new phase of work
- When starting a new interaction and it's clear previous info won't be needed
- Use ***ENTIRE_SESSION*** when conversation is messy and you want to restart from scratch

=== KEY POINTS ===

- Section tags are NOT parsed or treated specially - they just mark ranges
- ***ENTIRE_SESSION*** replaces everything after [SECTIONS] message
- /sections list shows all active sections
- Tags MUST be the FIRST LINE of a message (only thing on that line)
- You CANNOT create and replace a section in the same message
- Replace sections at the START of new interactions (when info is clearly not needed)

=== SECTION SUMMARY MESSAGES ===

Messages that start with `[SECTION_SUMMARY]` are ALREADY condensed summaries of previously
completed sections. When asked to summarize the entire session:

✓ DO: Acknowledge these as "Previous section summaries:" and briefly mention what they cover
✗ DON'T: Re-summarize or expand these summaries - they're already condensed
✗ DON'T: Include them in a detailed breakdown - just note their existence

Example: "Previous sections included file exploration (found the issue in utils.py line 42) and debugging (confirmed the fix)."

These summaries represent completed work that has already been condensed for efficiency.
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
