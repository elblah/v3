"""Tests for diff utilities module"""

import pytest
import tempfile
import os
from unittest.mock import patch
from aicoder.utils import diff_utils


class TestColorizeDiff:
    """Tests for colorize_diff function"""

    def test_colorize_diff_with_removal_lines(self):
        """Test colorizing diff with removal lines (starting with -)"""
        diff_output = "-line1\n-line2\n+line3"
        result = diff_utils.colorize_diff(diff_output)
        # Removal lines should be in result (colorized)
        assert "-line1" in result
        assert "-line2" in result
        # Addition lines should also be in result
        assert "+line3" in result

    def test_colorize_diff_with_addition_lines(self):
        """Test colorizing diff with addition lines (starting with +)"""
        diff_output = "-old\n+new"
        result = diff_utils.colorize_diff(diff_output)
        assert "-old" in result
        assert "+new" in result

    def test_colorize_diff_with_hunk_lines(self):
        """Test colorizing diff with hunk lines (starting with @@)"""
        diff_output = "@@ -1,2 +1,3 @@\n context"
        result = diff_utils.colorize_diff(diff_output)
        # Hunk lines should be in result (colorized)
        assert "@@ -1,2 +1,3 @@" in result

    def test_colorize_diff_skips_header_lines(self):
        """Test that colorize_diff skips --- and +++ header lines"""
        diff_output = "--- old.txt\n+++ new.txt\n@@ -1 +1 @@\n-old\n+new"
        result = diff_utils.colorize_diff(diff_output)
        # Header lines should not be in output (they're skipped)
        assert "--- old.txt" not in result
        assert "+++ new.txt" not in result

    def test_colorize_diff_preserves_context_lines(self):
        """Test that context lines (without prefix) are preserved"""
        diff_output = " context line\n-old\n+new"
        result = diff_utils.colorize_diff(diff_output)
        assert "context line" in result

    def test_colorize_diff_empty_input(self):
        """Test colorize_diff with empty input"""
        result = diff_utils.colorize_diff("")
        assert result == ""

    def test_colorize_diff_unicode_content(self):
        """Test colorize_diff with unicode content in diff"""
        diff_output = "-日本語\n+English"
        result = diff_utils.colorize_diff(diff_output)
        assert "日本語" in result
        assert "English" in result


class TestGenerateUnifiedDiff:
    """Tests for generate_unified_diff function"""

    def test_generate_diff_identical_files(self):
        """Test generating diff for identical files"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("same content")
            temp_path = f.name
        try:
            result = diff_utils.generate_unified_diff(temp_path, temp_path)
            assert "No changes" in result or result.strip() == ""
        finally:
            os.unlink(temp_path)

    def test_generate_diff_different_files(self):
        """Test generating diff for different files"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f1:
            f1.write("old content")
            old_path = f1.name
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f2:
            f2.write("new content")
            new_path = f2.name
        try:
            result = diff_utils.generate_unified_diff(old_path, new_path)
            assert result is not None
            # diff output contains the differences
        finally:
            os.unlink(old_path)
            os.unlink(new_path)


class TestGenerateUnifiedDiffWithStatus:
    """Tests for generate_unified_diff_with_status function"""

    def test_diff_no_changes(self):
        """Test generate_unified_diff_with_status for identical files"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("same content")
            temp_path = f.name
        try:
            result = diff_utils.generate_unified_diff_with_status(temp_path, temp_path)
            assert result["has_changes"] is False
            assert result["exit_code"] == 0
        finally:
            os.unlink(temp_path)

    def test_diff_with_changes(self):
        """Test generate_unified_diff_with_status for different files"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f1:
            f1.write("old content")
            old_path = f1.name
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f2:
            f2.write("new content")
            new_path = f2.name
        try:
            result = diff_utils.generate_unified_diff_with_status(old_path, new_path)
            assert result["has_changes"] is True
            assert result["exit_code"] == 1
        finally:
            os.unlink(old_path)
            os.unlink(new_path)

    def test_diff_nonexistent_file(self):
        """Test generate_unified_diff_with_status for nonexistent files"""
        result = diff_utils.generate_unified_diff_with_status(
            "/nonexistent/old.txt",
            "/nonexistent/new.txt"
        )
        # Should return an error result
        assert result["has_changes"] is False
        assert "Error" in result["diff"]
