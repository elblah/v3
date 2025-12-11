"""
Enhanced token estimation based on Python implementation
More accurate than simple 4 chars per token while remaining fast and dependency-free
Ported exactly from TypeScript version
"""

import re
import json
from typing import List, Dict, Any, Optional


# Token estimation weights (matching Python config)
TOKEN_LETTER_WEIGHT = 4.2
TOKEN_NUMBER_WEIGHT = 3.5
TOKEN_PUNCTUATION_WEIGHT = 1.0
TOKEN_WHITESPACE_WEIGHT = 0.15
TOKEN_OTHER_WEIGHT = 3.0

# Punctuation set for fast lookup
PUNCTUATION_SET = set(
    [
        "!",
        '"',
        "#",
        "$",
        "%",
        "&",
        "'",
        "(",
        ")",
        "*",
        "+",
        ",",
        "-",
        ".",
        "/",
        ":",
        ";",
        "<",
        "=",
        ">",
        "?",
        "@",
        "[",
        "\\",
        "]",
        "^",
        "_",
        "`",
        "{",
        "|",
        "}",
        "~",
    ]
)

# Cache for message token estimation (like Python version)
_message_token_cache = {}
_last_tool_definitions_tokens = 0


def estimate_tokens(text: str) -> int:
    """Estimate the number of tokens in a text string
    Uses enhanced character-based estimation that accounts for different content types
    """
    if not text or len(text) == 0:
        return 0

    # Count character types
    letters = 0
    numbers = 0
    punctuation = 0
    whitespace = 0
    other = 0

    for char in text:
        if re.match(r"[a-zA-Z]", char):
            letters += 1
        elif re.match(r"[0-9]", char):
            numbers += 1
        elif char in PUNCTUATION_SET:
            punctuation += 1
        elif re.match(r"\s", char):
            whitespace += 1
        else:
            other += 1

    # Use configurable weights (matching Python implementation)
    token_estimate = (
        letters / TOKEN_LETTER_WEIGHT
        + numbers / TOKEN_NUMBER_WEIGHT
        + punctuation * TOKEN_PUNCTUATION_WEIGHT
        + whitespace * TOKEN_WHITESPACE_WEIGHT
        + other / TOKEN_OTHER_WEIGHT
    )

    return max(0, round(token_estimate))


def estimate_messages_tokens(messages: List[Dict[str, Any]]) -> int:
    """Estimate tokens for a message array (matching Python implementation)
    Based on real API testing, this estimates the full API request JSON including:
    - Message content
    - JSON structure (field names, quotes, braces)
    - Tool definitions (if any)
    """
    global _message_token_cache, _last_tool_definitions_tokens

    if not messages or len(messages) == 0:
        return 0

    token_count = 0

    # Estimate tokens for each message (with caching like Python)
    for msg in messages:
        msg_json = json.dumps(
            msg, sort_keys=True
        )  # sort_keys for consistent cache keys
        if msg_json in _message_token_cache:
            token_count += _message_token_cache[msg_json]
        else:
            msg_tokens = estimate_tokens(msg_json)
            _message_token_cache[msg_json] = msg_tokens
            token_count += msg_tokens

    # Add tool definitions tokens (if any)
    token_count += _last_tool_definitions_tokens

    return token_count


def set_tool_definitions_tokens(tokens: int) -> None:
    """Set tool definitions tokens for estimation (called when tools are used)"""
    global _last_tool_definitions_tokens
    _last_tool_definitions_tokens = tokens


def clear_token_cache() -> None:
    """Clear the token cache
    Called when messages are cleared or replaced to prevent stale cache entries
    """
    global _message_token_cache, _last_tool_definitions_tokens
    _message_token_cache.clear()
    _last_tool_definitions_tokens = 0
