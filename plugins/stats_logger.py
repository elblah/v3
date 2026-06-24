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

    # Register hook for usage data (fires for ALL API calls including compaction)
    ctx.register_hook("after_usage_data", _on_usage_data)

    return {}
