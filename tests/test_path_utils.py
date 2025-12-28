"""
Test path_utils module
Tests for
"""

from aicoder.utils.path_utils import is_safe_path, validate_path, validate_tool_path


def test_is_safe_path():
    """Test path safety detection"""
    assert is_safe_path("normal/path") == True
    assert is_safe_path("file.txt") == True
    assert is_safe_path("../dangerous") == False
    assert is_safe_path("../../very/dangerous") == False
    assert is_safe_path("safe/../") == False  # Contains parent traversal


def test_validate_path():
    """Test path validation with logging"""
    import io
    import sys

    # Capture stdout
    captured_output = io.StringIO()
    sys.stdout = captured_output

    # Safe path should return True and not log
    result = validate_path("safe/path")
    assert result == True
    assert "Sandbox" not in captured_output.getvalue()

    # Unsafe path should return False and log
    result = validate_path("../dangerous", "test_operation")
    assert result == False
    assert "Sandbox" in captured_output.getvalue()

    # Restore stdout
    sys.stdout = sys.__stdout__


def test_validate_tool_path():
    """Test tool path validation"""
    import io
    import sys

    # Capture stdout
    captured_output = io.StringIO()
    sys.stdout = captured_output

    # Safe path should return True and not log
    result = validate_tool_path("safe/path", "test_tool")
    assert result == True
    assert "Sandbox-fs" not in captured_output.getvalue()

    # Unsafe path should return False and log
    result = validate_tool_path("../dangerous", "test_tool")
    assert result == False
    assert "Sandbox-fs" in captured_output.getvalue()

    # Restore stdout
    sys.stdout = sys.__stdout__
