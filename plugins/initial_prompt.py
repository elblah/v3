"""
Plugin: initial_prompt

Reads AICODER_INITIAL_PROMPT env var and sends it automatically at startup.
No user input needed - the prompt fires immediately.

Usage:
    export AICODER_INITIAL_PROMPT="Explain this video thoroughly"
    aicoder
    # AI responds immediately with explanation
"""

import os

from aicoder.core.config import Config

_initial_prompt_sent = False


def create_plugin(ctx):
    """Register hook to inject initial prompt at startup"""
    def inject_initial_prompt():
        global _initial_prompt_sent
        if _initial_prompt_sent:
            return

        initial = os.environ.get("AICODER_INITIAL_PROMPT", "").strip()
        if not initial:
            return

        _initial_prompt_sent = True
        c = Config.colors
        print(f"\n{c['cyan']}[initial_prompt] Injecting first message: {initial}{c['reset']}")
        # Set as next prompt - will be used instead of waiting for user input
        ctx.app.set_next_prompt(initial)

    ctx.register_hook("before_user_prompt", inject_initial_prompt)
