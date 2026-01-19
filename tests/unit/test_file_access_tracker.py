"""
Tests for file_access_tracker module
"""

import pytest
from aicoder.core.file_access_tracker import FileAccessTracker


class TestFileAccessTracker:
    """Test FileAccessTracker class"""

    def setup_method(self):
        """Clear state before each test"""
        FileAccessTracker.clear_state()

    def teardown_method(self):
        """Clear state after each test"""
        FileAccessTracker.clear_state()

    def test_record_read(self):
        """Test recording a file read"""
        FileAccessTracker.record_read("/path/to/file.py")
        assert FileAccessTracker.was_file_read("/path/to/file.py") is True

    def test_was_file_read_false(self):
        """Test checking file that was never read"""
        assert FileAccessTracker.was_file_read("/path/to/unread.py") is False

    def test_record_multiple_files(self):
        """Test recording multiple files"""
        FileAccessTracker.record_read("/path/to/file1.py")
        FileAccessTracker.record_read("/path/to/file2.py")
        assert FileAccessTracker.was_file_read("/path/to/file1.py") is True
        assert FileAccessTracker.was_file_read("/path/to/file2.py") is True

    def test_record_same_file_twice(self):
        """Test recording the same file twice doesn't duplicate"""
        FileAccessTracker.record_read("/path/to/file.py")
        FileAccessTracker.record_read("/path/to/file.py")
        assert FileAccessTracker.get_read_count() == 1

    def test_clear_state(self):
        """Test clearing all tracked files"""
        FileAccessTracker.record_read("/path/to/file1.py")
        FileAccessTracker.record_read("/path/to/file2.py")
        assert FileAccessTracker.get_read_count() == 2

        FileAccessTracker.clear_state()
        assert FileAccessTracker.get_read_count() == 0
        assert FileAccessTracker.was_file_read("/path/to/file1.py") is False

    def test_get_all_read_files(self):
        """Test getting all read files"""
        FileAccessTracker.record_read("/path/to/file1.py")
        FileAccessTracker.record_read("/path/to/file2.py")

        all_files = FileAccessTracker.get_all_read_files()
        assert len(all_files) == 2
        assert "/path/to/file1.py" in all_files
        assert "/path/to/file2.py" in all_files

    def test_get_all_read_files_returns_copy(self):
        """Test that get_all_read_files returns a copy"""
        FileAccessTracker.record_read("/path/to/file.py")
        all_files = FileAccessTracker.get_all_read_files()
        all_files.add("/another/path.py")  # Modify the returned set
        assert "/another/path.py" not in FileAccessTracker.get_all_read_files()

    def test_get_read_count(self):
        """Test getting read count"""
        assert FileAccessTracker.get_read_count() == 0
        FileAccessTracker.record_read("/path/to/file1.py")
        assert FileAccessTracker.get_read_count() == 1
        FileAccessTracker.record_read("/path/to/file2.py")
        assert FileAccessTracker.get_read_count() == 2

    def test_empty_string_path(self):
        """Test with empty string path"""
        FileAccessTracker.record_read("")
        assert FileAccessTracker.was_file_read("") is True

    def test_special_characters_in_path(self):
        """Test with special characters in path"""
        path = "/path/with spaces/and-dashes/file@123.py"
        FileAccessTracker.record_read(path)
        assert FileAccessTracker.was_file_read(path) is True

    def test_relative_path(self):
        """Test with relative path"""
        path = "./relative/path/file.py"
        FileAccessTracker.record_read(path)
        assert FileAccessTracker.was_file_read(path) is True

    def test_absolute_path(self):
        """Test with absolute path"""
        path = "/absolute/path/to/file.py"
        FileAccessTracker.record_read(path)
        assert FileAccessTracker.was_file_read(path) is True
