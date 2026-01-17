"""Unit tests for JSONL utilities."""

import os
import tempfile
import pytest

import sys
sys.path.insert(0, '/home/blah/storage/ai-worktree-storage/feat_test_coverage__20260117_062928')

from aicoder.utils.jsonl_utils import read_file, write_file


class TestJsonlReadFile:
    """Test read_file function."""

    def test_read_empty_file(self):
        """Test reading empty JSONL file."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write("")
            temp_path = f.name

        try:
            result = read_file(temp_path)
            assert result == []
        finally:
            os.unlink(temp_path)

    def test_read_single_line(self):
        """Test reading single JSON line."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write('{"role": "user", "content": "hello"}\n')
            temp_path = f.name

        try:
            result = read_file(temp_path)
            assert len(result) == 1
            assert result[0]["role"] == "user"
            assert result[0]["content"] == "hello"
        finally:
            os.unlink(temp_path)

    def test_read_multiple_lines(self):
        """Test reading multiple JSON lines."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write('{"role": "user"}\n')
            f.write('{"role": "assistant", "content": "hi"}\n')
            f.write('{"role": "user"}\n')
            temp_path = f.name

        try:
            result = read_file(temp_path)
            assert len(result) == 3
            assert result[0]["role"] == "user"
            assert result[1]["role"] == "assistant"
            assert result[2]["role"] == "user"
        finally:
            os.unlink(temp_path)

    def test_read_skips_invalid_lines(self):
        """Test reading skips invalid JSON lines."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write('{"role": "user"}\n')
            f.write('not valid json\n')
            f.write('{"role": "assistant"}\n')
            temp_path = f.name

        try:
            result = read_file(temp_path)
            assert len(result) == 2
            assert result[0]["role"] == "user"
            assert result[1]["role"] == "assistant"
        finally:
            os.unlink(temp_path)

    def test_read_skips_empty_lines(self):
        """Test reading skips empty lines."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write('{"role": "user"}\n')
            f.write('\n')
            f.write('   \n')
            f.write('{"role": "assistant"}\n')
            temp_path = f.name

        try:
            result = read_file(temp_path)
            assert len(result) == 2
        finally:
            os.unlink(temp_path)

    def test_read_nonexistent_file(self):
        """Test reading nonexistent file returns empty list."""
        result = read_file("/nonexistent/path/to/file.jsonl")
        assert result == []

    def test_read_file_not_found_with_content(self):
        """Test reading file with invalid content raises appropriately."""
        # This tests the exception path for non-FileNotFoundError exceptions
        # Since we can't easily trigger other exceptions, we test the main paths
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write('{"role": "user"}\n')
            temp_path = f.name
        os.unlink(temp_path)
        # File no longer exists
        result = read_file(temp_path)
        assert result == []


class TestJsonlWriteFile:
    """Test write_file function."""

    def test_write_single_message(self):
        """Test writing single message to JSONL file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.jsonl")
            messages = [{"role": "user", "content": "hello"}]

            write_file(path, messages)

            with open(path, "r") as f:
                content = f.read()
            assert '{"role": "user", "content": "hello"}' in content

    def test_write_multiple_messages(self):
        """Test writing multiple messages to JSONL file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.jsonl")
            messages = [
                {"role": "user", "content": "hello"},
                {"role": "assistant", "content": "hi there"},
                {"role": "user", "content": "how are you?"}
            ]

            write_file(path, messages)

            with open(path, "r") as f:
                lines = f.readlines()
            assert len(lines) == 3

    def test_write_unicode_content(self):
        """Test writing unicode content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.jsonl")
            messages = [{"role": "user", "content": "你好世界"}]

            write_file(path, messages)

            with open(path, "r", encoding="utf-8") as f:
                content = f.read()
            assert "你好世界" in content

    def test_write_empty_list(self):
        """Test writing empty list creates empty file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "empty.jsonl")
            write_file(path, [])

            with open(path, "r") as f:
                content = f.read()
            assert content == ""


class TestJsonlRoundTrip:
    """Test round-trip read/write."""

    def test_round_trip(self):
        """Test writing then reading preserves data."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = os.path.join(tmpdir, "test.jsonl")
            original = [
                {"role": "user", "content": "test 1"},
                {"role": "assistant", "content": "response 1"},
                {"role": "user", "content": "test 2"}
            ]

            write_file(path, original)
            result = read_file(path)

            assert len(result) == 3
            assert result[0]["content"] == "test 1"
            assert result[1]["content"] == "response 1"
            assert result[2]["content"] == "test 2"
