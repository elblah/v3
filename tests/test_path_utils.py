"""Tests for path_utils module"""

import pytest
from aicoder.utils import path_utils


class TestIsSafePath:
    """Tests for is_safe_path function"""

    def test_safe_relative_path(self):
        """Test that simple relative paths are safe"""
        assert path_utils.is_safe_path("file.txt") is True
        assert path_utils.is_safe_path("dir/file.txt") is True
        assert path_utils.is_safe_path("dir/subdir/file.txt") is True

    def test_unsafe_parent_traversal(self):
        """Test that parent directory traversal is detected (returns False)"""
        # is_safe_path returns False when "../" is in the path (unsafe)
        assert path_utils.is_safe_path("../file.txt") is False
        assert path_utils.is_safe_path("../") is False
        assert path_utils.is_safe_path("../dir/file.txt") is False
        assert path_utils.is_safe_path("dir/../file.txt") is False
        assert path_utils.is_safe_path("dir/../../file.txt") is False

    def test_edge_cases(self):
        """Test edge cases"""
        assert path_utils.is_safe_path("") is True
        assert path_utils.is_safe_path(".") is True


class TestValidatePath:
    """Tests for validate_path function"""

    def test_valid_path_returns_true(self, capsys):
        """Test that valid paths return True"""
        result = path_utils.validate_path("test.txt")
        assert result is True

    def test_invalid_path_returns_false(self, capsys):
        """Test that invalid paths return False"""
        result = path_utils.validate_path("../file.txt")
        assert result is False


class TestValidateToolPath:
    """Tests for validate_tool_path function"""

    def test_valid_tool_path_returns_true(self, capsys):
        """Test that valid tool paths return True"""
        result = path_utils.validate_tool_path("test.txt", "test_tool")
        assert result is True

    def test_invalid_tool_path_returns_false(self, capsys):
        """Test that invalid tool paths return False"""
        result = path_utils.validate_tool_path("../file.txt", "test_tool")
        assert result is False
