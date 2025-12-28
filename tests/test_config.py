"""
Test Config class
Tests for
"""

import os
import pytest
from unittest.mock import patch
from aicoder.core.config import Config


def test_colors():
    """Test that all colors are defined"""
    expected_colors = [
        "reset",
        "bold",
        "dim",
        "black",
        "red",
        "green",
        "yellow",
        "blue",
        "magenta",
        "cyan",
        "white",
        "brightGreen",
        "brightRed",
        "brightYellow",
        "brightBlue",
        "brightMagenta",
        "brightCyan",
        "brightWhite",
    ]

    for color in expected_colors:
        assert color in Config.colors
        assert Config.colors[color].startswith("\x1b[")


def test_yolo_mode():
    """Test YOLO mode functionality"""
    # Reset state
    Config.reset()

    # Save original YOLO_MODE
    original_yolo = os.environ.get("YOLO_MODE")

    try:
        # Test default with clean environment
        with patch.dict(os.environ, {}, clear=True):
            assert Config.yolo_mode() == False

        # Test runtime setting
        Config.set_yolo_mode(True)
        assert Config.yolo_mode() == True

        Config.set_yolo_mode(False)
        assert Config.yolo_mode() == False

        # Test environment variable
        with patch.dict(os.environ, {"YOLO_MODE": "1"}):
            assert Config.yolo_mode() == True
    finally:
        # Restore original YOLO_MODE
        if original_yolo is not None:
            os.environ["YOLO_MODE"] = original_yolo
        elif "YOLO_MODE" in os.environ:
            del os.environ["YOLO_MODE"]


def test_sandbox_disabled():
    """Test sandbox disabled functionality"""
    # Reset state
    Config.reset()

    # Test default
    assert Config.sandbox_disabled() == False

    # Test runtime setting
    Config.set_sandbox_disabled(True)
    assert Config.sandbox_disabled() == True

    Config.set_sandbox_disabled(False)
    assert Config.sandbox_disabled() == False

    # Test environment variable
    with patch.dict(os.environ, {"MINI_SANDBOX": "0"}):
        assert Config.sandbox_disabled() == True


def test_detail_mode():
    """Test detail mode functionality"""
    # Reset state
    Config.reset()

    # Test default
    assert Config.detail_mode() == False

    # Test setting
    Config.set_detail_mode(True)
    assert Config.detail_mode() == True

    Config.set_detail_mode(False)
    assert Config.detail_mode() == False


def test_api_config():
    """Test API configuration"""
    # Test with no environment variables
    with patch.dict(os.environ, {}, clear=True):
        assert Config.api_key() == ""
        assert Config.base_url() == ""
        assert Config.api_endpoint() == ""
        assert Config.model() == ""
        assert Config.temperature() == 0.0
        assert Config.max_tokens() is None

    # Test with OPENAI variables
    with patch.dict(
        os.environ,
        {
            "OPENAI_API_KEY": "test-key",
            "OPENAI_BASE_URL": "https://api.openai.com/v1",
            "OPENAI_MODEL": "gpt-4",
            "TEMPERATURE": "0.7",
            "MAX_TOKENS": "2048",
        },
    ):
        assert Config.api_key() == "test-key"
        assert Config.base_url() == "https://api.openai.com/v1"
        assert Config.api_endpoint() == "https://api.openai.com/v1/chat/completions"
        assert Config.model() == "gpt-4"
        assert Config.temperature() == 0.7
        assert Config.max_tokens() == 2048

    # Test with API variables (fallback)
    with patch.dict(
        os.environ,
        {
            "API_KEY": "fallback-key",
            "API_BASE_URL": "https://fallback.com/v1",
            "API_MODEL": "fallback-model",
            "TEMPERATURE": "0.5",
        },
    ):
        assert Config.api_key() == "fallback-key"
        assert Config.base_url() == "https://fallback.com/v1"
        assert Config.model() == "fallback-model"
        assert Config.temperature() == 0.5


def test_streaming_config():
    """Test streaming configuration"""
    # Test defaults
    with patch.dict(os.environ, {}, clear=True):
        assert Config.streaming_timeout() == 300
        assert Config.streaming_read_timeout() == 30
        assert Config.total_timeout() == 300000  # 300s * 1000ms

    # Test custom values
    with patch.dict(
        os.environ,
        {
            "STREAMING_TIMEOUT": "600",
            "STREAMING_READ_TIMEOUT": "60",
            "TOTAL_TIMEOUT": "120",
        },
    ):
        assert Config.streaming_timeout() == 600
        assert Config.streaming_read_timeout() == 60
        assert Config.total_timeout() == 120000


def test_context_config():
    """Test context configuration"""
    # Test defaults
    with patch.dict(os.environ, {}, clear=True):
        assert Config.context_size() == 128000
        assert Config.context_compact_percentage() == 0
        assert Config.auto_compact_threshold() == 0
        assert Config.auto_compact_enabled() == False

    # Test with compact percentage
    with patch.dict(os.environ, {"CONTEXT_COMPACT_PERCENTAGE": "75"}):
        assert Config.context_compact_percentage() == 75
        assert Config.auto_compact_threshold() == 96000  # 128000 * 0.75
        assert Config.auto_compact_enabled() == True

    # Test with over 100% (should be capped)
    with patch.dict(os.environ, {"CONTEXT_COMPACT_PERCENTAGE": "150"}):
        assert Config.auto_compact_threshold() == 128000  # Capped at 100%


def test_compaction_config():
    """Test compaction configuration"""
    # Test defaults
    with patch.dict(os.environ, {}, clear=True):
        assert Config.tmux_prune_percentage() == 50
        assert Config.compact_protect_rounds() == 2
        assert Config.min_summary_length() == 100
        assert Config.force_compact_size() == 5

    # Test custom values
    with patch.dict(
        os.environ,
        {
            "TMUX_PRUNE_PERCENTAGE": "75",
            "COMPACT_PROTECT_ROUNDS": "3",
            "MIN_SUMMARY_LENGTH": "200",
            "FORCE_COMPACT_SIZE": "10",
        },
    ):
        assert Config.tmux_prune_percentage() == 75
        assert Config.compact_protect_rounds() == 3
        assert Config.min_summary_length() == 200
        assert Config.force_compact_size() == 10


def test_tool_config():
    """Test tool configuration"""
    # Test default
    with patch.dict(os.environ, {}, clear=True):
        assert Config.max_tool_result_size() == 300000

    # Test custom values
    with patch.dict(os.environ, {"MAX_TOOL_RESULT_SIZE": "500000"}):
        assert Config.max_tool_result_size() == 500000


def test_debug():
    """Test debug configuration"""
    # Test default
    with patch.dict(os.environ, {}, clear=True):
        assert Config.debug() == False

    # Test enabled
    with patch.dict(os.environ, {"DEBUG": "1"}):
        assert Config.debug() == True


def test_fallback_configs():
    """Test fallback configs"""
    assert Config.fallback_configs() == []


def test_reset():
    """Test reset functionality"""
    # Set some values
    Config.set_yolo_mode(True)
    Config.set_sandbox_disabled(True)
    Config.set_detail_mode(True)

    # Reset
    Config.reset()

    # Check all are reset
    assert Config.yolo_mode() == False
    assert Config.sandbox_disabled() == False
    assert Config.detail_mode() == False


def test_validate_config_no_exit():
    """Test validate_config without actually exiting"""
    # Test with valid config
    with patch.dict(os.environ, {"OPENAI_BASE_URL": "https://test.com"}):
        # Should not raise an error
        Config.validate_config()


def test_print_startup_info(capsys):
    """Test print_startup_info output"""
    with patch.dict(
        os.environ,
        {"OPENAI_BASE_URL": "https://test.com/v1", "OPENAI_MODEL": "test-model"},
    ):
        Config.print_startup_info()
        captured = capsys.readouterr()
        output = captured.out

        assert "Configuration:" in output
        assert "API Endpoint: https://test.com/v1/chat/completions" in output
        assert "Model: test-model" in output
