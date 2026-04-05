"""
Auto-reload system prompt when any source changes.

Monitors:
- AGENTS.md
- PROMPT-OVERRIDE.md
- default-system-prompt.md (via template reload)
- AICODER_SYSTEM_PROMPT env var
- AICODER_SYSTEM_PROMPT_APPEND env var

This replaces agents_md_reloader.py with comprehensive monitoring.
"""

import os
from aicoder.core.prompt_builder import PromptBuilder
from aicoder.utils.log import LogUtils


def _get_template_path():
    """Get the actual path to default-system-prompt.md by looking at where PromptBuilder loads it from"""
    import aicoder.core.prompt_builder as pb_module
    
    # Get the directory of the prompt_builder module
    pb_dir = os.path.dirname(os.path.abspath(pb_module.__file__))
    
    # Go up one level (from core/ to project root), then to aicoder/prompts/
    project_root = os.path.dirname(pb_dir)
    return os.path.join(project_root, "prompts", "default-system-prompt.md")


def create_plugin(ctx):
    app = ctx.app

    # Get the actual template path from PromptBuilder's perspective
    _template_path = _get_template_path()

    # File name -> path mapping
    file_paths = {
        "AGENTS.md": "AGENTS.md",
        "PROMPT-OVERRIDE.md": "PROMPT-OVERRIDE.md",
        "default-system-prompt.md": _template_path,
    }

    # Track mtimes separately
    file_mtimes = {name: None for name in file_paths}

    # Track env var values
    env_vars = {
        "AICODER_SYSTEM_PROMPT": None,
        "AICODER_SYSTEM_PROMPT_APPEND": None,
    }

    def get_mtime(path):
        try:
            return os.path.getmtime(path)
        except OSError:
            return None

    def get_env(var):
        return os.environ.get(var)

    # Initialize mtimes
    for name, path in file_paths.items():
        file_mtimes[name] = get_mtime(path)

    for var in env_vars:
        env_vars[var] = get_env(var)

    def check():
        changed = []

        # Check file modifications
        for name, path in file_paths.items():
            current_mtime = get_mtime(path)
            cached_mtime = file_mtimes[name]

            if current_mtime is None and cached_mtime is not None:
                changed.append(f"{name} (DELETED)")
                file_mtimes[name] = None
            elif current_mtime is not None and cached_mtime is None:
                changed.append(f"{name} (CREATED)")
                file_mtimes[name] = current_mtime
            elif current_mtime is not None and current_mtime != cached_mtime:
                changed.append(f"{name} (MODIFIED)")
                file_mtimes[name] = current_mtime

        # Check env var changes
        for var, cached_value in env_vars.items():
            current_value = get_env(var)
            if current_value != cached_value:
                old_val = (cached_value[:30] + "...") if cached_value and len(cached_value) > 30 else repr(cached_value)
                new_val = (current_value[:30] + "...") if current_value and len(current_value) > 30 else repr(current_value)
                changed.append(f"{var} (CHANGED): {old_val} -> {new_val}")
                env_vars[var] = current_value

        if not changed:
            return

        # Log each changed source explicitly
        for item in changed:
            LogUtils.info(f"[prompt-reload] Detected change: {item}")

        # Rebuild system prompt (clear cache first to force re-read of template)
        PromptBuilder._default_prompt_template = None
        PromptBuilder.initialize()
        prompt = PromptBuilder.build_system_prompt()

        # Update system message in conversation
        msgs = app.message_history.messages
        if msgs and msgs[0].get("role") == "system":
            msgs[0]["content"] = prompt
            app.message_history.estimate_context()
            LogUtils.info("System prompt updated in conversation")

    def force_reload(args):
        """Force reload system prompt from all sources"""
        LogUtils.info("[prompt-reload] Force reload triggered")

        # Clear template cache and re-initialize
        PromptBuilder._default_prompt_template = None
        PromptBuilder.initialize()

        # Rebuild
        prompt = PromptBuilder.build_system_prompt()

        # Update system message
        msgs = app.message_history.messages
        if msgs and msgs[0].get("role") == "system":
            old_len = len(msgs[0]["content"])
            msgs[0]["content"] = prompt
            app.message_history.estimate_context()
            new_len = len(msgs[0]["content"])
            return f"System prompt rebuilt ({old_len} -> {new_len} chars)"
        return "System prompt rebuilt (no system message found)"

    def on_session_init(args):
        """Hook to reload prompt on session load/start"""
        LogUtils.info("[prompt-reload] Session initialized, rebuilding prompt")
        force_reload(None)

    def on_session_change(args=None):
        """Hook called when session changes (before load/new)"""
        pass

    def on_messages_set(args=None):
        """Hook called after messages are set (e.g., after /load)"""
        force_reload(None)

    ctx.register_command("prompt-reload", force_reload, "Force reload system prompt from all sources")
    ctx.register_hook("after_session_initialized", on_session_init)
    ctx.register_hook("on_session_change", on_session_change)
    ctx.register_hook("after_messages_set", on_messages_set)
    ctx.register_hook("before_ai_processing", check)
