"""
Memory plugin - Auto-managed persistent memory for cross-session learning.

Creates .aicoder/memory/ structure:
  autoload.md - auto-injected into system prompt (max 2KB)
  index.md - main memory file, AI manages freely
  *.md - any additional files AI creates

The AI uses write_file/edit_file tools to manage memory naturally.
No special API calls or background processes needed.
"""

import os
from typing import List
from aicoder.core.config import Config

MEMORY_DIR = ".aicoder/memory"
AUTOLOAD_FILE = os.path.join(MEMORY_DIR, "autoload.md")
INDEX_FILE = os.path.join(MEMORY_DIR, "index.md")
MAX_AUTOLOAD_BYTES = 2048
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
        """Inject autoload.md content into system prompt"""
        autoload = get_autoload()
        if autoload:
            instructions = (
                "\n\n## Persistent Memory\n"
                "You have a persistent memory directory at `.aicoder/memory/`.\n"
                "You manage it yourself using `write_file`/`edit_file`.\n"
                "- `autoload.md` < 2KB: This file (loaded into your prompt each session).\n"
                "- `index.md`: Your main working file. Organize project knowledge, "
                "user preferences, patterns.\n"
                "- Create more `.md` files for different topics.\n\n"
                "### Current Memory\n"
                + autoload
            )
            return instructions
        return None

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
                "The AI manages these files using write_file/edit_file.\n\n"
                "## Rules\n"
                "- `autoload.md` (max 2KB) is loaded into your system prompt each session. "
                "Keep it concise.\n"
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

            # Tell the AI
            if ctx.app and ctx.app.message_history:
                ctx.app.message_history.add_user_message(
                    "## Memory System\n\n"
                    "`.aicoder/memory/` persistent memory has been initialized.\n"
                    "- `autoload.md` (max 2KB): loaded into your system prompt each session.\n"
                    "- `index.md`: working memory file. Update with key learnings.\n"
                    "- Create additional `.md` files as needed.\n"
                    "Use `write_file`/`edit_file` to manage memory files."
                )

        elif subcmd == "rm-all":
            if not os.path.isdir(MEMORY_DIR):
                LogUtils.info("[memory] not initialized")
                return

            LogUtils.print("Remove all memory files? [y/N]: ", end="")
            try:
                answer = input().strip().lower()
            except (EOFError, KeyboardInterrupt):
                answer = ""
            if answer in ("y", "yes"):
                import shutil
                shutil.rmtree(MEMORY_DIR)
                LogUtils.success(f"[memory] {MEMORY_DIR} removed")
            else:
                LogUtils.info("[memory] cancelled")

        elif subcmd == "status":
            c = Config.colors
            lines = [f"{c['bold']}Memory Status:{c['reset']}"]

            if not os.path.isdir(MEMORY_DIR):
                lines.append(f"  Not initialized. Run {c['green']}/memory init{c['reset']}")
                LogUtils.print("\n".join(lines))
                return

            # autoload.md (check active, then disabled)
            try:
                with open(AUTOLOAD_FILE, "r", encoding="utf-8") as f:
                    content = f.read()
                size = len(content)
                ok = size <= MAX_AUTOLOAD_BYTES
                status = f"  {c['cyan']}autoload.md{c['reset']} ({size} bytes"
                if not ok:
                    status += f"{c['red']} OVER LIMIT{c['reset']}"
                status += ")"
                if ok:
                    status += " [injected]"
                lines.append(status)
            except (FileNotFoundError, IOError, OSError):
                # Check disabled
                try:
                    with open(AUTOLOAD_DISABLED, "r", encoding="utf-8") as f:
                        content = f.read()
                    lines.append(f"  {c['cyan']}autoload.md.disabled{c['reset']} "
                                 f"({len(content)} bytes) [disabled]")
                except (FileNotFoundError, IOError, OSError):
                    lines.append(f"  {c['cyan']}autoload.md{c['reset']} (not found)")

            # index.md
            try:
                with open(INDEX_FILE, "r", encoding="utf-8") as f:
                    content = f.read()
                lines.append(f"  {c['cyan']}index.md{c['reset']} ({len(content)} bytes)")
            except (FileNotFoundError, IOError, OSError):
                lines.append(f"  {c['cyan']}index.md{c['reset']} (not found)")

            # Count additional .md files
            extra = 0
            try:
                for fname in os.listdir(MEMORY_DIR):
                    if fname.endswith(".md") and fname not in ("autoload.md", "index.md"):
                        extra += 1
            except (FileNotFoundError, IOError, OSError):
                pass

            if extra > 0:
                lines.append(f"  + {extra} additional file(s)")

            LogUtils.print("\n".join(lines))

        elif subcmd == "on":
            if os.path.isfile(AUTOLOAD_DISABLED):
                os.rename(AUTOLOAD_DISABLED, AUTOLOAD_FILE)
                LogUtils.success("[memory] enabled (restored autoload.md)")
            elif os.path.isfile(AUTOLOAD_FILE):
                LogUtils.info("[memory] already enabled")
            else:
                LogUtils.info("[memory] not initialized, use /memory init")

        elif subcmd == "off":
            if os.path.isfile(AUTOLOAD_FILE):
                os.rename(AUTOLOAD_FILE, AUTOLOAD_DISABLED)
                LogUtils.info("[memory] disabled (autoload.md -> autoload.md.disabled)")
            elif os.path.isfile(AUTOLOAD_DISABLED):
                LogUtils.info("[memory] already disabled")
            else:
                LogUtils.info("[memory] not initialized, use /memory init")

        else:
            c = Config.colors
            LogUtils.print(f"{c['bold']}Usage:{c['reset']}")
            LogUtils.print(f"  {c['green']}/memory rm-all{c['reset']}  "
                           "Remove all memory files (safe prompt)")
            LogUtils.print(f"  {c['green']}/memory init{c['reset']}   "
                           "Create .aicoder/memory/ structure")
            LogUtils.print(f"  {c['green']}/memory status{c['reset']} "
                           "Show memory file info")
            LogUtils.print(f"  {c['green']}/memory on{c['reset']}    "
                           "Enable autoload injection")
            LogUtils.print(f"  {c['green']}/memory off{c['reset']}   "
                           "Disable autoload injection")
            LogUtils.print(f"  {c['green']}/m{c['reset']}            "
                           "Alias for /memory")

    # Register hooks
    ctx.register_hook("after_file_write", on_autoload_write)
    ctx.register_hook("after_tool_results", on_tool_results)
    ctx.register_hook("on_system_prompt_append", on_system_prompt_append)

    # Register command
    ctx.register_command("memory", handle_command, description="Persistent memory management")
    ctx.register_command("m", handle_command, description="Alias for /memory")

    if Config.debug():
        from aicoder.utils.log import LogUtils
        LogUtils.print("[+] Memory plugin loaded")
        LogUtils.print("    - /memory command (aliases: /m)")
        LogUtils.print("    - on_system_prompt_append hook (inject autoload.md)")
        LogUtils.print("    - after_file_write hook (monitor autoload.md)")
        LogUtils.print("    - after_tool_results hook (warn on oversized autoload.md)")
