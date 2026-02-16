"""
NOTES Plugin - Persistent Notes That Survive Compaction

Allows AI to save notes that persist through compaction:
- save_note tool: append or replace notes
- [NOTE] messages survive compaction
- Commands: /notes show

Notes are perfect for:
- Important file locations
- Key decisions and rationale
- Current state
- Pending tasks
- Context that shouldn't be forgotten
"""

from typing import Optional
from aicoder.utils.log import LogUtils
from aicoder.core.config import Config


def create_plugin(ctx):
    """Create the notes plugin"""

    # ==================== INTERNAL STATE ====================
    saved_notes = []  # Store notes before compaction

    # ==================== TOOL IMPLEMENTATION ====================
    def handle_save_note(args):
        """
        Save a note that persists through compaction

        Parameters:
        - action: "append" (default) or "replace"
        - content: The note content to save

        Creates a [NOTE] message that will survive compaction.
        """
        action = args.get("action", "append")
        content = args.get("content", "")

        if not content:
            return {
                "tool": "save_note",
                "friendly": "[!] No content provided",
                "detailed": "Error: content parameter is required"
            }

        if action == "replace":
            # Remove all existing [NOTE] messages
            messages = ctx.app.message_history.messages
            for i in range(len(messages) - 1, -1, -1):
                msg = messages[i]
                msg_content = msg.get("content", "")
                if isinstance(msg_content, str) and msg_content.startswith("[NOTE]"):
                    del messages[i]

        # Add new note
        note_msg = {
            "role": "user",
            "content": f"[NOTE]\n{content}"
        }
        ctx.app.message_history.add_user_message(note_msg)

        action_text = "replaced" if action == "replace" else "appended to"

        return {
            "tool": "save_note",
            "friendly": f"Note {action_text} successfully",
            "detailed": f"Saved note: {content}"
        }

    # ==================== COMMAND IMPLEMENTATION ====================
    def handle_notes_command(args_value: str) -> str:
        """Show all notes"""
        messages = ctx.app.message_history.messages

        notes = []
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str) and content.startswith("[NOTE]"):
                notes.append(content.replace("[NOTE]\n", "").strip())

        if not notes:
            return "No notes saved"

        result = "Saved Notes:\n" + "=" * 60 + "\n"
        for i, note in enumerate(notes, 1):
            result += f"{i}. {note}\n"
        result += "=" * 60

        return result

    # ==================== HOOK IMPLEMENTATION ====================
    def _before_compaction():
        """Save all [NOTE] messages before compaction"""
        nonlocal saved_notes
        messages = ctx.app.message_history.messages

        saved_notes = []
        for msg in messages:
            content = msg.get("content", "")
            if isinstance(content, str) and content.startswith("[NOTE]"):
                saved_notes.append(content)

        if Config.debug() and saved_notes:
            LogUtils.print(f"[NOTES] Saved {len(saved_notes)} note(s) before compaction")

    def _after_compaction():
        """Restore all [NOTE] messages after compaction"""
        nonlocal saved_notes

        if not saved_notes:
            return

        # Insert notes at the beginning (after system prompt)
        messages = ctx.app.message_history.messages

        # Find insertion point (after system prompt)
        insert_idx = 0
        for i, msg in enumerate(messages):
            if msg.get("role") == "system":
                insert_idx = i + 1
                break

        # Insert notes in reverse order to maintain original order
        for note in reversed(saved_notes):
            note_msg = {
                "role": "user",
                "content": note
            }
            messages.insert(insert_idx, note_msg)

        if Config.debug():
            LogUtils.print(f"[NOTES] Restored {len(saved_notes)} note(s) after compaction")

        saved_notes = []

    # ==================== REGISTRATION ====================
    # Register tool
    ctx.register_tool(
        name="save_note",
        fn=handle_save_note,
        description="Save a note that persists through compaction",
        auto_approved=True,
        parameters={
            "action": {
                "description": "Action: 'append' (default) or 'replace'",
                "type": "string",
                "enum": ["append", "replace"]
            },
            "content": {
                "description": "The note content to save",
                "type": "string"
            }
        }
    )

    # Register command
    ctx.register_command("/notes", handle_notes_command, description="Show all saved notes")

    # Register hooks
    ctx.register_hook("before_compaction", _before_compaction)
    ctx.register_hook("after_compaction", _after_compaction)

    if Config.debug():
        print("[+] Notes plugin loaded")
        print("    - save_note tool")
        print("    - /notes command")
        print("    - before_compaction hook")
        print("    - after_compaction hook")

    # Return cleanup function
    def cleanup():
        if Config.debug():
            print("[-] Notes plugin unloaded")

    return {"cleanup": cleanup}
