"""Unit tests for JSON utilities."""

import json
import tempfile
import os
import pytest
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, '/home/blah/storage/ai-worktree-storage/feat_test_coverage__20260117_062928')

from aicoder.utils.json_utils import (
    write_file,
    read_file,
    read_file_safe,
    is_valid,
    parse_safe
)


class TestIsValid:
    """Test is_valid function."""

    def test_valid_json_object(self):
        """Test valid JSON object returns True."""
        assert is_valid('{"key": "value"}') is True

    def test_valid_json_array(self):
        """Test valid JSON array returns True."""
        assert is_valid('[1, 2, 3]') is True

    def test_valid_json_string(self):
        """Test valid JSON string returns True."""
        assert is_valid('"hello"') is True

    def test_valid_json_number(self):
        """Test valid JSON number returns True."""
        assert is_valid('42') is True

    def test_valid_json_boolean(self):
        """Test valid JSON boolean returns True."""
        assert is_valid('true') is True
        assert is_valid('false') is True

    def test_valid_json_null(self):
        """Test valid JSON null returns True."""
        assert is_valid('null') is True

    def test_invalid_json_missing_brace(self):
        """Test invalid JSON with missing brace returns False."""
        assert is_valid('{"key": "value"') is False

    def test_invalid_json_trailing_comma(self):
        """Test invalid JSON with trailing comma returns False."""
        assert is_valid('{"key": "value",}') is False

    def test_invalid_json_text(self):
        """Test invalid JSON plain text returns False."""
        assert is_valid('not json') is False

    def test_invalid_json_empty(self):
        """Test empty string returns False."""
        assert is_valid('') is False


class TestParseSafe:
    """Test parse_safe function."""

    def test_parse_valid_json(self):
        """Test parsing valid JSON returns parsed object."""
        result = parse_safe('{"key": "value"}')
        assert result == {"key": "value"}

    def test_parse_valid_array(self):
        """Test parsing valid JSON array."""
        result = parse_safe('[1, 2, 3]')
        assert result == [1, 2, 3]

    def test_parse_invalid_returns_default(self):
        """Test invalid JSON returns default (None)."""
        result = parse_safe('invalid')
        assert result is None

    def test_parse_invalid_with_custom_default(self):
        """Test invalid JSON with custom default."""
        result = parse_safe('invalid', default={"error": True})
        assert result == {"error": True}

    def test_parse_empty_returns_default(self):
        """Test empty string returns default."""
        result = parse_safe('')
        assert result is None


class TestReadFileSafe:
    """Test read_file_safe function."""

    def test_read_valid_json_file(self):
        """Test reading valid JSON file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"key": "value"}, f)
            path = f.name

        try:
            result = read_file_safe(path)
            assert result == {"key": "value"}
        finally:
            os.unlink(path)

    def test_read_nonexistent_file_returns_default(self):
        """Test reading nonexistent file returns default."""
        result = read_file_safe("/nonexistent/path.json")
        assert result is None

    def test_read_nonexistent_with_custom_default(self):
        """Test nonexistent file with custom default."""
        result = read_file_safe("/nonexistent/path.json", default={"default": True})
        assert result == {"default": True}

    def test_read_invalid_json_returns_default(self):
        """Test reading invalid JSON returns default."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            f.write("not valid json")
            path = f.name

        try:
            result = read_file_safe(path)
            assert result is None
        finally:
            os.unlink(path)


class TestWriteFile:
    """Test write_file function."""

    def test_writes_formatted_json(self):
        """Test writes pretty-printed JSON."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.json")
            write_file(path, {"key": "value", "nested": {"a": 1}})

            with open(path, "r") as f:
                content = f.read()

            # Should be pretty-printed (has indent)
            assert "{\n" in content
            assert '  "key"' in content

    def test_writes_array_formatted(self):
        """Test writes pretty-printed JSON array."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "array.json")
            write_file(path, [1, 2, 3])

            with open(path, "r") as f:
                content = f.read()

            assert "[\n" in content


class TestReadFile:
    """Test read_file function."""

    def test_read_json_file(self):
        """Test reading JSON file returns parsed object."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump({"key": "value"}, f)
            path = f.name

        try:
            result = read_file(path)
            assert result == {"key": "value"}
        finally:
            os.unlink(path)

    def test_read_with_default_type(self):
        """Test reading with custom default type."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            json.dump([1, 2, 3], f)
            path = f.name

        try:
            # read_file always returns the parsed JSON, default_type is just a type hint
            result = read_file(path)
            assert result == [1, 2, 3]
        finally:
            os.unlink(path)
