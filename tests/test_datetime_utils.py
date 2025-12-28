"""
Test datetime_utils module
Tests for
"""

import re
from aicoder.utils.datetime_utils import (
    create_file_timestamp,
    create_timestamp_filename,
    get_current_iso_datetime,
)


def test_create_file_timestamp():
    """Test timestamp format"""
    timestamp = create_file_timestamp()

    # Should be 19 chars long (first 19 of ISO with replacements)
    assert len(timestamp) == 19, f"Expected 19 chars, got {len(timestamp)}"

    # Should match pattern YYYY-MM-DDTHH-MM-SS
    assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}", timestamp), (
        f"Invalid format: {timestamp}"
    )

    # Should not contain colons or dots
    assert ":" not in timestamp and "." not in timestamp, (
        f"Contains illegal chars: {timestamp}"
    )


def test_create_timestamp_filename():
    """Test filename creation"""
    filename = create_timestamp_filename("test", "txt")

    # Should have prefix, timestamp, and extension
    assert filename.startswith("test-"), f"Missing prefix: {filename}"
    assert filename.endswith(".txt"), f"Missing extension: {filename}"

    # Extract timestamp part and test format
    timestamp_part = filename[5:-4]
    assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}-\d{2}-\d{2}", timestamp_part), (
        f"Invalid timestamp: {timestamp_part}"
    )


def test_get_current_iso_datetime():
    """Test ISO datetime"""
    iso = get_current_iso_datetime()

    # Should be valid ISO format
    assert "T" in iso, f"Missing T separator: {iso}"
    assert re.match(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}", iso), (
        f"Invalid ISO format: {iso}"
    )

    # Should end with Z or timezone info
    assert iso.endswith("Z") or "+" in iso or "-" in iso[-6:], (
        f"Missing timezone: {iso}"
    )
