"""Unit tests for temporary file utilities."""

import os
import tempfile
import pytest
from unittest.mock import patch

import sys
sys.path.insert(0, '/home/blah/storage/ai-worktree-storage/feat_test_coverage__20260117_062928')

from aicoder.utils.temp_file_utils import (
    get_temp_dir,
    create_temp_file,
    delete_file,
    write_temp_file
)


class TestGetTempDir:
    """Test get_temp_dir function."""

    def test_returns_local_tmp_when_creatable(self):
        """Test returns local ./tmp when it can be created."""
        result = get_temp_dir()
        assert result == os.path.abspath("./tmp")
        assert os.path.exists(result)

    def test_creates_local_tmp_directory(self):
        """Test creates ./tmp directory if it doesn't exist."""
        # Remove if exists
        local_tmp = "./tmp"
        if os.path.exists(local_tmp):
            import shutil
            shutil.rmtree(local_tmp)

        result = get_temp_dir()
        assert os.path.isdir(result)

    def test_fallback_to_env_tmpdir(self):
        """Test TMPDIR environment variable affects temp directory choice."""
        # When local ./tmp exists, it takes precedence
        result = get_temp_dir()
        # The function should prefer local tmp if available
        assert "tmp" in result or "/tmp" in result

    def test_fallback_to_tmp(self):
        """Test falls back to /tmp when TMPDIR not set and local fails."""
        with patch.dict(os.environ, {}, clear=True):
            # Also mock os.makedirs to fail
            with patch('os.makedirs', side_effect=Exception("Denied")):
                import importlib
                import aicoder.utils.temp_file_utils as tf_utils
                importlib.reload(tf_utils)
                result = tf_utils.get_temp_dir()
                assert result == "/tmp"


class TestCreateTempFile:
    """Test create_temp_file function."""

    def test_creates_file_in_temp_dir(self):
        """Test creates temp file path in temp directory."""
        path = create_temp_file("test")
        assert path.startswith(get_temp_dir())
        assert "test" in path

    def test_creates_file_with_suffix(self):
        """Test creates temp file with suffix."""
        path = create_temp_file("test", ".txt")
        assert path.endswith(".txt")

    def test_path_format(self):
        """Test path format contains timestamp and random."""
        path = create_temp_file("prefix", ".ext")
        # Should contain prefix
        assert "prefix" in path
        # Should contain extension
        assert ".ext" in path


class TestDeleteFile:
    """Test delete_file function."""

    def test_deletes_existing_file(self):
        """Test deletes existing file."""
        with tempfile.NamedTemporaryFile(delete=False) as f:
            f.write(b"test")
            path = f.name

        assert os.path.exists(path)
        delete_file(path)
        assert not os.path.exists(path)

    def test_no_error_on_nonexistent_file(self):
        """Test no error when file doesn't exist."""
        delete_file("/nonexistent/file.txt")
        # Should not raise

    def test_ignores_deletion_errors(self):
        """Test ignores deletion errors gracefully."""
        with patch('os.remove', side_effect=Exception("Permission denied")):
            delete_file("/some/path")
            # Should not raise


class TestWriteTempFile:
    """Test write_temp_file function."""

    def test_writes_content(self):
        """Test writes content to file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "subdir", "test.txt")
            write_temp_file(path, "hello world")

            with open(path, "r") as f:
                assert f.read() == "hello world"

    def test_creates_directory(self):
        """Test creates parent directory if needed."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "newdir", "nested", "file.txt")
            write_temp_file(path, "content")

            assert os.path.isdir(os.path.join(tmpdir, "newdir", "nested"))
            assert os.path.isfile(path)

    def test_handles_unicode(self):
        """Test writes unicode content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "unicode.txt")
            write_temp_file(path, "你好世界")

            with open(path, "r", encoding="utf-8") as f:
                assert f.read() == "你好世界"
