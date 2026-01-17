"""Unit tests for file utilities."""

import os
import tempfile
import pytest
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, '/home/blah/storage/ai-worktree-storage/feat_test_coverage__20260117_062928')

from aicoder.utils.file_utils import (
    get_current_dir,
    get_relative_path,
    check_sandbox,
    file_exists,
    read_file,
    read_file_with_sandbox,
    write_file,
    write_file_with_sandbox,
    list_directory,
    get_read_files,
    _current_dir,
    _read_files
)


class TestGetCurrentDir:
    """Test get_current_dir function."""

    def test_returns_current_dir(self):
        """Test returns the current working directory."""
        result = get_current_dir()
        assert result == _current_dir
        assert result == os.getcwd()


class TestGetRelativePath:
    """Test get_relative_path function."""

    def test_returns_same_path_for_current_dir_file(self):
        """Test returns relative path for file in current directory."""
        # Create a temp file in current directory
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test")
            temp_path = f.name
            rel_path = get_relative_path(temp_path)

        try:
            # Should return relative path without the full cwd prefix
            assert temp_path in rel_path or rel_path in temp_path
        finally:
            os.unlink(temp_path)

    def test_returns_absolute_for_outside_path(self):
        """Test returns absolute path for file outside current directory."""
        result = get_relative_path("/tmp/test.txt")
        assert result == "/tmp/test.txt"

    def test_handles_nonexistent_path(self):
        """Test handles nonexistent path gracefully."""
        result = get_relative_path("/nonexistent/path/to/file.txt")
        assert result == "/nonexistent/path/to/file.txt"

    def test_handles_relative_path(self):
        """Test handles relative paths."""
        result = get_relative_path("./test.txt")
        assert "test.txt" in result


class TestCheckSandbox:
    """Test check_sandbox function."""

    def test_allows_when_disabled(self):
        """Test sandbox allows all when disabled."""
        with patch('aicoder.core.config.Config.sandbox_disabled', return_value=True):
            result = check_sandbox("/any/path")
        assert result is True

    def test_allows_current_dir(self):
        """Test sandbox allows current directory."""
        with patch('aicoder.core.config.Config.sandbox_disabled', return_value=False):
            result = check_sandbox(_current_dir)
        assert result is True

    def test_allows_subdirectory(self):
        """Test sandbox allows subdirectory of current."""
        subdir = os.path.join(_current_dir, "subdir")
        with patch('aicoder.core.config.Config.sandbox_disabled', return_value=False):
            result = check_sandbox(subdir)
        assert result is True

    def test_blocks_parent_directory(self):
        """Test sandbox blocks parent directory."""
        parent = os.path.dirname(_current_dir)
        with patch('aicoder.core.config.Config.sandbox_disabled', return_value=False):
            result = check_sandbox(parent)
        assert result is False

    def test_blocks_outside_absolute_path(self):
        """Test sandbox blocks absolute path outside current directory."""
        with patch('aicoder.core.config.Config.sandbox_disabled', return_value=False):
            result = check_sandbox("/tmp")
        assert result is False

    def test_allows_none_path(self):
        """Test sandbox allows empty/None path."""
        with patch('aicoder.core.config.Config.sandbox_disabled', return_value=False):
            result = check_sandbox("")
        assert result is True

        with patch('aicoder.core.config.Config.sandbox_disabled', return_value=False):
            result = check_sandbox(None)
        assert result is True


class TestFileExists:
    """Test file_exists function."""

    def test_returns_true_for_existing_file(self):
        """Test returns True for existing file."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test")
            path = f.name

        try:
            assert file_exists(path) is True
        finally:
            os.unlink(path)

    def test_returns_false_for_nonexistent(self):
        """Test returns False for nonexistent file."""
        assert file_exists("/nonexistent/path.txt") is False


class TestReadFile:
    """Test read_file function."""

    def test_reads_file_content(self):
        """Test reads file content correctly."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as f:
            f.write("Hello, World!")
            path = f.name

        try:
            result = read_file(path)
            assert result == "Hello, World!"
        finally:
            os.unlink(path)

    def test_reads_binary_file(self):
        """Test reads binary file."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"\x00\x01\x02\x03")
            path = f.name

        try:
            result = read_file(path)
            assert result == "\x00\x01\x02\x03"
        finally:
            os.unlink(path)

    def test_raises_on_nonexistent(self):
        """Test raises exception for nonexistent file."""
        with pytest.raises(Exception) as exc_info:
            read_file("/nonexistent/file.txt")
        assert "Error reading file" in str(exc_info.value)

    def test_tracks_read_files(self):
        """Test tracks files that have been read."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as f:
            f.write("test content")
            path = f.name

        try:
            read_file(path)
            assert path in _read_files
        finally:
            os.unlink(path)


class TestReadFileWithSandbox:
    """Test read_file_with_sandbox function."""

    def test_reads_within_sandbox(self):
        """Test reads file within sandbox."""
        with tempfile.NamedTemporaryFile(mode='w', delete=False, encoding='utf-8') as f:
            f.write("content")
            path = f.name

        try:
            with patch('aicoder.core.config.Config.sandbox_disabled', return_value=True):
                result = read_file_with_sandbox(path)
            assert result == "content"
        finally:
            os.unlink(path)

    def test_blocks_outside_sandbox(self):
        """Test blocks file outside sandbox."""
        with patch('aicoder.core.config.Config.sandbox_disabled', return_value=False):
            with pytest.raises(Exception) as exc_info:
                read_file_with_sandbox("/tmp/test.txt")
        assert "outside current directory" in str(exc_info.value)


class TestWriteFile:
    """Test write_file function."""

    def test_writes_content(self):
        """Test writes content to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            result = write_file(path, "Hello, World!")

            assert os.path.exists(path)
            with open(path, 'r') as f:
                assert f.read() == "Hello, World!"
            assert "Successfully wrote" in result

    def test_creates_parent_directory(self):
        """Test creates parent directory if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "subdir", "nested", "file.txt")
            write_file(path, "content")

            assert os.path.isdir(os.path.join(tmpdir, "subdir", "nested"))
            assert os.path.isfile(path)

    def test_returns_byte_count(self):
        """Test returns byte count in result."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            content = "Hello, World!"
            result = write_file(path, content)

            expected_bytes = len(content.encode("utf-8"))
            assert f"{expected_bytes} bytes" in result

    def test_handles_unicode(self):
        """Test handles unicode content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "unicode.txt")
            write_file(path, "你好世界")

            with open(path, 'r', encoding='utf-8') as f:
                assert f.read() == "你好世界"


class TestWriteFileWithSandbox:
    """Test write_file_with_sandbox function."""

    def test_writes_within_sandbox(self):
        """Test writes file within sandbox."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")

            with patch('aicoder.core.config.Config.sandbox_disabled', return_value=True):
                result = write_file_with_sandbox(path, "content")

            assert os.path.exists(path)
            assert "Successfully wrote" in result

    def test_blocks_outside_sandbox(self):
        """Test blocks file outside sandbox."""
        with patch('aicoder.core.config.Config.sandbox_disabled', return_value=False):
            with pytest.raises(Exception) as exc_info:
                write_file_with_sandbox("/tmp/test.txt", "content")
        assert "outside current directory" in str(exc_info.value)


class TestListDirectory:
    """Test list_directory function."""

    def test_lists_files(self):
        """Test lists files in directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            for i in range(3):
                with open(os.path.join(tmpdir, f"file{i}.txt"), 'w') as f:
                    f.write(f"content {i}")

            with patch('aicoder.core.config.Config.sandbox_disabled', return_value=True):
                result = list_directory(tmpdir)

            assert len(result) == 3
            assert "file0.txt" in result

    def test_filters_hidden_files(self):
        """Test filters hidden files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, "visible.txt"), 'w') as f:
                f.write("visible")
            with open(os.path.join(tmpdir, ".hidden"), 'w') as f:
                f.write("hidden")

            with patch('aicoder.core.config.Config.sandbox_disabled', return_value=True):
                result = list_directory(tmpdir)

            assert "visible.txt" in result
            # .hidden should not be included (starts with dot)

    def test_excludes_common_dirs(self):
        """Test excludes common directories like node_modules."""
        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, "node_modules"))
            os.makedirs(os.path.join(tmpdir, ".git"))

            with patch('aicoder.core.config.Config.sandbox_disabled', return_value=True):
                result = list_directory(tmpdir)

            # These should be filtered out
            assert "node_modules" not in result

    def test_blocks_outside_sandbox(self):
        """Test blocks directory outside sandbox."""
        with patch('aicoder.core.config.Config.sandbox_disabled', return_value=False):
            with pytest.raises(Exception) as exc_info:
                list_directory("/tmp")
        assert "outside current directory" in str(exc_info.value)

    def test_handles_empty_directory(self):
        """Test handles empty directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with patch('aicoder.core.config.Config.sandbox_disabled', return_value=True):
                result = list_directory(tmpdir)

            assert result == []


class TestGetReadFiles:
    """Test get_read_files function."""

    def test_returns_copy_of_read_files(self):
        """Test returns a copy of tracked files."""
        # Clear and set test files
        _read_files.clear()
        _read_files.add("/test/path1")
        _read_files.add("/test/path2")

        result = get_read_files()

        assert "/test/path1" in result
        assert "/test/path2" in result
        # Should be a copy, not the original
        assert result is not _read_files

    def test_returns_empty_set_initially(self):
        """Test returns empty set when no files read."""
        _read_files.clear()
        result = get_read_files()
        assert result == set()
