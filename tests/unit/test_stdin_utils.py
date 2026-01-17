"""Unit tests for stdin utilities."""

import sys
import pytest
from unittest.mock import patch

import sys as system_sys
system_sys.path.insert(0, '/home/blah/storage/ai-worktree-storage/feat_test_coverage__20260117_062928')

from aicoder.utils.stdin_utils import read_stdin_as_string


class TestReadStdinAsString:
    """Test read_stdin_as_string function."""

    def test_returns_empty_when_tty(self):
        """Test returns empty string when stdin is a tty."""
        with patch.object(sys, 'stdin') as mock_stdin:
            mock_stdin.isatty.return_value = True
            mock_stdin.read = pytest.fail  # Should not be called

            result = read_stdin_as_string()
            assert result == ""

    def test_reads_when_not_tty(self):
        """Test reads from stdin when not a tty (piped)."""
        with patch.object(sys, 'stdin') as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.read.return_value = "piped input"

            result = read_stdin_as_string()
            assert result == "piped input"
            mock_stdin.read.assert_called_once()

    def test_reads_multiline_input(self):
        """Test reads multiline piped input."""
        with patch.object(sys, 'stdin') as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.read.return_value = "line1\nline2\nline3"

            result = read_stdin_as_string()
            assert result == "line1\nline2\nline3"

    def test_reads_empty_piped_input(self):
        """Test reads empty piped input."""
        with patch.object(sys, 'stdin') as mock_stdin:
            mock_stdin.isatty.return_value = False
            mock_stdin.read.return_value = ""

            result = read_stdin_as_string()
            assert result == ""
