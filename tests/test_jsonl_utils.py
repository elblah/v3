"""Tests for JSONL utilities module"""

import os
import tempfile
import pytest
from aicoder.utils import jsonl_utils


class TestJsonlReadFile:
    """Tests for jsonl_utils.read_file function"""

    def test_read_empty_file(self):
        """Test reading an empty JSONL file returns empty list"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write("")
            temp_path = f.name
        try:
            result = jsonl_utils.read_file(temp_path)
            assert result == []
        finally:
            os.unlink(temp_path)

    def test_read_single_line_jsonl(self):
        """Test reading a single line JSONL file"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write('{"role": "user", "content": "hello"}\n')
            temp_path = f.name
        try:
            result = jsonl_utils.read_file(temp_path)
            assert len(result) == 1
            assert result[0] == {"role": "user", "content": "hello"}
        finally:
            os.unlink(temp_path)

    def test_read_multiple_lines_jsonl(self):
        """Test reading multiple line JSONL file"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write('{"role": "user", "content": "hello"}\n')
            f.write('{"role": "assistant", "content": "hi"}\n')
            f.write('{"role": "user", "content": "how are you?"}\n')
            temp_path = f.name
        try:
            result = jsonl_utils.read_file(temp_path)
            assert len(result) == 3
            assert result[0] == {"role": "user", "content": "hello"}
            assert result[1] == {"role": "assistant", "content": "hi"}
            assert result[2] == {"role": "user", "content": "how are you?"}
        finally:
            os.unlink(temp_path)

    def test_read_file_with_blank_lines(self):
        """Test reading JSONL file with blank lines (should skip them)"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write('{"role": "user", "content": "hello"}\n')
            f.write('\n')
            f.write('{"role": "assistant", "content": "hi"}\n')
            f.write('   \n')  # Whitespace only
            temp_path = f.name
        try:
            result = jsonl_utils.read_file(temp_path)
            assert len(result) == 2
        finally:
            os.unlink(temp_path)

    def test_read_file_with_invalid_json_lines(self):
        """Test reading JSONL file with invalid JSON lines (should skip them)"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write('{"role": "user", "content": "hello"}\n')
            f.write('not valid json\n')
            f.write('{"role": "assistant", "content": "hi"}\n')
            f.write('{invalid: json}\n')
            temp_path = f.name
        try:
            result = jsonl_utils.read_file(temp_path)
            assert len(result) == 2
            assert result[0] == {"role": "user", "content": "hello"}
            assert result[1] == {"role": "assistant", "content": "hi"}
        finally:
            os.unlink(temp_path)

    def test_read_nonexistent_file_returns_empty_list(self):
        """Test reading a non-existent file returns empty list"""
        result = jsonl_utils.read_file("/nonexistent/path/file.jsonl")
        assert result == []

    def test_read_file_with_whitespace_lines(self):
        """Test reading JSONL file with lines containing only whitespace"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write('{"role": "user"}\n')
            f.write('  \n')
            f.write('\t\n')
            f.write('{"role": "assistant"}\n')
            temp_path = f.name
        try:
            result = jsonl_utils.read_file(temp_path)
            assert len(result) == 2
        finally:
            os.unlink(temp_path)


class TestJsonlWriteFile:
    """Tests for jsonl_utils.write_file function"""

    def test_write_single_message(self):
        """Test writing a single message to JSONL file"""
        messages = [{"role": "user", "content": "hello"}]
        with tempfile.NamedTemporaryFile(mode='r', suffix='.jsonl', delete=False) as f:
            temp_path = f.name
        try:
            jsonl_utils.write_file(temp_path, messages)
            with open(temp_path, 'r') as f:
                content = f.read()
            assert content == '{"role": "user", "content": "hello"}\n'
        finally:
            os.unlink(temp_path)

    def test_write_multiple_messages(self):
        """Test writing multiple messages to JSONL file"""
        messages = [
            {"role": "user", "content": "hello"},
            {"role": "assistant", "content": "hi"},
            {"role": "user", "content": "how are you?"},
        ]
        with tempfile.NamedTemporaryFile(mode='r', suffix='.jsonl', delete=False) as f:
            temp_path = f.name
        try:
            jsonl_utils.write_file(temp_path, messages)
            with open(temp_path, 'r') as f:
                lines = f.readlines()
            assert len(lines) == 3
            assert lines[0] == '{"role": "user", "content": "hello"}\n'
            assert lines[1] == '{"role": "assistant", "content": "hi"}\n'
            assert lines[2] == '{"role": "user", "content": "how are you?"}\n'
        finally:
            os.unlink(temp_path)

    def test_write_empty_list(self):
        """Test writing an empty list to JSONL file"""
        messages = []
        with tempfile.NamedTemporaryFile(mode='r', suffix='.jsonl', delete=False) as f:
            temp_path = f.name
        try:
            jsonl_utils.write_file(temp_path, messages)
            with open(temp_path, 'r') as f:
                content = f.read()
            assert content == ""
        finally:
            os.unlink(temp_path)

    def test_write_to_existing_directory(self):
        """Test that write_file works when directory exists"""
        messages = [{"role": "test"}]
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = os.path.join(temp_dir, "test.jsonl")
            jsonl_utils.write_file(temp_path, messages)
            assert os.path.exists(temp_path)
            with open(temp_path, 'r') as f:
                content = f.read()
            assert content == '{"role": "test"}\n'

    def test_write_with_unicode_characters(self):
        """Test writing messages with unicode characters"""
        messages = [{"role": "user", "content": "Hello 世界 🌍"}]
        with tempfile.NamedTemporaryFile(mode='r', suffix='.jsonl', delete=False) as f:
            temp_path = f.name
        try:
            jsonl_utils.write_file(temp_path, messages)
            with open(temp_path, 'r', encoding='utf-8') as f:
                content = f.read()
            # Check that unicode is preserved
            assert "世界" in content
            assert "🌍" in content
        finally:
            os.unlink(temp_path)

    def test_write_with_special_characters(self):
        """Test writing messages with special characters (quotes, newlines)"""
        messages = [{"role": "user", "content": "Line1\nLine2\tTab"}]
        with tempfile.NamedTemporaryFile(mode='r', suffix='.jsonl', delete=False) as f:
            temp_path = f.name
        try:
            jsonl_utils.write_file(temp_path, messages)
            with open(temp_path, 'r') as f:
                content = f.read()
            # Should be valid JSON on a single line
            lines = content.strip().split('\n')
            assert len(lines) == 1
        finally:
            os.unlink(temp_path)


class TestJsonlRoundTrip:
    """Tests for JSONL round-trip (read/write)"""

    def test_write_then_read_returns_equivalent_data(self):
        """Test that writing and reading back gives equivalent data"""
        original_messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"},
        ]
        with tempfile.NamedTemporaryFile(mode='r', suffix='.jsonl', delete=False) as f:
            temp_path = f.name
        try:
            jsonl_utils.write_file(temp_path, original_messages)
            read_messages = jsonl_utils.read_file(temp_path)
            assert read_messages == original_messages
        finally:
            os.unlink(temp_path)

    def test_read_write_preserves_unicode(self):
        """Test that read/write preserves unicode characters"""
        original_messages = [
            {"role": "user", "content": "Japanese: こんにちは"},
            {"role": "assistant", "content": "Chinese: 你好"},
            {"role": "user", "content": "Emoji: 🎉🎂"},
        ]
        with tempfile.NamedTemporaryFile(mode='r', suffix='.jsonl', delete=False) as f:
            temp_path = f.name
        try:
            jsonl_utils.write_file(temp_path, original_messages)
            read_messages = jsonl_utils.read_file(temp_path)
            assert read_messages == original_messages
        finally:
            os.unlink(temp_path)
