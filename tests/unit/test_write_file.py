"""Unit tests for write_file tool"""

import pytest
from unittest.mock import MagicMock, patch
import os
import tempfile
from aicoder.tools.internal.write_file import (
    execute,
    generate_preview,
    format_arguments,
    validate_arguments,
    _check_sandbox,
    set_plugin_system,
    file_read,
)
from aicoder.core.file_access_tracker import FileAccessTracker


@pytest.fixture
def temp_file():
    """Create a temporary file for testing"""
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write("Original content\nLine 2\nLine 3")
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


class TestCheckSandbox:
    """Test _check_sandbox function"""

    def test_sandbox_disabled(self):
        """Test when sandbox is disabled"""
        with patch('aicoder.tools.internal.write_file.Config') as mock_config:
            mock_config.sandbox_disabled.return_value = True
            result = _check_sandbox("/some/path", print_message=False)
            assert result is True

    def test_empty_path(self):
        """Test empty path returns True"""
        with patch('aicoder.tools.internal.write_file.Config') as mock_config:
            mock_config.sandbox_disabled.return_value = False
            result = _check_sandbox("", print_message=False)
            assert result is True

    def test_path_within_current_dir(self):
        """Test path within current directory"""
        with patch('aicoder.tools.internal.write_file.Config') as mock_config:
            mock_config.sandbox_disabled.return_value = False
            with patch('os.getcwd', return_value='/home/user/project'):
                result = _check_sandbox('/home/user/project/file.txt', print_message=False)
                assert result is True

    def test_path_outside_current_dir(self):
        """Test path outside current directory"""
        with patch('aicoder.tools.internal.write_file.Config') as mock_config:
            mock_config.sandbox_disabled.return_value = False
            with patch('os.getcwd', return_value='/home/user/project'):
                result = _check_sandbox('/etc/passwd', print_message=False)
                assert result is False


class TestFileRead:
    """Test file_read helper function"""

    def test_reads_file_content(self, temp_file):
        """Test reading file content"""
        content = file_read(temp_file)
        assert "Original content" in content

    def test_read_empty_file(self):
        """Test reading empty file"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            path = f.name

        try:
            content = file_read(path)
            assert content == ""
        finally:
            os.unlink(path)


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
            execute({"content": "test"})
        assert "Path is required" in str(excinfo.value)

    def test_new_file_success(self, clean_file_access_tracker):
        """Test creating a new file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            new_file = os.path.join(tmpdir, "new_file.txt")
            with patch('aicoder.tools.internal.write_file._check_sandbox', return_value=True):
                with patch('aicoder.tools.internal.write_file.file_write') as mock_write:
                    result = execute({
                        "path": new_file,
                        "content": "New content"
                    })
                    assert result["tool"] == "write_file"
                    assert "Created" in result["friendly"]
                    assert mock_write.called

    def test_existing_file_update(self, temp_file, clean_file_access_tracker):
        """Test updating an existing file"""
        FileAccessTracker.record_read(temp_file)
        with patch('aicoder.tools.internal.write_file._check_sandbox', return_value=True):
            with patch('aicoder.tools.internal.write_file.file_write') as mock_write:
                result = execute({
                    "path": temp_file,
                    "content": "Updated content"
                })
                assert result["tool"] == "write_file"
                assert "Updated" in result["friendly"]
                assert mock_write.called

    def test_sandbox_violation(self, clean_file_access_tracker):
        """Test sandbox violation is caught"""
        with patch('aicoder.tools.internal.write_file._check_sandbox', return_value=False):
            with patch('os.getcwd', return_value='/home/user/project'):
                with pytest.raises(Exception) as excinfo:
                    execute({
                        "path": "/etc/passwd",
                        "content": "Malicious"
                    })
                assert "Sandbox" in str(excinfo.value)


class TestGeneratePreview:
    """Test generate_preview function"""

    def setup_method(self):
        """Setup for each test"""
        FileAccessTracker.clear_state()

    def teardown_method(self):
        """Cleanup after each test"""
        FileAccessTracker.clear_state()

    def test_new_file_preview(self, clean_file_access_tracker):
        """Test preview for new file"""
        with tempfile.TemporaryDirectory() as tmpdir:
            new_file = os.path.join(tmpdir, "new_file.txt")
            result = generate_preview({
                "path": new_file,
                "content": "New content"
            })
            assert result["tool"] == "write_file"
            assert result["can_approve"] is True
            assert "New file" in result["content"]

    def test_existing_file_not_read_first(self, temp_file):
        """Test preview when file exists but wasn't read"""
        result = generate_preview({
            "path": temp_file,
            "content": "Updated content"
        })
        assert result["tool"] == "write_file"
        assert result["can_approve"] is False
        assert "Warning" in result["content"] or "read" in result["content"].lower()

    def test_existing_file_read_first(self, temp_file):
        """Test preview when file was read first"""
        FileAccessTracker.record_read(temp_file)
        result = generate_preview({
            "path": temp_file,
            "content": "Updated content"
        })
        assert result["tool"] == "write_file"
        assert result["can_approve"] is True
        assert "update" in result["content"].lower() or "Existing" in result["content"]

    def test_no_changes_detected(self, temp_file):
        """Test when no changes are detected"""
        FileAccessTracker.record_read(temp_file)
        result = generate_preview({
            "path": temp_file,
            "content": "Original content\nLine 2\nLine 3"  # Same as original
        })
        assert result["tool"] == "write_file"
        assert result["can_approve"] is False


class TestFormatArguments:
    """Test format_arguments function"""

    def test_basic_formatting(self):
        """Test basic argument formatting"""
        result = format_arguments({
            "path": "/path/to/file.txt",
            "content": "test content"
        })
        assert "/path/to/file.txt" in result
        assert "test content" in result

    def test_truncates_long_content(self):
        """Test that long content is truncated"""
        long_content = "a" * 150
        result = format_arguments({
            "path": "/path/to/file.txt",
            "content": long_content
        })
        assert "..." in result
        assert f"({len(long_content)} chars total)" in result

    def test_empty_content(self):
        """Test formatting with empty content"""
        result = format_arguments({
            "path": "/path/to/file.txt",
            "content": ""
        })
        assert "/path/to/file.txt" in result


class TestValidateArguments:
    """Test validate_arguments function"""

    def test_valid_arguments(self):
        """Test with valid arguments"""
        # Should not raise
        validate_arguments({
            "path": "/path/to/file.txt",
            "content": "test"
        })

    def test_missing_path(self):
        """Test with missing path"""
        with pytest.raises(Exception) as excinfo:
            validate_arguments({"content": "test"})
        assert 'path' in str(excinfo.value).lower()

    def test_invalid_path_type(self):
        """Test with invalid path type"""
        with pytest.raises(Exception) as excinfo:
            validate_arguments({"path": 123, "content": "test"})
        assert 'path' in str(excinfo.value).lower()

    def test_none_content(self):
        """Test with None content"""
        # None content is NOT allowed - it raises exception
        with pytest.raises(Exception) as excinfo:
            validate_arguments({"path": "/path/to/file.txt", "content": None})
        assert 'content' in str(excinfo.value).lower()

    def test_missing_content(self):
        """Test with missing content"""
        # Missing content raises exception
        with pytest.raises(Exception) as excinfo:
            validate_arguments({"path": "/path/to/file.txt"})
        assert 'content' in str(excinfo.value).lower()


class TestSetPluginSystem:
    """Test set_plugin_system function"""

    def test_set_plugin_system(self):
        """Test setting plugin system"""
        mock_plugin_system = MagicMock()
        set_plugin_system(mock_plugin_system)
        from aicoder.tools.internal.write_file import _plugin_system
        assert _plugin_system is mock_plugin_system

    def test_set_plugin_system_none(self):
        """Test setting plugin system to None"""
        set_plugin_system(None)
        from aicoder.tools.internal.write_file import _plugin_system
        assert _plugin_system is None


class TestExecuteWithPluginHooks:
    """Test execute function with plugin hooks"""

    def setup_method(self):
        """Setup for each test"""
        FileAccessTracker.clear_state()
        set_plugin_system(None)

    def teardown_method(self):
        """Cleanup after each test"""
        FileAccessTracker.clear_state()
        set_plugin_system(None)

    def test_plugin_hook_before_write(self, clean_file_access_tracker):
        """Test plugin hook is called before file write"""
        with tempfile.TemporaryDirectory() as tmpdir:
            new_file = os.path.join(tmpdir, "new_file.txt")

            mock_plugin_system = MagicMock()
            mock_plugin_system.call_hooks.return_value = None
            set_plugin_system(mock_plugin_system)

            with patch('aicoder.tools.internal.write_file._check_sandbox', return_value=True):
                with patch('aicoder.tools.internal.write_file.file_write') as mock_write:
                    execute({
                        "path": new_file,
                        "content": "Original content"
                    })

            # Verify before_file_write hook was called
            mock_plugin_system.call_hooks.assert_any_call("before_file_write", new_file, "Original content")

    def test_plugin_hook_modifies_content(self, clean_file_access_tracker):
        """Test plugin hook can modify content"""
        with tempfile.TemporaryDirectory() as tmpdir:
            new_file = os.path.join(tmpdir, "new_file.txt")

            mock_plugin_system = MagicMock()
            # Plugin returns modified content
            mock_plugin_system.call_hooks.return_value = ["Modified by plugin"]
            set_plugin_system(mock_plugin_system)

            with patch('aicoder.tools.internal.write_file._check_sandbox', return_value=True):
                with patch('aicoder.tools.internal.write_file.file_write') as mock_write:
                    execute({
                        "path": new_file,
                        "content": "Original content"
                    })

            # Verify file_write was called with modified content
            args, kwargs = mock_write.call_args
            assert args[1] == "Modified by plugin"


class TestExecuteErrorHandling:
    """Test execute function error handling"""

    def setup_method(self):
        """Setup for each test"""
        FileAccessTracker.clear_state()

    def teardown_method(self):
        """Cleanup after each test"""
        FileAccessTracker.clear_state()

    def test_write_error_returns_friendly_message(self, clean_file_access_tracker):
        """Test that write errors return friendly message"""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a directory instead of file to cause write error
            dir_path = os.path.join(tmpdir, "test_dir")
            os.makedirs(dir_path)

            with patch('aicoder.tools.internal.write_file._check_sandbox', return_value=True):
                result = execute({
                    "path": dir_path,
                    "content": "Cannot write to directory"
                })

                assert result["tool"] == "write_file"
                assert "Error" in result["friendly"]
                assert "❌" in result["friendly"]


class TestGeneratePreviewErrorHandling:
    """Test generate_preview error handling"""

    def test_invalid_json_in_diff(self, clean_file_access_tracker):
        """Test handling invalid diff result"""
        with tempfile.TemporaryDirectory() as tmpdir:
            new_file = os.path.join(tmpdir, "new_file.txt")

            with patch('aicoder.tools.internal.write_file.generate_unified_diff_with_status') as mock_diff:
                mock_diff.return_value = {"diff": "", "has_changes": False}
                result = generate_preview({
                    "path": new_file,
                    "content": "New content"
                })

                assert result["tool"] == "write_file"
                assert result["can_approve"] is False
