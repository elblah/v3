"""
Git Aware Plugin - Adds git context to AI system prompt

This plugin detects if the current directory is a git repository and adds
context to the AI system prompt about git awareness and commit requirements.
Runs git command only once at plugin load to cache branch name.
"""

import subprocess

from aicoder.core.config import Config

# Cache git branch at module level - run once at plugin load
_cached_git_branch = None


def _get_git_branch():
    """Get current git branch, returns None if not a git repo"""
    try:
        result = subprocess.run(
            ["git", "branch", "--show-current"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
        pass
    return None


def create_plugin(ctx):
    """Git awareness plugin"""
    global _cached_git_branch

    # Run git command once at load time
    _cached_git_branch = _get_git_branch()

    if Config.debug():
        if _cached_git_branch:
            print(f"[*] Git aware: Branch = '{_cached_git_branch}'")
        else:
            print("[*] Git aware: Not a git repository")

    def on_before_user_prompt():
        """Hook: Add git context to system prompt before user prompt"""
        if not _cached_git_branch:
            return

        messages = ctx.app.message_history.messages
        if not messages or len(messages) == 0:
            return

        system_msg = messages[0]
        if system_msg.get("role") != "system":
            return

        original_content = system_msg.get("content", "")
        if "Git Repository:" in original_content:
            return

        git_context = f"""

Git Repository:
- Branch: {_cached_git_branch}
"""
        system_msg["content"] = original_content + git_context

    # Register hook
    ctx.register_hook("before_user_prompt", on_before_user_prompt)

    if Config.debug():
        print("  - before_user_prompt hook (git awareness)")
