"""Unit tests for diff utilities."""

import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, '/home/blah/storage/ai-worktree-storage/feat_test_coverage__20260117_062928')

from aicoder.utils.diff_utils import (
    colorize_diff,
    generate_unified_diff,
    generate_unified_diff_with_status,
)


class MockShellResult:
    """Mock result for execute_command_sync."""
    def __init__(self, success, exit_code, stdout, stderr):
        self.success = success
        self.exit_code = exit_code
        self.stdout = stdout
        self.stderr = stderr


class TestColorizeDiff:
    """Test colorize_diff function."""

    def test_colorize_additions_green(self):
        """Test addition lines are colored green."""
        diff = "+ This is an added line"
        result = colorize_diff(diff)
        assert "\033[32m" in result  # Green color code

    def test_colorize_deletions_red(self):
        """Test deletion lines are colored red."""
        diff = "- This is a deleted line"
        result = colorize_diff(diff)
        assert "\033[31m" in result  # Red color code

    def test_colorize_hunks_cyan(self):
        """Test hunk headers are colored cyan."""
        diff = "@@ -1,3 +1,4 @@"
        result = colorize_diff(diff)
        assert "\033[36m" in result  # Cyan color code

    def test_skips_diff_headers(self):
        """Test that diff header lines (--- and +++) are skipped."""
        diff = "--- a/file.txt\n+++ b/file.txt"
        result = colorize_diff(diff)
        assert "---" not in result
        assert "+++" not in result

    def test_preserves_context_lines(self):
        """Test that context lines are preserved unchanged."""
        diff = "  This is a context line"
        result = colorize_diff(diff)
        assert "This is a context line" in result
        assert "\033[" not in result  # No color codes

    def test_empty_diff(self):
        """Test handling empty diff."""
        result = colorize_diff("")
        assert result == ""

    def test_multiline_diff(self):
        """Test handling multiline diff."""
        diff = """@@ -1,3 +1,4 @@
+Added line
-Deleted line
  Context line"""
        result = colorize_diff(diff)
        assert "Added line" in result
        assert "Deleted line" in result
        assert "Context line" in result


class TestGenerateUnifiedDiff:
    """Test generate_unified_diff function."""

    def test_identical_files(self):
        """Test diff of identical files returns success."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f1:
            f1.write("same content")
            path1 = f1.name

        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f2:
            f2.write("same content")
            path2 = f2.name

        try:
            with patch('aicoder.utils.diff_utils.execute_command_sync') as mock:
                mock.return_value = MockShellResult(success=True, exit_code=0, stdout="", stderr="")
                result = generate_unified_diff(path1, path2)
                assert "No changes" in result or mock.called
        finally:
            os.unlink(path1)
            os.unlink(path2)

    def test_different_files(self):
        """Test diff of different files."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f1:
            f1.write("old content")
            path1 = f1.name

        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f2:
            f2.write("new content")
            path2 = f2.name

        try:
            with patch('aicoder.utils.diff_utils.execute_command_sync') as mock:
                mock.return_value = MockShellResult(
                    success=False, exit_code=1,
                    stdout="--- a/file.txt\n+++ b/file.txt\n@@ -1 +1 @@\n-old content\n+new content\n",
                    stderr=""
                )
                result = generate_unified_diff(path1, path2)
                assert mock.called
        finally:
            os.unlink(path1)
            os.unlink(path2)


class TestGenerateUnifiedDiffWithStatus:
    """Test generate_unified_diff_with_status function."""

    def test_no_changes(self):
        """Test diff with no changes returns has_changes=False."""
        with patch('aicoder.utils.diff_utils.execute_command_sync') as mock:
            mock.return_value = MockShellResult(success=True, exit_code=0, stdout="No changes", stderr="")
            result = generate_unified_diff_with_status("/path1", "/path2")
            assert result["has_changes"] is False
            assert result["exit_code"] == 0

    def test_with_changes(self):
        """Test diff with changes returns has_changes=True."""
        with patch('aicoder.utils.diff_utils.execute_command_sync') as mock:
            mock.return_value = MockShellResult(
                success=False, exit_code=1,
                stdout="--- a/file.txt\n+++ b/file.txt\n@@ -1 +1 @@\n-old\n+new\n",
                stderr=""
            )
            result = generate_unified_diff_with_status("/path1", "/path2")
            assert result["has_changes"] is True
            assert result["exit_code"] == 1

    def test_error_in_diff(self):
        """Test diff with error returns has_changes=False."""
        with patch('aicoder.utils.diff_utils.execute_command_sync') as mock:
            mock.return_value = MockShellResult(
                success=False, exit_code=2,
                stdout="",
                stderr="diff: /path: No such file or directory"
            )
            result = generate_unified_diff_with_status("/path1", "/path2")
            assert result["has_changes"] is False
            assert result["exit_code"] == 2
            assert "Error" in result["diff"]
