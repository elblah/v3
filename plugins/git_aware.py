"""
Git Aware Plugin - Adds git context to AI system prompt

This plugin detects if the current directory is a git repository and adds
context to the AI system prompt about git awareness and commit requirements.
"""

import os
import subprocess

from aicoder.core.config import Config


def create_plugin(ctx):
    """Git awareness plugin"""
    if Config.debug():
        print("[*] Git aware plugin loading...")

    def is_git_repo() -> bool:
        """Check if current directory is a git repository"""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--is-inside-work-tree"],
                capture_output=True,
                text=True,
                timeout=5
            )
            return result.returncode == 0 and result.stdout.strip() == "true"
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
            return False

    def get_git_context() -> str:
        """Get git context information for system prompt"""
        if not is_git_repo():
            return ""

        try:
            # Get current branch
            branch_result = subprocess.run(
                ["git", "branch", "--show-current"],
                capture_output=True,
                text=True,
                timeout=5
            )
            current_branch = branch_result.stdout.strip() if branch_result.returncode == 0 else "unknown"

            # Get status summary
            status_result = subprocess.run(
                ["git", "status", "--porcelain"],
                capture_output=True,
                text=True,
                timeout=5
            )
            has_changes = bool(status_result.stdout.strip()) if status_result.returncode == 0 else False

            return f"""

Git Repository:
- Branch: {current_branch}
- Status: {'Has changes' if has_changes else 'Clean'}

Note: Tasks are complete when changes are committed to git.
"""
        except (subprocess.TimeoutExpired, FileNotFoundError, subprocess.SubprocessError):
            return ""

    def on_before_user_prompt():
        """Hook: Add git context to system prompt before user prompt"""
        # Access messages through the app context
        messages = ctx.app.message_history.messages
        if Config.debug():
            print(f"[*] Git aware: before_user_prompt called with {len(messages)} messages")
        
        git_context = get_git_context()
        if Config.debug():
            print(f"[*] Git aware: git_context = '{git_context.strip()}'")
        
        # Early return if no git context
        if not git_context:
            if Config.debug():
                print("[*] Git aware: Not in git repo or no git context")
            return
        
        # Early return if no messages
        if not messages or len(messages) == 0:
            if Config.debug():
                print("[*] Git aware: No messages found")
            return
        
        system_msg = messages[0]
        if Config.debug():
            print(f"[*] Git aware: First message role = {system_msg.get('role')}")
        
        # Early return if not a system message
        if system_msg.get("role") != "system":
            if Config.debug():
                print("[*] Git aware: First message is not system message")
            return
        
        # Append git context to existing system message
        original_content = system_msg.get("content", "")
        if Config.debug():
            print(f"[*] Git aware: Original content length = {len(original_content)}")
            print(f"[*] Git aware: Contains 'Git Repository:' = {'Git Repository:' in original_content}")
        
        # Early return if git context already present
        if "Git Repository:" in original_content:
            if Config.debug():
                print("[*] Git aware: Git context already present, skipping")
            return
        
        # Add git context
        system_msg["content"] = original_content + git_context
        if Config.debug():
            print("[*] Git aware: Added git context to system prompt")
            print(f"[*] Git aware: New content length = {len(system_msg['content'])}")

    # Register hook
    ctx.register_hook("before_user_prompt", on_before_user_prompt)

    if Config.debug():
        print("  - before_user_prompt hook (git awareness)")