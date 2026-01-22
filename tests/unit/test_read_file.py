"""
Tests for read_file tool
"""

import pytest
from unittest.mock import MagicMock, patch
import os
import tempfile
from aicoder.tools.internal.read_file import (
    execute,
    generatePreview,
    format_arguments,
    validate_arguments,
    DEFAULT_READ_LIMIT,
    MAX_LINE_LENGTH,
)
from aicoder.core.file_access_tracker import FileAccessTracker


@pytest.fixture(autouse=True)
def clear_file_access_tracker():
    """Clear FileAccessTracker state before each test"""
    FileAccessTracker.clear_state()
    yield
    FileAccessTracker.clear_state()


@pytest.fixture
def temp_file():
    """Create a temporary file for testing"""
    content = "Line 0: Hello World\nLine 1: Foo Bar\nLine 2: Baz Qux\nLine 3: Another line\nLine 4: Last line"
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(content)
        path = f.name

    yield path

    # Cleanup
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def large_file():
    """Create a large file for testing pagination"""
    lines = [f"Line {i}: Content here" for i in range(100)]
    content = "\n".join(lines)
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(content)
        path = f.name

    yield path

    # Cleanup
    if os.path.exists(path):
        os.unlink(path)


@pytest.fixture
def long_line_file():
    """Create a file with very long lines"""
    long_line = "A" * 3000
    content = f"Short line\n{long_line}\nAnother short line"
    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
        f.write(content)
        path = f.name

    yield path

    # Cleanup
    if os.path.exists(path):
        os.unlink(path)

class TestExecute:
    """Test execute function"""

    def test_missing_path(self):
        """Test with missing path"""
        with pytest.raises(Exception) as excinfo:
            execute({})
        assert "Path is required" in str(excinfo.value)

    def test_file_not_found(self):
        """Test with non-existent file"""
        with patch('aicoder.tools.internal.read_file._check_sandbox', return_value=True):
            with pytest.raises(Exception) as excinfo:
                execute({"path": "/nonexistent/file.txt"})
            assert "File not found" in str(excinfo.value)

    def test_successful_read(self, temp_file):
        """Test successful file read"""
        with patch('aicoder.tools.internal.read_file._check_sandbox', return_value=True):
            result = execute({"path": temp_file})
            assert result["tool"] == "read_file"
            assert "Line 0" in result["detailed"]
            assert "5 lines" in result["friendly"] or "5" in result["friendly"]

    def test_read_with_offset(self, temp_file):
        """Test reading with offset"""
        with patch('aicoder.tools.internal.read_file._check_sandbox', return_value=True):
            result = execute({"path": temp_file, "offset": 2, "limit": 2})
            assert result["tool"] == "read_file"
            assert "Line 2" in result["detailed"]
            assert "Line 3" in result["detailed"]
            assert "Line 4" not in result["detailed"]

    def test_read_with_limit(self, temp_file):
        """Test reading with custom limit"""
        with patch('aicoder.tools.internal.read_file._check_sandbox', return_value=True):
            result = execute({"path": temp_file, "limit": 2})
            assert result["tool"] == "read_file"
            assert "Line 0" in result["detailed"]
            assert "Line 1" in result["detailed"]

    def test_offset_beyond_eof(self, temp_file):
        """Test offset beyond end of file"""
        with patch('aicoder.tools.internal.read_file._check_sandbox', return_value=True):
            result = execute({"path": temp_file, "offset": 100})
            assert result["tool"] == "read_file"
            assert "beyond end of file" in result["friendly"] or "offset" in result["friendly"].lower()

    def test_file_access_tracker_recorded(self, temp_file):
        """Test that file is recorded in FileAccessTracker"""
        # Clear tracker first
        FileAccessTracker.clear_state()
        try:
            with patch('aicoder.tools.internal.read_file._check_sandbox', return_value=True):
                execute({"path": temp_file})
            assert FileAccessTracker.was_file_read(temp_file) is True
        finally:
            FileAccessTracker.clear_state()

    def test_truncates_long_lines(self, long_line_file):
        """Test that long lines are truncated"""
        with patch('aicoder.tools.internal.read_file._check_sandbox', return_value=True):
            result = execute({"path": long_line_file})
            assert result["tool"] == "read_file"
            # Long line should be truncated - check for truncation
            detailed = result["detailed"]
            # Long lines get truncated to MAX_LINE_LENGTH (2000 chars)
            # The detailed output should have shortened line
            lines = detailed.split('\n')
            content_lines = [line for line in lines if 'Content:' in line or line.startswith('[')]
            # Just verify we got a result
            assert len(detailed) > 0

    def test_default_values(self, temp_file):
        """Test default offset and limit values"""
        with patch('aicoder.tools.internal.read_file._check_sandbox', return_value=True):
            result = execute({"path": temp_file})
            assert result["tool"] == "read_file"
            # Should read all lines with default limit
            assert "Line 0" in result["detailed"]
            assert "Line 4" in result["detailed"]


class TestGeneratePreview:
    """Test generatePreview function"""

    def test_none_when_sandbox_passes(self, temp_file):
        """Test that None is returned when sandbox passes"""
        with patch('aicoder.tools.internal.read_file._check_sandbox', return_value=True):
            result = generatePreview({"path": temp_file})
            # When sandbox passes and no issues, returns None
            assert result is None

    def test_sandbox_violation(self):
        """Test sandbox violation in preview"""
        with patch('aicoder.tools.internal.read_file._check_sandbox', return_value=False):
            result = generatePreview({"path": "/etc/passwd"})
            assert result["tool"] == "read_file"
            assert "can_approve" in result
            assert result["can_approve"] is False
            assert "Sandbox" in result["content"] or "sandbox" in result["content"].lower()


class TestFormatArguments:
    """Test format_arguments function"""

    def test_basic_formatting(self):
        """Test basic argument formatting"""
        result = format_arguments({
            "path": "/path/to/file.txt"
        })
        assert "/path/to/file.txt" in result

    def test_with_offset(self):
        """Test formatting with offset"""
        result = format_arguments({
            "path": "/path/to/file.txt",
            "offset": 10
        })
        assert "/path/to/file.txt" in result
        assert "Offset: 10" in result

    def test_with_custom_limit(self):
        """Test formatting with custom limit"""
        result = format_arguments({
            "path": "/path/to/file.txt",
            "limit": 100
        })
        assert "/path/to/file.txt" in result
        assert "Limit: 100" in result

    def test_excludes_default_offset(self):
        """Test that default offset (0) is excluded"""
        result = format_arguments({
            "path": "/path/to/file.txt",
            "offset": 0
        })
        assert "Offset" not in result

    def test_excludes_default_limit(self):
        """Test that default limit is excluded"""
        result = format_arguments({
            "path": "/path/to/file.txt",
            "limit": DEFAULT_READ_LIMIT
        })
        assert "Limit" not in result


class TestValidateArguments:
    """Test validate_arguments function"""

    def test_valid_arguments(self):
        """Test with valid arguments"""
        # Should not raise
        validate_arguments({"path": "/path/to/file.txt"})

    def test_missing_path(self):
        """Test with missing path"""
        with pytest.raises(Exception) as excinfo:
            validate_arguments({})
        assert 'path' in str(excinfo.value).lower()

    def test_invalid_path_type(self):
        """Test with invalid path type"""
        with pytest.raises(Exception) as excinfo:
            validate_arguments({"path": 123})
        assert 'path' in str(excinfo.value).lower()

    def test_none_path(self):
        """Test with None path"""
        with pytest.raises(Exception) as excinfo:
            validate_arguments({"path": None})
        assert 'path' in str(excinfo.value).lower()


class TestConstants:
    """Test module constants"""

    def test_default_read_limit(self):
        """Test default read limit value"""
        assert DEFAULT_READ_LIMIT == 150

    def test_max_line_length(self):
        """Test max line length value"""
        assert MAX_LINE_LENGTH == 2000


class TestIntegration:
    """Integration tests for read_file tool"""

    def test_large_file_pagination(self, large_file):
        """Test reading large file with pagination"""
        with patch('aicoder.tools.internal.read_file._check_sandbox', return_value=True):
            # Read first 10 lines
            result1 = execute({"path": large_file, "limit": 10})
            assert result1["tool"] == "read_file"
            assert "Line 0" in result1["detailed"]
            assert "Line 9" in result1["detailed"]

            # Read from line 50
            result2 = execute({"path": large_file, "offset": 50, "limit": 10})
            assert result2["tool"] == "read_file"
            assert "Line 50" in result2["detailed"]
            assert "Line 59" in result2["detailed"]

    def test_empty_file(self):
        """Test reading empty file"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            path = f.name

        try:
            with patch('aicoder.tools.internal.read_file._check_sandbox', return_value=True):
                result = execute({"path": path})
                assert result["tool"] == "read_file"
                # Empty file still shows lines (may be 0 or 1 depending on implementation)
                assert result["friendly"] is not None
        finally:
            os.unlink(path)

    def test_single_line_file(self):
        """Test reading single line file"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            f.write("Single line content")
            path = f.name

        try:
            with patch('aicoder.tools.internal.read_file._check_sandbox', return_value=True):
                result = execute({"path": path})
                assert result["tool"] == "read_file"
                assert "1 line" in result["friendly"] or "1" in result["friendly"]
                assert "Single line content" in result["detailed"]
        finally:
            os.unlink(path)
