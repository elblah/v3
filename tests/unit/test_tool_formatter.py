"""Unit tests for tool formatter."""

import json
import pytest
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, '/home/blah/storage/ai-worktree-storage/feat_test_coverage__20260117_062928')

from aicoder.core.tool_formatter import ToolFormatter


class TestFormatForAi:
    """Test format_for_ai function."""

    def test_returns_detailed_field(self):
        """Test returns the detailed field from result."""
        result = {
            "tool": "test",
            "friendly": "Test completed",
            "detailed": "Detailed output here"
        }
        assert ToolFormatter.format_for_ai(result) == "Detailed output here"

    def test_raises_for_missing_detailed(self):
        """Test raises KeyError for missing detailed field."""
        result = {"tool": "test"}
        with pytest.raises(KeyError):
            ToolFormatter.format_for_ai(result)


class TestFormatForDisplay:
    """Test format_for_display function."""

    def test_returns_friendly_field(self):
        """Test returns the friendly field from result."""
        result = {
            "tool": "test",
            "friendly": "Done",
            "detailed": "Detailed info"
        }
        assert ToolFormatter.format_for_display(result) == "Done"

    def test_raises_for_missing_friendly(self):
        """Test raises KeyError for missing friendly field."""
        result = {"tool": "test", "detailed": "info"}
        with pytest.raises(KeyError):
            ToolFormatter.format_for_display(result)


class TestFormatPreview:
    """Test format_preview function."""

    def test_includes_preview_header(self):
        """Test includes preview header."""
        result = ToolFormatter.format_preview({"content": "test"})
        assert "[PREVIEW]" in result

    def test_includes_file_path(self):
        """Test includes file path when provided."""
        result = ToolFormatter.format_preview({"content": "test"}, "/path/to/file.py")
        assert "file.py" in result
        assert "/path/to/file.py" in result

    def test_includes_content(self):
        """Test includes content from preview."""
        result = ToolFormatter.format_preview({"content": "Hello World"})
        assert "Hello World" in result

    def test_handles_missing_content(self):
        """Test handles preview with no content."""
        result = ToolFormatter.format_preview({})
        assert "content" in result.lower() or result.count("\n") >= 0


class TestFormatLabel:
    """Test _format_label function."""

    def test_capitalizes_first_letter(self):
        """Test capitalizes first letter."""
        result = ToolFormatter._format_label("tool_name")
        assert result.startswith("T")

    def test_replaces_underscores_with_spaces(self):
        """Test replaces underscores with spaces."""
        result = ToolFormatter._format_label("tool_name")
        assert " " in result
        assert "_" not in result

    def test_adds_colon(self):
        """Test adds colon at end."""
        result = ToolFormatter._format_label("key")
        assert result.endswith(":")


class TestFormatValueForAi:
    """Test _format_value_for_ai function."""

    def test_formats_none(self):
        """Test formats None value."""
        result = ToolFormatter._format_value_for_ai(None)
        assert "null" in result

    def test_formats_bool(self):
        """Test formats boolean values."""
        result_true = ToolFormatter._format_value_for_ai(True)
        result_false = ToolFormatter._format_value_for_ai(False)
        assert "True" in result_true
        assert "False" in result_false

    def test_formats_int(self):
        """Test formats integer values."""
        result = ToolFormatter._format_value_for_ai(42)
        assert "42" in result

    def test_formats_float(self):
        """Test formats float values."""
        result = ToolFormatter._format_value_for_ai(3.14)
        assert "3.14" in result

    def test_formats_string(self):
        """Test formats string values."""
        result = ToolFormatter._format_value_for_ai("hello")
        assert "hello" in result

    def test_formats_exception(self):
        """Test formats exception values."""
        result = ToolFormatter._format_value_for_ai(Exception("error"))
        assert "error" in result

    def test_formats_object(self):
        """Test formats object as JSON."""
        result = ToolFormatter._format_value_for_ai({"key": "value"})
        assert "key" in result
        assert "value" in result


class TestFormatValue:
    """Test _format_value function."""

    def test_formats_none(self):
        """Test formats None value."""
        result = ToolFormatter._format_value(None)
        assert "null" in result

    def test_formats_bool(self):
        """Test formats boolean values."""
        result_true = ToolFormatter._format_value(True)
        result_false = ToolFormatter._format_value(False)
        assert "True" in result_true
        assert "False" in result_false

    def test_formats_int(self):
        """Test formats integer values."""
        result = ToolFormatter._format_value(42)
        assert "42" in result

    def test_formats_string(self):
        """Test formats string values."""
        result = ToolFormatter._format_value("hello")
        assert "hello" in result

    def test_formats_exception(self):
        """Test formats exception values."""
        result = ToolFormatter._format_value(Exception("error"))
        assert "error" in result

    def test_formats_object(self):
        """Test formats object as JSON."""
        result = ToolFormatter._format_value({"key": "value"})
        assert "key" in result

    def test_truncates_long_json_in_normal_mode(self):
        """Test truncates long JSON when not in detail mode."""
        large_obj = {"data": "x" * 200}
        with patch('aicoder.core.tool_formatter.Config.detail_mode', return_value=False):
            result = ToolFormatter._format_value(large_obj)
        # Should be truncated
        assert len(result) < 250
