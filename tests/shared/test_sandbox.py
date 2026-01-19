"""
Shared tests for sandbox behavior across all tools.

These tests verify that the sandbox mechanism works consistently
for all file operations (read, write, edit, list, grep).
"""

import os
import pytest
from unittest.mock import patch


# Tool modules to test
SANDBOX_MODULES = [
    "aicoder.tools.internal.read_file",
    "aicoder.tools.internal.write_file",
    "aicoder.tools.internal.edit_file",
    "aicoder.tools.internal.list_directory",
]


class TestSandboxBehavior:
    """Test sandbox enforcement across all tools."""

    @pytest.fixture(params=SANDBOX_MODULES)
    def tool_module(self, request):
        """Dynamically import tool module."""
        return __import__(request.param, fromlist=[''])

    def test_sandbox_disabled(self, tool_module):
        """Test when sandbox is disabled."""
        module_name = tool_module.__name__
        with patch(f'{module_name}.Config') as mock_config:
            mock_config.sandbox_disabled.return_value = True
            result = tool_module._check_sandbox("/some/path", print_message=False)
            assert result is True

    def test_empty_path(self, tool_module):
        """Test empty path returns True."""
        module_name = tool_module.__name__
        with patch(f'{module_name}.Config') as mock_config:
            mock_config.sandbox_disabled.return_value = False
            result = tool_module._check_sandbox("", print_message=False)
            assert result is True

    def test_path_within_current_dir(self, tool_module):
        """Test path within current directory."""
        module_name = tool_module.__name__
        with patch(f'{module_name}.Config') as mock_config:
            mock_config.sandbox_disabled.return_value = False
            with patch('os.getcwd', return_value='/home/user/project'):
                result = tool_module._check_sandbox('/home/user/project/file.txt', print_message=False)
                assert result is True

    def test_path_outside_current_dir(self, tool_module):
        """Test path outside current directory."""
        module_name = tool_module.__name__
        with patch(f'{module_name}.Config') as mock_config:
            mock_config.sandbox_disabled.return_value = False
            with patch('os.getcwd', return_value='/home/user/project'):
                result = tool_module._check_sandbox('/etc/passwd', print_message=False)
                assert result is False

    def test_path_equal_to_current_dir(self, tool_module):
        """Test path equal to current directory."""
        module_name = tool_module.__name__
        with patch(f'{module_name}.Config') as mock_config:
            mock_config.sandbox_disabled.return_value = False
            with patch('os.getcwd', return_value='/home/user/project'):
                result = tool_module._check_sandbox('/home/user/project', print_message=False)
                assert result is True

    def test_subdirectory_allowed(self, tool_module):
        """Test subdirectory of current is allowed."""
        module_name = tool_module.__name__
        with patch(f'{module_name}.Config') as mock_config:
            mock_config.sandbox_disabled.return_value = False
            with patch('os.getcwd', return_value='/home/user/project'):
                result = tool_module._check_sandbox('/home/user/project/subdir/file.txt', print_message=False)
                assert result is True

    def test_deeply_nested_subdirectory_allowed(self, tool_module):
        """Test deeply nested subdirectory is allowed."""
        module_name = tool_module.__name__
        with patch(f'{module_name}.Config') as mock_config:
            mock_config.sandbox_disabled.return_value = False
            with patch('os.getcwd', return_value='/home/user/project'):
                result = tool_module._check_sandbox('/home/user/project/a/b/c/file.txt', print_message=False)
                assert result is True

    def test_parent_directory_denied(self, tool_module):
        """Test parent directory is denied."""
        module_name = tool_module.__name__
        with patch(f'{module_name}.Config') as mock_config:
            mock_config.sandbox_disabled.return_value = False
            with patch('os.getcwd', return_value='/home/user/project'):
                result = tool_module._check_sandbox('/home/user', print_message=False)
                assert result is False

    def test_path_traversal_denied(self, tool_module):
        """Test path traversal using ../ is denied."""
        module_name = tool_module.__name__
        with patch(f'{module_name}.Config') as mock_config:
            mock_config.sandbox_disabled.return_value = False
            with patch('os.getcwd', return_value='/home/user/project'):
                # Even after resolution, should be outside
                result = tool_module._check_sandbox('/home/user/project/../outside', print_message=False)
                assert result is False
