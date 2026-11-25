"""
Memory plugin - Auto-managed persistent memory for cross-session learning.

Creates `<MEMORY_DIR>/` structure (configurable via AICODER_MEMORY_DIR, defaults to `.aicoder/memory`):
  autoload.md - auto-injected into system prompt (limit configurable via AICODER_MEMORY_AUTOLOAD_LIMIT env var)
  index.md - main memory file, AI manages freely
  *.md - any additional files AI creates

The AI uses write_file/edit_file tools to manage memory naturally.
No special API calls or background processes needed.

Transient band: `99-*.md` = scratch/temp/unsure notes, auto-archived to `.archive/`
after TRANSIENT_TTL_DAYS (default 7) without edits. Promotion = rename below 99.
Editing refreshes the clock. No wipe hooks needed.
"""

import os
import sys
import time
import math
from typing import List

from aicoder.utils.bool_utils import env_bool, parse_bool

# Resolve to an absolute path at load time so the prompt can show the exact
# location. The relative default resolves against aicoder's working directory
# (NOT the OS home dir) — surfacing the absolute path stops the AI from guessing
# ~/.aicoder/memory and writing into a read-only location.
MEMORY_DIR = os.path.abspath(os.environ.get("AICODER_MEMORY_DIR", ".aicoder/memory"))
AUTOLOAD_FILE = os.path.join(MEMORY_DIR, "autoload.md")
INDEX_FILE = os.path.join(MEMORY_DIR, "index.md")
MAX_AUTOLOAD_BYTES = int(os.environ.get("AICODER_MEMORY_AUTOLOAD_LIMIT", "2048"))
# Topic files named in the system prompt (sorted by NN- band). Names are cheap
# (~7 tokens each); a *partial* listing is expensive: the AI reads the visible
# nearest-sounding name and answers from the wrong note, because the right one
# sits one sort position past the cut. So list every name up to a high cap and
# only count the remainder.
LIST_LIMIT = int(os.environ.get("AICODER_MEMORY_LIST_LIMIT", "120"))
LIMIT_FILE = os.path.join(os.path.dirname(MEMORY_DIR), "memory_limit")
NUDGE_FILE = os.path.join(os.path.dirname(MEMORY_DIR), "memory_nudge")
# Nudge when the topic-file count exceeds this (0 = disabled). Advertises that
# extra files cost no tokens but are invisible past LIST_LIMIT.
MAX_FILES_NUDGE_FILE = os.path.join(os.path.dirname(MEMORY_DIR), "memory_max_files")


def _parse_size(value: str) -> int:
    """Parse size string like '10k', '1.5m', '50000'"""
    value = value.strip().lower()
    if value.endswith("k"):
        return int(float(value[:-1]) * 1000)
    if value.endswith("m"):
        return int(float(value[:-1]) * 1000000)
    return int(value)


def _load_project_limit() -> int | None:
    """Load per-project memory limit override from LIMIT_FILE."""
    try:
        if os.path.isfile(LIMIT_FILE):
            with open(LIMIT_FILE) as f:
                val = f.read().strip()
            if val:
                return int(val)
    except (ValueError, OSError, IOError):
        pass
    return None


_project_limit = _load_project_limit()
if _project_limit is not None:
    MAX_AUTOLOAD_BYTES = _project_limit

# Nudge config — on by default; disable via /memory nudge off (persists
# per-project in NUDGE_FILE, overrides env) or AICODER_MEMORY_NUDGE=0
NUDGE_ENABLED = env_bool("AICODER_MEMORY_NUDGE", default=True)
NUDGE_CHARS = int(os.environ.get("AICODER_MEMORY_NUDGE_CHARS", "1000"))
NUDGE_SECONDS = int(os.environ.get("AICODER_MEMORY_NUDGE_SECONDS", "300"))


def _load_project_nudge() -> bool | None:
    """Load per-project nudge override from NUDGE_FILE ('1'/'0')."""
    try:
        if os.path.isfile(NUDGE_FILE):
            with open(NUDGE_FILE) as f:
                return parse_bool(f.read())
    except (ValueError, OSError, IOError):
        pass
    return None


_project_nudge = _load_project_nudge()
if _project_nudge is not None:
    NUDGE_ENABLED = _project_nudge

# File-count nudge — fire once per session when topic files exceed this count.
# Overridable per project (/memory max-files-nudge <N|off>) or via env; 0 = off.
MAX_FILES_NUDGE = int(os.environ.get("AICODER_MEMORY_MAX_FILES_NUDGE", "60"))
# Minimum seconds between two file-count nudges (default 10 min).
MAX_FILES_NUDGE_SECONDS = int(os.environ.get("AICODER_MEMORY_MAX_FILES_NUDGE_SECONDS", "600"))


def _load_project_max_files() -> int | None:
    """Load per-project file-count nudge threshold ('0'/'off' disables)."""
    try:
        if os.path.isfile(MAX_FILES_NUDGE_FILE):
            with open(MAX_FILES_NUDGE_FILE) as f:
                val = f.read().strip().lower()
            if val in ("off", "none", "no"):
                return 0
            if val:
                return int(val)
    except (ValueError, OSError, IOError):
        pass
    return None


_project_max_files = _load_project_max_files()
if _project_max_files is not None:
    MAX_FILES_NUDGE = _project_max_files

# Auto-approve write_file/edit_file targeting the memory dir (skip approval prompt)
AUTO_APPROVE_MEMORY = env_bool("AICODER_MEMORY_AUTO_APPROVE", default=True)
# Hide memory-dir write previews entirely (default: show one-line summary instead of diff)
PREVIEW_HIDE = env_bool("AICODER_MEMORY_PREVIEW_HIDE", default=False)

# Transient band: 99-*.md files auto-archive to .archive/ after TTL days without edits (promotion = rename below 99)
TRANSIENT_BAND = 99
TRANSIENT_TTL_DAYS = int(os.environ.get("AICODER_MEMORY_TRANSIENT_TTL_DAYS", "7"))
# Dot-prefixed on purpose: list_directory never descends into dot dirs, so
# archived notes cost nothing and never leak into tool output.
ARCHIVE_DIR_NAME = ".archive"


def _band_of(fname: str) -> int | None:
    """Extract NN band from a `NN-name.md` filename; None if not banded."""
    if len(fname) >= 3 and fname[:2].isdigit() and fname[2] == "-":
        return int(fname[:2])
    return None


def _is_transient(fname: str) -> bool:
    return _band_of(fname) == TRANSIENT_BAND


def _transient_days_left(fname: str, memory_dir: str = MEMORY_DIR) -> int | None:
    """Days until a transient file auto-archives; None for non-transient files."""
    if not _is_transient(fname):
        return None
    try:
        age_days = (time.time() - os.path.getmtime(os.path.join(memory_dir, fname))) / 86400.0
    except OSError:
        return None
    return max(0, math.ceil(TRANSIENT_TTL_DAYS - age_days))


def _migrate_legacy_archive(memory_dir: str = MEMORY_DIR) -> bool:
    """Move a legacy visible `archive/` into the dot-prefixed `.archive/`.

    The old name was recursed by list_directory (every file inside showed up in
    tool output). Dot dirs are skipped there, so archived notes become truly
    invisible. Returns True when something was moved.
    """
    legacy = os.path.join(memory_dir, "archive")
    if not os.path.isdir(legacy):
        return False
    target = os.path.join(memory_dir, ARCHIVE_DIR_NAME)
    moved = False
    try:
        os.makedirs(target, exist_ok=True)
        for name in os.listdir(legacy):
            src = os.path.join(legacy, name)
            if not os.path.isfile(src):
                continue
            dst = os.path.join(target, name)
            if os.path.exists(dst):
                dst = os.path.join(target, f"legacy-{name}")
            try:
                os.rename(src, dst)
                moved = True
            except OSError:
                pass
        try:
            os.rmdir(legacy)  # only succeeds when fully drained
        except OSError:
            pass
    except OSError:
        pass
    return moved


def _archive_expired(memory_dir: str = MEMORY_DIR) -> list[str]:
    """Move 99- transient files past TTL (no edits in TRANSIENT_TTL_DAYS days) to .archive/."""
    now = time.time()
    archived = []
    _migrate_legacy_archive(memory_dir)
    archive_dir = os.path.join(memory_dir, ARCHIVE_DIR_NAME)
    try:
        for fname in os.listdir(memory_dir):
            if not _is_transient(fname):
                continue
            fpath = os.path.join(memory_dir, fname)
            try:
                age_days = (now - os.path.getmtime(fpath)) / 86400.0
            except OSError:
                continue
            if age_days >= TRANSIENT_TTL_DAYS:
                try:
                    os.makedirs(archive_dir, exist_ok=True)
                    stamp = time.strftime("%Y%m%d", time.localtime(now))
                    os.rename(fpath, os.path.join(archive_dir, f"{stamp}-{fname}"))
                    archived.append(fname)
                except OSError:
                    pass
    except OSError:
        pass
    return archived


def create_plugin(ctx):
    """Memory plugin - persistent memory management"""
    _pending_check: List[str] = []

    # Nudge tracking
    _last_memory_write: float = 0.0
    _substantial_response: bool = False
    # File-count nudge state: pending check after a memory write; fires at most
    # once per MAX_FILES_NUDGE_SECONDS (default 10 min)
    _pending_count_check: bool = False
    _last_count_nudge: float = 0.0

    def _is_memory_path(path: str) -> bool:
        """Check if a file path is inside the memory directory."""
        try:
            return os.path.commonpath([os.path.abspath(path), os.path.abspath(MEMORY_DIR)]) == os.path.abspath(MEMORY_DIR)
        except ValueError:
            return False

    def _before_approval_prompt(tool_name: str, arguments: dict) -> bool | None:
        """Auto-approve write_file/edit_file when the target is inside the memory dir.

        Returns True (approve), or None (normal approval flow) otherwise.
        Preview still displays before execution, so writes stay visible.
        """
        if not AUTO_APPROVE_MEMORY:
            return None
        if tool_name not in ("write_file", "edit_file"):
            return None
        if not isinstance(arguments, dict):
            return None
        path = arguments.get("path")
        if not path or not _is_memory_path(str(path)):
            return None
        from aicoder.utils.log import LogUtils
        if sys.stdout.isatty():
            LogUtils.print(f"[memory] auto-approved {tool_name} -> {path}")
        return True

    def _on_tool_preview(tool_name: str, arguments: dict, preview_result: dict) -> bool | dict | None:
        """Replace/suppress diffs for write_file/edit_file targeting the memory dir."""
        if tool_name not in ("write_file", "edit_file"):
            return None
        if not isinstance(arguments, dict):
            return None
        path = arguments.get("path")
        if not path or not _is_memory_path(str(path)):
            return None
        if PREVIEW_HIDE:
            return False
        rel = os.path.relpath(str(path), MEMORY_DIR)
        return {
            "tool": tool_name,
            "content": f"Memory update: {rel} (diff hidden)",
            "can_approve": True,
        }

    def _on_after_file_write(path: str, _content: str):
        """Track writes to memory directory + autoload size/count checks."""
        nonlocal _last_memory_write, _substantial_response, _pending_count_check
        if _is_memory_path(path):
            _last_memory_write = time.time()
            _substantial_response = False
            if MAX_FILES_NUDGE > 0 and str(path).endswith(".md"):
                _pending_count_check = True
        on_autoload_write(path, _content)

    def _on_after_assistant_message(message) -> None:
        """Track substantial assistant responses for nudging."""
        nonlocal _substantial_response
        if not NUDGE_ENABLED:
            return
        content = message.get("content", "")
        if isinstance(content, list):
            text = "".join(
                part.get("text", "")
                for part in content
                if isinstance(part, dict) and part.get("type") == "text"
            )
        else:
            text = str(content)
        if len(text) >= NUDGE_CHARS:
            _substantial_response = True

    def _on_after_user_prompt(user_input: str) -> str:
        """Nudge AI to write memory if substantial work done and memory is stale."""
        nonlocal _substantial_response
        if not NUDGE_ENABLED:
            return user_input
        if not _substantial_response:
            return user_input
        # Skip nudge on commands — they're not conversational turns
        if user_input.strip().startswith("/"):
            return user_input
        if _last_memory_write > 0 and (time.time() - _last_memory_write) < NUDGE_SECONDS:
            return user_input
        _substantial_response = False
        return (
            f"{user_input}\n\n<system-reminder>\n"
            "If you learned anything worth persisting across sessions, "
            f"update your memory notes now (in `{MEMORY_DIR}`) — before your answer, not after.\n"
            "</system-reminder>"
        )

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
        archived = _archive_expired()
        from aicoder.utils.log import LogUtils
        if archived and sys.stdout.isatty():
            LogUtils.dim(f"[memory] archived transient: {', '.join(archived)}")
        if sys.stdout.isatty():
            LogUtils.printc(f"[memory] auto-initialized at {MEMORY_DIR}", color="blue", stderr=True)

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
            if sys.stdout.isatty():
                LogUtils.warn(f"[memory] autoload.md truncated "
                              f"({len(content)} bytes, max {MAX_AUTOLOAD_BYTES})")
            trunc_note = f"\n\n[... truncated to {MAX_AUTOLOAD_BYTES} bytes ...]"
            content = content[:MAX_AUTOLOAD_BYTES - len(trunc_note)] + trunc_note

        return content

    def list_memory_files() -> list[str]:
        """List topic .md files in memory directory (sorted; autoload.md/index.md excluded)"""
        try:
            files = []
            for fname in os.listdir(MEMORY_DIR):
                if not fname.endswith(".md"):
                    continue
                if fname == "autoload.md" or fname == "index.md":
                    continue
                if os.path.isfile(os.path.join(MEMORY_DIR, fname)):
                    files.append(fname)
            return sorted(files)
        except FileNotFoundError:
            return []

    def _count_nudge_message() -> tuple[str, str] | None:
        """Build the file-count nudge text and its one-line screen summary.

        Returns (message, summary) or None when under threshold/throttled.
        """
        files = list_memory_files()
        total = len(files)
        if MAX_FILES_NUDGE <= 0 or total <= MAX_FILES_NUDGE:
            return None
        if _last_count_nudge > 0 and (time.time() - _last_count_nudge) < MAX_FILES_NUDGE_SECONDS:
            return None
        # Band breakdown of what sits beyond the prompt listing cut
        hidden = files[LIST_LIMIT:]
        bands: dict[str, int] = {}
        for fname in hidden:
            band = _band_of(fname)
            key = f"{band:02d}-" if band is not None else "none"
            bands[key] = bands.get(key, 0) + 1
        breakdown = ", ".join(f"{k}:{v}" for k, v in sorted(bands.items()))
        if hidden:
            hidden_txt = (
                f"{len(hidden)} are past the {LIST_LIMIT}-file prompt cut and "
                f"invisible to you in the system prompt (bands hidden — {breakdown})"
            )
        else:
            hidden_txt = f"all of them still fit under the {LIST_LIMIT}-file prompt cut"
        summary = f"{total} files, threshold {MAX_FILES_NUDGE}"
        if hidden:
            summary += f", {len(hidden)} past the {LIST_LIMIT}-file cut"
        return (
            f"Memory housekeeping: `{MEMORY_DIR}` holds {total} topic files "
            f"(threshold {MAX_FILES_NUDGE}); {hidden_txt}. Extra files cost no tokens, "
            "but the listing is a fixed budget. Consolidate related notes into fewer, "
            "richer files and prune stale ones now — see them with `list_directory`. "
            f"`.archive/` (dot dir) is free: `mv` stale-but-still-true notes there instead of deleting."
        ), summary

    def on_autoload_write(path, _content):
        """Queue autoload.md for size check after tool results"""
        if path and path.endswith("autoload.md"):
            _pending_check.append(path)

    def on_tool_results(_tool_results):
        """Check autoload.md size and memory file count after tool results"""
        nonlocal _pending_count_check, _last_count_nudge
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
                if sys.stdout.isatty():
                    LogUtils.warn(f"[memory] {msg}")
                if ctx.app and ctx.app.message_history:
                    ctx.app.message_history.add_user_message(msg)

        # File-count nudge: deferred-safe (after_tool_results fires with the
        # tool chain closed; add_user_message would defer anyway)
        if _pending_count_check:
            _pending_count_check = False
            nudge = _count_nudge_message()
            if nudge:
                count_msg, summary = nudge
                _last_count_nudge = time.time()
                from aicoder.utils.log import LogUtils
                if sys.stdout.isatty():
                    LogUtils.dim(f"[memory] file-count nudge: {summary}")
                if ctx.app and ctx.app.message_history:
                    ctx.app.message_history.add_user_message(count_msg)

    def on_system_prompt_append():
        """Inject memory info and autoload.md into system prompt"""
        _auto_init()

        autoload = get_autoload()
        files = list_memory_files()

        section = (
            "\n\n## Persistent Memory\n"
            "Your memory directory (absolute path — use this exact path):\n"
            " `" + MEMORY_DIR + "`\n"
            "This is aicoder's working-directory location, NOT `~/.aicoder/` and NOT your OS home "
            "(`~/.aicoder` is a different, possibly read-only dir). Always pass the absolute path above "
            "to `write_file`/`edit_file`.\n"
            "\n"
            "- `autoload.md` (< " + str(MAX_AUTOLOAD_BYTES) + " bytes) — injected into every session's system prompt. "
            "Every byte costs tokens. Write terse bullets. Pointers beat inlining (`see api-notes.md`).\n"
            "- `index.md` — main working memory.\n"
            "- Band + prefix rule: `NN-` is an IMPORTANCE BAND, NOT unique, NOT sequential "
            "(many files may share it; tie-break alphabetical). Lower band = listed first = survives the cut.\n"
            "- Always prefix new files with `NN-`: unprefixed `.md` files sort after every band and are "
            "first beyond the cut.\n"
            "- `99-*.md` = TRANSIENT (scratch, todos, unsure notes): auto-archived to `.archive/` after "
            + str(TRANSIENT_TTL_DAYS) + " days without edits. Promote: rename below 99 when it matters.\n"
            "- Every topic filename is listed below (up to " + str(LIST_LIMIT) + "); "
            "`.archive/` holds keep-without-cost files (never listed, and dot dirs are skipped by "
            "`list_directory` too).\n"
            "- Asked to read/recall a specific topic: pick the listed filename whose NAME matches, "
            "not the nearest-sounding one. If no name matches, search before answering — "
            "`ls " + MEMORY_DIR + " | grep -i -E '<words>'` (filenames first; content grep last, "
            "a memory dir is self-similar: every note mentions every topic). "
            "Never claim a note is missing unsearched.\n"
            "- More than " + str(LIST_LIMIT) + " files means the tail is only counted, not named: "
            "consolidate before the right note hides behind the cut.\n"
            "- Stale but still true: `mv` it into `.archive/` instead of deleting — cheaper than losing it. "
            "Delete only notes that were wrong. Never archive anything that still earns its `NN-` band.\n"
            "- Prune stale entries — they waste every future session.\n"
            "\n"
            "Write autonomously when you learn something worth persisting. "
            "Never ask permission. Check before summarizing.\n"
            "Writes to this dir are auto-approved (no approval prompt); other files still prompt.\n"
            "Write diffs are replaced with a one-line summary (AICODER_MEMORY_PREVIEW_HIDE=1 hides entirely).\n"
            "Order: write memory BEFORE your final answer (tool calls first, answer last). "
            "Never end with a 'memory updated' recap — your answer must be the last line.\n"
        )

        if files:
            section += "\n### Memory Files\n"
            for name in files[:LIST_LIMIT]:
                dl = _transient_days_left(name)
                suffix = f" (transient: auto-archives in {dl}d)" if dl is not None else ""
                section += f"- {name}{suffix}\n"
            hidden = len(files) - LIST_LIMIT
            if hidden > 0:
                section += (f"- …and {hidden} more files in `{MEMORY_DIR}` "
                            "(same-or-later band; the cut is alphabetical, so these are "
                            "NOT junk — inspect with `list_directory` on "
                            f"`{MEMORY_DIR}`).\n")

        if autoload:
            section += "\n### autoload.md\n" + autoload

        return section

    def handle_command(args_str: str):
        """Handle /memory command"""
        global MAX_AUTOLOAD_BYTES, NUDGE_ENABLED, MAX_FILES_NUDGE
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
            if os.path.islink(MEMORY_DIR):
                real = os.path.normpath(os.path.join(
                    os.path.dirname(MEMORY_DIR), os.readlink(MEMORY_DIR)))
                LogUtils.print(f"  Location: {real} (via symlink)")
            else:
                LogUtils.print(f"  Location: {MEMORY_DIR}")
            LogUtils.dim(f"{'─' * 42}")
            for fname, size in sorted(files):
                dl = _transient_days_left(fname)
                suffix = f" (transient, {dl}d left)" if dl is not None else ""
                LogUtils.print(f"  {fname:<30} {size:>7} bytes{suffix}")
            LogUtils.dim(f"{'─' * 42}")
            LogUtils.print(f"  Transient TTL: {TRANSIENT_TTL_DAYS}d (99-*.md -> {ARCHIVE_DIR_NAME}/)")
            nudge_state = "on" if NUDGE_ENABLED else "off"
            LogUtils.print(f"  Nudge: {nudge_state} (chars>{NUDGE_CHARS}, stale>{NUDGE_SECONDS}s)")
            files_nudge = "off" if MAX_FILES_NUDGE <= 0 else f">{MAX_FILES_NUDGE} files"
            LogUtils.print(f"  File-count nudge: {files_nudge} "
                           f"(throttle {MAX_FILES_NUDGE_SECONDS}s, AICODER_MEMORY_MAX_FILES_NUDGE[_SECONDS])")
            aa_state = "on" if AUTO_APPROVE_MEMORY else "off"
            LogUtils.print(f"  Auto-approve memory writes: {aa_state} (AICODER_MEMORY_AUTO_APPROVE)")
            pv_state = "hidden" if PREVIEW_HIDE else "summary"
            LogUtils.print(f"  Memory write preview: {pv_state} (AICODER_MEMORY_PREVIEW_HIDE=1 hides)")
            if _last_memory_write > 0:
                ago = int(time.time() - _last_memory_write)
                LogUtils.print(f"  Last memory write: {ago}s ago")
            LogUtils.dim(f"{'─' * 42}\n")

        elif subcmd == "show":
            # Print the exact section injected into the system prompt
            LogUtils.print(on_system_prompt_append())

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

        elif subcmd == "move":
            import shutil
            target = parts[1] if len(parts) > 1 else None

            if target:
                # Move OUT: .aicoder/memory (real dir) → target, then symlink
                if os.path.islink(MEMORY_DIR):
                    link_dst = os.readlink(MEMORY_DIR)
                    LogUtils.error(
                        f"[memory] Already moved to {link_dst}. "
                        "Use /memory move to undo first."
                    )
                    return
                if not os.path.isdir(MEMORY_DIR):
                    LogUtils.info("[memory] Not initialized — initializing first")
                    _auto_init()
                target = os.path.abspath(target)
                if os.path.exists(target):
                    LogUtils.error(f"[memory] Target already exists: {target}")
                    return
                parent = os.path.dirname(target)
                if parent and not os.path.isdir(parent):
                    LogUtils.error(f"[memory] Parent directory does not exist: {parent}")
                    return
                shutil.move(MEMORY_DIR, target)
                os.symlink(target, MEMORY_DIR)
                LogUtils.success(f"[memory] Moved to {target}, symlinked from {MEMORY_DIR}")
            else:
                # Move IN (undo): symlink back to real dir
                if not os.path.islink(MEMORY_DIR):
                    LogUtils.error("[memory] Not moved — nothing to undo")
                    return
                link_dst = os.readlink(MEMORY_DIR)
                real_dir = os.path.normpath(os.path.join(os.path.dirname(MEMORY_DIR), link_dst))
                if not os.path.isdir(real_dir):
                    LogUtils.error(f"[memory] Symlink target not found: {real_dir}")
                    return
                os.unlink(MEMORY_DIR)
                shutil.move(real_dir, MEMORY_DIR)
                LogUtils.success(f"[memory] Moved back from {real_dir} to {MEMORY_DIR}")

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

        elif subcmd == "nudge":
            if len(parts) < 2:
                src = "project file" if os.path.isfile(NUDGE_FILE) else "env/default"
                LogUtils.info(f"[memory] Nudge: {'on' if NUDGE_ENABLED else 'off'} ({src})")
                return
            try:
                NUDGE_ENABLED = parse_bool(parts[1])
            except ValueError as e:
                LogUtils.error(f"[memory] {e}")
                return
            try:
                os.makedirs(os.path.dirname(NUDGE_FILE), exist_ok=True)
                with open(NUDGE_FILE, "w") as f:
                    f.write("1" if NUDGE_ENABLED else "0")
                LogUtils.success(f"[memory] Nudge {'enabled' if NUDGE_ENABLED else 'disabled'} "
                                 f"for this project ({NUDGE_FILE})")
            except OSError as e:
                LogUtils.error(f"[memory] Nudge set for this session, but could not persist: {e}")

        elif subcmd == "max-files-nudge":
            if len(parts) < 2:
                src = "project file" if os.path.isfile(MAX_FILES_NUDGE_FILE) else "env/default"
                state = "off" if MAX_FILES_NUDGE <= 0 else f"{MAX_FILES_NUDGE} files"
                LogUtils.info(f"[memory] File-count nudge: {state} ({src}), "
                              f"throttle {MAX_FILES_NUDGE_SECONDS}s")
                return
            raw = parts[1].strip().lower()
            if raw in ("off", "none", "no", "0"):
                new_max = 0
            else:
                try:
                    new_max = int(raw)
                except ValueError:
                    LogUtils.error(f"[memory] Invalid count: {parts[1]} (use a number or 'off')")
                    return
                if new_max < 1:
                    LogUtils.error(f"[memory] Count must be >= 1 (or 'off'), got {parts[1]}")
                    return
            try:
                os.makedirs(os.path.dirname(MAX_FILES_NUDGE_FILE), exist_ok=True)
                with open(MAX_FILES_NUDGE_FILE, "w") as f:
                    f.write("off" if new_max == 0 else str(new_max))
                MAX_FILES_NUDGE = new_max
                state = "disabled" if new_max == 0 else f"set to {new_max} files"
                LogUtils.success(f"[memory] File-count nudge {state} for this project "
                                 f"({MAX_FILES_NUDGE_FILE})")
            except OSError as e:
                LogUtils.error(f"[memory] Nudge set for this session, but could not persist: {e}")

        elif subcmd == "limit":
            if len(parts) < 2:
                LogUtils.info(f"[memory] Current limit: {MAX_AUTOLOAD_BYTES} bytes")
                return
            try:
                new_limit = _parse_size(parts[1])
                if new_limit < 256:
                    LogUtils.error("[memory] Limit too small (min 256 bytes)")
                    return
                os.makedirs(os.path.dirname(LIMIT_FILE), exist_ok=True)
                with open(LIMIT_FILE, "w") as f:
                    f.write(str(new_limit))
                MAX_AUTOLOAD_BYTES = new_limit
                LogUtils.success(f"[memory] Project memory limit set to {new_limit} bytes ({LIMIT_FILE})")
            except ValueError:
                LogUtils.error(f"[memory] Invalid size: {parts[1]}")

        else:
            LogUtils.print("Memory plugin commands:", bold=True)
            LogUtils.dim("  /memory move <path>    - Move memory to <path>, symlink from .aicoder/memory")
            LogUtils.dim("  /memory move           - Undo: move memory back to .aicoder/memory")
            LogUtils.dim("  /memory export <path>  - Export memory to archive (.tar.gz)")
            LogUtils.dim("  /memory import <file>  - Import memory from archive (replaces files)")
            LogUtils.dim("  /memory nudge [on|off] - Toggle memory-write nudges (persisted per project)")
            LogUtils.dim("  /memory max-files-nudge [<N>|off] - Nudge when topic files exceed N (default 60, 10-min throttle)")
            LogUtils.dim("  /memory limit <size>   - Set per-project autoload size (e.g. 10k, 2m)")
            LogUtils.dim("  /memory rm-all         - Delete all memory (requires confirmation)")
            LogUtils.dim("  /memory status         - Show memory status and file sizes")
            LogUtils.dim("  /memory show           - Print the memory section as injected into the prompt")
            LogUtils.dim("  Disable via PLUGINS_DENY=...,memory env var")

    # Print startup message if project uses custom memory limit or nudge override
    _project_limit_now = _load_project_limit()
    if _project_limit_now is not None:
        from aicoder.utils.log import LogUtils
        if sys.stdout.isatty():
            LogUtils.info(f"[memory] Project memory limit: {_project_limit_now} bytes ({LIMIT_FILE})")
    if _project_nudge is not None:
        from aicoder.utils.log import LogUtils
        if sys.stdout.isatty():
            LogUtils.info(f"[memory] Project nudge: {'on' if NUDGE_ENABLED else 'off'} ({NUDGE_FILE})")
    if _project_max_files is not None:
        from aicoder.utils.log import LogUtils
        if sys.stdout.isatty():
            state = "off" if MAX_FILES_NUDGE <= 0 else f"{MAX_FILES_NUDGE} files"
            LogUtils.info(f"[memory] Project file-count nudge: {state} ({MAX_FILES_NUDGE_FILE})")

    # Register hooks
    ctx.register_hook("after_file_write", _on_after_file_write)
    ctx.register_hook("after_tool_results", on_tool_results)
    ctx.register_hook("on_system_prompt_append", on_system_prompt_append)
    ctx.register_hook("after_assistant_message_added", _on_after_assistant_message)
    ctx.register_hook("after_user_prompt", _on_after_user_prompt)
    ctx.register_hook("before_approval_prompt", _before_approval_prompt)
    ctx.register_hook("on_tool_preview", _on_tool_preview)

    # Register command
    ctx.register_command("memory", handle_command, description="Persistent memory management (.aicoder/memory/)")
    ctx.register_command("m", handle_command, description="Alias for /memory")

    return {
        "name": "memory",
        "description": "Persistent memory management (.aicoder/memory/)",
        "command": handle_command,
        "hooks": {
            "after_file_write": _on_after_file_write,
            "after_tool_results": on_tool_results,
            "on_system_prompt_append": on_system_prompt_append,
            "after_assistant_message_added": _on_after_assistant_message,
            "after_user_prompt": _on_after_user_prompt,
            "before_approval_prompt": _before_approval_prompt,
            "on_tool_preview": _on_tool_preview,
        },
    }
