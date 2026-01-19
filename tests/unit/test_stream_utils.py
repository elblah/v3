"""Unit tests for stream utilities."""

import pytest
from unittest.mock import patch, MagicMock
import sys
from io import StringIO

sys.path.insert(0, '/home/blah/storage/ai-worktree-storage/feat_test_coverage__20260117_062928')

from aicoder.utils.stream_utils import read_stdin_as_string


class TestReadStdinAsString:
    """Test read_stdin_as_string function."""

    def test_reads_from_stdin_when_piped(self):
        """Test reads content from stdin when not a tty."""
        test_content = "Hello, World!\nLine 2"
        with patch('sys.stdin') as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.read.return_value = test_content

            result = read_stdin_as_string()

        assert result == test_content
        mock_stdin.read.assert_called_once()

    def test_trims_whitespace(self):
        """Test trims whitespace from stdin content."""
        test_content = "  Hello, World!  \n  Line 2  \n  "
        expected = "Hello, World!  \n  Line 2"
        with patch('sys.stdin') as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.read.return_value = test_content

            result = read_stdin_as_string()

        assert result == expected

    def test_returns_empty_string_when_tty(self):
        """Test returns empty string when stdin is a tty (interactive)."""
        with patch('sys.stdin') as mock_stdin:
            mock_stdin.isatty.return_value = True

            result = read_stdin_as_string()

        assert result == ""
        mock_stdin.read.assert_not_called()

    def test_handles_empty_stdin(self):
        """Test handles empty stdin content."""
        with patch('sys.stdin') as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.read.return_value = ""

            result = read_stdin_as_string()

        assert result == ""

    def test_handles_whitespace_only(self):
        """Test handles stdin with only whitespace."""
        with patch('sys.stdin') as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.read.return_value = "   \n\n\t  \n"

            result = read_stdin_as_string()

        assert result == ""

    def test_handles_multiline_content(self):
        """Test handles multiline content correctly."""
        test_content = "Line 1\nLine 2\nLine 3"
        with patch('sys.stdin') as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.read.return_value = test_content

            result = read_stdin_as_string()

        assert result == test_content

    def test_handles_unicode_content(self):
        """Test handles unicode content."""
        test_content = "你好世界\nこんにちは\nمرحبا"
        with patch('sys.stdin') as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.read.return_value = test_content

            result = read_stdin_as_string()

        assert result == test_content

    def test_preserves_internal_whitespace(self):
        """Test preserves internal whitespace while trimming edges."""
        test_content = "  Hello,   World!  \n  Test  Content  \n  "
        expected = "Hello,   World!  \n  Test  Content"
        with patch('sys.stdin') as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.read.return_value = test_content

            result = read_stdin_as_string()

        assert result == expected

    def test_handles_single_line(self):
        """Test handles single line content."""
        test_content = "Single line"
        with patch('sys.stdin') as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.read.return_value = test_content

            result = read_stdin_as_string()

        assert result == test_content

    def test_trailing_newline(self):
        """Test content with trailing newline."""
        test_content = "Hello, World!\n"
        with patch('sys.stdin') as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.read.return_value = test_content

            result = read_stdin_as_string()

        assert result == "Hello, World!"

    def test_leading_newline(self):
        """Test content with leading newline."""
        test_content = "\nHello, World!"
        with patch('sys.stdin') as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.read.return_value = test_content

            result = read_stdin_as_string()

        assert result == "Hello, World!"
