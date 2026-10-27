"""
Enhanced token estimation based on Python implementation
More accurate than simple 4 chars per token while remaining fast and dependency-free
Maximum performance with cache-once, lookup-forever strategy
"""

import json
from typing import List, Dict, Any, Optional


# Token estimation weights (matching TSV config)
TOKEN_LETTER_WEIGHT = 4.2
TOKEN_NUMBER_WEIGHT = 3.5
TOKEN_PUNCTUATION_WEIGHT = 1.0
TOKEN_WHITESPACE_WEIGHT = 0.15
TOKEN_OTHER_WEIGHT = 3.0

# Punctuation set for fast lookup
PUNCTUATION_SET = {
    '!', '"', '#', '$', '%', '&', "'", '(', ')', '*', '+', ',', '-', '.', '/', ':', ';', '<', '=', '>', '?', '@', '[', '\\', ']', '^', '_', '`', '{', '|', '}', '~'
}

# Performance caches - cache-once strategy
_message_cache: Dict[int, int] = {}  # id(msg) -> tokens
_tools_tokens = 0
_original_tool_tokens = 0  # Preserved across cache clears (tool definitions don't change during session)
_MAX_CACHE_SIZE = 1000  # Prevent unbounded growth


def _estimate_weighted_tokens(text: str) -> int:
    """TSV-style weighted character estimation - fast, no regex"""
    if not text:
        return 0
    
    # Count character types (fast character comparisons, no regex)
    letters = numbers = punctuation = whitespace = other = 0
    
    for char in text:
        if 'a' <= char <= 'z' or 'A' <= char <= 'Z':
            letters += 1
        elif '0' <= char <= '9':
            numbers += 1
        elif char in PUNCTUATION_SET:
            punctuation += 1
        elif char.isspace():
            whitespace += 1
        else:
            other += 1
    
    # Apply TSV weights
    token_estimate = (
        letters / TOKEN_LETTER_WEIGHT
        + numbers / TOKEN_NUMBER_WEIGHT
        + punctuation * TOKEN_PUNCTUATION_WEIGHT
        + whitespace * TOKEN_WHITESPACE_WEIGHT
        + other / TOKEN_OTHER_WEIGHT
    )
    
    return max(0, round(token_estimate))


# Fixed cost of one injected image, in tokens. Providers bill vision by pixel
# tiles (a 768px image is ~1.1k tokens), never by base64 length. Counting the
# data URI as text inflated one phone screenshot to ~24k tokens, which pushed
# every round past the compaction trigger and made the image vanish from
# history (the tool call then got the "cancelled by the user" placeholder).
IMAGE_PART_TOKENS = 1600

_IMAGE_PART_TYPES = {"image_url", "image", "input_audio"}


def _strip_image_payloads(msg: Any) -> tuple:
    """Return (message_with_image_payloads_removed, image_part_count)."""
    if not isinstance(msg, dict):
        return msg, 0
    content = msg.get("content")
    if not isinstance(content, list):
        return msg, 0
    stripped = []
    images = 0
    for item in content:
        if isinstance(item, dict) and item.get("type") in _IMAGE_PART_TYPES:
            images += 1
            kind = item.get("type")
            placeholder: Dict[str, Any] = {"type": kind}
            if kind == "image_url":
                placeholder["image_url"] = {"url": "<image>"}
            elif kind == "image":
                placeholder["source"] = {"type": "base64", "data": "<image>"}
            else:
                placeholder["input_audio"] = {"data": "<audio>"}
            stripped.append(placeholder)
        else:
            stripped.append(item)
    if not images:
        return msg, 0
    clone = dict(msg)
    clone["content"] = stripped
    return clone, images


def message_tokens(msg: Dict[str, Any]) -> int:
    """Estimate tokens for one message.

    Image parts cost a fixed amount instead of their base64 length, so a vision
    message never eats the context budget.
    """
    stripped, images = _strip_image_payloads(msg)
    tokens = _estimate_weighted_tokens(
        json.dumps(stripped, sort_keys=True, separators=(",", ":"))
    )
    return tokens + images * IMAGE_PART_TOKENS


def cache_message(msg: Dict[str, Any]) -> None:
    """Cache FULL JSON message tokens IMMEDIATELY on creation
    Cache-once strategy - compute once, lookup forever
    """
    msg_id = id(msg)

    # Always update the cache, even if message was already cached
    _message_cache[msg_id] = message_tokens(msg)


def estimate_messages(messages: List[Dict[str, Any]]) -> int:
    """Super fast token estimation - cache-once, lookup-forever"""
    global _tools_tokens, _MAX_CACHE_SIZE
    
    if not messages:
        return 0
    
    # Cache cleanup when it gets too large (prevents memory issues)
    if len(_message_cache) >= _MAX_CACHE_SIZE:
        _message_cache.clear()
    
    # Cache any uncached messages, then sum all tokens
    total = 0
    for msg in messages:
        msg_id = id(msg)
        if msg_id not in _message_cache:
            _message_cache[msg_id] = message_tokens(msg)
        total += _message_cache[msg_id]
    
    return total + _tools_tokens


def set_tool_tokens(tokens: int) -> None:
    """Set tool definition tokens (cached separately)"""
    global _tools_tokens, _original_tool_tokens
    _tools_tokens = tokens
    # Store original value to preserve across cache clears
    _original_tool_tokens = tokens


def clear_cache() -> None:
    """Clear message cache but preserve tool tokens (they don't change during session)"""
    global _message_cache, _tools_tokens, _original_tool_tokens
    _message_cache.clear()
    # Restore tool tokens from stored value instead of resetting to 0
    _tools_tokens = _original_tool_tokens
