"""
Stats Logger Plugin

Logs each AI API request to:
- .aicoder/stats.log (local, per-project)
- stats_server via Unix socket (for central aggregation)

Format: JSONL (one JSON object per line)

Before writing, fires on_stats_entry(entry) so plugins can complement the
entry (e.g. ai_cost sets entry["cost_estimate"] next to provider-reported
entry["cost"]).

WARNING (Aug 15): firing after_usage_data with this plugin registered writes
to PRODUCTION data — stats_server daemon appends to
~/.aicoder/central_stats.log (real usage reports, read by ai_usage.py).
NEVER run this handler with test/synthetic usage: it pollutes real reports.
Tests MUST set STATS_CENTRAL=0 (and STATS_FALLBACK_FILE=0) before firing,
or stub sl._write_to_central.
"""

import json
import os
import sys
from datetime import datetime
from aicoder.core.config import Config
from aicoder.utils.bool_utils import env_bool

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


def _write_to_central(line):
    """Write to stats_server via Unix socket. Returns True on success.

    PRODUCTION WRITE PATH: the daemon appends to ~/.aicoder/central_stats.log.
    Never call with test/fake data; disable via STATS_CENTRAL=0.
    """
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
            if env_bool("STATS_ERROR_DUNSTIFY"):
                os.system(f"timeout -k 2 5s dunstify -t 3000 'stats_logger error' '{err_msg}' &")
            return False
    except FileNotFoundError:
        # Socket doesn't exist - server not running
        return False
    except (socket.timeout, ConnectionRefusedError, OSError) as e:
        err_msg = f"central write failed: {e}"
        print(f"\n[stats_logger] {err_msg}\n  line: {line.strip()}", file=sys.stderr)
        if env_bool("STATS_ERROR_DUNSTIFY"):
            os.system(f"timeout -k 2 5s dunstify -t 3000 'stats_logger error' '{err_msg}' &")
        return False


def _write_central_fallback(line):
    """Append to ~/.aicoder/central_stats.log if writable. Silently skip if not.
    Disable with STATS_FALLBACK_FILE=0."""
    if os.environ.get("STATS_FALLBACK_FILE", "1") == "0":
        return
    try:
        path = os.path.join(os.path.expanduser("~"), ".aicoder", "central_stats.log")
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "a") as f:
            f.write(line)
    except (PermissionError, OSError):
        pass


def create_plugin(ctx):
    """Plugin entry point"""
    session_id = None

    def _on_usage_data(usage):
        """Hook when usage data is received from API"""
        nonlocal session_id
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

        # Provider-reported cost (field only added when provider reports one)
        cost = _extract_cost(usage)
        if cost is not None:
            entry["cost"] = cost

        # Let plugins complement the entry (e.g. ai_cost adds cost_estimate)
        if ctx.app and ctx.app.plugin_system:
            ctx.app.plugin_system.call_hooks("on_stats_entry", entry)

        json_line = json.dumps(entry, separators=(",", ":"))

        # Ensure .aicoder dir exists
        aicoder_dir = os.path.join(cwd, ".aicoder")
        os.makedirs(aicoder_dir, exist_ok=True)

        # Append to local stats.log
        log_path = os.path.join(aicoder_dir, "stats.log")
        with open(log_path, "a") as f:
            f.write(json_line + "\n")

        # Send to central server (or fallback if unavailable).
        # PRODUCTION WRITE: lands in ~/.aicoder/central_stats.log via the
        # stats_server daemon. Tests with synthetic usage MUST set
        # STATS_CENTRAL=0 + STATS_FALLBACK_FILE=0 — this corrupts real reports.
        if os.environ.get("STATS_CENTRAL", "1") != "0":
            if not _write_to_central(json_line + "\n"):
                _write_central_fallback(json_line + "\n")

    # Register hook for usage data (fires for ALL API calls including compaction)
    ctx.register_hook("after_usage_data", _on_usage_data)

    return {}
