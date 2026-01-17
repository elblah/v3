"""
Tests for file utilities
"""

import pytest
import tempfile
import os


class TestFileUtils:
    """Test file utility functions"""

    def test_get_current_dir(self):
        """Test getting current directory"""
        from aicoder.utils.file_utils import get_current_dir

        current = get_current_dir()

        # Should be a valid directory path
        assert isinstance(current, str)
        assert len(current) > 0

    def test_get_relative_path_within_cwd(self):
        """Test getting relative path within current directory"""
        from aicoder.utils.file_utils import get_relative_path

        # Get path relative to current directory
        rel_path = get_relative_path("./aicoder/utils/file_utils.py")

        # Should return a string path
        assert isinstance(rel_path, str)

    def test_file_exists(self):
        """Test checking if file exists"""
        from aicoder.utils.file_utils import file_exists

        assert file_exists(__file__) is True
        assert file_exists("/nonexistent/file.txt") is False

    def test_read_file(self):
        """Test reading a file"""
        from aicoder.utils.file_utils import read_file

        content = read_file(__file__)

        assert isinstance(content, str)
        assert len(content) > 0

    def test_read_file_error(self):
        """Test reading non-existent file raises error"""
        from aicoder.utils.file_utils import read_file

        with pytest.raises(Exception):
            read_file("/nonexistent/file.txt")

    def test_write_file(self):
        """Test writing to a file"""
        from aicoder.utils.file_utils import write_file

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            content = "Hello, World!"

            result = write_file(path, content)

            assert "Successfully wrote" in result

            # Verify content
            with open(path, "r") as f:
                assert f.read() == content

    def test_write_file_creates_directory(self):
        """Test write_file creates parent directories"""
        from aicoder.utils.file_utils import write_file

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "subdir", "nested", "test.txt")
            content = "nested content"

            result = write_file(path, content)

            assert os.path.exists(path)

            with open(path, "r") as f:
                assert f.read() == content

    def test_write_file_with_sandbox(self):
        """Test writing file with sandbox check"""
        from aicoder.utils.file_utils import write_file_with_sandbox

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.txt")
            content = "sandbox test"

            result = write_file_with_sandbox(path, content)

            assert "Successfully wrote" in result

    def test_read_file_with_sandbox(self):
        """Test reading file with sandbox check"""
        from aicoder.utils.file_utils import read_file_with_sandbox

        content = read_file_with_sandbox(__file__)

        assert isinstance(content, str)
        assert len(content) > 0

    def test_list_directory(self):
        """Test listing directory contents"""
        from aicoder.utils.file_utils import list_directory

        with tempfile.TemporaryDirectory() as tmpdir:
            # Create some files
            os.makedirs(os.path.join(tmpdir, "subdir"))
            with open(os.path.join(tmpdir, "file1.txt"), "w") as f:
                f.write("test")
            with open(os.path.join(tmpdir, "file2.txt"), "w") as f:
                f.write("test")

            entries = list_directory(tmpdir)

            assert isinstance(entries, list)
            assert "file1.txt" in entries
            assert "file2.txt" in entries
            assert "subdir" in entries

    def test_list_directory_excludes_hidden(self):
        """Test that list_directory excludes hidden files"""
        from aicoder.utils.file_utils import list_directory

        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, ".hidden"), "w") as f:
                f.write("test")
            with open(os.path.join(tmpdir, "visible.txt"), "w") as f:
                f.write("test")

            entries = list_directory(tmpdir)

            assert ".hidden" not in entries
            assert "visible.txt" in entries

    def test_list_directory_excludes_common_dirs(self):
        """Test that list_directory excludes common directories"""
        from aicoder.utils.file_utils import list_directory

        with tempfile.TemporaryDirectory() as tmpdir:
            os.makedirs(os.path.join(tmpdir, ".git"))
            os.makedirs(os.path.join(tmpdir, "node_modules"))
            os.makedirs(os.path.join(tmpdir, "src"))
            with open(os.path.join(tmpdir, "file.txt"), "w") as f:
                f.write("test")

            entries = list_directory(tmpdir)

            assert ".git" not in entries
            assert "node_modules" not in entries
            assert "src" in entries
            assert "file.txt" in entries

    def test_get_read_files(self):
        """Test tracking files that have been read"""
        from aicoder.utils.file_utils import get_read_files, read_file

        # Read some files
        read_file(__file__)

        tracked = get_read_files()

        assert isinstance(tracked, set)
        assert __file__ in tracked
