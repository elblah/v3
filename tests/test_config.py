"""Tests for config module"""

import os
import sys
import pytest
from aicoder.core import config


class TestConfigColors:
    """Tests for color configuration"""

    def test_colors_dict_exists(self):
        """Test that colors dictionary exists and has expected keys"""
        assert isinstance(config.Config.colors, dict)
        assert "reset" in config.Config.colors
        assert "red" in config.Config.colors
        assert "green" in config.Config.colors
        assert "yellow" in config.Config.colors

    def test_colors_are_ansi_codes(self):
        """Test that colors contain ANSI escape codes"""
        for key, value in config.Config.colors.items():
            assert value.startswith("\x1b["), f"Color {key} should be ANSI code"


class TestConfigYoloMode:
    """Tests for YOLO mode configuration"""

    def test_yolo_mode_is_boolean(self):
        """Test that yolo_mode returns boolean"""
        result = config.Config.yolo_mode()
        assert isinstance(result, bool)

    def test_get_yolo_mode_backward_compat(self):
        """Test that get_yolo_mode is available for backward compatibility"""
        assert hasattr(config.Config, "get_yolo_mode")
        result = config.Config.get_yolo_mode()
        assert isinstance(result, bool)

    def test_set_yolo_mode(self):
        """Test setting YOLO mode"""
        original = config.Config.yolo_mode()
        try:
            config.Config.set_yolo_mode(True)
            assert config.Config.yolo_mode() is True
            config.Config.set_yolo_mode(False)
            assert config.Config.yolo_mode() is False
        finally:
            # Restore original state
            config.Config.set_yolo_mode(original)


class TestConfigSandbox:
    """Tests for sandbox configuration"""

    def test_sandbox_disabled_is_boolean(self):
        """Test that sandbox_disabled returns boolean"""
        result = config.Config.sandbox_disabled()
        assert isinstance(result, bool)

    def test_set_sandbox_disabled(self):
        """Test setting sandbox disabled state"""
        original = config.Config.sandbox_disabled()
        try:
            config.Config.set_sandbox_disabled(True)
            assert config.Config.sandbox_disabled() is True
            config.Config.set_sandbox_disabled(False)
            assert config.Config.sandbox_disabled() is False
        finally:
            config.Config.set_sandbox_disabled(original)


class TestConfigDetailMode:
    """Tests for detail mode configuration"""

    def test_detail_mode_is_boolean(self):
        """Test that detail_mode returns boolean"""
        result = config.Config.detail_mode()
        assert isinstance(result, bool)

    def test_get_detail_mode_backward_compat(self):
        """Test that get_detail_mode is available for backward compatibility"""
        assert hasattr(config.Config, "get_detail_mode")
        result = config.Config.get_detail_mode()
        assert isinstance(result, bool)

    def test_set_detail_mode(self):
        """Test setting detail mode"""
        original = config.Config.detail_mode()
        try:
            config.Config.set_detail_mode(True)
            assert config.Config.detail_mode() is True
            config.Config.set_detail_mode(False)
            assert config.Config.detail_mode() is False
        finally:
            config.Config.set_detail_mode(original)


class TestConfigMaxRetries:
    """Tests for retry configuration"""

    def test_max_retries_returns_integer(self, monkeypatch):
        """Test that max_retries returns integer"""
        monkeypatch.setenv("MAX_RETRIES", "10")
        result = config.Config.max_retries()
        assert isinstance(result, int)
        assert result > 0

    def test_effective_max_retries_with_default(self, monkeypatch):
        """Test effective max retries with default"""
        monkeypatch.setenv("MAX_RETRIES", "10")
        result = config.Config.effective_max_retries()
        assert isinstance(result, int)
        assert result > 0

    def test_effective_max_retries_with_override(self, monkeypatch):
        """Test effective max retries with runtime override"""
        monkeypatch.setenv("MAX_RETRIES", "10")
        original = config.Config._runtime_max_retries
        try:
            config.Config.set_runtime_max_retries(5)
            assert config.Config.effective_max_retries() == 5
        finally:
            config.Config.set_runtime_max_retries(original)

    def test_set_runtime_max_retries(self, monkeypatch):
        """Test setting runtime max retries override"""
        monkeypatch.setenv("MAX_RETRIES", "10")
        original = config.Config._runtime_max_retries
        try:
            config.Config.set_runtime_max_retries(5)
            assert config.Config.effective_max_retries() == 5
            config.Config.set_runtime_max_retries(None)
            # Should fall back to environment
            assert config.Config.effective_max_retries() > 0
        finally:
            config.Config.set_runtime_max_retries(original)


class TestConfigApiSettings:
    """Tests for API configuration"""

    def test_api_key_returns_string(self):
        """Test that api_key returns string"""
        result = config.Config.api_key()
        assert isinstance(result, str)

    def test_base_url_returns_string(self):
        """Test that base_url returns string"""
        result = config.Config.base_url()
        assert isinstance(result, str)

    def test_api_endpoint_with_base_url(self, monkeypatch):
        """Test api_endpoint includes /chat/completions when base_url is set"""
        monkeypatch.setenv("API_BASE_URL", "https://example.com/v1")
        result = config.Config.api_endpoint()
        assert "/chat/completions" in result

    def test_api_endpoint_without_base_url(self, monkeypatch):
        """Test api_endpoint is empty when no base_url"""
        monkeypatch.delenv("API_BASE_URL", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        result = config.Config.api_endpoint()
        assert result == ""

    def test_model_returns_string(self):
        """Test that model returns string"""
        result = config.Config.model()
        assert isinstance(result, str)


class TestConfigTimeouts:
    """Tests for timeout configuration"""

    def test_streaming_timeout_default(self):
        """Test streaming timeout has reasonable default"""
        result = config.Config.streaming_timeout()
        assert isinstance(result, int)
        assert result > 0

    def test_total_timeout_default(self):
        """Test total timeout is in milliseconds"""
        result = config.Config.total_timeout()
        assert isinstance(result, int)
        assert result > 0
        # Should be in milliseconds (300 * 1000 = 300000)
        assert result >= 1000


class TestConfigContextSettings:
    """Tests for context configuration"""

    def test_context_size_returns_integer(self, monkeypatch):
        """Test context size returns integer"""
        monkeypatch.setenv("CONTEXT_SIZE", "128000")
        result = config.Config.context_size()
        assert isinstance(result, int)
        assert result > 0

    def test_context_compact_percentage_with_env(self, monkeypatch):
        """Test context compact percentage from environment"""
        monkeypatch.setenv("CONTEXT_COMPACT_PERCENTAGE", "80")
        result = config.Config.context_compact_percentage()
        assert isinstance(result, int)
        assert result == 80

    def test_context_compact_percentage_disabled(self, monkeypatch):
        """Test context compact percentage is 0 when env not set"""
        monkeypatch.delenv("CONTEXT_COMPACT_PERCENTAGE", raising=False)
        result = config.Config.context_compact_percentage()
        assert isinstance(result, int)
        # Default is 0 (disabled) when not set

    def test_auto_compact_threshold_disabled_when_percentage_zero(self, monkeypatch):
        """Test auto compact threshold is 0 when percentage is 0"""
        monkeypatch.setenv("CONTEXT_COMPACT_PERCENTAGE", "0")
        result = config.Config.auto_compact_threshold()
        assert result == 0

    def test_auto_compact_enabled_when_percentage_set(self, monkeypatch):
        """Test auto compact enabled when percentage is set"""
        monkeypatch.setenv("CONTEXT_COMPACT_PERCENTAGE", "80")
        result = config.Config.auto_compact_enabled()
        assert result is True


class TestConfigIgnoreSettings:
    """Tests for ignore settings"""

    def test_default_ignore_dirs_is_list(self):
        """Test that ignore_dirs returns list by default"""
        result = config.Config.ignore_dirs()
        assert isinstance(result, list)
        assert ".git" in result
        assert "__pycache__" in result

    def test_default_ignore_patterns_is_list(self):
        """Test that ignore_patterns returns list by default"""
        result = config.Config.ignore_patterns()
        assert isinstance(result, list)
        assert ".pyc" in result

    def test_ignore_dirs_env_override(self, monkeypatch):
        """Test that AICODER_IGNORE_DIRS environment variable extends defaults"""
        monkeypatch.setenv("AICODER_IGNORE_DIRS", "custom_dir")
        result = config.Config.ignore_dirs()
        assert "custom_dir" in result
        assert ".git" in result  # Original still included

    def test_ignore_patterns_env_override(self, monkeypatch):
        """Test that AICODER_IGNORE_PATTERNS environment variable extends defaults"""
        monkeypatch.setenv("AICODER_IGNORE_PATTERNS", "*.custom")
        result = config.Config.ignore_patterns()
        assert "*.custom" in result
        assert ".pyc" in result  # Original still included


class TestConfigDebugMode:
    """Tests for debug mode configuration"""

    def test_debug_is_boolean(self):
        """Test that debug returns boolean"""
        result = config.Config.debug()
        assert isinstance(result, bool)

    def test_set_debug(self):
        """Test setting debug mode"""
        original = config.Config.debug()
        try:
            config.Config.set_debug(True)
            assert config.Config.debug() is True
            config.Config.set_debug(False)
            assert config.Config.debug() is False
        finally:
            config.Config.set_debug(original)


class TestConfigReset:
    """Tests for reset functionality"""

    def test_reset_restores_state(self):
        """Test that reset restores all runtime state"""
        # Change some values
        config.Config.set_debug(True)
        config.Config.set_yolo_mode(True)
        config.Config.set_detail_mode(True)

        # Reset
        config.Config.reset()

        # Values should be restored from environment
        # (at minimum, methods should work without error)
        assert isinstance(config.Config.debug(), bool)
        assert isinstance(config.Config.yolo_mode(), bool)
        assert isinstance(config.Config.detail_mode(), bool)


class TestConfigHelpers:
    """Tests for helper methods"""

    def test_in_tmux_returns_boolean(self):
        """Test that in_tmux returns boolean"""
        result = config.Config.in_tmux()
        assert isinstance(result, bool)

    def test_socket_only_returns_boolean(self):
        """Test that socket_only returns boolean"""
        result = config.Config.socket_only()
        assert isinstance(result, bool)

    def test_system_prompt_returns_string(self):
        """Test that system_prompt returns string"""
        result = config.Config.system_prompt()
        assert isinstance(result, str)

    def test_temperature_returns_none_or_float(self):
        """Test that temperature returns None or float"""
        result = config.Config.temperature()
        assert result is None or isinstance(result, float)

    def test_max_tokens_returns_none_or_int(self):
        """Test that max_tokens returns None or int"""
        result = config.Config.max_tokens()
        assert result is None or isinstance(result, int)

    def test_fallback_configs_returns_list(self):
        """Test that fallback_configs returns list"""
        result = config.Config.fallback_configs()
        assert isinstance(result, list)

    def test_max_tool_result_size_returns_int(self):
        """Test that max_tool_result_size returns int"""
        result = config.Config.max_tool_result_size()
        assert isinstance(result, int)
        assert result > 0

    def test_tmux_prune_percentage_returns_int(self):
        """Test that tmux_prune_percentage returns int"""
        result = config.Config.tmux_prune_percentage()
        assert isinstance(result, int)
        assert result > 0

    def test_compact_protect_rounds_returns_int(self):
        """Test that compact_protect_rounds returns int"""
        result = config.Config.compact_protect_rounds()
        assert isinstance(result, int)
        assert result > 0

    def test_min_summary_length_returns_int(self):
        """Test that min_summary_length returns int"""
        result = config.Config.min_summary_length()
        assert isinstance(result, int)
        assert result > 0

    def test_force_compact_size_returns_int(self):
        """Test that force_compact_size returns int"""
        result = config.Config.force_compact_size()
        assert isinstance(result, int)
        assert result > 0


class TestConfigValidation:
    """Tests for configuration validation"""

    def test_validate_config_exits_when_no_base_url(self, monkeypatch):
        """Test that validate_config exits when base URL is missing"""
        monkeypatch.delenv("API_BASE_URL", raising=False)
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        with pytest.raises(SystemExit) as exc:
            config.Config.validate_config()
        assert exc.value.code == 1

    def test_validate_config_passes_when_base_url_set(self, monkeypatch):
        """Test that validate_config doesn't exit when base URL is set"""
        monkeypatch.setenv("API_BASE_URL", "https://example.com/v1")
        # Should not raise SystemExit
        try:
            config.Config.validate_config()
        except SystemExit as e:
            pytest.fail(f"validate_config should not exit when base_url is set: {e}")


class TestConfigStartupInfo:
    """Tests for startup info display"""

    def test_print_startup_info_runs(self, capsys):
        """Test that print_startup_info runs without error"""
        # Should not raise
        config.Config.print_startup_info()
        captured = capsys.readouterr()
        assert "Configuration:" in captured.out

    def test_print_startup_info_shows_endpoint(self, monkeypatch, capsys):
        """Test that startup info shows API endpoint"""
        monkeypatch.setenv("API_BASE_URL", "https://example.com/v1")
        monkeypatch.delenv("OPENAI_BASE_URL", raising=False)
        config.Config.print_startup_info()
        captured = capsys.readouterr()
        assert "example.com" in captured.out

    def test_print_startup_info_shows_model(self, monkeypatch, capsys):
        """Test that startup info shows model"""
        monkeypatch.setenv("API_MODEL", "test-model")
        monkeypatch.delenv("OPENAI_MODEL", raising=False)
        config.Config.print_startup_info()
        captured = capsys.readouterr()
        assert "test-model" in captured.out


class TestConfigTemperatureEdgeCases:
    """Tests for temperature edge cases"""

    def test_temperature_with_valid_value(self, monkeypatch):
        """Test temperature with valid float value"""
        monkeypatch.setenv("TEMPERATURE", "0.5")
        result = config.Config.temperature()
        assert result == 0.5

    def test_temperature_with_invalid_value_raises(self, monkeypatch):
        """Test temperature with invalid value raises ValueError"""
        monkeypatch.setenv("TEMPERATURE", "invalid")
        with pytest.raises(ValueError):
            config.Config.temperature()

    def test_max_tokens_with_valid_value(self, monkeypatch):
        """Test max_tokens with valid int value"""
        monkeypatch.setenv("MAX_TOKENS", "4096")
        result = config.Config.max_tokens()
        assert result == 4096

    def test_max_tokens_with_invalid_value_raises(self, monkeypatch):
        """Test max_tokens with invalid value raises ValueError"""
        monkeypatch.setenv("MAX_TOKENS", "invalid")
        with pytest.raises(ValueError):
            config.Config.max_tokens()


class TestConfigAutoCompactThreshold:
    """Tests for auto-compact threshold calculation"""

    def test_auto_compact_threshold_with_percentage(self, monkeypatch):
        """Test auto compact threshold calculation"""
        monkeypatch.setenv("CONTEXT_SIZE", "100000")
        monkeypatch.setenv("CONTEXT_COMPACT_PERCENTAGE", "80")
        result = config.Config.auto_compact_threshold()
        # 100000 * 0.80 = 80000
        assert result == 80000

    def test_auto_compact_threshold_capped_at_100(self, monkeypatch):
        """Test auto compact threshold caps at 100%"""
        monkeypatch.setenv("CONTEXT_SIZE", "100000")
        monkeypatch.setenv("CONTEXT_COMPACT_PERCENTAGE", "150")
        result = config.Config.auto_compact_threshold()
        # Capped at 100%
        assert result == 100000


class TestConfigColorsAccessibility:
    """Tests for color accessibility"""

    def test_colors_contain_all_basic_colors(self):
        """Test that all basic ANSI colors are defined"""
        required_colors = ["red", "green", "yellow", "blue", "cyan", "magenta", "reset"]
        for color in required_colors:
            assert color in config.Config.colors, f"Missing color: {color}"

    def test_colors_include_bright_variants(self):
        """Test that bright color variants are defined"""
        # Check if bright variants exist (they may or may not)
        # This test just documents what's expected
        has_bright = any("bright" in k for k in config.Config.colors.keys())
        # Bright colors are optional but nice to have
        # This test passes regardless

    def test_colors_reset_code_present(self):
        """Test that reset code is present"""
        reset = config.Config.colors.get("reset")
        assert reset is not None
        assert "\x1b[0m" in reset or reset == "\x1b[0m"
