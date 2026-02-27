"""Tests for LogUtils logging utility"""

import pytest
from aicoder.utils.log import LogUtils, success, warn, error, info, debug, printc
from aicoder.core.config import Config


class TestLogUtilsColorNames:
    """Test LogUtils with color names"""

    def test_success_with_color_name(self, capsys):
        """Test success() uses green color"""
        LogUtils.success("Success message")
        captured = capsys.readouterr()
        assert Config.colors["green"] in captured.out
        assert "Success message" in captured.out

    def test_warn_with_color_name(self, capsys):
        """Test warn() uses yellow color"""
        LogUtils.warn("Warning message")
        captured = capsys.readouterr()
        assert Config.colors["yellow"] in captured.out
        assert "Warning message" in captured.out

    def test_error_with_color_name(self, capsys):
        """Test error() uses red color"""
        LogUtils.error("Error message")
        captured = capsys.readouterr()
        assert Config.colors["red"] in captured.out
        assert "Error message" in captured.out

    def test_info_with_color_name(self, capsys):
        """Test info() uses blue color"""
        LogUtils.info("Info message")
        captured = capsys.readouterr()
        assert Config.colors["blue"] in captured.out
        assert "Info message" in captured.out

    def test_printc_with_color_name(self, capsys):
        """Test printc() accepts color names"""
        LogUtils.printc("Cyan message", color="cyan")
        captured = capsys.readouterr()
        assert Config.colors["cyan"] in captured.out
        assert "Cyan message" in captured.out

    def test_printc_with_invalid_color_name(self, capsys):
        """Test printc() handles invalid color names gracefully"""
        LogUtils.printc("Message with unknown color", color="not_a_color")
        captured = capsys.readouterr()
        # Should print message without color codes
        assert "Message with unknown color" in captured.out
        assert "\x1b[" not in captured.out  # No ANSI codes


class TestLogUtilsAnsiCodes:
    """Test LogUtils with direct ANSI codes (backward compatibility)"""

    def test_printc_with_ansi_code(self, capsys):
        """Test printc() accepts direct ANSI codes"""
        LogUtils.printc("Green ANSI", color=Config.colors["green"])
        captured = capsys.readouterr()
        assert Config.colors["green"] in captured.out
        assert "Green ANSI" in captured.out

    def test_printc_with_logoptions_ansi(self, capsys):
        """Test printc() with LogOptions using ANSI codes"""
        from aicoder.utils.log import LogOptions
        LogUtils.printc("Message", LogOptions(color=Config.colors["yellow"]))
        captured = capsys.readouterr()
        assert Config.colors["yellow"] in captured.out
        assert "Message" in captured.out


class TestLogUtilsFormatting:
    """Test LogUtils formatting options"""

    def test_printc_bold(self, capsys):
        """Test printc() with bold option"""
        LogUtils.printc("Bold message", bold=True)
        captured = capsys.readouterr()
        assert Config.colors["bold"] in captured.out
        assert "Bold message" in captured.out

    def test_printc_color_and_bold(self, capsys):
        """Test printc() with both color and bold"""
        LogUtils.printc("Colored bold", color="red", bold=True)
        captured = capsys.readouterr()
        assert Config.colors["bold"] in captured.out
        assert Config.colors["red"] in captured.out
        assert "Colored bold" in captured.out

    def test_printc_debug_suppressed(self, capsys, monkeypatch):
        """Test debug messages are suppressed when DEBUG=0"""
        from aicoder.core.config import Config
        monkeypatch.setattr(Config, '_debug_enabled', False)
        LogUtils.debug("Debug message")
        captured = capsys.readouterr()
        assert "Debug message" not in captured.out

    def test_printc_debug_enabled(self, capsys, monkeypatch):
        """Test debug messages show when DEBUG=1"""
        from aicoder.core.config import Config
        monkeypatch.setattr(Config, '_debug_enabled', True)
        LogUtils.debug("Debug message")
        captured = capsys.readouterr()
        assert "Debug message" in captured.out


class TestStandaloneFunctions:
    """Test standalone convenience functions"""

    def test_standalone_success(self, capsys):
        """Test success() standalone function"""
        success("Standalone success")
        captured = capsys.readouterr()
        assert Config.colors["green"] in captured.out
        assert "Standalone success" in captured.out

    def test_standalone_warn(self, capsys):
        """Test warn() standalone function"""
        warn("Standalone warn")
        captured = capsys.readouterr()
        assert Config.colors["yellow"] in captured.out
        assert "Standalone warn" in captured.out

    def test_standalone_error(self, capsys):
        """Test error() standalone function"""
        error("Standalone error")
        captured = capsys.readouterr()
        assert Config.colors["red"] in captured.out
        assert "Standalone error" in captured.out

    def test_standalone_info(self, capsys):
        """Test info() standalone function"""
        info("Standalone info")
        captured = capsys.readouterr()
        assert Config.colors["blue"] in captured.out
        assert "Standalone info" in captured.out

    def test_standalone_printc(self, capsys):
        """Test printc() standalone function"""
        printc("Standalone printc", color="cyan")
        captured = capsys.readouterr()
        assert Config.colors["cyan"] in captured.out
        assert "Standalone printc" in captured.out


class TestLogUtilsReset:
    """Test that messages are properly reset"""

    def test_message_includes_reset_code(self, capsys):
        """Test that colored messages include reset code at end"""
        LogUtils.success("Test message")
        captured = capsys.readouterr()
        assert Config.colors["reset"] in captured.out

    def test_subsequent_messages_not_colored(self, capsys):
        """Test that subsequent print statements are not affected"""
        LogUtils.success("First")
        print("Second")
        captured = capsys.readouterr()
        lines = captured.out.split("\n")
        # First line has color code
        assert Config.colors["green"] in lines[0]
        # Second line should not have any color codes
        assert "\x1b[" not in lines[1] or lines[1] == ""
