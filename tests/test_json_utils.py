"""Tests for json_utils module"""

import json
import pytest
from aicoder.utils import json_utils


class TestJsonWriteFile:
    """Tests for write_file function"""

    def test_write_file_creates_valid_json(self, tmp_path):
        """Test that write_file creates valid JSON"""
        path = tmp_path / "test.json"
        data = {"key": "value", "number": 42}
        result = json_utils.write_file(str(path), data)
        assert "Successfully wrote" in result

        # Verify file content
        with open(path, "r") as f:
            content = json.load(f)
        assert content == data

    def test_write_file_nested_structure(self, tmp_path):
        """Test writing nested JSON structure"""
        path = tmp_path / "nested.json"
        data = {"outer": {"inner": [1, 2, 3]}, "nested": True}
        json_utils.write_file(str(path), data)

        with open(path, "r") as f:
            content = json.load(f)
        assert content == data


class TestJsonReadFile:
    """Tests for read_file function"""

    def test_read_file_parses_json(self, tmp_path):
        """Test that read_file correctly parses JSON"""
        path = tmp_path / "read_test.json"
        data = {"test": "data"}
        with open(path, "w") as f:
            json.dump(data, f)

        result = json_utils.read_file(str(path))
        assert result == data

    def test_read_file_default_type(self, tmp_path):
        """Test that read_file uses dict as default type hint"""
        path = tmp_path / "default_type.json"
        data = {"key": "value"}
        with open(path, "w") as f:
            json.dump(data, f)

        result = json_utils.read_file(str(path))
        assert isinstance(result, dict)


class TestJsonReadFileSafe:
    """Tests for read_file_safe function"""

    def test_read_file_safe_valid_json(self, tmp_path):
        """Test read_file_safe with valid JSON"""
        path = tmp_path / "valid.json"
        data = {"valid": True}
        with open(path, "w") as f:
            json.dump(data, f)

        result = json_utils.read_file_safe(str(path))
        assert result == data

    def test_read_file_safe_missing_file(self):
        """Test read_file_safe with missing file returns default"""
        result = json_utils.read_file_safe("/nonexistent/path.json")
        assert result is None

    def test_read_file_safe_invalid_json(self, tmp_path):
        """Test read_file_safe with invalid JSON returns default"""
        path = tmp_path / "invalid.json"
        with open(path, "w") as f:
            f.write("not valid json")

        result = json_utils.read_file_safe(str(path), default={})
        assert result == {}

    def test_read_file_safe_custom_default(self):
        """Test read_file_safe with custom default value"""
        result = json_utils.read_file_safe("/nonexistent.json", default="fallback")
        assert result == "fallback"


class TestJsonIsValid:
    """Tests for is_valid function"""

    def test_is_valid_valid_json(self):
        """Test is_valid with valid JSON string"""
        valid_json = '{"key": "value"}'
        assert json_utils.is_valid(valid_json) is True

    def test_is_valid_array(self):
        """Test is_valid with valid JSON array"""
        valid_json = '[1, 2, 3, "test"]'
        assert json_utils.is_valid(valid_json) is True

    def test_is_valid_invalid_json(self):
        """Test is_valid with invalid JSON string"""
        invalid_json = '{invalid: json}'
        assert json_utils.is_valid(invalid_json) is False

    def test_is_valid_empty_string(self):
        """Test is_valid with empty string"""
        assert json_utils.is_valid("") is False


class TestJsonParseSafe:
    """Tests for parse_safe function"""

    def test_parse_safe_valid_json(self):
        """Test parse_safe with valid JSON"""
        json_str = '{"key": "value"}'
        result = json_utils.parse_safe(json_str)
        assert result == {"key": "value"}

    def test_parse_safe_invalid_json(self):
        """Test parse_safe with invalid JSON returns default (None)"""
        result = json_utils.parse_safe("invalid")
        assert result is None

    def test_parse_safe_custom_default(self):
        """Test parse_safe with custom default"""
        result = json_utils.parse_safe("invalid", default={"default": True})
        assert result == {"default": True}
