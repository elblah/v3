"""
Tests for log utilities
"""

import pytest
import os
from unittest.mock import patch


class TestLogUtils:
    """Test logging utility functions"""

    def test_log_options_defaults(self):
        """Test LogOptions default values"""
        from aicoder.utils.log import LogOptions

        options = LogOptions()

        assert options.color is None
        assert options.debug is False
        assert options.bold is False

    def test_log_options_custom(self):
        """Test LogOptions with custom values"""
        from aicoder.utils.log import LogOptions

        options = LogOptions(color="red", debug=True, bold=True)

        assert options.color == "red"
        assert options.debug is True
        assert options.bold is True

    def test_standalone_success(self):
        """Test standalone success function"""
        from aicoder.utils.log import success

        # Should not raise, just print
        success("Test message")

    def test_standalone_warn(self):
        """Test standalone warn function"""
        from aicoder.utils.log import warn

        # Should not raise, just print
        warn("Test warning")

    def test_standalone_error(self):
        """Test standalone error function"""
        from aicoder.utils.log import error

        # Should not raise, just print
        error("Test error")

    def test_standalone_info(self):
        """Test standalone info function"""
        from aicoder.utils.log import info

        # Should not raise, just print
        info("Test info")

    def test_standalone_debug_disabled_by_default(self):
        """Test debug messages don't print by default"""
        from aicoder.utils.log import debug

        # In non-debug mode, should print nothing
        debug("Debug message")

    def test_log_utils_print_simple(self):
        """Test LogUtils.print with simple message"""
        from aicoder.utils.log import LogUtils

        # Should not raise
        LogUtils.print("Test message")

    def test_log_utils_print_with_color(self):
        """Test LogUtils.print with color"""
        from aicoder.utils.log import LogUtils, LogOptions

        # Should not raise
        LogUtils.print("Test message", LogOptions(color="blue"))

    def test_log_utils_print_bold(self):
        """Test LogUtils.print with bold"""
        from aicoder.utils.log import LogUtils, LogOptions

        # Should not raise
        LogUtils.print("Test message", LogOptions(bold=True))

    def test_log_utils_error(self):
        """Test LogUtils.error"""
        from aicoder.utils.log import LogUtils

        # Should not raise
        LogUtils.error("Error message")

    def test_log_utils_success(self):
        """Test LogUtils.success"""
        from aicoder.utils.log import LogUtils

        # Should not raise
        LogUtils.success("Success message")

    def test_log_utils_warn(self):
        """Test LogUtils.warn"""
        from aicoder.utils.log import LogUtils

        # Should not raise
        LogUtils.warn("Warning message")

    def test_log_utils_debug_with_color(self):
        """Test LogUtils.debug with color"""
        from aicoder.utils.log import LogUtils

        # Should not raise
        LogUtils.debug("Debug message", color="yellow")

    def test_is_debug_disabled(self):
        """Test that DEBUG is disabled by default"""
        from aicoder.utils.log import _is_debug

        # Remove DEBUG env var if set
        original = os.environ.get("DEBUG")
        try:
            os.environ.pop("DEBUG", None)
            assert _is_debug() is False
        finally:
            if original:
                os.environ["DEBUG"] = original
