"""
Snippets Plugin - Reusable prompt snippets

Features:
- Load snippets from .aicoder/snippets (project) and ~/.config/aicoder-v3/snippets (global)
- Local snippets override global on name collision
- Tab completion with @@ prefix
- Automatic snippet replacement in prompts
- /snippets command to list available snippets
"""

import os
import re
from typing import Optional
from pathlib import Path
from aicoder.utils.log import LogUtils, LogOptions, success, warn, error, info, dim, print
from aicoder.core.config import Config


def create_plugin(ctx):
    """
    Create snippets plugin

    ctx.app provides access to all components:
    - ctx.app.input_handler: Register completers
    - ctx.app.message_history: Add messages
    """
    project_snippets_dir = ".aicoder/snippets"
    global_snippets_dir = os.path.expanduser("~/.config/aicoder-v3/snippets")

    # Cache for snippet files: {filename: (source, dir_path)}
    _cache = {
        "snippets": {},   # filename -> (source, dir_path)
        "mtimes": {},     # dir_path -> mtime
    }

    def _get_dirs() -> list:
        """Get snippet directories in scan order (global first, local second for override)"""
        dirs = []
        if os.path.exists(global_snippets_dir):
            dirs.append(("global", global_snippets_dir))
        if os.path.exists(project_snippets_dir):
            dirs.append(("local", project_snippets_dir))
        return dirs

    def _refresh_cache() -> None:
        """Refresh snippet cache if any directory mtime changed"""
        dirs = _get_dirs()
        if not dirs:
            return

        need_reload = False
        for _, d in dirs:
            try:
                mtime = os.path.getmtime(d)
                if _cache["mtimes"].get(d) != mtime:
                    need_reload = True
                    break
            except Exception:
                pass

        if not need_reload and _cache["snippets"]:
            return

        # Reload from all dirs (global first, local overrides)
        _cache["snippets"] = {}
        for source, d in dirs:
            try:
                current_mtime = os.path.getmtime(d)
                _cache["mtimes"][d] = current_mtime
                for f in os.scandir(d):
                    if f.is_file() and not f.name.startswith("."):
                        _cache["snippets"][f.name] = (source, d)
            except Exception:
                pass

    def _get_snippets() -> list:
        """Get list of snippet filenames"""
        _refresh_cache()
        return list(_cache["snippets"].keys())

    def _load_snippet(name: str) -> Optional[str]:
        """Load snippet content by name (with or without extension)"""
        _refresh_cache()

        # Try exact match first
        if name in _cache["snippets"]:
            _, d = _cache["snippets"][name]
            path = os.path.join(d, name)
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    return f.read()
            except Exception:
                return None

        # Try without extension (find first matching file)
        name_without_ext = Path(name).stem
        for filename, (source, d) in _cache["snippets"].items():
            if Path(filename).stem == name_without_ext:
                path = os.path.join(d, filename)
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
                    success(f"Loaded snippet: @@{snippet_name}")
                else:
                    # Warn user about missing snippet
                    warn(f"Snippet '@@{snippet_name}' not found")

            return prompt
        except Exception as e:
            error(f"Snippet hook error: {e}")
            return prompt

    # Register hook
    ctx.register_hook("after_user_prompt", transform_prompt_with_snippets)

    # ==================== /snippets Command ====================

    def handle_snippets_command(args: list = None) -> None:
        """Handle /snippets command - list available snippets"""
        dirs = _get_dirs()
        if not dirs:
            warn("No snippets directory found.")
            dim("  Create .aicoder/snippets/ (project) or ~/.config/aicoder-v3/snippets/ (global)")
            return

        snippets = _get_snippets()
        if not snippets:
            warn("No snippets found.")
            return

        # Display snippets grouped by source
        dirs_display = " + ".join(
            ("project" if s == "local" else "global") for s, _ in dirs
        )
        info(f"Available snippets ({dirs_display}):")

        for snippet in snippets:
            source, _ = _cache["snippets"][snippet]
            tag = "local" if source == "local" else "global"
            print(f"  - {snippet} [{tag}]")

        # Show usage
        dim("\nUsage: Include @@snippet_name in your prompt.")
        dim("Example: Use @@ultrathink to analyze the code")

    # Register command
    ctx.register_command("snippets", handle_snippets_command, "List available snippets")

    # No cleanup needed
    return None
