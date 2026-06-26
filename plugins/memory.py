"""
Memory plugin - Auto-managed persistent memory for cross-session learning.

Creates .aicoder/memory/ structure:
  autoload.md - auto-injected into system prompt (limit configurable via LUNA_MEMORY_AUTOLOAD_LIMIT env var)
  index.md - main memory file, AI manages freely
  *.md - any additional files AI creates

The AI uses write_file/edit_file tools to manage memory naturally.
No special API calls or background processes needed.
"""

import os
from typing import List

MEMORY_DIR = ".aicoder/memory"
AUTOLOAD_FILE = os.path.join(MEMORY_DIR, "autoload.md")
INDEX_FILE = os.path.join(MEMORY_DIR, "index.md")
MAX_AUTOLOAD_BYTES = int(os.environ.get("LUNA_MEMORY_AUTOLOAD_LIMIT", "2048"))
AUTOLOAD_DISABLED = AUTOLOAD_FILE + ".disabled"


def create_plugin(ctx):
    """Memory plugin - persistent memory management"""
    _pending_check: List[str] = []

    def get_autoload() -> str | None:
        """Read autoload.md content, truncated if over limit"""
        try:
            with open(AUTOLOAD_FILE, "r", encoding="utf-8") as f:
                content = f.read()
        except (FileNotFoundError, IOError, OSError):
            return None

        if not content:
            return None

        if len(content) > MAX_AUTOLOAD_BYTES:
            from aicoder.utils.log import LogUtils
            LogUtils.warn(f"[memory] autoload.md truncated "
                          f"({len(content)} bytes, max {MAX_AUTOLOAD_BYTES})")
            trunc_note = f"\n\n[... truncated to {MAX_AUTOLOAD_BYTES} bytes ...]"
            content = content[:MAX_AUTOLOAD_BYTES - len(trunc_note)] + trunc_note

        return content

    def list_memory_files() -> list[str]:
        """List .md files in memory directory"""
        try:
            files = []
            for fname in os.listdir(MEMORY_DIR):
                if fname.endswith(".md") and os.path.isfile(os.path.join(MEMORY_DIR, fname)):
                    files.append(fname)
            return sorted(files)
        except FileNotFoundError:
            return []

    def on_autoload_write(path, _content):
        """Queue autoload.md for size check after tool results"""
        if path and path.endswith("autoload.md"):
            _pending_check.append(path)

    def on_tool_results(_tool_results):
        """Check autoload.md size after tool results"""
        while _pending_check:
            filepath = _pending_check.pop(0)
            try:
                with open(filepath, "r", encoding="utf-8") as f:
                    content = f.read()
            except (FileNotFoundError, IOError, OSError):
                continue

            if len(content) > MAX_AUTOLOAD_BYTES:
                msg = (
                    f"CRITICAL: `{filepath}` is {len(content)} bytes, "
                    f"exceeding the {MAX_AUTOLOAD_BYTES} byte limit. "
                    "Your persistent memory from `autoload.md` is being TRUNCATED. "
                    "Fix this NOW: use `edit_file` to trim `autoload.md` "
                    f"under {MAX_AUTOLOAD_BYTES} bytes, or you will lose memory each session."
                )
                from aicoder.utils.log import LogUtils
                LogUtils.warn(f"[memory] {msg}")
                if ctx.app and ctx.app.message_history:
                    ctx.app.message_history.add_user_message(msg)

    def on_system_prompt_append():
        """Inject memory info and autoload.md into system prompt"""
        autoload = get_autoload()
        files = list_memory_files()

        section = (
            "\n\n## Persistent Memory\n"
            "Memory files live in `.aicoder/memory/` (relative to CWD, already exists).\n"
            "Manage them with `write_file`/`edit_file`. Keep everything inside that directory.\n"
            "\n"
            "**How it works:**\n"
            "- `autoload.md` (< " + str(MAX_AUTOLOAD_BYTES) + " bytes) - loaded into **every session's prompt**. "
            "Put critical facts here.\n"
            "- `index.md` - main working memory (project knowledge, patterns, "
            "user preferences).\n"
            "- Create additional `.md` files for specific topics.\n"
        )

        if files:
            section += "\n### Memory Files\n"
            for name in files:
                section += f"- {name}\n"

        if autoload:
            section += "\n### autoload.md\n" + autoload

        return section

    def handle_command(args_str: str):
        """Handle /memory command"""
        from aicoder.utils.log import LogUtils

        parts = args_str.split()
        subcmd = parts[0] if parts else ""

        if subcmd == "init":
            if os.path.isdir(MEMORY_DIR):
                LogUtils.info("[memory] already initialized")
                return

            os.makedirs(MEMORY_DIR, exist_ok=True)

            # Create index.md
            index_content = (
                "# Memory Index\n\n"
                "This directory is your persistent memory. "
                "You manage these files using write_file/edit_file.\n\n"
                "## Rules\n"
                "- `autoload.md` (< " + str(MAX_AUTOLOAD_BYTES) + " bytes) - critical facts loaded into every session's "
                "prompt. Keep it concise.\n"
                "- `index.md` is your working memory. "
                "Organize project knowledge, patterns, conventions here.\n"
                "- Create additional `.md` files for specific topics as needed.\n"
                "- Update memory when you learn something important "
                "about the project or user preferences.\n\n"
                "## Guidelines\n"
                "- Be specific. Prefer facts over vague statements.\n"
                "- Replace \"today\", \"yesterday\", \"last time\" with actual dates.\n"
                "- Prune stale entries. Don't let contradictions accumulate.\n"
            )
            with open(INDEX_FILE, "w", encoding="utf-8") as f:
                f.write(index_content)

            # Create autoload.md only if it doesn't exist
            if not os.path.isfile(AUTOLOAD_FILE):
                with open(AUTOLOAD_FILE, "w", encoding="utf-8") as f:
                    f.write("_No persistent memories yet._")

            LogUtils.success(f"[memory] Memory initialized at {MEMORY_DIR}")

            # Rebuild system prompt so memory section is visible immediately
            if ctx.app and ctx.app.message_history:
                from aicoder.core.prompt_builder import PromptBuilder
                from aicoder.core.token_estimator import cache_message
                system_prompt = PromptBuilder.build_complete_system_prompt(
                    ctx.app.plugin_system
                )
                messages = ctx.app.message_history.messages
                if messages and len(messages) > 0 and messages[0].get("role") == "system":
                    messages[0]["content"] = system_prompt
                    cache_message(messages[0])

        elif subcmd == "rm-all":
            msg = "Are you sure you want to DELETE all persistent memory? [y/N] "
            import sys
            sys.stdout.write(msg)
            sys.stdout.flush()
            resp = input().strip().lower()
            if resp != "y":
                LogUtils.info("[memory] rm-all cancelled")
                return

            try:
                import shutil
                shutil.rmtree(MEMORY_DIR)
                LogUtils.warn(f"[memory] Memory directory {MEMORY_DIR} deleted")
            except FileNotFoundError:
                LogUtils.error("[memory] Memory directory does not exist")
            except PermissionError:
                LogUtils.error(f"[memory] Cannot delete {MEMORY_DIR} - permission denied")

            # Tell the AI
            if ctx.app and ctx.app.message_history:
                ctx.app.message_history.add_user_message(
                    "**Memory Reset**: The `.aicoder/memory/` directory has been deleted. "
                    "All persistent memory is gone."
                )

        elif subcmd == "status":
            if not os.path.isdir(MEMORY_DIR):
                LogUtils.info("[memory] Memory directory does not exist")
                LogUtils.info("  Use /memory init to create it")
                return

            files = []
            try:
                for fname in os.listdir(MEMORY_DIR):
                    fpath = os.path.join(MEMORY_DIR, fname)
                    if os.path.isfile(fpath):
                        size = os.path.getsize(fpath)
                        files.append((fname, size))
            except FileNotFoundError:
                LogUtils.error("[memory] Memory directory not found")
                return

            disabled = os.path.isfile(AUTOLOAD_DISABLED)

            LogUtils.print(f"\n{'[memory] Persistent Memory Status':^40}", bold=True)
            LogUtils.dim(f"{'─' * 42}")
            LogUtils.print(f"  Directory: {MEMORY_DIR}")
            LogUtils.print(f"  Autoload:  {'DISABLED' if disabled else 'ENABLED'}")
            LogUtils.dim(f"{'─' * 42}")
            for fname, size in sorted(files):
                label = fname
                if fname == "autoload.md" and disabled:
                    label += " (disabled, not loaded)"
                LogUtils.print(f"  {label:<30} {size:>7} bytes")
            LogUtils.dim(f"{'─' * 42}\n")

        elif subcmd == "on":
            if os.path.isfile(AUTOLOAD_DISABLED):
                os.rename(AUTOLOAD_DISABLED, AUTOLOAD_FILE)
                LogUtils.success("[memory] Autoload re-enabled")
                if ctx.app and ctx.app.message_history:
                    ctx.app.message_history.add_user_message(
                        "**Memory Autoload**: Persistent memory autoload is now ON. "
                        "Your session prompt will include autoload.md content again."
                    )
            else:
                LogUtils.info("[memory] Autoload is already enabled")

        elif subcmd == "off":
            if os.path.isfile(AUTOLOAD_FILE):
                os.rename(AUTOLOAD_FILE, AUTOLOAD_DISABLED)
                LogUtils.warn("[memory] Autoload disabled")
                if ctx.app and ctx.app.message_history:
                    ctx.app.message_history.add_user_message(
                        "**Memory Autoload**: Persistent memory autoload is now OFF. "
                        "Your session prompt will NOT include autoload.md content."
                    )
            else:
                LogUtils.info("[memory] Autoload is already disabled")

        else:
            LogUtils.print("Memory plugin commands:", bold=True)
            LogUtils.dim("  /memory init     - Initialize memory directory")
            LogUtils.dim("  /memory rm-all   - Delete all memory (requires confirmation)")
            LogUtils.dim("  /memory status   - Show memory status and file sizes")
            LogUtils.dim("  /memory on       - Enable autoload")
            LogUtils.dim("  /memory off      - Disable autoload")

    # Register hooks
    ctx.register_hook("after_file_write", on_autoload_write)
    ctx.register_hook("after_tool_results", on_tool_results)
    ctx.register_hook("on_system_prompt_append", on_system_prompt_append)

    # Register command
    ctx.register_command("memory", handle_command, description="Persistent memory management (.aicoder/memory/)")
    ctx.register_command("m", handle_command, description="Alias for /memory")

    return {
        "name": "memory",
        "description": "Persistent memory management (.aicoder/memory/)",
        "command": handle_command,
        "hooks": {
            "after_file_write": on_autoload_write,
            "after_tool_results": on_tool_results,
            "on_system_prompt_append": on_system_prompt_append,
        },
    }
