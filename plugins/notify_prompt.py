"""
Notify Prompt Plugin - Audio notifications for prompts and approvals

Features:
- Uses espeak for text-to-speech
- Only notifies when .notify-prompt file exists in project
- Hooks into before_user_prompt and before_approval_prompt events
- Detects HDMI audio sink and redirects audio there if available
"""

import os
import subprocess

from aicoder.core.config import Config
from aicoder.utils.log import LogUtils


def create_plugin(ctx):
    """Audio notifications plugin"""

    DEV_NULL = "/dev/null"  # Keep simple for now

    current_sink = "pipewire/combined"  # Default sink

    def detect_audio_sink():
        """Detect audio sink (HDMI preferred, fallback to pipewire)"""
        nonlocal current_sink
        try:
            # Try to detect HDMI sink first
            result = subprocess.run(
                ["pactl", "list", "sinks", "short"],
                capture_output=True,
                text=True
            )
            for line in result.stdout.split("\n"):
                if "hdmi" in line.lower():
                    # Extract sink name (second column)
                    parts = line.split()
                    if len(parts) >= 2:
                        current_sink = parts[1]
                        return
        except:
            pass
        # Fallback to default
        current_sink = "pipewire/combined"

    # Detect audio sink on load
    detect_audio_sink()

    def should_notify() -> bool:
        """Check if .notify-prompt file exists"""
        return os.path.exists(".notify-prompt")

    def say(message: str) -> None:
        """Speak message using espeak with audio sink"""
        subprocess.Popen(
            f'PULSE_SINK="{current_sink}" espeak "{message}" 2>{DEV_NULL}',
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

    def on_before_user_prompt():
        """Hook: Called before showing user input prompt"""
        if should_notify():
            say("prompt available")

    def on_before_approval_prompt(tool_name: str = None, arguments: dict = None):
        """Hook: Called before showing tool approval prompt"""
        if should_notify():
            say("approval available")

    # Register hooks
    ctx.register_hook("before_user_prompt", on_before_user_prompt)
    ctx.register_hook("before_approval_prompt", on_before_approval_prompt)

    if Config.debug():
        LogUtils.print("  - before_user_prompt hook")
        LogUtils.print("  - before_approval_prompt hook")
