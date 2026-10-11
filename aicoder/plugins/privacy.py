"""
Privacy Plugin - wipe known local artifacts that can hold conversation content

Why: personal info pasted into a session survives in several local files
(prompt history, session autosave, debug dumps, memory notes...). Wiping
memory notes alone is not enough.

Commands:
- /privacy            status: which known artifacts exist
- /privacy clear      ask y/n per existing artifact, then delete
- /privacy clear-all  delete all existing artifacts, no prompts

Extensibility: every clear run fires the `on_privacy_clear` hook with the
mode ("clear" | "clear-all"). Other plugins can register this hook and
return a list of dicts describing their own sensitive resources:

    return [{"path": "outbox/dump.json", "description": "captured dumps"}]

Returned paths are existence-checked and included in the same run
(relative paths resolve against cwd; "~" expands).
"""

import os
import shutil

from aicoder.core.config import Config
from aicoder.utils.log import LogUtils
from aicoder.utils.input_utils import prompt_choice
from aicoder.utils.bool_utils import TRUTHY, FALSY

# Fixed, known core artifacts that may hold conversation/personal content.
# cwd-relative unless the path starts with "~".
REGISTRY = [
    ".aicoder/history",                  # raw user prompts (JSONL)
    ".aicoder/current-session.jsonl",    # full session autosave
    ".aicoder/last-request.json",        # debug: full API request (incl. API key header)
    ".aicoder/last-response.log",        # debug: raw response dump
    ".aicoder/last-response.json",       # debug: raw response dump
    ".aicoder/last-session.json",        # core autosave (when SESSION_FILE is unset)
    ".aicoder/errors.log",               # tracebacks (may embed payloads)
    ".aicoder/occapture",                # third-party capture dumps
    ".aicoder/.aicoder",                 # stale nested state dir
]
# Never in registry:
# - .aicoder/memory (AI working state; wiped via its own flow, never wholesale)
# - .aicoder/stats.log + ~/.aicoder/central_stats.log (metadata only, kept)

SESSION_FILE = ".aicoder/current-session.jsonl"
EVENT = "on_privacy_clear"


def _human(size: int) -> str:
    """Format a byte count for display"""
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.1f} {unit}" if unit != "B" else f"{int(value)} B"
        value /= 1024
    return f"{int(size)} B"


def _size(path: str) -> int:
    """Total byte size of a file or directory (0 on errors)"""
    try:
        if os.path.isdir(path) and not os.path.islink(path):
            total = 0
            for root, _dirs, files in os.walk(path):
                for name in files:
                    try:
                        total += os.path.getsize(os.path.join(root, name))
                    except OSError:
                        pass
            return total
        return os.path.getsize(path)
    except OSError:
        return 0


def _kind(path: str) -> str:
    """Human label for the path type"""
    if os.path.islink(path):
        return "link"
    if os.path.isdir(path):
        return "dir"
    return "file"


def _delete(path: str) -> None:
    """Delete a file/symlink, or a directory tree. Never follows symlinks."""
    if os.path.islink(path) or not os.path.isdir(path):
        os.remove(path)
    else:
        shutil.rmtree(path)


def _normalize_contributions(returns) -> list:
    """Flatten on_privacy_clear hook returns into (path, description) rows.

    Accepts dicts ({"path": ..., "description": ...}) and bare path strings.
    Empty paths and filesystem root are rejected.
    """
    items = []
    for ret in returns or []:
        if ret is None:
            continue
        entries = list(ret) if isinstance(ret, (list, tuple, set)) else [ret]
        for entry in entries:
            if isinstance(entry, dict):
                raw = entry.get("path") or ""
                desc = entry.get("description") or ""
            elif isinstance(entry, str):
                raw, desc = entry, ""
            else:
                continue
            raw = str(raw).strip()
            if not raw:
                continue
            path = os.path.abspath(os.path.expanduser(raw))
            if path == os.sep:
                continue  # never a valid target
            items.append((path, str(desc)))
    return items


def _merge_entries(rows: list) -> list:
    """Dedupe (path, description) rows by absolute path, first one wins."""
    merged, seen = [], set()
    for path, desc in rows:
        if path in seen:
            continue
        seen.add(path)
        merged.append({"path": path, "description": desc})
    return merged


def create_plugin(ctx):
    """Privacy cleanup plugin"""

    def ask_yn(prompt: str) -> bool:
        """Yes/no prompt; empty answer means no"""
        while True:
            answer = prompt_choice(prompt, ["no", "yes"]).lower()
            if answer == "":
                return False
            if answer in TRUTHY:
                return True
            if answer in FALSY:
                return False

    def collect(mode: str) -> list:
        """Existing artifacts to consider: registry + plugin contributions"""
        returns = []
        app = getattr(ctx, "app", None)
        plugin_system = getattr(app, "plugin_system", None)
        if plugin_system is not None:
            returns = plugin_system.call_hooks(EVENT, mode) or []

        registry_rows = [
            (os.path.abspath(os.path.expanduser(path)), "") for path in REGISTRY
        ]
        rows = registry_rows + _normalize_contributions(returns)

        items = []
        for entry in _merge_entries(rows):
            path = entry["path"]
            if os.path.exists(path) or os.path.islink(path):
                items.append(entry)
        return items

    def item_label(item: dict) -> str:
        path = item["path"]
        label = os.path.relpath(path) if _is_inside_cwd(path) else path
        info = f"{_kind(path)}, {_human(_size(path))}"
        if item["description"]:
            info += f" -- {item['description']}"
        return f"{label} ({info})"

    def _is_inside_cwd(path: str) -> bool:
        try:
            return os.path.commonpath([path, os.getcwd()]) == os.getcwd()
        except ValueError:
            return False

    def status_text() -> str:
        lines = ["Privacy artifacts (known local files that may hold conversation content):", ""]
        present = 0
        for raw in REGISTRY:
            path = os.path.abspath(os.path.expanduser(raw))
            if os.path.exists(path) or os.path.islink(path):
                present += 1
                lines.append(f"  [x] {raw}  ({_kind(path)}, {_human(_size(path))})")
            else:
                lines.append(f"  [ ] {raw}  (absent)")
        lines.append("")
        lines.append(f"{present}/{len(REGISTRY)} present.")
        lines.append(
            "  /privacy clear      remove them one by one (y/n each)\n"
            "  /privacy clear-all  remove all of them without prompts"
        )
        lines.append(
            "Note: the running session keeps its own in-memory copy; after the wipe "
            "you are asked whether to reset it too (same as /new)."
        )
        lines.append(
            "Note: .aicoder/memory (AI notes) and the stats logs are never touched "
            "by this plugin."
        )
        return "\n".join(lines)

    def reset_live_session() -> None:
        """Same effect as the /new command"""
        app = ctx.app
        app.plugin_system.call_hooks("on_session_change", "new")
        app.stats.reset()
        app.message_history.clear()

    def do_clear(mode: str) -> str:
        items = collect(mode)
        if not items:
            return "Nothing to do: none of the known privacy artifacts exist."

        LogUtils.print(f"Privacy {mode}: {len(items)} artifact(s) present")

        selected = []
        for idx, item in enumerate(items, 1):
            label = item_label(item)
            if mode == "clear":
                if ask_yn(f"  [{idx}/{len(items)}] Clear {label}? [y/N] "):
                    selected.append(item)
            else:
                LogUtils.print(f"  [clear] {label}")
                selected.append(item)

        session_path = os.path.abspath(os.path.expanduser(SESSION_FILE))
        deleted, failed = [], []
        kept = [item for item in items if item not in selected]

        for item in selected:
            label = item_label(item)
            try:
                _delete(item["path"])
                deleted.append(item)
                LogUtils.print(f"  [deleted] {label}")
            except OSError as e:
                failed.append(item)
                LogUtils.error(f"  [failed] {label}: {e}")

        for item in kept:
            LogUtils.print(f"  [kept] {item_label(item)}")

        LogUtils.print(
            f"Summary: deleted {len(deleted)}, kept {len(kept)}, failed {len(failed)}."
        )

        if any(item["path"] == session_path for item in deleted):
            LogUtils.print("")
            LogUtils.print(
                "Note: the running session still holds this content in memory and "
                "can re-save it on compaction."
            )
            if ask_yn("Reset the live session as well (same as /new)? [y/N] "):
                reset_live_session()
                LogUtils.success("Session reset. Starting fresh.")
            else:
                LogUtils.print("Live session kept. Run /new when you want to drop it.")

        LogUtils.print(
            "Reminder: provider-side logs, terminal scrollback and copies outside "
            "these paths are out of reach."
        )
        return ""

    def handle_privacy(args_str: str) -> str:
        """Handle /privacy command"""
        args = (args_str or "").strip().split()
        mode = args[0] if args else "status"

        if mode == "status":
            return status_text()
        if mode in ("clear", "clear-all"):
            return do_clear(mode)

        return (
            f"Unknown argument: {mode}\n"
            "Usage:\n"
            "  /privacy            show known artifacts and whether they exist\n"
            "  /privacy clear      remove them one by one (y/n each)\n"
            "  /privacy clear-all  remove all of them without prompts\n"
            f"Plugins can add their own paths by hooking {EVENT}."
        )

    ctx.register_command(
        "/privacy",
        handle_privacy,
        description="Wipe known local privacy artifacts (history, session autosave, debug dumps)",
    )

    if Config.debug():
        LogUtils.debug("  - /privacy command")
        LogUtils.debug(f"  - fires {EVENT} hook on clear runs")
