"""
Auto-reload AGENTS.md when it changes.
"""

import os
from aicoder.core.prompt_builder import PromptBuilder
from aicoder.utils.log import LogUtils


def create_plugin(ctx):
    app = ctx.app
    path = "AGENTS.md"
    mtime = None

    def check():
        nonlocal mtime

        if not os.path.exists(path):
            return

        try:
            current = os.path.getmtime(path)
        except OSError:
            return

        if mtime is None:
            mtime = current
            return

        if current == mtime:
            return

        mtime = current
        LogUtils.info("AGENTS.md changed, reloading...")

        if not PromptBuilder.is_initialized():
            PromptBuilder.initialize()

        prompt = PromptBuilder.build_system_prompt()
        msgs = app.message_history.messages
        if msgs and msgs[0].get("role") == "system":
            msgs[0]["content"] = prompt
            app.message_history.estimate_context()

    ctx.register_hook("before_ai_processing", check)
