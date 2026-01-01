"""
Snippets Plugin - Reusable prompt snippets

Features:
- Load snippets from .aicoder/snippets (project) or ~/.config/aicoder-v3/snippets (global)
- Tab completion with @@ prefix
- Automatic snippet replacement in prompts
- /snippets command to list available snippets
"""

import os
import re
from typing import Optional
from pathlib import Path
from aicoder.utils.log import LogUtils, LogOptions
from aicoder.core.config import Config


def create_plugin(ctx):
    """
    Create snippets plugin

    ctx.app provides access to all components:
    - ctx.app.input_handler: Register completers
    - ctx.app.message_history: Add messages
    """
    # Snippet directories
    project_snippets_dir = ".aicoder/snippets"
    global_snippets_dir = os.path.expanduser("~/.config/aicoder-v3/snippets")

    # Cache for snippet files
    _cache = {
        "snippets": [],
        "mtime": 0,
        "source_dir": None
    }

    def _get_snippets_dir() -> Optional[str]:
        """Get the snippets directory (project takes precedence)"""
        if os.path.exists(project_snippets_dir):
            return project_snippets_dir
        elif os.path.exists(global_snippets_dir):
            return global_snippets_dir
        return None

    def _refresh_cache() -> None:
        """Refresh snippet cache if directory mtime changed"""
        snippets_dir = _get_snippets_dir()
        if not snippets_dir:
            return

        try:
            mtime = os.path.getmtime(snippets_dir)
            if mtime != _cache["mtime"] or snippets_dir != _cache["source_dir"]:
                # Reload snippet files
                _cache["snippets"] = [
                    f.name for f in os.scandir(snippets_dir)
                    if f.is_file() and not f.name.startswith(".")
                ]
                _cache["mtime"] = mtime
                _cache["source_dir"] = snippets_dir
        except Exception:
            pass

    def _get_snippets() -> list:
        """Get list of snippet files"""
        _refresh_cache()
        return _cache["snippets"]

    def _load_snippet(name: str) -> Optional[str]:
        """Load snippet content by name (with or without extension)"""
        snippets_dir = _get_snippets_dir()
        if not snippets_dir:
            return None

        # Try exact match first (with extension)
        path = os.path.join(snippets_dir, name)
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception:
                return None

        # Try without extension (find first matching file)
        name_without_ext = Path(name).stem
        for snippet_file in _get_snippets():
            if Path(snippet_file).stem == name_without_ext:
                path = os.path.join(snippets_dir, snippet_file)
                try:
                    with open(path, 'r', encoding='utf-8') as f:
                        return f.read()
                except Exception:
                    return None

        return None

    # ==================== Tab Completion ====================

    def snippet_completer(text: str, state: int) -> Optional[str]:
        """
        Completer function for snippet completion

        Activates when text starts with @@
        Uses readline state machine pattern: state=0 to init, state>0 to iterate
        """
        # Only activate for @@ prefix
        if not text.startswith("@@"):
            return None

        if state == 0:
            options = []

            # Remove @@ prefix for matching
            prefix = text[2:]
            snippets = _get_snippets()

            # Match snippets
            for snippet in snippets:
                if snippet.startswith(prefix):
                    # Complete with @@ prefix
                    options.append(f"@@{snippet}")

            # Store for iteration
            snippet_completer.matches = options

        # Return the appropriate match based on state
        if hasattr(snippet_completer, 'matches') and state < len(snippet_completer.matches):
            return snippet_completer.matches[state]
        return None

    # Register completer (let PluginSystem handle the checks)
    ctx.register_completer(snippet_completer)

    # ==================== Hook for Snippet Replacement ====================

    def transform_prompt_with_snippets(prompt: str) -> str:
        """
        Transform prompt by replacing @@snippet with file content

        Hook: after_user_prompt
        """
        try:
            if not prompt or "@@" not in prompt:
                return prompt

            # Find all @@snippet references
            pattern = r'@@(\S+)'
            matches = re.findall(pattern, prompt)

            for snippet_name in matches:
                content = _load_snippet(snippet_name)
                if content:
                    # Replace @@snippet with content
                    prompt = prompt.replace(f'@@{snippet_name}', content)
                    # Log the replacement
                    LogUtils.print(
                        f"[+] Loaded snippet: @@{snippet_name}",
                        LogOptions(color=Config.colors['green'])
                    )
                else:
                    # Warn user about missing snippet
                    LogUtils.print(
                        f"[!] Snippet '@@{snippet_name}' not found",
                        LogOptions(color=Config.colors['yellow'])
                    )

            return prompt
        except Exception as e:
            LogUtils.print(
                f"[!] Snippet hook error: {e}",
                LogOptions(color=Config.colors['red'])
            )
            return prompt

    # Register hook
    ctx.register_hook("after_user_prompt", transform_prompt_with_snippets)

    # ==================== /snippets Command ====================

    def handle_snippets_command(args: list = None) -> None:
        """Handle /snippets command - list available snippets"""
        snippets_dir = _get_snippets_dir()
        if not snippets_dir:
            LogUtils.print(
                "No snippets directory found.",
                LogOptions(color=Config.colors['yellow'])
            )
            LogUtils.print(
                "  Create .aicoder/snippets/ (project) or ~/.config/aicoder-v3/snippets/ (global)",
                LogOptions(color=Config.colors['dim'])
            )
            return

        snippets = _get_snippets()
        if not snippets:
            LogUtils.print(
                "No snippets found in directory.",
                LogOptions(color=Config.colors['yellow'])
            )
            return

        # Display snippets
        source_name = "project" if snippets_dir == project_snippets_dir else "global"
        LogUtils.print(
            f"Available snippets ({source_name}):",
            LogOptions(color=Config.colors['cyan'])
        )
        for snippet in snippets:
            LogUtils.print(f"  - {snippet}", LogOptions())

        # Show usage
        LogUtils.print(
            "\nUsage: Include @@snippet_name in your prompt.",
            LogOptions(color=Config.colors['dim'])
        )
        LogUtils.print(
            "Example: Use @@ultrathink to analyze the code",
            LogOptions(color=Config.colors['dim'])
        )

    # Register command
    ctx.register_command("snippets", handle_snippets_command, "List available snippets")

    # No cleanup needed
    return None
