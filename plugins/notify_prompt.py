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

    DEV_NULL = "/dev/null"

    # Configuration
    voice = os.environ.get("NOTIFY_VOICE", "en-us+f3")  # Default female f3
    speed = int(os.environ.get("NOTIFY_SPEED", "250"))  # Faster than default (175)

    # Detect audio sink (HDMI preferred)
    current_sink = "pipewire/combined"

    def detect_audio_sink():
        """Detect audio sink (HDMI preferred, fallback to pipewire)"""
        nonlocal current_sink
        try:
            result = subprocess.run(
                ["pactl", "list", "sinks", "short"],
                capture_output=True,
                text=True,
                timeout=2  # Don't hang if pactl is slow
            )
            for line in result.stdout.split("\n"):
                if "hdmi" in line.lower():
                    parts = line.split()
                    if len(parts) >= 2:
                        current_sink = parts[1]
                        return
        except Exception:
            pass
        current_sink = "pipewire/combined"

    # Detect audio sink on load (cached)
    detect_audio_sink()

    def should_notify() -> bool:
        """Check if .notify-prompt file exists"""
        return os.path.exists(".notify-prompt")

    def say(message: str) -> None:
        """Speak message using espeak with audio sink, voice, and speed"""
        # Build environment with audio sink
        env = os.environ.copy()
        env["PULSE_SINK"] = current_sink

        # Use list args for faster startup (no shell=True)
        subprocess.Popen(
            ["espeak", "-v", voice, "-s", str(speed), message],
            env=env,
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
        LogUtils.print(f"  - before_user_prompt hook (notify, voice: {voice}, speed: {speed})")
        LogUtils.print(f"  - before_approval_prompt hook (notify, sink: {current_sink})")
