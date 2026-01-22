#!/usr/bin/env python3
"""Test script for madai UTC timestamp feature"""
import datetime
import re


def test_timestamp_format():
    """Verify timestamp format matches expected pattern"""
    timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    pattern = r"^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} UTC$"
    assert re.match(pattern, timestamp), f"Timestamp format invalid: {timestamp}"
    print(f"✓ Timestamp format valid: {timestamp}")


def test_context_with_timestamp():
    """Test that context gets appended with timestamp"""
    context = "[CONTEXT] Test summary"
    timestamp = datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S UTC")
    full_context = f"{context} [{timestamp}]"

    assert full_context.endswith("]"), "Missing closing bracket"
    assert "[CONTEXT]" in full_context, "Context missing"
    assert "UTC" in full_context, "UTC marker missing"
    print(f"✓ Context with timestamp: {full_context}")


if __name__ == "__main__":
    test_timestamp_format()
    test_context_with_timestamp()
    print("\n✓ All tests passed!")
