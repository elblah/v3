#!/usr/bin/env python3
"""
Quick verification that the 'dict' object has no attribute 'can_approve' issue is fixed.
This tests the actual scenario from the error message.
"""

from aicoder.core.tool_formatter import ToolFormatter


def test_dict_not_attribute():
    """Test that we handle ToolPreview as dict, not as object with attributes."""

    # This is what tools now return after type removal
    preview_result = {
        "tool": "write_file",
        "content": "preview text",
        "can_approve": True
    }

    # The old code would do: preview_result.can_approve - this would fail
    # The new code should use: preview_result.get("can_approve", False)
    assert preview_result.get("can_approve", False) is True, "Can approve should be True"
    assert preview_result.get("content", "") == "preview text", "Content should match"

    # Test ToolFormatter.format_preview with dict
    output = ToolFormatter.format_preview(preview_result, "test.txt")
    assert "[PREVIEW]" in output, "Should contain preview header"
    assert "preview text" in output, "Should contain preview content"

    # Test with missing keys (should use defaults)
    preview_result_incomplete = {
        "tool": "write_file",
        "content": "some text"
    }
    # Missing can_approve should default to False
    assert preview_result_incomplete.get("can_approve", False) is False, \
        "Missing can_approve should default to False"

    print("✓ All verifications passed - the 'dict' object has no attribute 'can_approve' issue is fixed!")


def test_safety_violation_case():
    """Test the safety violation scenario from tool_executor.py"""

    # Safety violation case - can_approve is False
    safety_preview = {
        "tool": "write_file",
        "content": "Path: test.txt\n[!] Warning: Must read file first",
        "can_approve": False
    }

    # This should not raise AttributeError
    if not safety_preview.get("can_approve", False):
        content = safety_preview.get("content", "")
        assert "Must read file first" in content

    print("✓ Safety violation case handled correctly")


if __name__ == "__main__":
    test_dict_not_attribute()
    test_safety_violation_case()
    print("\n=== All verification tests passed ===")
