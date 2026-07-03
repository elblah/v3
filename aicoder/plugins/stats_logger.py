"""
Stats Logger Plugin

Logs each AI API request to:
- .aicoder/stats.log (local, per-project)
- stats_server via Unix socket (for central aggregation)

Format: JSONL (one JSON object per line)
"""

import json
import os
import sys
from datetime import datetime
from aicoder.core.config import Config

SOCKET_PATH = os.path.join(os.environ.get("TMP", "/tmp"), "stats_server.sock")


def _extract_cost(usage):
    """Extract USD cost from usage dict, handling various formats. Returns float or None."""
    if not usage or not isinstance(usage, dict):
        return None

    # Format 1: usage["cost"]["usd"]
    cost_obj = usage.get("cost")
    if isinstance(cost_obj, dict):
        usd = cost_obj.get("usd")
        if usd is not None and isinstance(usd, (int, float)) and usd > 0:
            return float(usd)

    # Format 2: usage["cost_details"]["upstream_inference_cost"]
    cost_details = usage.get("cost_details")
    if isinstance(cost_details, dict):
        for key in ("upstream_inference_cost", "upstream_inference_prompt_cost"):
            val = cost_details.get(key)
            if val is not None and isinstance(val, (int, float)) and val > 0:
                return float(val)

    # Format 3: usage["cost"] is a direct number
    if isinstance(cost_obj, (int, float)) and cost_obj > 0:
        return float(cost_obj)

    # Format 4: flat keys like "upstream_inference_cost" or "usd_cost"
    for key in ("upstream_inference_cost", "usd_cost", "total_cost"):
        val = usage.get(key)
        if val is not None and isinstance(val, (int, float)) and val > 0:
            return float(val)

    return None


def _extract_cached_tokens(usage):
    """Extract cached tokens from usage dict, handling various provider formats.

    Semantics differ by provider:
    - OpenAI-style: prompt_tokens = total, cached_tokens is a subset
    - Anthropic-style: input_tokens = miss only, cache_read_input_tokens is separate
    - Returns int if cache field present (0 = no cache, >0 = cached tokens)
    - Returns None if no cache field found (provider didn't report it)
    """
    if not usage or not isinstance(usage, dict):
        return None

    # 1. OpenAI: prompt_tokens_details.cached_tokens (subset of prompt_tokens)
    ptd = usage.get("prompt_tokens_details")
    if isinstance(ptd, dict):
        val = ptd.get("cached_tokens")
        if val is not None and isinstance(val, (int, float)):
            return int(val)

    # 2. Direct cached_tokens key (some providers)
    val = usage.get("cached_tokens")
    if val is not None and isinstance(val, (int, float)):
        return int(val)

    # 3. Anthropic-style: cache_read_input_tokens (separate from input_tokens)
    val = usage.get("cache_read_input_tokens")
    if val is not None and isinstance(val, (int, float)):
        return int(val)

    # 4. Fallback: prompt_cache_hit_tokens (other providers)
    val = usage.get("prompt_cache_hit_tokens")
    if val is not None and isinstance(val, (int, float)):
        return int(val)

    # No cache info in response at all
    return None


def _write_to_central(line):
    """Write to stats_server via Unix socket. Returns True on success."""
    import socket
    try:
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.settimeout(2.0)
        sock.connect(SOCKET_PATH)
        sock.sendall(line.encode())
        # Read response
        response = sock.recv(64).decode().strip()
        sock.close()
        if response == "ok":
            return True
        else:
            err_msg = f"central server responded: {response}"
            print(f"\n[stats_logger] {err_msg}\n  line: {line.strip()}", file=sys.stderr)
            if os.environ.get("STATS_ERROR_DUNSTIFY") == "1":
                os.system(f"timeout -k 2 5s dunstify -t 3000 'stats_logger error' '{err_msg}' &")
            return False
    except FileNotFoundError:
        # Socket doesn't exist - server not running
        return False
    except (socket.timeout, ConnectionRefusedError, OSError) as e:
        err_msg = f"central write failed: {e}"
        print(f"\n[stats_logger] {err_msg}\n  line: {line.strip()}", file=sys.stderr)
        if os.environ.get("STATS_ERROR_DUNSTIFY") == "1":
            os.system(f"timeout -k 2 5s dunstify -t 3000 'stats_logger error' '{err_msg}' &")
        return False


def create_plugin(ctx):
    """Plugin entry point"""
    session_id = None
    total_cost = 0.0
    _last_cached_tokens = None

    def _on_usage_data(usage):
        """Hook when usage data is received from API"""
        nonlocal session_id, total_cost, _last_cached_tokens
        if session_id is None:
            import uuid
            session_id = str(uuid.uuid4())

        stats = ctx.app.stats
        if not stats:
            return

        # Get metadata
        cwd = os.getcwd()
        api_provider = os.environ.get("API_PROVIDER", "").lower() or "openai"
        model = Config.model()
        base_url = Config.base_url() or Config.api_endpoint()
        elapsed = stats.last_api_time
        timestamp = datetime.utcnow().strftime("%Y-%m-%d_%H:%M:%S")

        # Accumulate cost
        cost = _extract_cost(usage)
        if cost is not None:
            total_cost += cost

        # Build JSONL entry
        entry = {
            "ts": timestamp,
            "session": session_id,
            "cwd": cwd,
            "api_provider": api_provider,
            "url": base_url,
            "model": model,
            "elapsed": round(elapsed, 2),
            "usage": usage,
            "origin": "v3",
        }

        # Add optional tag
        tag = os.environ.get("STATS_TAG", "")
        if tag:
            entry["tag"] = tag

        json_line = json.dumps(entry, separators=(",", ":"))

        # Ensure .aicoder dir exists
        aicoder_dir = os.path.join(cwd, ".aicoder")
        os.makedirs(aicoder_dir, exist_ok=True)

        # Append to local stats.log
        log_path = os.path.join(aicoder_dir, "stats.log")
        with open(log_path, "a") as f:
            f.write(json_line + "\n")

        # Send to central server
        _write_to_central(json_line + "\n")

        # Cache miss detection (disabled via STATS_LOGGER_CACHE_ALERTS=0)
        if os.environ.get("STATS_LOGGER_CACHE_ALERTS", "1") != "0":
            current_cached = _extract_cached_tokens(usage)
            bold_yellow = f"{Config.colors['bold']}{Config.colors['yellow']}"
            reset = Config.colors['reset']
            if _last_cached_tokens is not None and _last_cached_tokens > 0:
                if current_cached is not None:
                    if current_cached == 0:
                        print(f"\n{bold_yellow}[!] FULL CACHE MISS (was {_last_cached_tokens} tokens){reset}")
                    elif current_cached < _last_cached_tokens:
                        pct = (1 - current_cached / _last_cached_tokens) * 100
                        print(f"\n{bold_yellow}[!] CACHE DROP: {_last_cached_tokens} → {current_cached} tokens (-{pct:.0f}%){reset}")
                # else: provider didn't report cache — skip alert, keep baseline
            # Track baseline only on reported data (even 0 is a real answer)
            if current_cached is not None:
                _last_cached_tokens = current_cached

    def _on_context_bar():
        """Hook: Add cost to context bar"""
        nonlocal total_cost
        if total_cost <= 0:
            return None
        if os.environ.get("STATS_LOGGER_COST_CONTEXT_BAR", "1") == "0":
            return None

        # Show in cents if < $1, dollars if >= $1
        if total_cost < 1.0:
            cost_str = f"{total_cost * 100:.1f}¢"
        else:
            cost_str = f"${total_cost:.4f}"
        return f"{Config.colors['dim']}{cost_str}{Config.colors['reset']}"

    # Register hook for usage data (fires for ALL API calls including compaction)
    ctx.register_hook("after_usage_data", _on_usage_data)
    ctx.register_hook("on_context_bar", _on_context_bar)

    return {}
