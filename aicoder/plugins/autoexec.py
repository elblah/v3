"""
autoexec.py - Execute .aicoder/autoexec line by line at startup

Each line is fed as the next prompt. The main loop handles commands/prompts.

Example .aicoder/autoexec:
  /cs 100k
  /detail on
  hello my name is Blah
"""

import os
from aicoder.core.config import Config

_AUTOEXEC_FILE = ".aicoder/autoexec"


def create_plugin(ctx):
    """Load .aicoder/autoexec and feed lines one by one via hook"""
    app = ctx.app
    lines = []
    started = False

    def feed_next():
        nonlocal lines, started

        if not started:
            # First call: read file and set first prompt
            started = True
            if not os.path.exists(_AUTOEXEC_FILE):
                return

            try:
                with open(_AUTOEXEC_FILE, 'r') as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith('#'):
                            if ' #' in line:
                                line = line[:line.index(' #')].strip()
                            if line:
                                lines.append(line)
            except Exception as e:
                if Config.debug():
                    print(f"[autoexec] Read error: {e}")
                return

            if not lines:
                return

            c = Config.colors
            print(f"\n{c['cyan']}[autoexec] {len(lines)} line(s){c['reset']}")

            next_line = lines.pop(0)
            print(f"\n{c['cyan']}[autoexec] {next_line}{c['reset']}")
            app.set_next_prompt(next_line)
            return

        # Subsequent calls: feed next line if any
        if not lines:
            return

        c = Config.colors
        next_line = lines.pop(0)
        print(f"\n{c['cyan']}[autoexec] {next_line}{c['reset']}")
        app.set_next_prompt(next_line)

    ctx.register_hook("before_user_prompt", feed_next)
