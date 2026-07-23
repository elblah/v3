"""
Plugin: initial_prompt

Reads AICODER_INITIAL_PROMPT or AICODER_INITIAL_PROMPT_FILE env vars
and sends the prompt automatically at startup.

Usage:
    export AICODER_INITIAL_PROMPT="Explain this video thoroughly"
    # or for large prompts:
    export AICODER_INITIAL_PROMPT_FILE=/path/to/prompt.txt
    aicoder
"""

import os

from aicoder.core.config import Config

_initial_prompt_sent = False


def _read_initial_prompt():
    """Try AICODER_INITIAL_PROMPT first, then AICODER_INITIAL_PROMPT_FILE."""
    direct = os.environ.get("AICODER_INITIAL_PROMPT", "").strip()
    if direct:
        return direct

    path = os.environ.get("AICODER_INITIAL_PROMPT_FILE", "").strip()
    if path:
        try:
            with open(path) as f:
                return f.read().strip()
        except (OSError, UnicodeDecodeError) as e:
            c = Config.colors
            print(f"{c['red']}[initial_prompt] Error reading {path}: {e}{c['reset']}")
            return ""

    return ""


def create_plugin(ctx):
    """Register hook to inject initial prompt at startup"""
    def inject_initial_prompt():
        global _initial_prompt_sent
        if _initial_prompt_sent:
            return

        initial = _read_initial_prompt()
        if not initial:
            return

        _initial_prompt_sent = True
        c = Config.colors
        preview = initial[:2048] + "..." if len(initial) > 2048 else initial
        print(f"\n{c['cyan']}[initial_prompt] Injecting first message: {preview}{c['reset']}")
        ctx.app.set_next_prompt(initial)

    ctx.register_hook("before_user_prompt", inject_initial_prompt)
