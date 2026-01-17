"""
Test stream_utils module
Tests for stdin reading functionality
"""

import pytest
from io import StringIO
from unittest.mock import patch
from aicoder.utils.stream_utils import read_stdin_as_string


class TestReadStdinAsString:
    """Test read_stdin_as_string function"""

    def test_reads_content_when_not_tty(self):
        mock_stdin = StringIO("Hello world\nTest content\n")
        with patch('sys.stdin', mock_stdin):
            with patch('sys.stdin.isatty', return_value=False):
                result = read_stdin_as_string()
        assert result == "Hello world\nTest content"

    def test_returns_empty_when_tty(self):
        mock_stdin = StringIO("Should not read this")
        with patch('sys.stdin', mock_stdin):
            with patch('sys.stdin.isatty', return_value=True):
                result = read_stdin_as_string()
        assert result == ""

    def test_strips_whitespace(self):
        mock_stdin = StringIO("  content with spaces  \n")
        with patch('sys.stdin', mock_stdin):
            with patch('sys.stdin.isatty', return_value=False):
                result = read_stdin_as_string()
        assert result == "content with spaces"

    def test_handles_empty_input(self):
        mock_stdin = StringIO("")
        with patch('sys.stdin', mock_stdin):
            with patch('sys.stdin.isatty', return_value=False):
                result = read_stdin_as_string()
        assert result == ""

    def test_handles_unicode_content(self):
        mock_stdin = StringIO("Hello 世界 🌍")
        with patch('sys.stdin', mock_stdin):
            with patch('sys.stdin.isatty', return_value=False):
                result = read_stdin_as_string()
        assert result == "Hello 世界 🌍"
