"""
Request Transform Plugin

Transforms request JSON for specific providers (e.g., Alibaba/Qwen cache control).
Activated by AICODER_TRANSFORM_REQUEST env var (e.g., "alibaba").

Matches sample-qwen.json structure:
- "system" as separate key with array format and cache_control
- "messages" without system role  
- Content as {"type": "text"} blocks
- reasoning_content -> {"type": "thinking", ...} block
- cache_control on last 2 messages
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
    """Transform for Alibaba/Qwen cache format - matches sample-qwen.json structure"""
    messages = data.get("messages", [])
    if not messages:
        return data

    # Move system message to separate "system" key (like sample-qwen.json)
    system_msgs = [m for m in messages if m.get("role") == "system"]
    if system_msgs:
        system_content = system_msgs[0].get("content", "")
        data["messages"] = [m for m in messages if m.get("role") != "system"]
        data["system"] = [{
            "type": "text",
            "text": system_content,
            "cache_control": {"type": "ephemeral"}
        }]

    # Transform each message
    for msg in data.get("messages", []):
        content = msg.get("content", "")
        reasoning = msg.get("reasoning_content") or msg.get("reasoning") or msg.get("reasoning_text")

        # Handle reasoning -> thinking block
        if reasoning:
            text_content = content if isinstance(content, str) else ""
            msg["content"] = [
                {"type": "thinking", "thinking": reasoning, "signature": ""},
                {"type": "text", "text": text_content}
            ]
            # Remove reasoning fields
            for field in ["reasoning_content", "reasoning", "reasoning_text"]:
                msg.pop(field, None)
        elif isinstance(content, str):
            msg["content"] = [{"type": "text", "text": content}]

    # Add cache_control to last 3 messages
    last_msgs = data.get("messages", [])
    for msg in last_msgs[-3:]:
        content = msg.get("content", "")
        if isinstance(content, list) and content:
            last = content[-1]
            if isinstance(last, dict) and last.get("type") not in ("tool-approval-request", "tool-approval-response"):
                last["cache_control"] = {"type": "ephemeral"}

    return data