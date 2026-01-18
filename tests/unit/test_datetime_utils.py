"""Unit tests for datetime utilities."""

import pytest
import re
import sys
from datetime import datetime
from unittest.mock import patch

sys.path.insert(0, '/home/blah/storage/ai-worktree-storage/feat_test_coverage__20260117_062928')

from aicoder.utils.datetime_utils import (
    create_file_timestamp,
    create_timestamp_filename,
    get_current_iso_datetime
)


class TestCreateFileTimestamp:
    """Test create_file_timestamp function."""

    def test_returns_valid_format(self):
        """Test returns valid timestamp format."""
        timestamp = create_file_timestamp()
        # Should match format: YYYY-MM-DDTHH-MM-SS
        assert re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}$', timestamp)

    def test_replaces_colons_with_hyphens(self):
        """Test replaces colons with hyphens in timestamp."""
        timestamp = create_file_timestamp()
        # Should not contain colons in time part
        time_part = timestamp.split('T')[1]
        assert ':' not in time_part
        # Should use hyphens instead
        assert '-' in time_part

    def test_length_is_correct(self):
        """Test timestamp length is exactly 19 characters."""
        timestamp = create_file_timestamp()
        assert len(timestamp) == 19

    def test_contains_t_separator(self):
        """Test timestamp contains T separator between date and time."""
        timestamp = create_file_timestamp()
        assert 'T' in timestamp

    def test_date_part_is_valid(self):
        """Test date part is valid."""
        timestamp = create_file_timestamp()
        date_part = timestamp.split('T')[0]
        # Should match YYYY-MM-DD format
        assert re.match(r'^\d{4}-\d{2}-\d{2}$', date_part)

    def test_time_part_is_valid(self):
        """Test time part is valid."""
        timestamp = create_file_timestamp()
        time_part = timestamp.split('T')[1]
        # Should match HH-MM-SS format
        assert re.match(r'^\d{2}-\d{2}-\d{2}$', time_part)


class TestCreateTimestampFilename:
    """Test create_timestamp_filename function."""

    def test_creates_filename_with_prefix(self):
        """Test creates filename with given prefix."""
        filename = create_timestamp_filename("test", "txt")
        assert filename.startswith("test-")

    def test_includes_extension(self):
        """Test includes extension in filename."""
        filename = create_timestamp_filename("test", "txt")
        assert filename.endswith(".txt")

    def test_adds_dot_if_missing(self):
        """Test adds dot to extension if missing."""
        filename = create_timestamp_filename("test", "txt")
        assert ".txt" in filename

        filename2 = create_timestamp_filename("test", ".txt")
        assert ".txt" in filename2

    def test_handles_extension_with_dot(self):
        """Test handles extension that already has dot."""
        filename = create_timestamp_filename("test", ".json")
        assert filename.endswith(".json")
        # Should not have double dots
        assert ".." not in filename

    def test_includes_timestamp(self):
        """Test includes timestamp in filename."""
        filename = create_timestamp_filename("test", "txt")
        # Extract timestamp part (between prefix and extension)
        timestamp_part = filename[5:-4]  # Remove "test-" and ".txt"
        assert re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}$', timestamp_part)

    def test_works_without_extension(self):
        """Test works when extension is empty string."""
        filename = create_timestamp_filename("test", "")
        assert filename.startswith("test-")
        # Note: Empty extension still adds a dot at the end
        assert filename.endswith(".")

    def test_different_prefixes(self):
        """Test works with different prefixes."""
        filename1 = create_timestamp_filename("backup", "txt")
        filename2 = create_timestamp_filename("log", "json")
        filename3 = create_timestamp_filename("data", "csv")

        assert filename1.startswith("backup-")
        assert filename2.startswith("log-")
        assert filename3.startswith("data-")

        assert filename1.endswith(".txt")
        assert filename2.endswith(".json")
        assert filename3.endswith(".csv")

    def test_timestamp_in_filename_matches_create_file_timestamp(self):
        """Test timestamp in filename matches create_file_timestamp output."""
        timestamp = create_file_timestamp()
        filename = create_timestamp_filename("test", "txt")
        filename_timestamp = filename[5:-4]  # Extract timestamp from filename
        assert filename_timestamp == timestamp


class TestGetCurrentIsoDatetime:
    """Test get_current_iso_datetime function."""

    def test_returns_valid_iso_format(self):
        """Test returns valid ISO datetime format."""
        iso_datetime = get_current_iso_datetime()
        # Should be valid ISO 8601 format
        datetime.fromisoformat(iso_datetime)

    def test_contains_colons_in_time(self):
        """Test contains colons in time part (ISO format)."""
        iso_datetime = get_current_iso_datetime()
        # ISO format should have colons in time
        time_part = iso_datetime.split('T')[1]
        assert ':' in time_part

    def test_differs_from_file_timestamp(self):
        """Test differs from file timestamp format."""
        iso_datetime = get_current_iso_datetime()
        file_timestamp = create_file_timestamp()

        # ISO datetime should have colons, file timestamp should have hyphens
        assert ':' in iso_datetime
        assert ':' not in file_timestamp

    def test_is_parsable(self):
        """Test result is parsable by datetime.fromisoformat."""
        iso_datetime = get_current_iso_datetime()
        dt = datetime.fromisoformat(iso_datetime)
        assert isinstance(dt, datetime)

    def test_within_recent_range(self):
        """Test returns datetime within recent range (not cached)."""
        iso_datetime = get_current_iso_datetime()
        dt = datetime.fromisoformat(iso_datetime)
        now = datetime.now()

        # Should be within 1 second of current time
        diff = abs((now - dt).total_seconds())
        assert diff < 1.0

    def test_format_matches_iso_standard(self):
        """Test format matches ISO 8601 standard."""
        iso_datetime = get_current_iso_datetime()
        # ISO 8601 format: YYYY-MM-DDTHH:MM:SS.ffffff
        assert re.match(r'^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}', iso_datetime)
