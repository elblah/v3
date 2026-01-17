"""Unit tests for FileAccessTracker."""

import pytest

import sys
sys.path.insert(0, '/home/blah/storage/ai-worktree-storage/feat_test_coverage__20260117_062928')

from aicoder.core.file_access_tracker import FileAccessTracker


class TestFileAccessTracker:
    """Test FileAccessTracker class."""

    def setup_method(self):
        """Clear state before each test."""
        FileAccessTracker.clear_state()

    def teardown_method(self):
        """Clear state after each test."""
        FileAccessTracker.clear_state()

    def test_record_read_adds_path(self):
        """Test recording a file read."""
        FileAccessTracker.record_read("/path/to/file.txt")
        assert FileAccessTracker.was_file_read("/path/to/file.txt") is True

    def test_was_file_read_returns_false_for_unread(self):
        """Test returns False for unread files."""
        assert FileAccessTracker.was_file_read("/path/to/file.txt") is False

    def test_record_multiple_files(self):
        """Test recording multiple files."""
        FileAccessTracker.record_read("/path/to/file1.txt")
        FileAccessTracker.record_read("/path/to/file2.txt")
        assert FileAccessTracker.was_file_read("/path/to/file1.txt") is True
        assert FileAccessTracker.was_file_read("/path/to/file2.txt") is True

    def test_same_file_recorded_twice(self):
        """Test recording same file twice doesn't duplicate."""
        FileAccessTracker.record_read("/path/to/file.txt")
        FileAccessTracker.record_read("/path/to/file.txt")
        assert FileAccessTracker.get_read_count() == 1

    def test_clear_state_removes_all(self):
        """Test clearing all tracked files."""
        FileAccessTracker.record_read("/path/to/file1.txt")
        FileAccessTracker.record_read("/path/to/file2.txt")
        FileAccessTracker.clear_state()
        assert FileAccessTracker.get_read_count() == 0
        assert FileAccessTracker.was_file_read("/path/to/file1.txt") is False
        assert FileAccessTracker.was_file_read("/path/to/file2.txt") is False

    def test_get_all_read_files_returns_copy(self):
        """Test get_all_read_files returns a copy."""
        FileAccessTracker.record_read("/path/to/file.txt")
        files = FileAccessTracker.get_all_read_files()
        files.add("/another/path.txt")  # Modify the returned set
        assert FileAccessTracker.was_file_read("/another/path.txt") is False

    def test_get_read_count(self):
        """Test getting count of read files."""
        assert FileAccessTracker.get_read_count() == 0
        FileAccessTracker.record_read("/path/to/file1.txt")
        assert FileAccessTracker.get_read_count() == 1
        FileAccessTracker.record_read("/path/to/file2.txt")
        assert FileAccessTracker.get_read_count() == 2

    def test_empty_path(self):
        """Test handling empty path."""
        FileAccessTracker.record_read("")
        assert FileAccessTracker.was_file_read("") is True

    def test_special_characters_in_path(self):
        """Test handling paths with special characters."""
        path = "/path/with spaces and 中文/file.txt"
        FileAccessTracker.record_read(path)
        assert FileAccessTracker.was_file_read(path) is True
