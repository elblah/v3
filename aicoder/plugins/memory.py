"""
Memory plugin - Auto-managed persistent memory for cross-session learning.

Creates `<MEMORY_DIR>/` structure (configurable via AICODER_MEMORY_DIR, defaults to `.aicoder/memory`):
  autoload.md - auto-injected into system prompt (limit configurable via AICODER_MEMORY_AUTOLOAD_LIMIT env var)
  index.md - main memory file, AI manages freely
  *.md - any additional files AI creates

The AI uses write_file/edit_file tools to manage memory naturally.
No special API calls or background processes needed.
"""

import os
from typing import List

MEMORY_DIR = os.environ.get("AICODER_MEMORY_DIR", ".aicoder/memory")
AUTOLOAD_FILE = os.path.join(MEMORY_DIR, "autoload.md")
INDEX_FILE = os.path.join(MEMORY_DIR, "index.md")
MAX_AUTOLOAD_BYTES = int(os.environ.get("AICODER_MEMORY_AUTOLOAD_LIMIT", "2048"))


def create_plugin(ctx):
    """Memory plugin - persistent memory management"""
    _pending_check: List[str] = []

    def _auto_init():
        """Auto-init memory dir + seed files if missing"""
        if not os.path.isdir(MEMORY_DIR):
            os.makedirs(MEMORY_DIR, exist_ok=True)
            index_content = (
                "# Memory Index\n\n"
                "This directory is your persistent memory. "
                "Manage files via write_file/edit_file.\n\n"
                "## Rules\n"
                "- `autoload.md` (< " + str(MAX_AUTOLOAD_BYTES) + " bytes) - critical facts loaded into every session's prompt.\n"
                "- `index.md` - working memory for project knowledge, patterns, conventions.\n"
                "- Create more `.md` files for specific topics as needed.\n"
                "- Update memory when you learn something important.\n\n"
                "## Guidelines\n"
                "- Be specific. Prefer facts over vague statements.\n"
                "- Replace dates with actual values (no 'today', 'yesterday').\n"
                "- Prune stale entries.\n"
            )
            with open(INDEX_FILE, "w", encoding="utf-8") as f:
                f.write(index_content)
        if not os.path.isfile(AUTOLOAD_FILE):
            with open(AUTOLOAD_FILE, "w", encoding="utf-8") as f:
                f.write("_No persistent memories yet._")
        from aicoder.utils.log import LogUtils
        LogUtils.info(f"[memory] auto-initialized at {MEMORY_DIR}")

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
        _auto_init()

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
            "\n"
            "**When to write to memory:**\n"
            "- During conversation (including tool use) — if user gives "
            "feedback, corrects you, shares useful context, or you discover "
            "something worth remembering across sessions, write it immediately.\n"
            "- Before summarizing — always check if anything from this turn "
            "is worth persisting. Write before the summary.\n"
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

        if subcmd == "rm-all":
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
                LogUtils.warn("[memory] Memory directory deleted, will re-initialize")
            except FileNotFoundError:
                LogUtils.error("[memory] Memory directory does not exist")
            except PermissionError:
                LogUtils.error(f"[memory] Cannot delete {MEMORY_DIR} - permission denied")

            # Dir deleted. on_system_prompt_append will auto-init fresh on next build.

        elif subcmd == "status":
            from aicoder.utils.log import LogUtils
            if not os.path.isdir(MEMORY_DIR):
                LogUtils.info("[memory] Not initialized (will auto-init on next request)")
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

            LogUtils.print(f"\n{'[memory] Memory Status':^40}", bold=True)
            LogUtils.dim(f"{'─' * 42}")
            LogUtils.print("  Disable via PLUGINS_DENY=...,memory (env var)")
            LogUtils.dim(f"{'─' * 42}")
            for fname, size in sorted(files):
                LogUtils.print(f"  {fname:<30} {size:>7} bytes")
            LogUtils.dim(f"{'─' * 42}\n")

        elif subcmd == "export":
            if len(parts) < 2:
                LogUtils.error("[memory] Usage: /memory export <archive-path>")
                return

            archive_path = os.path.abspath(parts[1])
            archive_dir = os.path.dirname(archive_path)
            if archive_dir and not os.path.isdir(archive_dir):
                LogUtils.error(f"[memory] Parent directory does not exist: {archive_dir}")
                return
            if not os.path.isdir(MEMORY_DIR):
                LogUtils.error("[memory] No memory directory to export")
                return

            import tarfile

            try:
                mem_files = [f for f in os.listdir(MEMORY_DIR) if f.endswith(".md")]
                if not mem_files:
                    LogUtils.error("[memory] No memory files to export")
                    return

                with tarfile.open(archive_path, "w:gz") as tar:
                    for fname in mem_files:
                        fpath = os.path.join(MEMORY_DIR, fname)
                        tar.add(fpath, arcname=fname)
                LogUtils.success(f"[memory] Exported {len(mem_files)} files to {archive_path}")
            except Exception as e:
                LogUtils.error(f"[memory] Export failed: {e}")

        elif subcmd == "import":
            if len(parts) < 2:
                LogUtils.error("[memory] Usage: /memory import <archive.tgz>")
                return

            archive_path = os.path.abspath(parts[1])
            if not os.path.isfile(archive_path):
                LogUtils.error(f"[memory] Archive not found: {archive_path}")
                return

            import tarfile
            try:
                with tarfile.open(archive_path, "r:gz") as tar:
                    members = tar.getmembers()
                    md_members = [m for m in members if m.name.endswith(".md") and ".." not in m.name]
                    if not md_members:
                        LogUtils.error("[memory] No .md files found in archive")
                        return

                    os.makedirs(MEMORY_DIR, exist_ok=True)
                    for member in md_members:
                        # Strip any directory components for safety
                        member.name = os.path.basename(member.name)
                        tar.extract(member, path=MEMORY_DIR)
                    LogUtils.success(f"[memory] Imported {len(md_members)} files from {archive_path}")
            except Exception as e:
                LogUtils.error(f"[memory] Import failed: {e}")

        else:
            LogUtils.print("Memory plugin commands:", bold=True)
            LogUtils.dim("  /memory export <path> - Export memory to archive (.tar.gz)")
            LogUtils.dim("  /memory import <file> - Import memory from archive (replaces files)")
            LogUtils.dim("  /memory rm-all       - Delete all memory (requires confirmation)")
            LogUtils.dim("  /memory status       - Show memory status and file sizes")
            LogUtils.dim("  Disable via PLUGINS_DENY=...,memory env var")

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
