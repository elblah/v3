"""Tests for stdin utilities module"""

import pytest
from io import StringIO
from unittest.mock import patch
from aicoder.utils.stdin_utils import read_stdin_as_string


class TestReadStdinAsString:
    """Test read_stdin_as_string function"""

    def test_reads_content_when_not_tty(self):
        """Test reading content when stdin is not a tty (piped input)"""
        mock_stdin = StringIO("Hello world\nTest content\n")
        with patch('sys.stdin', mock_stdin):
            with patch('sys.stdin.isatty', return_value=False):
                result = read_stdin_as_string()
        assert result == "Hello world\nTest content\n"

    def test_returns_empty_when_tty(self):
        """Test returning empty string when stdin is a tty (interactive)"""
        mock_stdin = StringIO("Should not read this")
        with patch('sys.stdin', mock_stdin):
            with patch('sys.stdin.isatty', return_value=True):
                result = read_stdin_as_string()
        assert result == ""

    def test_handles_empty_input(self):
        """Test handling empty stdin input"""
        mock_stdin = StringIO("")
        with patch('sys.stdin', mock_stdin):
            with patch('sys.stdin.isatty', return_value=False):
                result = read_stdin_as_string()
        assert result == ""

    def test_preserves_whitespace(self):
        """Test that whitespace is preserved (not stripped)"""
        mock_stdin = StringIO("  content with spaces  \n")
        with patch('sys.stdin', mock_stdin):
            with patch('sys.stdin.isatty', return_value=False):
                result = read_stdin_as_string()
        assert result == "  content with spaces  \n"

    def test_handles_unicode_content(self):
        """Test handling unicode content"""
        mock_stdin = StringIO("Hello 世界 🌍")
        with patch('sys.stdin', mock_stdin):
            with patch('sys.stdin.isatty', return_value=False):
                result = read_stdin_as_string()
        assert result == "Hello 世界 🌍"

    def test_handles_multiline_content(self):
        """Test handling multiline content"""
        mock_stdin = StringIO("Line 1\nLine 2\nLine 3\n")
        with patch('sys.stdin', mock_stdin):
            with patch('sys.stdin.isatty', return_value=False):
                result = read_stdin_as_string()
        assert result == "Line 1\nLine 2\nLine 3\n"

    def test_handles_json_content(self):
        """Test handling JSON-like content"""
        mock_stdin = StringIO('{"key": "value", "nested": {"inner": true}}')
        with patch('sys.stdin', mock_stdin):
            with patch('sys.stdin.isatty', return_value=False):
                result = read_stdin_as_string()
        assert '{"key": "value"' in result
