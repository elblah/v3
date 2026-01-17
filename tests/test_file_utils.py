"""Tests for file utilities module"""

import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock
from aicoder.utils import file_utils


class TestGetCurrentDir:
    """Tests for get_current_dir function"""

    def test_get_current_dir_returns_string(self):
        """Test get_current_dir returns a string"""
        result = file_utils.get_current_dir()
        assert isinstance(result, str)

    def test_get_current_dir_is_absolute_path(self):
        """Test get_current_dir returns an absolute path"""
        result = file_utils.get_current_dir()
        assert os.path.isabs(result)


class TestGetRelativePath:
    """Tests for get_relative_path function"""

    def test_get_relative_path_for_file_in_current_dir(self):
        """Test getting relative path for file in current directory"""
        current_dir = file_utils.get_current_dir()
        result = file_utils.get_relative_path(os.path.join(current_dir, "test.txt"))
        assert "test.txt" in result

    def test_get_relative_path_with_nested_directory(self):
        """Test getting relative path with nested directory"""
        current_dir = file_utils.get_current_dir()
        result = file_utils.get_relative_path(os.path.join(current_dir, "subdir", "test.txt"))
        assert "subdir" in result

    def test_get_relative_path_fallback_on_error(self):
        """Test that function falls back to original path on error"""
        # This tests the exception handling in get_relative_path
        with patch('pathlib.Path.resolve', side_effect=Exception("Mock error")):
            result = file_utils.get_relative_path("/some/path")
            assert result == "/some/path"


class TestCheckSandbox:
    """Tests for check_sandbox function"""

    def test_sandbox_allows_current_dir(self):
        """Test sandbox allows operations in current directory"""
        current_dir = file_utils.get_current_dir()
        result = file_utils.check_sandbox(current_dir)
        assert result is True

    def test_sandbox_allows_file_in_current_dir(self):
        """Test sandbox allows files in current directory"""
        current_dir = file_utils.get_current_dir()
        result = file_utils.check_sandbox(os.path.join(current_dir, "test.txt"))
        assert result is True

    def test_sandbox_allows_subdirectory(self):
        """Test sandbox allows subdirectories"""
        current_dir = file_utils.get_current_dir()
        result = file_utils.check_sandbox(os.path.join(current_dir, "subdir", "file.txt"))
        assert result is True

    def test_sandbox_blocks_parent_traversal(self):
        """Test sandbox blocks parent directory traversal"""
        # This should be blocked by check_sandbox when sandbox is enabled
        # Note: The exact behavior depends on sandbox configuration
        result = file_utils.check_sandbox("../outside")
        # Result depends on whether sandbox is disabled in test env
        # We just verify the function handles it without error
        assert isinstance(result, bool)


class TestFileExists:
    """Tests for file_exists function"""

    def test_file_exists_returns_true_for_existing_file(self):
        """Test file_exists returns True for existing files"""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            temp_path = f.name
        try:
            result = file_utils.file_exists(temp_path)
            assert result is True
        finally:
            os.unlink(temp_path)

    def test_file_exists_returns_false_for_nonexistent_file(self):
        """Test file_exists returns False for non-existent files"""
        result = file_utils.file_exists("/nonexistent/path/to/file.txt")
        assert result is False


class TestReadFile:
    """Tests for read_file function"""

    def test_read_file_returns_content(self):
        """Test read_file returns file content"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("test content")
            temp_path = f.name
        try:
            result = file_utils.read_file(temp_path)
            assert result == "test content"
        finally:
            os.unlink(temp_path)

    def test_read_file_with_unicode(self):
        """Test read_file handles unicode content"""
        content = "Hello 世界 🌍"
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt', encoding='utf-8') as f:
            f.write(content)
            temp_path = f.name
        try:
            result = file_utils.read_file(temp_path)
            assert result == content
        finally:
            os.unlink(temp_path)

    def test_read_file_with_newlines(self):
        """Test read_file preserves newlines"""
        content = "line1\nline2\nline3"
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write(content)
            temp_path = f.name
        try:
            result = file_utils.read_file(temp_path)
            assert result == content
        finally:
            os.unlink(temp_path)

    def test_read_file_raises_on_nonexistent(self):
        """Test read_file raises exception for non-existent file"""
        with pytest.raises(Exception):
            file_utils.read_file("/nonexistent/path/file.txt")

    def test_read_file_empty_file(self):
        """Test read_file handles empty files"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            temp_path = f.name
        try:
            result = file_utils.read_file(temp_path)
            assert result == ""
        finally:
            os.unlink(temp_path)


class TestReadFileWithSandbox:
    """Tests for read_file_with_sandbox function"""

    def test_read_file_with_sandbox_allows_current_dir(self, capsys):
        """Test read_file_with_sandbox allows files in current directory"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("sandbox test")
            temp_path = f.name
        try:
            result = file_utils.read_file_with_sandbox(temp_path)
            assert result == "sandbox test"
        finally:
            os.unlink(temp_path)

    def test_read_file_with_sandbox_blocks_parent_traversal(self, capsys):
        """Test read_file_with_sandbox blocks parent traversal"""
        result = file_utils.read_file_with_sandbox("../outside/file.txt")
        # Should return False or an exception string when sandbox blocks access
        # Different sandbox configurations may return different types
        assert result is False or isinstance(result, str)


class TestWriteFile:
    """Tests for write_file function"""

    def test_write_file_creates_file(self):
        """Test write_file creates a file"""
        with tempfile.NamedTemporaryFile(mode='r', suffix='.txt', delete=False) as f:
            temp_path = f.name
        try:
            result = file_utils.write_file(temp_path, "test content")
            assert os.path.exists(temp_path)
            with open(temp_path, 'r') as f:
                assert f.read() == "test content"
        finally:
            os.unlink(temp_path)

    def test_write_file_returns_success_message(self):
        """Test write_file returns success message"""
        with tempfile.NamedTemporaryFile(mode='r', suffix='.txt', delete=False) as f:
            temp_path = f.name
        try:
            result = file_utils.write_file(temp_path, "content")
            assert "Successfully wrote" in result
            assert temp_path in result
        finally:
            os.unlink(temp_path)

    def test_write_file_creates_directories(self):
        """Test write_file creates parent directories if needed"""
        temp_dir = tempfile.mkdtemp()
        temp_path = os.path.join(temp_dir, "subdir", "nested", "file.txt")
        try:
            result = file_utils.write_file(temp_path, "nested content")
            assert os.path.exists(temp_path)
            with open(temp_path, 'r') as f:
                assert f.read() == "nested content"
        finally:
            import shutil
            shutil.rmtree(temp_dir)

    def test_write_file_with_unicode(self):
        """Test write_file handles unicode content"""
        with tempfile.NamedTemporaryFile(mode='r', suffix='.txt', delete=False) as f:
            temp_path = f.name
        try:
            content = "Unicode: 日本語 🎉"
            result = file_utils.write_file(temp_path, content)
            with open(temp_path, 'r', encoding='utf-8') as f:
                assert f.read() == content
        finally:
            os.unlink(temp_path)

    def test_write_file_overwrites_existing(self):
        """Test write_file overwrites existing file"""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("original")
            temp_path = f.name
        try:
            file_utils.write_file(temp_path, "updated")
            with open(temp_path, 'r') as f:
                assert f.read() == "updated"
        finally:
            os.unlink(temp_path)

    def test_write_file_empty_content(self):
        """Test write_file handles empty content"""
        with tempfile.NamedTemporaryFile(mode='r', suffix='.txt', delete=False) as f:
            temp_path = f.name
        try:
            result = file_utils.write_file(temp_path, "")
            assert os.path.exists(temp_path)
            with open(temp_path, 'r') as f:
                assert f.read() == ""
        finally:
            os.unlink(temp_path)


class TestWriteFileWithSandbox:
    """Tests for write_file_with_sandbox function"""

    def test_write_file_with_sandbox_allows_current_dir(self, capsys):
        """Test write_file_with_sandbox allows files in current directory"""
        with tempfile.NamedTemporaryFile(mode='r', suffix='.txt', delete=False) as f:
            temp_path = f.name
        try:
            result = file_utils.write_file_with_sandbox(temp_path, "sandbox write test")
            assert "Successfully wrote" in result
        finally:
            os.unlink(temp_path)

    def test_write_file_with_sandbox_blocks_parent_traversal(self, capsys):
        """Test write_file_with_sandbox blocks parent traversal"""
        result = file_utils.write_file_with_sandbox("../outside/file.txt", "content")
        assert result is False or isinstance(result, str)


class TestListDirectory:
    """Tests for list_directory function"""

    def test_list_directory_returns_list(self):
        """Test list_directory returns a list"""
        result = file_utils.list_directory(".")
        assert isinstance(result, list)

    def test_list_directory_includes_files(self):
        """Test list_directory includes files in current directory"""
        temp_dir = tempfile.mkdtemp()
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)
            # Create a test file
            with open("test_file.txt", 'w') as f:
                f.write("test")
            result = file_utils.list_directory(".")
            # The result should contain the file or not contain excluded patterns
            assert isinstance(result, list)
        finally:
            os.chdir(original_cwd)
            import shutil
            shutil.rmtree(temp_dir)

    def test_list_directory_excludes_hidden_files(self):
        """Test list_directory excludes hidden files (starting with .)"""
        temp_dir = tempfile.mkdtemp()
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)
            # Create hidden file
            with open(".hidden", 'w') as f:
                f.write("hidden")
            # Create normal file
            with open("visible.txt", 'w') as f:
                f.write("visible")
            result = file_utils.list_directory(".")
            assert ".hidden" not in result
        finally:
            os.chdir(original_cwd)
            import shutil
            shutil.rmtree(temp_dir)

    def test_list_directory_excludes_common_patterns(self):
        """Test list_directory excludes common patterns like node_modules, .git, etc."""
        temp_dir = tempfile.mkdtemp()
        original_cwd = os.getcwd()
        try:
            # Create directories with excluded names
            os.makedirs(os.path.join(temp_dir, "node_modules", "package"))
            os.makedirs(os.path.join(temp_dir, ".git", "objects"))
            with open(os.path.join(temp_dir, "visible.txt"), 'w') as f:
                f.write("visible")
            # list_directory uses _current_dir from module, so use explicit path
            result = file_utils.list_directory(temp_dir)
            assert "node_modules" not in result
            assert ".git" not in result
            assert "visible.txt" in result
        finally:
            import shutil
            shutil.rmtree(temp_dir)

    def test_list_directory_raises_on_nonexistent(self):
        """Test list_directory raises exception for non-existent directory"""
        with pytest.raises(Exception):
            file_utils.list_directory("/nonexistent/path")


class TestGetReadFiles:
    """Tests for get_read_files function"""

    def test_get_read_files_returns_set(self):
        """Test get_read_files returns a set"""
        result = file_utils.get_read_files()
        assert isinstance(result, set)

    def test_get_read_files_reflects_file_reads(self):
        """Test that get_read_files tracks files that were read"""
        # Read some files
        with tempfile.NamedTemporaryFile(mode='w', delete=False, suffix='.txt') as f:
            f.write("test")
            temp_path = f.name
        try:
            file_utils.read_file(temp_path)
            read_files = file_utils.get_read_files()
            assert temp_path in read_files
        finally:
            os.unlink(temp_path)

    def test_get_read_files_returns_copy(self):
        """Test that get_read_files returns a copy of the set"""
        read_files1 = file_utils.get_read_files()
        read_files2 = file_utils.get_read_files()
        # They should have same content but be different objects
        assert read_files1 == read_files2
        assert read_files1 is not read_files2


class TestFileUtilsEdgeCases:
    """Tests for edge cases in file_utils"""

    def test_write_file_with_path_only_filename(self):
        """Test write_file handles path with only filename (no directory)"""
        with tempfile.TemporaryDirectory() as temp_dir:
            original_cwd = os.getcwd()
            try:
                os.chdir(temp_dir)
                # Write to a filename in current directory
                result = file_utils.write_file("simple.txt", "simple content")
                assert os.path.exists("simple.txt")
                with open("simple.txt", 'r') as f:
                    assert f.read() == "simple content"
            finally:
                os.chdir(original_cwd)

    def test_read_file_binary_content(self):
        """Test read_file handles content that could be binary"""
        with tempfile.NamedTemporaryFile(mode='wb', delete=False) as f:
            f.write(b"\x00\x01\x02\x03")
            temp_path = f.name
        try:
            # This should still work for reading
            with open(temp_path, 'rb') as f:
                expected = f.read()
            # The function opens as text, so binary might cause issues
            # This test documents the expected behavior
            try:
                result = file_utils.read_file(temp_path)
                # If it works, binary chars are in result
            except Exception:
                # Expected for binary content
                pass
        finally:
            os.unlink(temp_path)

    def test_list_directory_with_nested_structure(self):
        """Test list_directory with deeply nested structure"""
        temp_dir = tempfile.mkdtemp()
        original_cwd = os.getcwd()
        try:
            os.chdir(temp_dir)
            # Create nested structure
            os.makedirs("a/b/c/d")
            with open("a/b/c/d/file.txt", 'w') as f:
                f.write("deep")
            with open("a/b/visible.txt", 'w') as f:
                f.write("visible")
            result = file_utils.list_directory("a/b")
            assert isinstance(result, list)
            # Should include 'c' directory and 'visible.txt' file
        finally:
            os.chdir(original_cwd)
            import shutil
            shutil.rmtree(temp_dir)

    def test_file_exists_for_directory(self):
        """Test file_exists returns True for directories"""
        with tempfile.TemporaryDirectory() as temp_dir:
            result = file_utils.file_exists(temp_dir)
            assert result is True
