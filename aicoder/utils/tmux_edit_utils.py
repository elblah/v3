"""Tmux editor utility — open $EDITOR in a new tmux window and wait for close.

Usage:
    from aicoder.utils.tmux_edit_utils import tmux_open_editor

    if tmux_open_editor("/tmp/myfile.md", "my-prefix"):
        content = open("/tmp/myfile.md").read()
"""

import os
import secrets
import subprocess


def tmux_open_editor(filepath: str, window_name_prefix: str = "edit",
                     editor: str | None = None) -> bool:
    """Open editor in a new tmux window, wait for editor to close.

    Args:
        filepath: Path to file to open in editor.
        window_name_prefix: Prefix for tmux window name and sync point.
                           e.g. "edit" → window "edit_abc123", sync "edit_done_abc123".
        editor: Editor to use. If None, uses $EDITOR or "nano".

    Returns:
        True if editor opened and closed successfully, False otherwise.
    """
    if editor is None:
        editor = os.environ.get("EDITOR", "nano")
    token = secrets.token_hex(4)
    sync_point = f"{window_name_prefix}_done_{token}"
    window_name = f"{window_name_prefix}_{token}"

    tmux_cmd = (
        f'tmux new-window -n "{window_name}" '
        f'\'bash -c "{editor} {filepath}; tmux wait-for -S {sync_point}"\''
    )

    result = subprocess.run(tmux_cmd, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        return False

    result = subprocess.run(
        f"tmux wait-for {sync_point}", shell=True, capture_output=True, text=True
    )
    return result.returncode == 0
