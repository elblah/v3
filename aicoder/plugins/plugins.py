"""
Plugin Manager - List and inspect loaded plugins.

Commands:
  /plugins list       - List loaded plugins by tier (Project/Global/Internal)
  /plugins show <id>  - Show details for a plugin (id = filename stem)
"""

import functools

from aicoder.core.config import Config

_SOURCE_LABELS = {
    "local": "project",
    "global": "global",
    "bundled": "internal",
}

# Section order follows plugin precedence (higher tier wins)
_SECTIONS = (
    ("local", "Project"),
    ("global", "Global"),
    ("bundled", "Internal"),
)


def _source_label(source: str) -> str:
    return _SOURCE_LABELS.get(source, source)


def _entries(ctx):
    if ctx and ctx.app and ctx.app.plugin_system:
        return ctx.app.plugin_system.plugin_info
    return []


def _list_plugins(ctx) -> str:
    entries = _entries(ctx)
    if not entries:
        return "\nNo plugins found"

    green = Config.colors["green"]
    reset = Config.colors["reset"]
    bold = Config.colors["bold"]

    sections = []
    for source, title in _SECTIONS:
        group = sorted((e for e in entries if e["source"] == source), key=lambda e: e["id"])
        if not group:
            continue

        id_width = max(len(e["id"]) for e in group)
        lines = [f"{bold}{title}:{reset}"]
        for entry in group:
            detail = entry["name"] if entry["name"] != entry["id"] else ""
            if entry["error"]:
                detail = f"FAILED: {entry['error'].splitlines()[0]}"

            line = f"  {green}{entry['id']}{reset}"
            if detail:
                padding = " " * (id_width - len(entry["id"]) + 2)
                line += f"{padding}- {detail}"
            lines.append(line)

        sections.append("\n".join(lines))

    return "\n\n".join(sections)


def _show_plugin(plugin_id: str, ctx) -> str:
    if not plugin_id:
        return "Usage: /plugins show <id>"

    matches = [entry for entry in _entries(ctx) if entry["id"] == plugin_id]
    if not matches:
        return f"Plugin not found: {plugin_id}"

    blocks = []
    for entry in matches:
        lines = [
            f"Name: {entry['name']}",
            f"ID: {entry['id']}",
            f"Source: {_source_label(entry['source'])}",
            f"File: {entry['path']}",
        ]
        if entry["error"]:
            lines.append(f"Error: {entry['error']}")
        lines.append("Description:")
        lines.append(entry["description"] or "(no description)")
        blocks.append("\n".join(lines))
    return "\n\n".join(blocks)


def _handle_plugins(args: str, ctx=None) -> str:
    parts = args.strip().split()
    sub = parts[0] if parts else "list"

    if sub == "list":
        return "\n" + _list_plugins(ctx)
    if sub == "show":
        return _show_plugin(" ".join(parts[1:]), ctx)
    return "Usage: /plugins [list | show <id>]"


def create_plugin(
    ctx,
    name="Plugin Manager",
    description="List and inspect loaded plugins (/plugins list, /plugins show <id>)",
):
    handler = functools.partial(_handle_plugins, ctx=ctx)
    ctx.register_command("plugins", handler, "List and inspect loaded plugins")
    return {}
