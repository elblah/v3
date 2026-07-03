"""
Cache Monitor - Message integrity watchdog + cache drop analysis.

Tracks every message positionally by hash. If any previously tracked
message changes or is removed, alerts loudly — because messages should
never change unless compaction or system prompt reload happens.

Also handles cache drop alerts (moved from stats_logger) and correlates
them with message changes: if no message changed but cache dropped,
it's likely a provider-side eviction.

NOT auto-loaded. Set AICODER_CACHE_MONITOR=1 to enable.

Env:
    AICODER_CACHE_MONITOR=1      (required to load)
    CACHE_MONITOR_ENABLE=1       (default: 1)
    CACHE_MONITOR_CACHE_ALERTS=1 (default: 1)

Hooks:
    on_session_change      -> clear state
    before_ai_processing   -> hash messages, detect changes
    after_usage_data       -> cache drop analysis

Commands:
    /cache-monitor         - Show status
    /cache-monitor on|off  - Enable/disable
    /cm                    - Alias
"""

import hashlib
import json
import os

from aicoder.core.config import Config
from aicoder.utils.log import LogUtils

# --- State ---

_enabled = True
_cache_alerts = True
_message_hashes = []  # list of md5 hashes, one per message position
_last_cached_tokens = None
_msg_changed_this_turn = False  # flag set by before_ai, read by after_usage
_msg_count_at_hash = 0  # message count at last hash snapshot, to detect compaction after the fact

_RED = "\033[91m"
_YELLOW = "\033[93m"
_RESET = "\033[0m"


def _hash_message(msg: dict) -> str:
    """Deterministic hash of a single message dict"""
    serialized = json.dumps(msg, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.md5(serialized.encode()).hexdigest()


def _extract_cached_tokens(usage):
    """Extract cached tokens from usage dict, handling various provider formats.

    Returns int if cache field present, None if absent.
    """
    if not usage or not isinstance(usage, dict):
        return None

    # 1. OpenAI: prompt_tokens_details.cached_tokens
    ptd = usage.get("prompt_tokens_details")
    if isinstance(ptd, dict):
        val = ptd.get("cached_tokens")
        if val is not None and isinstance(val, (int, float)):
            return int(val)

    # 2. Direct cached_tokens key
    val = usage.get("cached_tokens")
    if val is not None and isinstance(val, (int, float)):
        return int(val)

    # 3. Anthropic-style: cache_read_input_tokens
    val = usage.get("cache_read_input_tokens")
    if val is not None and isinstance(val, (int, float)):
        return int(val)

    # 4. Fallback: prompt_cache_hit_tokens
    val = usage.get("prompt_cache_hit_tokens")
    if val is not None and isinstance(val, (int, float)):
        return int(val)

    return None


def _on_session_change() -> None:
    """Session reset ( /new /load ) — clear all state"""
    global _message_hashes, _last_cached_tokens, _msg_changed_this_turn, _msg_count_at_hash
    _message_hashes.clear()
    _last_cached_tokens = None
    _msg_changed_this_turn = False
    _msg_count_at_hash = 0


def _on_before_ai() -> None:
    """Snapshot message hashes, alert on any change to existing messages"""
    global _message_hashes, _msg_changed_this_turn, _msg_count_at_hash, _app
    if not _enabled:
        return

    if _app is None:
        return
    try:
        messages = _app.message_history.get_messages()
    except Exception:
        return

    current_hashes = [_hash_message(m) for m in messages]
    _msg_changed_this_turn = False

    if not _message_hashes:
        # First run — just store
        _message_hashes = current_hashes
        return

    # Detect compaction: message count shrunk significantly
    old_count = len(_message_hashes)
    new_count = len(current_hashes)
    compaction = old_count > 0 and new_count < old_count * 0.9

    if compaction:
        # Compaction rewrites everything — individual msg changes are noise
        _msg_changed_this_turn = True
        print(f"\n{_YELLOW}[!] COMPACTION: {old_count} → {new_count} messages, hashes reset{_RESET}")
        _message_hashes = current_hashes
        return

    # Check for changes
    changed_positions = []

    for i in range(old_count):
        if i >= new_count:
            changed_positions.append((i, "REMOVED"))
        elif current_hashes[i] != _message_hashes[i]:
            role = messages[i].get("role", "?") if i < len(messages) else "?"
            changed_positions.append((i, f"CHANGED (role={role})"))

    if changed_positions:
        _msg_changed_this_turn = True
        print(f"\n{_RED}[!] MESSAGE INTEGRITY:{_RESET}")
        for pos, reason in changed_positions:
            print(f"  {_YELLOW}msg[{pos}]: {reason}{_RESET}")

    # Update stored hashes
    _message_hashes = current_hashes
    _msg_count_at_hash = len(current_hashes)


def _on_usage_data(usage: dict) -> None:
    """Cache drop analysis — correlates with message changes"""
    global _last_cached_tokens, _msg_changed_this_turn, _msg_count_at_hash, _app
    if not _enabled or not _cache_alerts:
        return

    # Compaction may have happened between before_ai and usage_data,
    # check if message count changed since hash snapshot
    if _app is not None and _msg_count_at_hash > 0:
        try:
            current_count = len(_app.message_history.get_messages())
            if current_count != _msg_count_at_hash:
                _msg_changed_this_turn = True
        except Exception:
            pass

    current_cached = _extract_cached_tokens(usage)
    if current_cached is None:
        # Provider didn't report cache — skip
        _msg_changed_this_turn = False
        return

    if _last_cached_tokens is not None and _last_cached_tokens > 0:
        if current_cached == 0:
            context = ""
            if _msg_changed_this_turn:
                context = " [messages changed — expected]"
            else:
                context = " [messages unchanged — provider-side eviction]"
            print(
                f"\n{_YELLOW}[!] FULL CACHE MISS"
                f" (was {_last_cached_tokens} tokens){context}{_RESET}"
            )
        elif current_cached < _last_cached_tokens:
            pct = (1 - current_cached / _last_cached_tokens) * 100
            context = ""
            if _msg_changed_this_turn:
                context = " [messages changed]"
            else:
                context = " [messages unchanged]"
            print(
                f"\n{_YELLOW}[!] CACHE DROP: {_last_cached_tokens} → {current_cached}"
                f" tokens (-{pct:.0f}%){context}{_RESET}"
            )

    _last_cached_tokens = current_cached
    _msg_changed_this_turn = False  # reset after consumption


def _handle_command(args: str) -> None:
    global _enabled
    parts = args.strip().split() if args.strip() else []

    if not parts or parts[0] == "help":
        status = "enabled" if _enabled else "disabled"
        print(f"[cache-monitor] {status}, cache_alerts={_cache_alerts}")
        print("  /cm on|off   - Enable/disable")
        print("  /cm status   - Show state")
        return

    if parts[0] == "on":
        _enabled = True
        LogUtils.printc("[cache-monitor] Enabled", color="cyan")
        return

    if parts[0] == "off":
        _enabled = False
        LogUtils.printc("[cache-monitor] Disabled", color="cyan")
        return

    if parts[0] == "status":
        status = "enabled" if _enabled else "disabled"
        hash_count = len(_message_hashes)
        last_cache = _last_cached_tokens or "none"
        print(f"[cache-monitor] {status}, {hash_count} msg hashes tracked")
        print(f"[cache-monitor] last cached_tokens: {last_cache}")
        return

    print("Unknown. Try: /cm on|off|status")


# --- Entry Point ---

_app = None


def create_plugin(ctx):
    global _enabled, _cache_alerts, _app, _message_hashes, _last_cached_tokens

    # Only load when explicitly enabled
    if os.environ.get("AICODER_CACHE_MONITOR") != "1":
        return {}

    _app = ctx.app
    _message_hashes = []
    _last_cached_tokens = None

    # Env overrides
    env_enabled = os.environ.get("CACHE_MONITOR_ENABLE", "").lower()
    if env_enabled in ("0", "false", "off", "no"):
        _enabled = False

    env_cache = os.environ.get("CACHE_MONITOR_CACHE_ALERTS", "").lower()
    if env_cache in ("0", "false", "off", "no"):
        _cache_alerts = False

    ctx.register_hook("on_session_change", _on_session_change)
    ctx.register_hook("before_ai_processing", _on_before_ai)
    ctx.register_hook("after_usage_data", _on_usage_data)

    ctx.register_command("cache-monitor", _handle_command, "Cache monitor: detect message changes + correlate cache drops")
    ctx.register_command("cm", _handle_command, "Cache monitor (alias)")

    if Config.debug():
        LogUtils.printc("[+] Loaded cache_monitor plugin", color="cyan")

    return {}
