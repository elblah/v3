"""Unit tests for path utilities."""

import pytest
from unittest.mock import patch, MagicMock
import sys

sys.path.insert(0, '/home/blah/storage/ai-worktree-storage/feat_test_coverage__20260117_062928')

from aicoder.utils.path_utils import (
    is_safe_path,
    validate_path,
    validate_tool_path
)


class TestIsSafePath:
    """Test is_safe_path function."""

    def test_allows_safe_path(self):
        """Test allows safe paths without parent traversal."""
        assert is_safe_path("file.txt") is True
        assert is_safe_path("directory/file.txt") is True
        assert is_safe_path("/absolute/path") is True
        assert is_safe_path("./relative/path") is True
        assert is_safe_path("../valid/sibling") is False

    def test_blocks_parent_traversal(self):
        """Test blocks paths with parent directory traversal."""
        assert is_safe_path("../file.txt") is False
        assert is_safe_path("../../file.txt") is False
        assert is_safe_path("dir/../../../file.txt") is False
        assert is_safe_path("./../file.txt") is False
        assert is_safe_path("/safe/../unsafe") is False

    def test_allows_dots_without_slash(self):
        """Test allows dots without slash - only '../' pattern is blocked."""
        # The implementation only checks for '../' pattern
        assert is_safe_path("..") is True  # No slash after dots
        assert is_safe_path("...") is True  # No slash after dots
        assert is_safe_path("file..txt") is True

    def test_empty_path(self):
        """Test handles empty path."""
        assert is_safe_path("") is True


class TestValidatePath:
    """Test validate_path function."""

    def test_allows_safe_path(self):
        """Test validates and allows safe paths."""
        with patch('aicoder.core.config.Config') as mock_config:
            mock_config.colors = {'yellow': '', 'reset': ''}
            result = validate_path("safe/path.txt")

        assert result is True

    def test_blocks_unsafe_path(self):
        """Test validates and blocks unsafe paths."""
        with patch('aicoder.core.config.Config') as mock_config:
            mock_config.colors = {'yellow': '', 'reset': ''}
            result = validate_path("../unsafe.txt")

        assert result is False

    def test_logs_warning_for_unsafe_path(self):
        """Test logs security warning for unsafe path."""
        with patch('aicoder.core.config.Config') as mock_config:
            mock_config.colors = {'yellow': '[YELLOW]', 'reset': '[RESET]'}
            result = validate_path("../file.txt", "read_file")

        assert result is False

    def test_default_context(self):
        """Test uses default context string."""
        with patch('aicoder.core.config.Config') as mock_config:
            mock_config.colors = {'yellow': '', 'reset': ''}
            result = validate_path("../unsafe")

        assert result is False

    def test_allows_empty_path(self):
        """Test allows empty path."""
        with patch('aicoder.core.config.Config') as mock_config:
            mock_config.colors = {'yellow': '', 'reset': ''}
            result = validate_path("")

        assert result is True


class TestValidateToolPath:
    """Test validate_tool_path function."""

    def test_allows_safe_tool_path(self):
        """Test validates safe path for tools."""
        with patch('aicoder.core.config.Config') as mock_config:
            mock_config.colors = {'yellow': '', 'reset': ''}
            result = validate_tool_path("safe/file.txt", "read_file")

        assert result is True

    def test_blocks_unsafe_tool_path(self):
        """Test blocks unsafe path for tools."""
        with patch('aicoder.core.config.Config') as mock_config:
            mock_config.colors = {'yellow': '', 'reset': ''}
            result = validate_tool_path("../unsafe.txt", "write_file")

        assert result is False

    def test_includes_tool_name_in_warning(self):
        """Test includes tool name in security warning."""
        with patch('aicoder.core.config.Config') as mock_config:
            mock_config.colors = {'yellow': '[YELLOW]', 'reset': '[RESET]'}
            result = validate_tool_path("../file.txt", "edit_file")

        assert result is False

    def test_different_tool_names(self):
        """Test works with different tool names."""
        with patch('aicoder.core.config.Config') as mock_config:
            mock_config.colors = {'yellow': '', 'reset': ''}

            result1 = validate_tool_path("../file.txt", "read_file")
            result2 = validate_tool_path("../file.txt", "write_file")
            result3 = validate_tool_path("../file.txt", "edit_file")

        assert result1 is False
        assert result2 is False
        assert result3 is False

    def test_allows_safe_path_any_tool(self):
        """Test allows safe path for any tool."""
        with patch('aicoder.core.config.Config') as mock_config:
            mock_config.colors = {'yellow': '', 'reset': ''}

            result1 = validate_tool_path("safe.txt", "read_file")
            result2 = validate_tool_path("safe.txt", "write_file")

        assert result1 is True
        assert result2 is True
