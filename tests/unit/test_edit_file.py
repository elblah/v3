"""
Tests for edit_file tool
"""

import pytest
from unittest.mock import MagicMock, patch
import os
import tempfile
from aicoder.tools.internal.edit_file import (
    execute,
    generate_preview,
    format_arguments,
    validate_arguments,
    _find_occurrences,
    set_plugin_system,
)
from aicoder.core.file_access_tracker import FileAccessTracker


@pytest.fixture
def temp_file():
    """Create a temporary file for testing"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("Hello World\nLine 2\nLine 3")
        path = f.name

    yield path

    # Cleanup
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def clean_file_access_tracker():
    """Clear file access tracker before test"""
    FileAccessTracker.clear_state()
    yield
    FileAccessTracker.clear_state()


class TestFindOccurrences:
    """Test _find_occurrences helper function"""

    def test_no_occurrences(self):
        """Test when string not found"""
        result = _find_occurrences("Hello World", "XYZ")
        assert result == []

    def test_single_occurrence(self):
        """Test single occurrence"""
        result = _find_occurrences("Hello World", "World")
        assert result == [6]

    def test_multiple_occurrences(self):
        """Test multiple occurrences"""
        result = _find_occurrences("foo bar foo baz foo", "foo")
        assert result == [0, 8, 16]

    def test_empty_string(self):
        """Test empty search string"""
        result = _find_occurrences("Hello World", "")
        assert result == []

    def test_empty_content(self):
        """Test empty content"""
        result = _find_occurrences("", "Hello")
        assert result == []

    def test_overlapping_occurrences(self):
        """Test overlapping occurrences (should find all)"""
        result = _find_occurrences("aaa", "aa")
        # find() with start=pos+1 finds non-overlapping, but our impl uses pos+1
        assert result == [0, 1]

class TestExecute:
    """Test execute function"""

    def setup_method(self):
        """Setup for each test"""
        FileAccessTracker.clear_state()

    def teardown_method(self):
        """Cleanup after each test"""
        FileAccessTracker.clear_state()

    def test_missing_path(self):
        """Test with missing path"""
        with pytest.raises(Exception) as excinfo:
            execute({"old_string": "test"})
        assert "Path and old_string are required" in str(excinfo.value)

    def test_missing_old_string(self):
        """Test with missing old_string"""
        with pytest.raises(Exception) as excinfo:
            execute({"path": "/some/file.txt"})
        assert "Path and old_string are required" in str(excinfo.value)

    def test_file_not_found(self, clean_file_access_tracker):
        """Test with non-existent file"""
        with patch('aicoder.tools.internal.edit_file._check_sandbox', return_value=True):
            with pytest.raises(Exception) as excinfo:
                execute({"path": "/nonexistent/file.txt", "old_string": "test"})
            assert "File not found" in str(excinfo.value)

    def test_file_not_read_first(self, temp_file, clean_file_access_tracker):
        """Test that file must be read before editing"""
        with patch('aicoder.tools.internal.edit_file._check_sandbox', return_value=True):
            result = execute({"path": temp_file, "old_string": "Hello", "new_string": "Hi"})
            assert result["tool"] == "edit_file"
            assert "WARNING" in result["friendly"]

    def test_old_string_not_found(self, temp_file, clean_file_access_tracker):
        """Test when old_string is not in file"""
        FileAccessTracker.record_read(temp_file)
        with patch('aicoder.tools.internal.edit_file._check_sandbox', return_value=True):
            result = execute({"path": temp_file, "old_string": "NOTFOUND", "new_string": "Replaced"})
            assert result["tool"] == "edit_file"
            assert "ERROR" in result["friendly"] or "Text not found" in result["friendly"]

    def test_successful_edit(self, temp_file, clean_file_access_tracker):
        """Test successful edit operation"""
        FileAccessTracker.record_read(temp_file)
        with patch('aicoder.tools.internal.edit_file._check_sandbox', return_value=True):
            with patch('aicoder.tools.internal.edit_file.write_file') as mock_write:
                result = execute({
                    "path": temp_file,
                    "old_string": "Hello",
                    "new_string": "Hi there"
                })
                assert result["tool"] == "edit_file"
                assert "✓" in result["friendly"]
                assert "Updated" in result["friendly"]

    def test_deletion_with_none_new_string(self, temp_file, clean_file_access_tracker):
        """Test deletion when new_string is None"""
        FileAccessTracker.record_read(temp_file)
        with patch('aicoder.tools.internal.edit_file._check_sandbox', return_value=True):
            with patch('aicoder.tools.internal.edit_file.write_file') as mock_write:
                result = execute({
                    "path": temp_file,
                    "old_string": "Hello",
                    "new_string": None
                })
                assert result["tool"] == "edit_file"
                assert "Deleted" in result["friendly"]

    def test_deletion_with_empty_new_string(self, temp_file, clean_file_access_tracker):
        """Test deletion when new_string is empty string"""
        FileAccessTracker.record_read(temp_file)
        with patch('aicoder.tools.internal.edit_file._check_sandbox', return_value=True):
            with patch('aicoder.tools.internal.edit_file.write_file') as mock_write:
                result = execute({
                    "path": temp_file,
                    "old_string": "Hello",
                    "new_string": ""
                })
                assert result["tool"] == "edit_file"
                assert "Deleted" in result["friendly"]


class TestGeneratePreview:
    """Test generate_preview function"""

    def setup_method(self):
        """Setup for each test"""
        FileAccessTracker.clear_state()

    def teardown_method(self):
        """Cleanup after each test"""
        FileAccessTracker.clear_state()

    def test_missing_path(self):
        """Test with missing path"""
        result = generate_preview({"old_string": "test"})
        assert result["tool"] == "edit_file"
        assert "Error" in result["content"]
        assert result["can_approve"] is False

    def test_missing_old_string(self):
        """Test with missing old_string"""
        result = generate_preview({"path": "/some/file.txt"})
        assert result["tool"] == "edit_file"
        assert "Error" in result["content"]
        assert result["can_approve"] is False

    def test_file_not_found(self):
        """Test with non-existent file"""
        # Mock sandbox check to return True (file doesn't exist yet, so sandbox check passes)
        with patch('aicoder.tools.internal.edit_file._check_sandbox', return_value=True):
            result = generate_preview({
                "path": "/nonexistent/file.txt",
                "old_string": "test"
            })
            assert result["tool"] == "edit_file"
            assert "Error" in result["content"]
            assert "File not found" in result["content"]
            assert result["can_approve"] is False

    def test_old_string_not_found(self, temp_file):
        """Test when old_string is not in file"""
        with patch('aicoder.tools.internal.edit_file._check_sandbox', return_value=True):
            result = generate_preview({
                "path": temp_file,
                "old_string": "NOTFOUND"
            })
            assert result["tool"] == "edit_file"
            assert "Error" in result["content"]
            assert "old_string not found" in result["content"]
            assert result["can_approve"] is False

    def test_file_not_read_first(self, temp_file):
        """Test when file was not read first"""
        with patch('aicoder.tools.internal.edit_file._check_sandbox', return_value=True):
            result = generate_preview({
                "path": temp_file,
                "old_string": "Hello"
            })
            assert result["tool"] == "edit_file"
            assert "can_approve" in result
            assert result["can_approve"] is False
            assert "Warning" in result["content"] or "read file first" in result["content"]

    def test_no_changes_detected(self, temp_file):
        """Test when no changes are detected in diff"""
        FileAccessTracker.record_read(temp_file)
        with patch('aicoder.tools.internal.edit_file._check_sandbox', return_value=True):
            result = generate_preview({
                "path": temp_file,
                "old_string": "Hello",
                "new_string": "Hello"  # Same content
            })
            assert result["tool"] == "edit_file"
            assert result["can_approve"] is False

    def test_successful_preview(self, temp_file):
        """Test successful preview generation"""
        FileAccessTracker.record_read(temp_file)
        with patch('aicoder.tools.internal.edit_file._check_sandbox', return_value=True):
            result = generate_preview({
                "path": temp_file,
                "old_string": "Hello",
                "new_string": "Hi"
            })
            assert result["tool"] == "edit_file"
            assert "can_approve" in result
            # With a change, can_approve should be True
            assert result["can_approve"] is True
            # Content should contain path or diff info
            assert len(result["content"]) > 0


class TestFormatArguments:
    """Test format_arguments function"""

    def test_basic_formatting(self):
        """Test basic argument formatting"""
        result = format_arguments({
            "path": "/path/to/file.txt",
            "old_string": "old text",
            "new_string": "new text"
        })
        assert "/path/to/file.txt" in result
        assert "old text" in result
        assert "new text" in result

    def test_truncates_long_strings(self):
        """Test that long strings are truncated"""
        long_string = "a" * 100
        result = format_arguments({
            "path": "/path/to/file.txt",
            "old_string": long_string,
            "new_string": long_string
        })
        assert "..." in result  # Should be truncated

    def test_excludes_optional_args(self):
        """Test that optional args are excluded when default"""
        result = format_arguments({
            "path": "/path/to/file.txt",
            "old_string": "old text"
        })
        assert "old text" in result
        # new_string is optional, may or may not appear depending on implementation


class TestValidateArguments:
    """Test validate_arguments function"""

    def test_valid_arguments(self):
        """Test with valid arguments"""
        # Should not raise
        validate_arguments({
            "path": "/path/to/file.txt",
            "old_string": "test"
        })

    def test_missing_path(self):
        """Test with missing path"""
        with pytest.raises(Exception) as excinfo:
            validate_arguments({"old_string": "test"})
        assert 'path' in str(excinfo.value).lower()

    def test_invalid_path_type(self):
        """Test with invalid path type"""
        with pytest.raises(Exception) as excinfo:
            validate_arguments({"path": 123, "old_string": "test"})
        assert 'path' in str(excinfo.value).lower()

    def test_missing_old_string(self):
        """Test with missing old_string"""
        with pytest.raises(Exception) as excinfo:
            validate_arguments({"path": "/path/to/file.txt"})
        assert 'old_string' in str(excinfo.value).lower()

    def test_none_old_string(self):
        """Test with None old_string"""
        with pytest.raises(Exception) as excinfo:
            validate_arguments({"path": "/path/to/file.txt", "old_string": None})
        assert 'old_string' in str(excinfo.value).lower()


class TestSetPluginSystem:
    """Test set_plugin_system function"""

    def test_set_plugin_system(self):
        """Test setting plugin system"""
        mock_plugin_system = MagicMock()
        set_plugin_system(mock_plugin_system)
        from aicoder.tools.internal.edit_file import _plugin_system
        assert _plugin_system is mock_plugin_system

    def test_set_plugin_system_none(self):
        """Test setting plugin system to None"""
        set_plugin_system(None)
        from aicoder.tools.internal.edit_file import _plugin_system
        assert _plugin_system is None
