"""
aliases.py - Command/prompt aliases from .aicoder/alias

File format (one per line, '#' comments, split on first '='):
  c2=/cs 200k
  review=Review this diff for bugs and scope creep:

Invocation (/name handled via the on_unknown_command hook):
  /c2           -> "/cs 200k"            (value starting with / runs as a command)
  /review a.py  -> "Review this diff for bugs and scope creep: a.py"
                   (plain value is sent to the AI as a user prompt)

Registered commands win by construction: the hook only fires when the
registry lookup misses, so aliases can never shadow real commands.

Commands:
  /alias            - list aliases (default)
  /alias list       - list aliases
  /alias edit       - open $EDITOR (tmux) to edit .aicoder/alias
  /alias name=value - set alias, persists to .aicoder/alias
  /alias rm <name>  - remove alias
  /alias <name>     - show a single alias value
"""
import os

from aicoder.core.config import Config
from aicoder.utils.log import LogUtils
from aicoder.core.commands.base import CommandResult

_ALIAS_FILE = ".aicoder/alias"
_MAX_DEPTH = 10


def _keep_line(line: str):
    """Return cleaned line, or None if blank/comment-only."""
    line = line.strip()
    if not line or line.startswith("#"):
        return None
    if " #" in line:
        line = line[: line.index(" #")].strip()
    return line or None


def _parse(content: str) -> dict:
    """Parse 'name=value' lines into a dict."""
    aliases = {}
    for raw in content.splitlines():
        line = _keep_line(raw)
        if not line or "=" not in line:
            continue
        name, _, value = line.partition("=")
        name = name.strip().lstrip("/")
        value = value.strip()
        if name and value:
            aliases[name] = value
    return aliases


def _read_file() -> str:
    if not os.path.exists(_ALIAS_FILE):
        return ""
    try:
        with open(_ALIAS_FILE, "r", encoding="utf-8") as f:
            return f.read()
    except Exception as e:
        LogUtils.error(f"[alias] Read error: {e}")
        return ""


def get_alias_names() -> list:
    """Alias names from .aicoder/alias (used by command_completer)."""
    return list(_parse(_read_file()).keys())


def create_plugin(ctx):
    """Create aliases plugin"""
    app = ctx.app

    # Hot-reload cache: {mtime, aliases}
    _cache = {"mtime": None, "aliases": {}}

    def _get_aliases() -> dict:
        try:
            mtime = os.path.getmtime(_ALIAS_FILE) if os.path.exists(_ALIAS_FILE) else None
        except Exception:
            mtime = None
        if _cache["mtime"] != mtime:
            _cache["aliases"] = _parse(_read_file())
            _cache["mtime"] = mtime
        return _cache["aliases"]

    def on_unknown_command(name: str, args_str: str):
        """Expand /name args -> value + args. Real commands never reach here."""
        depth = getattr(on_unknown_command, "_depth", 0)
        if depth >= _MAX_DEPTH:
            LogUtils.error(f"[alias] Alias chain too deep (> {_MAX_DEPTH}) at '/{name}'")
            return None

        value = _get_aliases().get(name.lstrip("/"))
        if value is None:
            return None

        expanded = f"{value} {args_str}".strip() if args_str else value

        c = Config.colors
        LogUtils.print(f"{c['cyan']}[alias] /{name} -> {expanded}{c['reset']}")

        if expanded.startswith("/"):
            # Re-dispatch immediately; chained aliases re-enter this hook
            on_unknown_command._depth = depth + 1
            try:
                return app.command_handler.handle_command(expanded)
            finally:
                on_unknown_command._depth = depth

        # Plain value: inject as user prompt and process with AI
        return CommandResult(should_quit=False, run_api_call=True, message=expanded)

    # ==================== Management command ====================

    def _list() -> str:
        aliases = _get_aliases()
        if not aliases:
            return "No aliases defined. Add one: /alias name=value"
        c = Config.colors
        width = max(len(n) for n in aliases)
        return "\n".join(
            f"  {c['cyan']}{name:<{width}}{c['reset']}  {value}"
            for name, value in sorted(aliases.items())
        )

    def _write(name: str, value=None):
        """Set (value not None) or remove (value None) a line, preserving order."""
        lines = _read_file().splitlines()
        if value is None:
            lines = [
                ln for ln in lines
                if not _keep_line(ln)
                or _keep_line(ln).partition("=")[0].strip().lstrip("/") != name
            ]
        else:
            replaced = False
            for i, ln in enumerate(lines):
                cleaned = _keep_line(ln)
                if cleaned and "=" in cleaned:
                    if cleaned.partition("=")[0].strip().lstrip("/") == name:
                        lines[i] = f"{name}={value}"
                        replaced = True
                        break
            if not replaced:
                lines.append(f"{name}={value}")
        os.makedirs(os.path.dirname(_ALIAS_FILE) or ".", exist_ok=True)
        with open(_ALIAS_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + ("\n" if lines else ""))
        _cache["mtime"] = None  # force reload

    def _edit() -> str:
        if not os.environ.get("TMUX"):
            return "This command only works inside a tmux environment."
        if not os.path.exists(_ALIAS_FILE):
            open(_ALIAS_FILE, "a").close()
            LogUtils.dim(f"Created {_ALIAS_FILE}")
        from aicoder.utils.tmux_edit_utils import tmux_open_editor
        if tmux_open_editor(_ALIAS_FILE, window_name_prefix="alias"):
            _cache["mtime"] = None
            return "alias file saved."
        return "Failed to open editor."

    def cmd_alias(args: str) -> str:
        """Handle /alias subcommands"""
        args = args.strip()
        parts = args.split(None, 1)
        sub = parts[0] if parts else "list"

        if sub == "help":
            return (
                "Usage: /alias <subcommand>\n"
                "  list            List aliases (default)\n"
                "  edit            Open $EDITOR in tmux to edit .aicoder/alias\n"
                "  name=value      Set alias (persists to file)\n"
                "  rm <name>       Remove alias\n"
                "  <name>          Show a single alias value\n"
                "Invoke: /<name> [args] - value starting with / runs as a command,\n"
                "otherwise it is sent to the AI as a prompt (args appended)."
            )
        elif sub == "list":
            return _list()
        elif sub == "edit":
            return _edit()
        elif sub == "rm":
            if len(parts) < 2:
                return "Usage: /alias rm <name>"
            name = parts[1].strip().lstrip("/")
            if name not in _get_aliases():
                return f"No alias '{name}'"
            _write(name, value=None)
            return f"Removed alias '{name}'"
        elif "=" in args:
            name, _, value = args.partition("=")
            name = name.strip().lstrip("/")
            value = value.strip()
            if not name or not value:
                return "Usage: /alias name=value"
            if app.command_handler.registry.get_command(name):
                return f"Refusing: '/{name}' is a registered command"
            _write(name, value)
            return _list()
        elif sub in _get_aliases():
            return f"{sub} -> {_get_aliases()[sub]}"
        else:
            return cmd_alias("help")

    ctx.register_command("alias", cmd_alias, "Manage aliases (.aicoder/alias): list|edit|name=value|rm <name>")
    ctx.register_hook("on_unknown_command", on_unknown_command)

    return None
