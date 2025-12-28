"""
Test TokenEstimator module
Tests for
CRITICAL: This must preserve the exact algorithm, not divide by 4
"""

import pytest
from aicoder.core.token_estimator import (
    _estimate_weighted_tokens,
    estimate_messages,
    set_tool_tokens,
    clear_cache,
    _message_cache,
    _tools_tokens,
)

# Type definitions are now dicts
Message = dict[str, object]


def test_estimate_tokens_basic():
    """Test basic token estimation"""
    # Empty string
    assert _estimate_weighted_tokens("") == 0

    # Simple text
    tokens = _estimate_weighted_tokens("Hello world")
    assert tokens > 0
    assert isinstance(tokens, int)


def test_estimate_tokens_character_types():
    """Test estimation handles different character types correctly"""
    # Only letters
    letters_only = "HelloWorld"
    tokens_letters = _estimate_weighted_tokens(letters_only)
    expected_letters = len(letters_only) / 4.2  # TOKEN_LETTER_WEIGHT
    assert abs(tokens_letters - round(expected_letters)) <= 1

    # Only numbers
    numbers_only = "1234567890"
    tokens_numbers = _estimate_weighted_tokens(numbers_only)
    expected_numbers = len(numbers_only) / 3.5  # TOKEN_NUMBER_WEIGHT
    assert abs(tokens_numbers - round(expected_numbers)) <= 1

    # Only punctuation
    punct_only = "!@#$%^&*()"
    tokens_punct = _estimate_weighted_tokens(punct_only)
    expected_punct = len(punct_only) * 1.0  # TOKEN_PUNCTUATION_WEIGHT
    assert abs(tokens_punct - round(expected_punct)) <= 1

    # Only whitespace
    space_only = "     \n\t  "
    tokens_space = _estimate_weighted_tokens(space_only)
    expected_space = len(space_only) * 0.15  # TOKEN_WHITESPACE_WEIGHT
    assert abs(tokens_space - round(expected_space)) <= 1

    # Mixed content
    mixed = "Hello 123! @#$"
    tokens_mixed = _estimate_weighted_tokens(mixed)
    assert tokens_mixed > 0


def test_estimate_tokens_not_simple_divide_by_4():
    """CRITICAL: Ensure this is NOT simple divide by 4"""
    simple_text = "Hello world"
    simple_divide = len(simple_text) / 4
    actual_tokens = _estimate_weighted_tokens(simple_text)

    # Should be different from simple divide by 4
    assert actual_tokens != simple_divide

    # And should be more accurate for mixed content
    mixed_text = "Hello 123! World"
    mixed_divide = len(mixed_text) / 4
    actual_mixed = _estimate_weighted_tokens(mixed_text)

    assert actual_mixed != mixed_divide


def test_estimate_messages_empty():
    """Test message token estimation with empty inputs"""
    assert estimate_messages([]) == 0


def test_estimate_messages_caching():
    """Test that message token estimation uses caching"""
    # Clear cache first
    clear_cache()

    # Create a message
    message = {"role": "user", "content": "Hello world"}

    # First call should calculate and cache
    tokens1 = estimate_messages([message])
    cache_size_after_first = len(_message_cache)

    # Second call should use cache
    tokens2 = estimate_messages([message])
    cache_size_after_second = len(_message_cache)

    # Results should be identical
    assert tokens1 == tokens2
    # Cache should not grow on second call
    assert cache_size_after_first == cache_size_after_second
    # Cache should have exactly one entry
    assert cache_size_after_first == 1


def test_estimate_messages_with_tools():
    """Test that tool definitions tokens are included"""
    clear_cache()

    message = {"role": "user", "content": "Hello"}

    # Without tool definitions
    tokens_without_tools = estimate_messages([message])

    # Set tool definitions tokens
    set_tool_tokens(100)

    # With tool definitions
    tokens_with_tools = estimate_messages([message])

    # Should be exactly 100 more tokens
    assert tokens_with_tools == tokens_without_tools + 100


def test_set_tool_tokens():
    """Test setting tool definitions tokens"""
    # Import fresh module state
    from aicoder.core import token_estimator

    token_estimator.clear_cache()

    # Set to different values
    token_estimator.set_tool_tokens(50)
    assert token_estimator._tools_tokens == 50

    token_estimator.set_tool_tokens(200)
    assert token_estimator._tools_tokens == 200


def test_clear_cache():
    """Test clearing token cache"""
    # Import fresh module state
    from aicoder.core import token_estimator

    # Add something to cache
    token_estimator._message_cache["test"] = 10
    token_estimator._tools_tokens = 100

    # Clear cache
    token_estimator.clear_cache()

    # Should be empty
    assert len(token_estimator._message_cache) == 0
    assert token_estimator._tools_tokens == 0


def test_estimate_messages_multiple():
    """Test estimation with multiple messages"""
    clear_cache()

    messages = [
        {"role": "system", "content": "You are a helpful assistant"},
        {"role": "user", "content": "Hello world"},
        {"role": "assistant", "content": "Hi there!"},
    ]

    tokens = estimate_messages(messages)
    assert tokens > 0

    # Should have cached all 3 messages
    assert len(_message_cache) == 3

    # Calling again should use cache
    tokens2 = estimate_messages(messages)
    assert tokens == tokens2
    assert len(_message_cache) == 3  # No new cache entries


def test_estimate_tokens_special_characters():
    """Test estimation with various special characters"""
    # Unicode and special chars
    special = "Hello 世界 émoji 🚀"
    tokens = _estimate_weighted_tokens(special)
    assert tokens > 0
    assert isinstance(tokens, int)

    # Should handle non-ASCII as "other" category
    assert tokens > len(special) / 4.2  # More than just letters


def test_token_weights_correctness():
    """Verify the exact weights match TypeScript version"""
    from aicoder.core.token_estimator import (
        TOKEN_LETTER_WEIGHT,
        TOKEN_NUMBER_WEIGHT,
        TOKEN_PUNCTUATION_WEIGHT,
        TOKEN_WHITESPACE_WEIGHT,
        TOKEN_OTHER_WEIGHT,
    )

    assert TOKEN_LETTER_WEIGHT == 4.2
    assert TOKEN_NUMBER_WEIGHT == 3.5
    assert TOKEN_PUNCTUATION_WEIGHT == 1.0
    assert TOKEN_WHITESPACE_WEIGHT == 0.15
    assert TOKEN_OTHER_WEIGHT == 3.0


def test_punctuation_set_completeness():
    """Verify correct punctuation set"""
    from aicoder.core.token_estimator import PUNCTUATION_SET

    expected_punct = {
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
    }

    assert PUNCTUATION_SET == expected_punct
