"""
API Throttle Plugin - Add configurable delay between API requests

Some APIs detect rapid requests as abuse. This plugin adds a delay
before each API request to avoid rate limiting issues.

Usage:
    Set environment variable: API_THROTTLE=10  (10 second fixed delay)
    Or: API_THROTTLE=10,30     (random 10-30 second delay)
    Or use command: /throttle set 10
    Or: /throttle set 10 30    (random between 10-30s)
    Disable with: /throttle off

Commands:
    /throttle              - Show help and current status
    /throttle N            - Set fixed N second delay
    /throttle set N        - Set fixed N second delay
    /throttle set N M      - Set random delay between N-M seconds
    /throttle off          - Disable throttling
"""

import os
import time
import random
from aicoder.core.config import Config
from aicoder.utils.log import LogUtils

# Runtime delay configuration
_throttle_min = 0.0
_throttle_max = 0.0  # If equal to min, it's fixed mode


def create_plugin(ctx):
    """Register throttle hooks and commands"""
    global _throttle_min, _throttle_max

    # Initialize from environment variable
    env_delay = os.environ.get("API_THROTTLE", "0")
    try:
        if "," in env_delay:
            parts = env_delay.split(",")
            _throttle_min = float(parts[0].strip())
            _throttle_max = float(parts[1].strip())
        else:
            _throttle_min = float(env_delay)
            _throttle_max = _throttle_min
    except ValueError:
        _throttle_min = 0.0
        _throttle_max = 0.0

    def before_api_request(endpoint: str, request_data: dict) -> None:
        """Hook: sleep before API request"""
        if _throttle_min <= 0:
            return

        # Calculate delay (fixed or random)
        if _throttle_min == _throttle_max:
            delay = _throttle_min
        else:
            delay = random.uniform(_throttle_min, _throttle_max)

        LogUtils.printc(f"[throttle] Sleeping {delay:.1f}s...", color="cyan")
        time.sleep(delay)

    def get_status() -> str:
        """Get current status string"""
        if _throttle_min <= 0:
            return "Status: Disabled"
        elif _throttle_min == _throttle_max:
            return f"Status: Fixed delay {_throttle_min}s"
        else:
            return f"Status: Random delay {_throttle_min}s - {_throttle_max}s"

    def show_help() -> None:
        """Show help with status"""
        LogUtils.printc("[throttle] API Throttle Plugin", color="cyan", bold=True)
        LogUtils.printc(f"  {get_status()}", color="cyan")
        LogUtils.print("")
        LogUtils.print("Commands:")
        LogUtils.print("  /throttle N          - Set fixed N second delay")
        LogUtils.print("  /throttle N M        - Set random delay between N-M seconds")
        LogUtils.print("  /throttle set N [M]  - Same as above (explicit)")
        LogUtils.print("  /throttle off        - Disable throttling")
        LogUtils.print("")
        LogUtils.print("Env: API_THROTTLE=10 or API_THROTTLE=10,30")

    def handle_throttle_command(args: str) -> None:
        """Handle /throttle command"""
        global _throttle_min, _throttle_max

        parts = args.strip().split() if args else []

        # No args or "help" -> show help
        if not parts or parts[0] == "help":
            show_help()
            return

        if parts[0] == "status":
            LogUtils.printc(f"[throttle] {get_status()}", color="cyan")
            return

        if parts[0] == "off":
            _throttle_min = 0.0
            _throttle_max = 0.0
            LogUtils.printc("[throttle] Disabled", color="cyan")
            return

        if parts[0] == "set":
            if len(parts) < 2:
                show_help()
                return
            try:
                _throttle_min = float(parts[1])
                if len(parts) >= 3:
                    _throttle_max = float(parts[2])
                    if _throttle_max < _throttle_min:
                        _throttle_min, _throttle_max = _throttle_max, _throttle_min
                    LogUtils.printc(f"[throttle] Random delay: {_throttle_min}s - {_throttle_max}s", color="cyan")
                else:
                    _throttle_max = _throttle_min
                    LogUtils.printc(f"[throttle] Fixed delay: {_throttle_min}s", color="cyan")
            except ValueError:
                LogUtils.printc("[throttle] Invalid number", color="cyan")
            return

        # Try to parse as number (shorthand)
        try:
            _throttle_min = float(parts[0])
            if len(parts) >= 2:
                _throttle_max = float(parts[1])
                if _throttle_max < _throttle_min:
                    _throttle_min, _throttle_max = _throttle_max, _throttle_min
                LogUtils.printc(f"[throttle] Random delay: {_throttle_min}s - {_throttle_max}s", color="cyan")
            else:
                _throttle_max = _throttle_min
                LogUtils.printc(f"[throttle] Fixed delay: {_throttle_min}s", color="cyan")
        except ValueError:
            show_help()

    # Register hook
    ctx.register_hook("before_api_request", before_api_request)

    # Register command
    ctx.register_command("throttle", handle_throttle_command, "Set API throttle delay in seconds")

    if Config.debug():
        LogUtils.printc(f"[+] Loaded api_throttle plugin ({get_status().lower()})", color="cyan")
