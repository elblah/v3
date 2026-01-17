"""
Tests for JSONL utilities
"""

import pytest
import tempfile
import os


class TestJsonlUtils:
    """Test JSONL utility functions"""

    def test_read_file_empty(self):
        """Test reading empty JSONL file"""
        from aicoder.utils.jsonl_utils import read_file

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "empty.jsonl")
            with open(path, "w") as f:
                pass  # Create empty file

            result = read_file(path)
            assert result == []

    def test_read_file_single_line(self):
        """Test reading JSONL file with single line"""
        from aicoder.utils.jsonl_utils import read_file

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "single.jsonl")
            with open(path, "w") as f:
                f.write('{"key": "value"}\n')

            result = read_file(path)
            assert result == [{"key": "value"}]

    def test_read_file_multiple_lines(self):
        """Test reading JSONL file with multiple lines"""
        from aicoder.utils.jsonl_utils import read_file

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "multiple.jsonl")
            with open(path, "w") as f:
                f.write('{"id": 1}\n')
                f.write('{"id": 2}\n')
                f.write('{"id": 3}\n')

            result = read_file(path)
            assert result == [{"id": 1}, {"id": 2}, {"id": 3}]

    def test_read_file_skips_invalid_lines(self):
        """Test that invalid JSON lines are skipped"""
        from aicoder.utils.jsonl_utils import read_file

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "mixed.jsonl")
            with open(path, "w") as f:
                f.write('{"valid": true}\n')
                f.write('not valid json\n')
                f.write('{"also": "valid"}\n')
                f.write('still not valid\n')

            result = read_file(path)
            assert result == [{"valid": True}, {"also": "valid"}]

    def test_read_file_file_not_found(self):
        """Test reading non-existent file returns empty list"""
        from aicoder.utils.jsonl_utils import read_file

        result = read_file("/nonexistent/file.jsonl")
        assert result == []

    def test_write_file(self):
        """Test writing JSONL file"""
        from aicoder.utils.jsonl_utils import write_file, read_file

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "output.jsonl")
            messages = [
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there"},
            ]

            write_file(path, messages)

            # Verify round-trip
            result = read_file(path)
            assert result == messages

    def test_write_file_with_unicode(self):
        """Test writing JSONL with unicode characters"""
        from aicoder.utils.jsonl_utils import write_file, read_file

        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "unicode.jsonl")
            messages = [
                {"content": "Hello 世界 🌍"},
            ]

            write_file(path, messages)

            result = read_file(path)
            assert result[0]["content"] == "Hello 世界 🌍"
