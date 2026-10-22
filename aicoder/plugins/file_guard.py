"""
File Guard Plugin - plugins decide which files the AI tools may touch

Registers the `on_file_access(path, write, context)` hook (fired by
check_sandbox for read_file / write_file / edit_file / grep / list_directory)
and vetoes paths the user wants to keep out of the AI's hands.

Default protected paths:
- .aicoder/stats.log              (this project's AI usage log)
- ~/.aicoder/central_stats.log    (central usage log)

The usage logs are written by stats_logger directly (pure Python), so
blocking them only stops the AI from reading or rewriting its own usage
data - the logger keeps working.

Extra paths come from AICODER_PROTECT_FILES, os.pathsep-separated. Entries
are `~`-expanded and resolved against cwd; a plain path protects the file
AND everything under it (if it is a dir), a path with glob chars
(`* ? [`) is matched with fnmatch against the resolved path:

    AICODER_PROTECT_FILES="/etc/hosts:~/.ssh:secrets/*.env"

Set AICODER_FILE_GUARD=0 to disable the plugin entirely.

Commands:
- /guard            show the effective protected list and how to extend it
"""

import fnmatch
import os
import shlex

from aicoder.utils.bool_utils import env_bool
from aicoder.utils.log import LogUtils

DEFAULT_PROTECTED = (
    ".aicoder/stats.log",
    "~/.aicoder/central_stats.log",
)


def _resolve(entry: str) -> str:
    """Expand ~ and make relative entries cwd-relative, symlinks resolved."""
    p = os.path.expanduser(entry)
    if not os.path.isabs(p):
        p = os.path.join(os.getcwd(), p)
    return os.path.realpath(p)


def _protected_entries() -> list:
    """Effective rules: defaults plus AICODER_PROTECT_FILES."""
    entries = list(DEFAULT_PROTECTED)
    extra = os.environ.get("AICODER_PROTECT_FILES", "")
    for chunk in extra.split(os.pathsep):
        chunk = chunk.strip()
        if chunk:
            entries.append(chunk)
    return entries


def _matches(rule: str, resolved: str) -> bool:
    """True if the resolved path falls under a protection rule."""
    if any(ch in rule for ch in "*?["):
        # Glob rule: expand ~ on the non-glob head only (os.path.expanduser
        # is a no-op when the pattern does not start with ~).
        pattern = os.path.expanduser(rule)
        if not os.path.isabs(pattern):
            pattern = os.path.join(os.getcwd(), pattern)
        return fnmatch.fnmatch(resolved, pattern) or fnmatch.fnmatch(
            resolved, pattern + "/*"
        )
    target = _resolve(rule)
    return resolved == target or resolved.startswith(target + "/")


def _reason(rule: str) -> str:
    """Plugins must explain themselves - shown to the AI and the user."""
    if rule in DEFAULT_PROTECTED:
        return (
            "AI usage log reserved for the stats logger "
            "(AICODER_PROTECT_FILES/AICODER_FILE_GUARD can change this)"
        )
    return f"protected by the user via AICODER_PROTECT_FILES ({rule})"


def create_plugin(ctx):
    """File guard - user/plugin-controlled path vetoes for AI file tools"""
    enabled = env_bool("AICODER_FILE_GUARD", default=True)

    def on_file_access(path, write, context):
        """Return a denial reason (str) to block, None to stay neutral.

        `path` is already resolved (absolute, symlinks followed) by
        check_sandbox; `write` tells read-only tools apart from writes.
        """
        if not enabled:
            return None
        for rule in _protected_entries():
            if _matches(rule, path):
                return _reason(rule)
        return None

    def _shell_hit(command):
        """Reason string if the command text mentions a protected path.

        Best effort: literal rules only (globs are too fuzzy for command
        text) and matching is textual, both the resolved absolute path and
        the rule as written (cwd-relative form included). A very short rule
        can therefore match unrelated commands - the file hook is the exact
        one, this is just a seatbelt against `cat`/`rg`.
        """
        cwd = os.getcwd()
        for rule in _protected_entries():
            if any(ch in rule for ch in "*?["):
                continue
            target = _resolve(rule)
            for form in (target, rule, os.path.relpath(target, cwd)):
                if form and form in command:
                    return _reason(rule)
        return None

    def on_before_run_shell_command(command):
        """Rewrite the shell command into an explanatory no-op when it names
        a protected path, so `cat`/`rg`/`cp` can't reach it either."""
        if not enabled:
            return None
        hit = _shell_hit(command)
        if not hit:
            return None
        return "printf '%s\\n' " + shlex.quote(f"[file_guard] blocked: {hit}")

    if enabled:
        ctx.register_hook("on_file_access", on_file_access)
        ctx.register_hook("on_before_run_shell_command", on_before_run_shell_command)

    def handle_guard(args):
        """Show the effective protected list."""
        LogUtils.print("\n--- File guard ---")
        state = "on" if enabled else "off (AICODER_FILE_GUARD=0)"
        LogUtils.print(f"Guard: {state}")
        LogUtils.print("Protected paths (AI read/write tools are refused):")
        for rule in _protected_entries():
            tag = " (default)" if rule in DEFAULT_PROTECTED else ""
            LogUtils.print(f"  {rule} -> {_resolve(rule)}{tag}")
        LogUtils.print(
            "\nAdd your own with AICODER_PROTECT_FILES "
            f"(separated by {os.pathsep!r}), globs allowed."
        )
        LogUtils.print("Hook: on_file_access(path, write, context) - any plugin")
        LogUtils.print("can register it and return a denial reason string.\n")

    ctx.register_command("/guard", handle_guard, description="Show protected file paths")

    return {"name": "file_guard", "enabled": enabled}
