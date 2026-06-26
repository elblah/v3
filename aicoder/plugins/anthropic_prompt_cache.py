"""
Anthropic Prompt Caching Plugin

Adds cacheControl: {type: "ephemeral"} to messages for Anthropic-compatible
endpoints that support prompt caching (e.g., opencode-go, AWS Bedrock).

Mirrors opencode's applyCaching() logic:
- System messages (first 2) + final messages (last 2) get cached
- Uses providerOptions.cacheControl for anthropic provider

Activated by AICODER_ANTHROPIC_CACHE=1 env var.
"""

import copy
import os

from aicoder.core.config import Config


def create_plugin(ctx):
    """Request transform plugin for Anthropic prompt caching"""

    enabled = os.environ.get("AICODER_ANTHROPIC_CACHE", "").lower() in ("1", "true", "yes")

    if enabled and Config.debug():
        print(f"{Config.colors['dim']}[+] anthropic_prompt_cache plugin enabled{Config.colors['reset']}")

    def transform_request(data, endpoint=None):
        """Add cacheControl to system and final messages"""
        if not enabled:
            return data

        return apply_anthropic_caching(data)

    ctx.register_hook("transform_request", transform_request)


def apply_anthropic_caching(data):
    """Apply Anthropic prompt caching - returns a copy, doesn't mutate original"""
    messages = data.get("messages", [])
    
    # Handle system prompt (convert string to array + cacheControl)
    system = data.get("system")
    if system:
        if isinstance(system, str):
            data["system"] = [{
                "type": "text",
                "text": system,
                "cacheControl": {"type": "ephemeral"}
            }]
        elif isinstance(system, list) and system:
            last = system[-1]
            if isinstance(last, dict) and last.get("type") not in ("tool-approval-request", "tool-approval-response"):
                last["cacheControl"] = {"type": "ephemeral"}
    
    if not messages:
        return data

    # Work on a deep copy to avoid mutating original message history
    data = copy.deepcopy(data)
    messages = data.get("messages", [])

    # Get first 2 system messages and last 2 non-system messages
    system_msgs = [m for m in messages if m.get("role") == "system"][:2]
    non_system_msgs = [m for m in messages if m.get("role") != "system"]
    final_msgs = non_system_msgs[-2:] if non_system_msgs else []

    target_msgs = system_msgs + final_msgs

    for msg in target_msgs:
        content = msg.get("content", "")

        if isinstance(content, str):
            # Convert string content to array format with cacheControl
            msg["content"] = [{
                "type": "text",
                "text": content,
                "cacheControl": {"type": "ephemeral"}
            }]
        elif isinstance(content, list) and content:
            # Add cacheControl to last content block
            last = content[-1]
            if isinstance(last, dict) and last.get("type") not in ("tool-approval-request", "tool-approval-response"):
                last["cacheControl"] = {"type": "ephemeral"}

    return data