"""Input prompt helpers built on readline.

The main prompt and any yes/no-style sub-prompts share the same global
readline history, so sub-prompts would otherwise offer the user's chat
prompts on up/down. These helpers swap in a dedicated history for the
duration of a sub-prompt and restore the original one afterwards.
"""

import readline
from contextlib import contextmanager


@contextmanager
def temporary_history(options):
    """Replace readline history with `options`; restore on exit.

    Entries are offered oldest-first, so up-arrow yields the LAST option
    first. Put the most useful/default option last.
    """
    saved = [
        readline.get_history_item(i)
        for i in range(1, readline.get_current_history_length() + 1)
    ]
    readline.clear_history()
    for opt in options:
        readline.add_history(opt)
    try:
        yield
    finally:
        readline.clear_history()
        for item in saved:
            readline.add_history(item)


def prompt_choice(prompt, history):
    """Input prompt with `history` as the up/down entries instead of the
    normal prompt history. Restored on return.

    Returns the stripped answer as typed; parsing/validation is the
    caller's job. KeyboardInterrupt/EOFError propagate.
    """
    with temporary_history(history):
        return input(prompt).strip()
