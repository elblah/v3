"""
Tests for temp file utilities
"""

import pytest
import tempfile
import os


class TestTempFileUtils:
    """Test temporary file utility functions"""

    def test_get_temp_dir_local(self):
        """Test getting temp directory creates local directory"""
        from aicoder.utils.temp_file_utils import get_temp_dir

        temp_dir = get_temp_dir()

        # Should be a string path
        assert isinstance(temp_dir, str)
        assert len(temp_dir) > 0

    def test_create_temp_file_basic(self):
        """Test creating temporary file path"""
        from aicoder.utils.temp_file_utils import create_temp_file

        path = create_temp_file("test")

        assert "test-" in path
        assert path.endswith(".tmp") or path.endswith("")

    def test_create_temp_file_with_suffix(self):
        """Test creating temp file with suffix"""
        from aicoder.utils.temp_file_utils import create_temp_file

        path = create_temp_file("log", ".txt")

        assert path.endswith(".txt")

    def test_delete_file(self):
        """Test deleting a file"""
        from aicoder.utils.temp_file_utils import delete_file, create_temp_file

        # Create a temp file
        path = create_temp_file("delete_test", ".txt")

        # Write content
        with open(path, "w") as f:
            f.write("test")

        # File should exist now
        assert os.path.exists(path)

        # Delete it
        delete_file(path)

        # File should no longer exist
        assert not os.path.exists(path)

    def test_delete_file_nonexistent(self):
        """Test deleting non-existent file doesn't raise error"""
        from aicoder.utils.temp_file_utils import delete_file

        # Should not raise exception
        delete_file("/nonexistent/path/file.txt")

    def test_write_temp_file(self):
        """Test writing to temp file"""
        from aicoder.utils.temp_file_utils import write_temp_file, create_temp_file

        path = create_temp_file("write_test", ".txt")
        content = "Hello, World!"

        write_temp_file(path, content)

        # File should exist with correct content
        assert os.path.exists(path)
        with open(path, "r") as f:
            assert f.read() == content

    def test_delete_file_sync(self):
        """Test synchronous file deletion"""
        from aicoder.utils.temp_file_utils import delete_file_sync, create_temp_file

        path = create_temp_file("sync_test", ".txt")

        with open(path, "w") as f:
            f.write("test")

        assert os.path.exists(path)

        delete_file_sync(path)

        assert not os.path.exists(path)
