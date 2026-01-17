"""
Tests for path utilities
"""

import pytest


class TestPathUtils:
    """Test path utility functions"""

    def test_is_safe_path_simple(self):
        """Test simple safe paths"""
        from aicoder.utils.path_utils import is_safe_path

        assert is_safe_path("file.txt") is True
        assert is_safe_path("path/to/file.txt") is True
        assert is_safe_path("/absolute/path.txt") is True

    def test_is_safe_path_traversal_attempt(self):
        """Test paths with parent directory traversal"""
        from aicoder.utils.path_utils import is_safe_path

        # These paths DO contain parent traversal patterns
        # The function checks for "../" in the path
        assert is_safe_path("../file.txt") is False
        assert is_safe_path("../etc/passwd") is False
        assert is_safe_path("path/../../etc/passwd") is False

    def test_validate_path_safe(self):
        """Test validation of safe paths"""
        from aicoder.utils.path_utils import validate_path

        # Safe paths should return True
        assert validate_path("file.txt") is True
        assert validate_path("path/to/file.txt") is True

    def test_validate_path_unsafe(self):
        """Test validation of unsafe paths (with traversal)"""
        from aicoder.utils.path_utils import validate_path

        # The function prints a warning but still returns False
        assert validate_path("../file.txt") is False
        assert validate_path("path/../../etc/passwd") is False

    def test_validate_tool_path_safe(self):
        """Test tool path validation for safe paths"""
        from aicoder.utils.path_utils import validate_tool_path

        assert validate_tool_path("file.txt", "mytool") is True
        assert validate_tool_path("path/to/file.txt", "mytool") is True

    def test_validate_tool_path_unsafe(self):
        """Test tool path validation for unsafe paths"""
        from aicoder.utils.path_utils import validate_tool_path

        assert validate_tool_path("../file.txt", "mytool") is False
        assert validate_tool_path("path/../../etc/passwd", "mytool") is False
