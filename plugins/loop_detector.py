"""
Loop Detector - Detects when AI repeats the same response N times consecutively.

When threshold hit -> stops AI processing + warns user.

Hooks:
    after_assistant_message_added -> track fingerprints
    after_ai_processing           -> check, stop, warn
    after_user_message_added      -> clear history/cooling on user input

Commands:
    /ld                - Show status
    /ld N              - Set threshold (default: 15)
    /ld on|off         - Enable/disable

Environment:
    LOOP_DETECTOR_THRESHOLD=15
    LOOP_DETECTOR_ENABLE=1
"""

import os
import hashlib

from aicoder.core.config import Config
from aicoder.utils.log import LogUtils

# --- State ---

_threshold = 15
_enabled = True
_cooling_down = False
_history = []
_max_history = 30
_app = None

# Colors
_RED = "\033[91m"
_YELLOW = "\033[93m"
_RESET = "\033[0m"


def _fingerprint(msg: dict) -> str:
    """Fingerprint entire message including text and tool calls"""
    # Extract text content
    content = msg.get("content", "")
    
    # Extract tool calls if present
    tool_calls = msg.get("tool_calls", [])
    
    # Build fingerprint parts
    parts = [f"text:{content}"]
    
    if tool_calls:
        # Sort tool calls for deterministic fingerprinting
        for tc in sorted(tool_calls, key=lambda x: str(x)):
            parts.append(f"tool:{tc}")
    
    combined = "|".join(parts)
    return hashlib.md5(combined.encode()).hexdigest()


def _count_repeats() -> int:
    if not _history:
        return 0
    last = _history[-1]
    count = 0
    for fp in reversed(_history):
        if fp == last:
            count += 1
        else:
            break
    return count


def _stop_ai() -> None:
    if _app and _app.session_manager:
        _app.session_manager.is_processing = False


# --- Hooks ---

def after_user_message_added(msg: dict) -> None:
    """User wrote new input -> loop is broken -> clear history"""
    global _cooling_down
    if not _enabled:
        return
    _cooling_down = False
    _history.clear()


def after_assistant_message_added(msg: dict) -> None:
    """Track fingerprints"""
    if not _enabled:
        return
    fp = _fingerprint(msg)
    _history.append(fp)
    if len(_history) > _max_history:
        _history.pop(0)


def after_ai_processing(has_tool_calls: bool) -> str | None:
    """Check loop. If threshold hit, stop AI and warn user."""
    global _cooling_down
    if not _enabled:
        return None
    if _cooling_down:
        return None
    if len(_history) < _threshold:
        return None

    repeats = _count_repeats()
    if repeats >= _threshold:
        print(
            f"{_RED}[!] LOOP DETECTED: {repeats} repeated responses "
            f"(threshold={_threshold}){_RESET}"
        )
        print(f"{_YELLOW}    AI processing stopped. Send new prompt to continue.{_RESET}")

        _history.clear()
        _cooling_down = True
        _stop_ai()
        return None

    return None


# --- Command ---

def show_help() -> None:
    status = "enabled" if _enabled else "disabled"
    LogUtils.printc(
        f"[loop-detector] {status}, threshold={_threshold}",
        color="cyan",
    )
    LogUtils.print("Commands:")
    LogUtils.print("  /ld N       - Set threshold")
    LogUtils.print("  /ld on|off  - Enable/disable")
    LogUtils.print("Env: LOOP_DETECTOR_THRESHOLD=15, LOOP_DETECTOR_ENABLE=1")


def handle_command(args: str) -> None:
    global _threshold, _enabled, _custom_message, _cooling_down

    parts = args.strip().split() if args.strip() else []

    if not parts or parts[0] == "help":
        show_help()
        return

    if parts[0] == "on":
        _enabled = True
        LogUtils.printc("[loop-detector] Enabled", color="cyan")
        return

    if parts[0] == "off":
        _enabled = False
        _cooling_down = False
        _history.clear()
        LogUtils.printc("[loop-detector] Disabled", color="cyan")
        return

    if parts[0].isdigit():
        _threshold = max(1, int(parts[0]))
        _history.clear()
        LogUtils.printc(f"[loop-detector] Threshold set to {_threshold}", color="cyan")
        return

    show_help()


# --- Entry Point ---

def create_plugin(ctx):
    global _threshold, _enabled, _app, _cooling_down

    _app = ctx.app
    _cooling_down = False

    # Env overrides
    env_threshold = os.environ.get("LOOP_DETECTOR_THRESHOLD", "")
    if env_threshold.isdigit():
        _threshold = max(1, int(env_threshold))

    env_enabled = os.environ.get("LOOP_DETECTOR_ENABLE", "").lower()
    if env_enabled in ("0", "false", "off", "no"):
        _enabled = False

    ctx.register_hook("after_assistant_message_added", after_assistant_message_added)
    ctx.register_hook("after_user_message_added", after_user_message_added)
    ctx.register_hook("after_ai_processing", after_ai_processing)

    ctx.register_command("loop-detector", handle_command, "Loop detector settings")
    ctx.register_command("ld", handle_command, "Loop detector (alias)")

    if Config.debug():
        LogUtils.printc(
            f"[+] Loaded loop_detector plugin (threshold={_threshold})",
            color="cyan",
        )

    return {}
