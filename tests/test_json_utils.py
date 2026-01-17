"""
Tests for JSON utilities
"""

import pytest
import tempfile
import os


class TestJsonUtils:
    """Test JSON utility functions"""

    def test_is_valid_json(self):
        """Test validation of valid JSON"""
        from aicoder.utils.json_utils import is_valid

        assert is_valid('{"key": "value"}') is True
        assert is_valid('[1, 2, 3]') is True
        assert is_valid('{"nested": {"key": 1}}') is True

    def test_is_valid_invalid_json(self):
        """Test validation of invalid JSON"""
        from aicoder.utils.json_utils import is_valid

        assert is_valid("not json") is False
        assert is_valid('{"incomplete":') is False
        assert is_valid("") is False

    def test_parse_safe_valid_json(self):
        """Test safe parsing of valid JSON"""
        from aicoder.utils.json_utils import parse_safe

        result = parse_safe('{"key": "value"}')
        assert result == {"key": "value"}

    def test_parse_safe_invalid_json(self):
        """Test safe parsing of invalid JSON with default"""
        from aicoder.utils.json_utils import parse_safe

        result = parse_safe("not json", default={"error": True})
        assert result == {"error": True}

    def test_parse_safe_invalid_json_no_default(self):
        """Test safe parsing of invalid JSON returns None by default"""
        from aicoder.utils.json_utils import parse_safe

        result = parse_safe("not json")
        assert result is None

    def test_write_and_read_json(self):
        """Test writing and reading JSON files"""
        from aicoder.utils.json_utils import write_file, read_file

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.json")
            data = {"key": "value", "number": 42, "list": [1, 2, 3]}

            result = write_file(path, data)
            assert "Successfully wrote" in result

            # Verify round-trip
            read_data = read_file(path)
            assert read_data == data

    def test_read_file_safe_file_not_found(self):
        """Test safe read when file doesn't exist"""
        from aicoder.utils.json_utils import read_file_safe

        result = read_file_safe("/nonexistent/path/file.json")
        assert result is None

    def test_read_file_safe_default_value(self):
        """Test safe read with custom default"""
        from aicoder.utils.json_utils import read_file_safe

        result = read_file_safe("/nonexistent/path/file.json", default=[])
        assert result == []
