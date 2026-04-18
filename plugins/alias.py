"""
Alias Plugin - Command aliases

Features:
- Alias any command by prefix (e.g., /yo -> /yolo on)
- Aliases stored in .aicoder/aliases (project) or ~/.config/aicoder-v3/aliases (global)
- /alias command to list, add, remove aliases
- Tab completion for /alias command
"""

import os
import json
import re
from typing import Optional, Dict
from pathlib import Path
from aicoder.utils.log import LogUtils, success, warn, error, info, dim, print
from aicoder.core.config import Config


def create_plugin(ctx):
    """
    Create alias plugin

    ctx.app provides access to all components:
    - ctx.app.plugin_system: Access hooks for input transformation
    """
    # Alias file locations
    project_aliases_file = ".aicoder/aliases"
    global_aliases_file = os.path.expanduser("~/.config/aicoder-v3/aliases")

    # Cache for aliases
    _cache = {
        "aliases": {},
        "mtime": 0,
        "source_file": None
    }

    def _get_aliases_file() -> Optional[str]:
        """Get aliases file (project takes precedence)"""
        if os.path.exists(project_aliases_file):
            return project_aliases_file
        elif os.path.exists(global_aliases_file):
            return global_aliases_file
        # Create project dir if needed
        if not os.path.exists(".aicoder"):
            os.makedirs(".aicoder", exist_ok=True)
        return project_aliases_file

    def _load_aliases() -> Dict[str, str]:
        """Load aliases from file"""
        aliases_file = _get_aliases_file()
        if not aliases_file:
            return {}

        try:
            if os.path.exists(aliases_file):
                with open(aliases_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return data.get("aliases", {})
        except (json.JSONDecodeError, IOError) as e:
            if Config.debug():
                LogUtils.warn(f"[!] Failed to load aliases: {e}")
        return {}

    def _save_aliases(aliases: Dict[str, str]) -> bool:
        """Save aliases to file"""
        aliases_file = _get_aliases_file()
        if not aliases_file:
            return False

        try:
            with open(aliases_file, 'w', encoding='utf-8') as f:
                json.dump({"aliases": aliases}, f, indent=2)
            return True
        except IOError as e:
            LogUtils.error(f"[!] Failed to save aliases: {e}")
            return False

    def _refresh_cache() -> None:
        """Refresh cache if file mtime changed"""
        aliases_file = _get_aliases_file()
        if not aliases_file:
            return

        try:
            if os.path.exists(aliases_file):
                mtime = os.path.getmtime(aliases_file)
            else:
                mtime = 0
            
            if mtime != _cache["mtime"] or aliases_file != _cache["source_file"]:
                _cache["aliases"] = _load_aliases()
                _cache["mtime"] = mtime
                _cache["source_file"] = aliases_file
        except Exception:
            pass

    def _get_aliases() -> Dict[str, str]:
        """Get current aliases"""
        _refresh_cache()
        return _cache["aliases"]

    def _transform_input(input_str: str) -> str:
        """
        Transform input by replacing aliases

        Hook: after_user_prompt
        """
        if not input_str or not input_str.startswith("/"):
            return input_str

        _refresh_cache()
        aliases = _cache["aliases"]
        if not aliases:
            return input_str

        # Parse command name (everything up to first space or end)
        parts = input_str.split()
        if not parts:
            return input_str

        cmd = parts[0]
        args = parts[1:] if len(parts) > 1 else []

        # Check if command is an alias
        if cmd in aliases:
            replacement = aliases[cmd]
            # Parse replacement: "command arg1 arg2" format
            replacement_parts = replacement.strip().split()
            if replacement_parts:
                # Build new command line
                new_cmd = replacement_parts[0]
                new_args = replacement_parts[1:] + args
                return " ".join([new_cmd] + new_args)

        return input_str

    # Register hook for input transformation
    ctx.register_hook("after_user_prompt", _transform_input)

    # ==================== /alias Command ====================

    def handle_alias_command(args_str: str) -> None:
        """Handle /alias command"""
        args = args_str.strip().split()
        
        if not args:
            # List all aliases
            aliases = _get_aliases()
            if not aliases:
                LogUtils.print("[i] No aliases defined. Use /alias add <alias> <replacement>")
                return
            
            LogUtils.print("[i] Aliases:")
            for alias, replacement in sorted(aliases.items()):
                LogUtils.print(f"  {alias} -> {replacement}")
            return

        subcmd = args[0].lower()
        
        if subcmd == "add":
            if len(args) < 3:
                LogUtils.error("[!] Usage: /alias add <alias> <replacement>")
                return
            
            alias = args[1]
            # Strip quotes from replacement (user may quote it like "/yolo on")
            replacement = " ".join(args[2:]).strip('"').strip("'")
            
            # Normalize alias (ensure / prefix)
            if not alias.startswith("/"):
                alias = "/" + alias
            
            aliases = _get_aliases()
            aliases[alias] = replacement
            
            if _save_aliases(aliases):
                success(f"Alias added: {alias} -> {replacement}")
            else:
                error("Failed to save alias")
        
        elif subcmd == "remove" or subcmd == "rm":
            if len(args) < 2:
                LogUtils.error("[!] Usage: /alias remove <alias>")
                return
            
            alias = args[1]
            if not alias.startswith("/"):
                alias = "/" + alias
            
            aliases = _get_aliases()
            if alias in aliases:
                del aliases[alias]
                if _save_aliases(aliases):
                    success(f"Alias removed: {alias}")
                else:
                    error("Failed to save alias")
            else:
                warn(f"Alias not found: {alias}")
        
        elif subcmd == "clear":
            aliases = _get_aliases()
            if aliases:
                if _save_aliases({}):
                    success("All aliases cleared")
                else:
                    error("Failed to clear aliases")
            else:
                warn("No aliases to clear")
        
        elif subcmd == "help":
            LogUtils.print("[i] /alias commands:")
            LogUtils.print("  /alias              - List all aliases")
            LogUtils.print("  /alias add <a> <b>   - Add alias: /yo -> /yolo on")
            LogUtils.print("  /alias remove <a>   - Remove alias")
            LogUtils.print("  /alias clear        - Clear all aliases")
        else:
            LogUtils.error(f"[!] Unknown subcommand: {subcmd}")
            LogUtils.print("  Use /alias help for usage")

    # Register /alias command
    ctx.register_command("alias", handle_alias_command, "Manage command aliases")

    # ==================== Tab Completion ====================

    def alias_completer(text: str, state: int) -> Optional[str]:
        """
        Completer for /alias command
        """
        if state == 0:
            options = []
            base_cmd = "/alias"

            # Match based on what user typed
            if text.startswith(base_cmd):
                prefix = text[len(base_cmd)+1:] if len(text) > len(base_cmd) + 1 else ""
                
                if not prefix:
                    # Complete subcommands
                    options = ["add", "remove", "rm", "clear", "help"]
                elif prefix in ("remove", "rm"):
                    # Complete with existing aliases
                    aliases = _get_aliases()
                    for alias in aliases:
                        options.append(f"{base_cmd} remove {alias}")
                elif prefix == "add":
                    # Complete with hint
                    options = [f"{base_cmd} add "]
                else:
                    # Filter subcommands
                    subcommands = ["add", "remove", "rm", "clear", "help"]
                    for sub in subcommands:
                        if sub.startswith(prefix):
                            options.append(f"{base_cmd} {sub}")
            
            alias_completer.matches = options

        if hasattr(alias_completer, 'matches') and state < len(alias_completer.matches):
            return alias_completer.matches[state]
        return None

    # Register completer
    ctx.register_completer(alias_completer)

    # No cleanup needed
    return None
