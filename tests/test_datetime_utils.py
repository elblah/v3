"""Tests for datetime_utils module"""

import re
from datetime import datetime
from aicoder.utils import datetime_utils


class TestCreateFileTimestamp:
    """Tests for create_file_timestamp function"""

    def test_timestamp_format(self):
        """Test that timestamp has correct format YYYY-MM-DDTHH-MM-SS"""
        timestamp = datetime_utils.create_file_timestamp()
        # Match format: YYYY-MM-DDTHH-MM-SS (19 chars)
        pattern = r"^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}$"
        assert re.match(pattern, timestamp) is not None

    def test_timestamp_length(self):
        """Test that timestamp is exactly 19 characters"""
        timestamp = datetime_utils.create_file_timestamp()
        assert len(timestamp) == 19

    def test_timestamp_is_iso_like(self):
        """Test that timestamp resembles ISO format"""
        timestamp = datetime_utils.create_file_timestamp()
        # Should be parseable by replacing '-' with ':' in time part
        iso_like = timestamp[:-6] + timestamp[-6:].replace("-", ":")
        parsed = datetime.fromisoformat(iso_like)
        assert parsed is not None


class TestCreateTimestampFilename:
    """Tests for create_timestamp_filename function"""

    def test_filename_with_extension(self):
        """Test filename creation with extension"""
        filename = datetime_utils.create_timestamp_filename("test", ".txt")
        assert filename.endswith(".txt")
        assert filename.startswith("test-")

    def test_filename_without_dot_extension(self):
        """Test filename creation when extension doesn't start with dot"""
        filename = datetime_utils.create_timestamp_filename("test", "txt")
        assert filename.endswith(".txt")
        assert filename.startswith("test-")

    def test_filename_empty_prefix(self):
        """Test filename with empty prefix"""
        filename = datetime_utils.create_timestamp_filename("", "log")
        assert filename.endswith(".log")
        assert filename.startswith("-")


class TestGetCurrentIsoDatetime:
    """Tests for get_current_iso_datetime function"""

    def test_returns_iso_format(self):
        """Test that returns valid ISO datetime string"""
        iso_str = datetime_utils.get_current_iso_datetime()
        # Should be parseable
        parsed = datetime.fromisoformat(iso_str)
        assert parsed is not None

    def test_contains_date_and_time(self):
        """Test that ISO string contains both date and time"""
        iso_str = datetime_utils.get_current_iso_datetime()
        assert "T" in iso_str or " " in iso_str
