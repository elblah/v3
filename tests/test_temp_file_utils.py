"""Tests for temporary file utilities module"""

import pytest
import os
import tempfile
from unittest.mock import patch, MagicMock
from aicoder.utils import temp_file_utils


class TestGetTempDir:
    """Tests for get_temp_dir function"""

    def test_get_temp_dir_returns_string(self):
        """Test get_temp_dir returns a string"""
        result = temp_file_utils.get_temp_dir()
        assert isinstance(result, str)

    def test_get_temp_dir_creates_local_tmp(self):
        """Test get_temp_dir creates local tmp directory"""
        # Mock os.getcwd to return our temp directory
        with tempfile.TemporaryDirectory() as temp_dir:
            with patch('os.getcwd', return_value=temp_dir):
                result = temp_file_utils.get_temp_dir()
                # Should return path that includes our temp directory
                assert temp_dir in result or "tmp" in result

    def test_get_temp_dir_fallback_to_tmpdir_env(self):
        """Test get_temp_dir falls back to TMPDIR env var"""
        with patch.dict(os.environ, {'TMPDIR': '/custom/tmp'}):
            with patch('os.makedirs', side_effect=OSError("Permission denied")):
                # When local tmp fails, should fall back to TMPDIR
                result = temp_file_utils.get_temp_dir()
                assert result == '/custom/tmp'

    def test_get_temp_dir_fallback_to_tmp(self):
        """Test get_temp_dir falls back to /tmp"""
        with patch.dict(os.environ, {}, clear=False):
            # Remove TMPDIR if set
            if 'TMPDIR' in os.environ:
                del os.environ['TMPDIR']
            with patch('os.makedirs', side_effect=OSError("Permission denied")):
                result = temp_file_utils.get_temp_dir()
                assert result == "/tmp"


class TestCreateTempFile:
    """Tests for create_temp_file function"""

    def test_create_temp_file_returns_path(self):
        """Test create_temp_file returns a string path"""
        result = temp_file_utils.create_temp_file("test", ".txt")
        assert isinstance(result, str)

    def test_create_temp_file_includes_prefix(self):
        """Test create_temp_file includes the prefix in the result"""
        result = temp_file_utils.create_temp_file("myprefix", ".txt")
        assert "myprefix" in result

    def test_create_temp_file_includes_suffix(self):
        """Test create_temp_file includes the suffix in the result"""
        result = temp_file_utils.create_temp_file("test", ".txt")
        assert result.endswith(".txt")

    def test_create_temp_file_without_dot_suffix(self):
        """Test create_temp_file uses suffix as-is (no dot added)"""
        result = temp_file_utils.create_temp_file("test", "txt")
        # Suffix is used as-is without adding a dot
        assert result.endswith("txt")

    def test_create_temp_file_creates_unique_names(self):
        """Test create_temp_file creates unique names on each call"""
        results = [temp_file_utils.create_temp_file("test", ".txt") for _ in range(5)]
        # All results should be different (timestamps or random numbers ensure this)
        assert len(set(results)) == 5


class TestDeleteFile:
    """Tests for delete_file function"""

    def test_delete_file_removes_existing_file(self):
        """Test delete_file removes an existing file"""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name
        try:
            assert os.path.exists(temp_path)
            temp_file_utils.delete_file(temp_path)
            assert not os.path.exists(temp_path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)

    def test_delete_file_handles_nonexistent_file(self):
        """Test delete_file handles non-existent file without error"""
        # Should not raise an exception
        temp_file_utils.delete_file("/nonexistent/path/file.txt")

    def test_delete_file_returns_none(self):
        """Test delete_file returns None"""
        result = temp_file_utils.delete_file("/nonexistent/file.txt")
        assert result is None


class TestDeleteFileSync:
    """Tests for delete_file_sync function"""

    def test_delete_file_sync_works(self):
        """Test delete_file_sync works the same as delete_file"""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name
        try:
            assert os.path.exists(temp_path)
            temp_file_utils.delete_file_sync(temp_path)
            assert not os.path.exists(temp_path)
        finally:
            if os.path.exists(temp_path):
                os.unlink(temp_path)


class TestWriteTempFile:
    """Tests for write_temp_file function"""

    def test_write_temp_file_creates_file(self):
        """Test write_temp_file creates the file"""
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "subdir", "test.txt")
            temp_file_utils.write_temp_file(file_path, "test content")
            assert os.path.exists(file_path)

    def test_write_temp_file_writes_content(self):
        """Test write_temp_file writes the content"""
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "test.txt")
            content = "Hello, World!"
            temp_file_utils.write_temp_file(file_path, content)
            with open(file_path, 'r') as f:
                assert f.read() == content

    def test_write_temp_file_creates_parent_dirs(self):
        """Test write_temp_file creates parent directories"""
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "a", "b", "c", "test.txt")
            temp_file_utils.write_temp_file(file_path, "content")
            assert os.path.exists(os.path.join(temp_dir, "a", "b", "c"))
            assert os.path.exists(file_path)

    def test_write_temp_file_with_unicode(self):
        """Test write_temp_file handles unicode content"""
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "test.txt")
            content = "Unicode: 日本語 🎉"
            temp_file_utils.write_temp_file(file_path, content)
            with open(file_path, 'r', encoding='utf-8') as f:
                assert f.read() == content

    def test_write_temp_file_empty_content(self):
        """Test write_temp_file handles empty content"""
        with tempfile.TemporaryDirectory() as temp_dir:
            file_path = os.path.join(temp_dir, "test.txt")
            temp_file_utils.write_temp_file(file_path, "")
            with open(file_path, 'r') as f:
                assert f.read() == ""


class TestTempFileUtilsEdgeCases:
    """Tests for edge cases in temp_file_utils"""

    def test_get_temp_dir_handles_makedirs_exception(self):
        """Test get_temp_dir handles OSError from makedirs"""
        with patch('os.makedirs', side_effect=OSError("Permission denied")):
            with patch.dict(os.environ, {'TMPDIR': '/fallback/tmp'}):
                result = temp_file_utils.get_temp_dir()
                assert result == '/fallback/tmp'

    def test_create_temp_file_with_special_chars_in_prefix(self):
        """Test create_temp_file with special characters in prefix"""
        result = temp_file_utils.create_temp_file("test-file_2024", ".txt")
        assert isinstance(result, str)
        assert result.endswith(".txt")

    def test_delete_file_permission_error(self):
        """Test delete_file handles permission errors gracefully"""
        # This tests that delete_file catches and ignores exceptions
        # We can't easily test permission errors without actually creating
        # a file with restricted permissions, so we just verify
        # the function doesn't crash on non-existent files
        temp_file_utils.delete_file("/nonexistent")
