"""
GLM Quota Plugin - Query Z.ai GLM Coding Plan quota and usage statistics

Commands:
- /glm-quota [week|month]: Query quota and usage for specified time period (default: 24h)
"""

from typing import Dict, Any
from datetime import datetime, timedelta
import time

from aicoder.core.config import Config
from aicoder.utils.http_utils import fetch


def create_plugin(ctx):
    """GLM quota plugin"""

    def format_reset_time(timestamp_ms: int) -> str:
        """Format reset time from unix timestamp in milliseconds"""
        reset_time = datetime.fromtimestamp(timestamp_ms / 1000)
        now = datetime.now()

        # Calculate time until reset
        time_diff = reset_time - now

        if time_diff.total_seconds() <= 0:
            return f"{Config.colors['green']}Reset{Config.colors['reset']}"

        # Format time remaining
        hours = int(time_diff.total_seconds() // 3600)
        minutes = int((time_diff.total_seconds() % 3600) // 60)

        if hours > 24:
            days = hours // 24
            hours = hours % 24
            return f"{days}d {hours}h {minutes}m"
        elif hours > 0:
            return f"{hours}h {minutes}m"
        else:
            return f"{minutes}m"

    def get_time_window(period: str = "24h") -> Dict[str, str]:
        """Get time window for specified period (24h, week, month)"""
        now = datetime.now()

        if period == "week":
            start_time = now - timedelta(days=7)
            end_time = now
        elif period == "month":
            start_time = now - timedelta(days=30)
            end_time = now
        else:
            # Default: 24-hour rolling window
            start_time = datetime(
                now.year, now.month, now.day - 1,
                now.hour, 0, 0, 0
            )
            end_time = datetime(
                now.year, now.month, now.day,
                now.hour, 59, 59, 0
            )

        return {
            "start_time": start_time.strftime("%Y-%m-%d %H:%M:%S"),
            "end_time": end_time.strftime("%Y-%m-%d %H:%M:%S"),
            "period": period
        }

    def is_zai_url(url: str) -> bool:
        """Check if URL is a Z.ai API endpoint"""
        return "z.ai" in url.lower()

    def get_zai_base_url(base_url: str) -> str:
        """Extract Z.ai base URL for quota endpoints"""
        if not base_url:
            return ""

        # Handle various Z.ai URL formats
        url_lower = base_url.lower()
        if "api.z.ai" in url_lower:
            # Extract base: https://api.z.ai/api/paas/v4 -> https://api.z.ai
            import urllib.parse
            parsed = urllib.parse.urlparse(base_url)
            return f"{parsed.scheme}://{parsed.netloc}"
        return ""

    def fetch_quota_data(base_url: str, api_key: str, period: str = "24h") -> Dict[str, Any]:
        """Fetch quota data from Z.ai endpoints"""
        import urllib.parse

        if not base_url or not api_key:
            return {"error": "Missing base URL or API key"}

        # Get time window query parameters
        time_window = get_time_window(period)
        query_params = f"startTime={urllib.parse.quote(time_window['start_time'])}&endTime={urllib.parse.quote(time_window['end_time'])}"

        if Config.debug():
            print(f"{Config.colors['dim']}[DEBUG] Time window: {time_window['start_time']} to {time_window['end_time']}{Config.colors['reset']}")
            print(f"{Config.colors['dim']}[DEBUG] Query params: {query_params}{Config.colors['reset']}")

        # Build endpoints - modelUsage and toolUsage need query params
        endpoints = {
            "model_usage": f"{base_url}/api/monitor/usage/model-usage?{query_params}",
            "tool_usage": f"{base_url}/api/monitor/usage/tool-usage?{query_params}",
            "quota_limit": f"{base_url}/api/monitor/usage/quota/limit",
        }

        if Config.debug():
            print(f"{Config.colors['dim']}[DEBUG] Endpoints:{Config.colors['reset']}")
            for name, url in endpoints.items():
                print(f"{Config.colors['dim']}  {name}: {url}{Config.colors['reset']}")

        results = {}
        headers = {
            "Authorization": api_key,  # Direct API key, no "Bearer" prefix
            "Content-Type": "application/json",
        }

        for name, url in endpoints.items():
            try:
                response = fetch(url, {
                    "method": "GET",
                    "headers": headers,
                    "timeout": 10,
                })

                if response.ok():
                    results[name] = response.json()
                else:
                    results[name] = {
                        "error": f"HTTP {response.status}: {response.reason}",
                        "status": response.status,
                    }
            except Exception as e:
                results[name] = {"error": str(e)}

        return results

    def format_quota_output(data: Dict[str, Any], period: str = "24h") -> str:
        """Format quota data for display"""
        if "error" in data:
            return f"{Config.colors['red']}Error: {data['error']}{Config.colors['reset']}"

        output = []
        output.append(f"{Config.colors['bold']}Z.ai GLM Coding Plan - Quota Status{Config.colors['reset']}")
        output.append("")

        # Model Usage
        model_usage = data.get("model_usage", {})
        if "error" in model_usage:
            output.append(f"{Config.colors['yellow']}Model Usage:{Config.colors['reset']} {Config.colors['red']}{model_usage.get('error', 'Unknown error')}{Config.colors['reset']}")
        elif isinstance(model_usage, dict) and model_usage.get("success"):
            total_usage = model_usage.get("data", {}).get("totalUsage", {})
            period_label = "24h" if period == "24h" else period
            output.append(f"{Config.colors['yellow']}Model Usage ({period_label}):{Config.colors['reset']}")
            output.append(f"  Calls: {Config.colors['green']}{total_usage.get('totalModelCallCount', 0)}{Config.colors['reset']}")
            output.append(f"  Tokens: {Config.colors['green']}{total_usage.get('totalTokensUsage', 0):,}{Config.colors['reset']}")
        else:
            period_label = "24h" if period == "24h" else period
            output.append(f"{Config.colors['yellow']}Model Usage:{Config.colors['reset']} {Config.colors['dim']}No usage in {period_label} window{Config.colors['reset']}")

        # Tool Usage
        tool_usage = data.get("tool_usage", {})
        if "error" in tool_usage:
            output.append(f"{Config.colors['yellow']}Tool Usage:{Config.colors['reset']} {Config.colors['red']}{tool_usage.get('error', 'Unknown error')}{Config.colors['reset']}")
        elif isinstance(tool_usage, dict) and tool_usage.get("success"):
            total_usage = tool_usage.get("data", {}).get("totalUsage", {})
            period_label = "24h" if period == "24h" else period
            output.append(f"{Config.colors['yellow']}Tool Usage ({period_label}):{Config.colors['reset']}")
            output.append(f"  Network Search: {Config.colors['green']}{total_usage.get('totalNetworkSearchCount', 0)}{Config.colors['reset']}")
            output.append(f"  Web Read MCP: {Config.colors['green']}{total_usage.get('totalWebReadMcpCount', 0)}{Config.colors['reset']}")
            output.append(f"  Zread MCP: {Config.colors['green']}{total_usage.get('totalZreadMcpCount', 0)}{Config.colors['reset']}")
        else:
            period_label = "24h" if period == "24h" else period
            output.append(f"{Config.colors['yellow']}Tool Usage:{Config.colors['reset']} {Config.colors['dim']}No usage in {period_label} window{Config.colors['reset']}")

        # Quota Limit
        quota_limit = data.get("quota_limit", {})
        if "error" in quota_limit:
            output.append(f"{Config.colors['yellow']}Quota Limit:{Config.colors['reset']} {Config.colors['red']}{quota_limit.get('error', 'Unknown error')}{Config.colors['reset']}")
        elif isinstance(quota_limit, dict) and quota_limit.get("success"):
            # Extract key quota information
            level = quota_limit.get("data", {}).get("level", "unknown")
            limits = quota_limit.get("data", {}).get("limits", [])

            if level:
                output.append(f"{Config.colors['yellow']}Plan Level:{Config.colors['reset']} {Config.colors['green']}{level.upper()}{Config.colors['reset']}")

            if isinstance(limits, list):
                for limit in limits:
                    if isinstance(limit, dict):
                        limit_type = limit.get("type", "")
                        percentage = limit.get("percentage", 0)
                        next_reset = limit.get("nextResetTime")

                        if limit_type == "TIME_LIMIT":
                            # 5-hour time limit (MCP usage)
                            current = limit.get('currentValue', 0)
                            total = limit.get('usage', 0)  # 'usage' is the total limit
                            output.append(f"{Config.colors['yellow']}5-Hour Usage (MCP):{Config.colors['reset']}")
                            output.append(f"  Used: {Config.colors['green']}{current}{Config.colors['reset']} / {Config.colors['green']}{total}{Config.colors['reset']} ({Config.colors['green']}{percentage}%{Config.colors['reset']})")
                            if next_reset:
                                output.append(f"  Reset: {Config.colors['dim']}{format_reset_time(next_reset)}{Config.colors['reset']}")
                        elif limit_type == "TOKENS_LIMIT":
                            # Token limit (no current/total fields available)
                            output.append(f"{Config.colors['yellow']}Token Limit (5h):{Config.colors['reset']}")
                            output.append(f"  Used: {Config.colors['green']}{percentage}%{Config.colors['reset']}")
                            if next_reset:
                                output.append(f"  Reset: {Config.colors['dim']}{format_reset_time(next_reset)}{Config.colors['reset']}")
        else:
            output.append(f"{Config.colors['yellow']}Quota Limit:{Config.colors['reset']} {Config.colors['dim']}No data{Config.colors['reset']}")

        return "\n".join(output)

    def cmd_glm_quota(args: str) -> None:
        """Handle /glm-quota command
        Arguments: week, month (default: 24h)
        """
        # Get API configuration
        base_url = Config.base_url()
        api_key = Config.api_key()

        if not base_url:
            print(f"{Config.colors['red']}Error: API_BASE_URL not configured{Config.colors['reset']}")
            return

        if not api_key:
            print(f"{Config.colors['red']}Error: API_KEY not configured{Config.colors['reset']}")
            return

        # Parse period argument
        period = "24h"
        args_lower = args.lower().strip()
        if args_lower in ("week", "month"):
            period = args_lower
        elif args_lower and args_lower not in ("24h", "default"):
            print(f"{Config.colors['yellow']}Warning: Unknown period '{args}', using default (24h){Config.colors['reset']}\n")

        # Check if it's a Z.ai URL
        if not is_zai_url(base_url):
            print(f"{Config.colors['yellow']}Warning: Current API_BASE_URL is not a Z.ai endpoint{Config.colors['reset']}")
            print(f"  Base URL: {base_url}")
            print(f"{Config.colors['cyan']}Attempting to query quota anyway...{Config.colors['reset']}\n")

        # Extract Z.ai base URL
        zai_base_url = get_zai_base_url(base_url)
        if not zai_base_url:
            print(f"{Config.colors['red']}Error: Could not extract Z.ai base URL from {base_url}{Config.colors['reset']}")
            return

        if Config.debug():
            print(f"{Config.colors['dim']}[DEBUG] Base URL: {base_url}{Config.colors['reset']}")
            print(f"{Config.colors['dim']}[DEBUG] Z.ai base URL: {zai_base_url}{Config.colors['reset']}")

        # Fetch quota data
        period_label = period.upper() if period != "24h" else "24h"
        print(f"{Config.colors['cyan']}Querying Z.ai quota ({period_label})...{Config.colors['reset']}")
        data = fetch_quota_data(zai_base_url, api_key, period)

        # Debug: show raw data
        if Config.debug():
            print(f"{Config.colors['dim']}[DEBUG] Raw response:{Config.colors['reset']}")
            import json
            print(json.dumps(data, indent=2, default=str))

        # Display results
        output = format_quota_output(data, period)
        print(output)

    # Register command
    ctx.register_command("glm-quota", cmd_glm_quota, "Query Z.ai GLM Coding Plan quota and usage statistics [week|month]")

    if Config.debug():
        print(f"[+] GLM Quota plugin loaded")
        print(f"    - /glm-quota command")
