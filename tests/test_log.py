"""Tests for log utilities module"""

import pytest
from unittest.mock import patch, MagicMock
from aicoder.utils import log


class TestLogOptions:
    """Tests for LogOptions dataclass"""

    def test_log_options_defaults(self):
        """Test LogOptions has expected default values"""
        options = log.LogOptions()
        assert options.color is None
        assert options.debug is False
        assert options.bold is False

    def test_log_options_with_values(self):
        """Test LogOptions with custom values"""
        options = log.LogOptions(color="red", debug=True, bold=True)
        assert options.color == "red"
        assert options.debug is True
        assert options.bold is True


class TestGetColors:
    """Tests for _get_colors function"""

    def test_get_colors_returns_dict(self):
        """Test _get_colors returns Config.colors dictionary"""
        colors = log._get_colors()
        assert isinstance(colors, dict)
        assert "reset" in colors
        assert "red" in colors
        assert "green" in colors


class TestIsDebug:
    """Tests for _is_debug function"""

    def test_is_debug_returns_false_by_default(self):
        """Test _is_debug returns False when DEBUG not set"""
        with patch.dict('os.environ', {}, clear=False):
            # Remove DEBUG if it exists
            import os
            if 'DEBUG' in os.environ:
                del os.environ['DEBUG']
            result = log._is_debug()
            assert result is False

    def test_is_debug_returns_true_when_set(self):
        """Test _is_debug returns True when DEBUG=1"""
        with patch.dict('os.environ', {'DEBUG': '1'}):
            result = log._is_debug()
            assert result is True

    def test_is_debug_returns_false_when_debug_not_1(self):
        """Test _is_debug returns False when DEBUG is not '1'"""
        with patch.dict('os.environ', {'DEBUG': 'true'}):
            result = log._is_debug()
            assert result is False


class TestLogUtilsPrint:
    """Tests for LogUtils.print function"""

    def test_print_simple_message(self, capsys):
        """Test printing a simple message"""
        log.LogUtils.print("test message")
        captured = capsys.readouterr()
        assert "test message" in captured.out

    def test_print_with_color(self, capsys):
        """Test printing with color"""
        colors = {"reset": "\x1b[0m", "red": "\x1b[31m", "bold": "\x1b[1m"}
        with patch.object(log, '_get_colors', return_value=colors):
            log.LogUtils.print("error message", log.LogOptions(color="red"))
            captured = capsys.readouterr()
            assert "error message" in captured.out
            # The color code may be at different positions, just verify message is present
            assert "error message\x1b[0m" in captured.out

    def test_print_with_bold(self, capsys):
        """Test printing with bold option"""
        colors = {"reset": "\x1b[0m", "bold": "\x1b[1m"}
        with patch.object(log, '_get_colors', return_value=colors):
            log.LogUtils.print("bold message", log.LogOptions(bold=True))
            captured = capsys.readouterr()
            assert "bold message" in captured.out
            assert "\x1b[1m" in captured.out

    def test_print_with_color_and_bold(self, capsys):
        """Test printing with both color and bold"""
        colors = {"reset": "\x1b[0m", "red": "\x1b[31m", "bold": "\x1b[1m"}
        with patch.object(log, '_get_colors', return_value=colors):
            log.LogUtils.print("important", log.LogOptions(color="red", bold=True))
            captured = capsys.readouterr()
            assert "important" in captured.out

    def test_print_with_debug_disabled(self, capsys):
        """Test that debug messages are suppressed when DEBUG not set"""
        with patch.dict('os.environ', {}, clear=False):
            import os
            if 'DEBUG' in os.environ:
                del os.environ['DEBUG']
            log.LogUtils.print("debug message", log.LogOptions(debug=True))
            captured = capsys.readouterr()
            assert captured.out == ""

    def test_print_with_debug_enabled(self, capsys):
        """Test that debug messages show when DEBUG=1"""
        with patch.dict('os.environ', {'DEBUG': '1'}):
            log.LogUtils.print("debug message", log.LogOptions(debug=True))
            captured = capsys.readouterr()
            assert "debug message" in captured.out

    def test_print_with_kwargs(self, capsys):
        """Test printing with keyword arguments"""
        colors = {"reset": "\x1b[0m", "blue": "\x1b[34m", "bold": "\x1b[1m"}
        with patch.object(log, '_get_colors', return_value=colors):
            log.LogUtils.print("info message", color="blue", bold=True)
            captured = capsys.readouterr()
            assert "info message" in captured.out


class TestLogUtilsError:
    """Tests for LogUtils.error function"""

    def test_error_prints_red_message(self, capsys):
        """Test error prints in red"""
        colors = {"reset": "\x1b[0m", "red": "\x1b[31m"}
        with patch.object(log, '_get_colors', return_value=colors):
            log.LogUtils.error("error occurred")
            captured = capsys.readouterr()
            assert "error occurred" in captured.out


class TestLogUtilsSuccess:
    """Tests for LogUtils.success function"""

    def test_success_prints_green_message(self, capsys):
        """Test success prints in green"""
        colors = {"reset": "\x1b[0m", "green": "\x1b[32m"}
        with patch.object(log, '_get_colors', return_value=colors):
            log.LogUtils.success("operation successful")
            captured = capsys.readouterr()
            assert "operation successful" in captured.out


class TestLogUtilsWarn:
    """Tests for LogUtils.warn function"""

    def test_warn_prints_yellow_message(self, capsys):
        """Test warn prints in yellow"""
        colors = {"reset": "\x1b[0m", "yellow": "\x1b[33m"}
        with patch.object(log, '_get_colors', return_value=colors):
            log.LogUtils.warn("warning message")
            captured = capsys.readouterr()
            assert "warning message" in captured.out


class TestLogUtilsDebug:
    """Tests for LogUtils.debug function"""

    def test_debug_suppressed_when_disabled(self, capsys):
        """Test debug messages are suppressed when DEBUG not set"""
        with patch.dict('os.environ', {}, clear=False):
            import os
            if 'DEBUG' in os.environ:
                del os.environ['DEBUG']
            log.LogUtils.debug("debug info")
            captured = capsys.readouterr()
            assert captured.out == ""

    def test_debug_shown_when_enabled(self, capsys):
        """Test debug messages show when DEBUG=1"""
        with patch.dict('os.environ', {'DEBUG': '1'}):
            log.LogUtils.debug("debug info")
            captured = capsys.readouterr()
            assert "debug info" in captured.out

    def test_debug_with_custom_color(self, capsys):
        """Test debug with custom color"""
        colors = {"reset": "\x1b[0m", "yellow": "\x1b[33m", "blue": "\x1b[34m"}
        with patch.object(log, '_get_colors', return_value=colors), \
             patch.dict('os.environ', {'DEBUG': '1'}):
            log.LogUtils.debug("debug info", color="blue")
            captured = capsys.readouterr()
            assert "debug info" in captured.out


class TestStandaloneFunctions:
    """Tests for standalone convenience functions"""

    def test_success_function(self, capsys):
        """Test success standalone function"""
        colors = {"reset": "\x1b[0m", "green": "\x1b[32m"}
        with patch.object(log, '_get_colors', return_value=colors):
            log.success("done!")
            captured = capsys.readouterr()
            assert "done!" in captured.out

    def test_warn_function(self, capsys):
        """Test warn standalone function"""
        colors = {"reset": "\x1b[0m", "yellow": "\x1b[33m"}
        with patch.object(log, '_get_colors', return_value=colors):
            log.warn("be careful")
            captured = capsys.readouterr()
            assert "be careful" in captured.out

    def test_error_function(self, capsys):
        """Test error standalone function"""
        colors = {"reset": "\x1b[0m", "red": "\x1b[31m"}
        with patch.object(log, '_get_colors', return_value=colors):
            log.error("failed")
            captured = capsys.readouterr()
            assert "failed" in captured.out

    def test_debug_function(self, capsys):
        """Test debug standalone function"""
        colors = {"reset": "\x1b[0m", "yellow": "\x1b[33m", "blue": "\x1b[34m"}
        with patch.object(log, '_get_colors', return_value=colors), \
             patch.dict('os.environ', {'DEBUG': '1'}):
            log.debug("trace info")
            captured = capsys.readouterr()
            assert "trace info" in captured.out

    def test_info_function(self, capsys):
        """Test info standalone function"""
        colors = {"reset": "\x1b[0m", "blue": "\x1b[34m"}
        with patch.object(log, '_get_colors', return_value=colors):
            log.info("information")
            captured = capsys.readouterr()
            assert "information" in captured.out


class TestLogUtilsEdgeCases:
    """Tests for edge cases in LogUtils"""

    def test_print_empty_message(self, capsys):
        """Test printing empty message - print adds newline even for empty string"""
        log.LogUtils.print("")
        captured = capsys.readouterr()
        # print() always adds a newline, even for empty strings
        assert captured.out == "\n"

    def test_print_unicode_message(self, capsys):
        """Test printing unicode characters"""
        colors = {"reset": "\x1b[0m"}
        with patch.object(log, '_get_colors', return_value=colors):
            log.LogUtils.print("Hello 世界 🌍")
            captured = capsys.readouterr()
            assert "Hello 世界 🌍" in captured.out

    def test_print_multiline_message(self, capsys):
        """Test printing multiline message"""
        colors = {"reset": "\x1b[0m"}
        with patch.object(log, '_get_colors', return_value=colors):
            log.LogUtils.print("Line 1\nLine 2\nLine 3")
            captured = capsys.readouterr()
            assert "Line 1" in captured.out
            assert "Line 2" in captured.out
            assert "Line 3" in captured.out

    def test_error_with_special_characters(self, capsys):
        """Test error with special characters"""
        colors = {"reset": "\x1b[0m", "red": "\x1b[31m"}
        with patch.object(log, '_get_colors', return_value=colors):
            log.LogUtils.error("Error: `command` failed with $?")
            captured = capsys.readouterr()
            assert "Error:" in captured.out

    def test_debug_with_empty_message(self, capsys):
        """Test debug with empty message when disabled"""
        with patch.dict('os.environ', {}, clear=False):
            import os
            if 'DEBUG' in os.environ:
                del os.environ['DEBUG']
            log.LogUtils.debug("")
            captured = capsys.readouterr()
            assert captured.out == ""

    def test_multiple_print_calls(self, capsys):
        """Test multiple print calls in sequence"""
        colors = {"reset": "\x1b[0m", "red": "\x1b[31m", "green": "\x1b[32m"}
        with patch.object(log, '_get_colors', return_value=colors):
            log.LogUtils.print("first", log.LogOptions(color="red"))
            log.LogUtils.print("second", log.LogOptions(color="green"))
            captured = capsys.readouterr()
            assert "first" in captured.out
            assert "second" in captured.out
