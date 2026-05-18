"""
Request Transform Plugin

Transforms request JSON for specific providers (e.g., Alibaba/Qwen cache control).
Activated by AICODER_TRANSFORM_REQUEST env var (e.g., "alibaba").

Usage:
    export AICODER_TRANSFORM_REQUEST=alibaba
"""

import os
from aicoder.core.config import Config


def create_plugin(ctx):
    """Request transform plugin"""

    transform_type = os.environ.get("AICODER_TRANSFORM_REQUEST", "")
    if Config.debug():
        print(f"{Config.colors['dim']}[+] transform_request plugin loaded (mode: {transform_type}){Config.colors['reset']}")

    def transform_request(data, endpoint=None):
        """Transform request data based on AICODER_TRANSFORM_REQUEST"""
        if transform_type == "alibaba":
            return transform_alibaba(data)
        return data

    ctx.register_hook("transform_request", transform_request)


def transform_alibaba(data):
    """Transform for Alibaba/Qwen cache format"""
    messages = data.get("messages", [])
    if not messages:
        return data

    # Transform system messages (first 2) to array format with cache_control
    system_count = 0
    for msg in messages:
        if msg.get("role") == "system" and system_count < 2:
            content = msg.get("content", "")
            if isinstance(content, str):
                msg["content"] = [{
                    "type": "text",
                    "text": content,
                    "cache_control": {"type": "ephemeral", "ttl": "5m"}
                }]
            elif isinstance(content, list):
                if content:
                    content[-1]["cache_control"] = {"type": "ephemeral", "ttl": "5m"}
            system_count += 1

    # Add cache_control to last 2 non-system messages
    non_system = [m for m in messages if m.get("role") != "system"]
    for msg in non_system[-2:]:
        content = msg.get("content", "")
        if isinstance(content, str):
            msg["content"] = [{
                "type": "text",
                "text": content,
                "cache_control": {"type": "ephemeral", "ttl": "5m"}
            }]
        elif isinstance(content, list) and content:
            last = content[-1]
            if isinstance(last, dict) and last.get("type") not in ("tool-approval-request", "tool-approval-response"):
                last["cache_control"] = {"type": "ephemeral", "ttl": "5m"}

    return data