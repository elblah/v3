"""
Unit tests for stream processor.
"""

import pytest
from unittest.mock import Mock, MagicMock

import sys
sys.path.insert(0, '/home/blah/storage/ai-worktree-storage/feat_test_coverage__20260117_062928')

from aicoder.core.stream_processor import StreamProcessor


class TestStreamProcessor:
    """Test StreamProcessor class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_streaming_client = Mock()
        self.processor = StreamProcessor(self.mock_streaming_client)

    def test_process_stream_basic_content(self):
        """Test processing stream with basic content."""
        # Create mock chunks
        chunks = [
            {"choices": [{"delta": {"content": "Hello "}}], "usage": None},
            {"choices": [{"delta": {"content": "world!"}}], "usage": None},
        ]
        self.mock_streaming_client.stream_request.return_value = iter(chunks)

        is_processing = Mock(return_value=True)
        process_chunk = Mock()

        result = self.processor.process_stream(
            [{"role": "user", "content": "hi"}],
            is_processing,
            process_chunk
        )

        assert result["should_continue"] == True
        assert result["full_response"] == "Hello world!"
        assert len(result["accumulated_tool_calls"]) == 0

    def test_process_stream_with_tool_calls(self):
        """Test processing stream with tool calls."""
        tool_call = {
            "index": 0,
            "id": "call_123",
            "type": "function",
            "function": {"name": "run_shell_command", "arguments": "echo test"}
        }
        chunks = [
            {"choices": [{"delta": {"tool_calls": [tool_call]}}], "usage": None},
        ]
        self.mock_streaming_client.stream_request.return_value = iter(chunks)

        is_processing = Mock(return_value=True)
        process_chunk = Mock()

        result = self.processor.process_stream(
            [{"role": "user", "content": "run command"}],
            is_processing,
            process_chunk
        )

        assert result["should_continue"] == True
        process_chunk.assert_called_once()

    def test_process_stream_user_interrupted(self):
        """Test processing stream when user interrupts."""
        # Need multiple chunks to test interruption during processing
        # is_processing is called before each chunk
        chunks = [
            {"choices": [{"delta": {"content": "Partial "}}], "usage": None},
            {"choices": [{"delta": {"content": "more "}}], "usage": None},
            {"choices": [{"delta": {"content": "text"}}], "usage": None},
        ]
        self.mock_streaming_client.stream_request.return_value = iter(chunks)

        # First two calls return True, third returns False (interrupted)
        is_processing = Mock(side_effect=[True, True, False])
        process_chunk = Mock()

        result = self.processor.process_stream(
            [{"role": "user", "content": "hi"}],
            is_processing,
            process_chunk
        )

        # Should stop processing after is_processing returns False
        assert result["should_continue"] == False
        # Chunks 1 and 2 processed before interruption = "Partial more "
        assert result["full_response"] == "Partial more "

    def test_process_stream_empty_response(self):
        """Test processing stream with empty response."""
        chunks = [
            {"choices": [{}], "usage": None},
        ]
        self.mock_streaming_client.stream_request.return_value = iter(chunks)

        is_processing = Mock(return_value=True)
        process_chunk = Mock()

        result = self.processor.process_stream(
            [{"role": "user", "content": "hi"}],
            is_processing,
            process_chunk
        )

        assert result["should_continue"] == True
        assert result["full_response"] == ""

    def test_process_stream_missing_choices(self):
        """Test processing stream with missing choices."""
        chunks = [
            {"other": "data"},  # No choices key
        ]
        self.mock_streaming_client.stream_request.return_value = iter(chunks)

        is_processing = Mock(return_value=True)
        process_chunk = Mock()

        result = self.processor.process_stream(
            [{"role": "user", "content": "hi"}],
            is_processing,
            process_chunk
        )

        assert result["should_continue"] == True
        assert result["full_response"] == ""

    def test_process_stream_with_usage_stats(self):
        """Test processing stream updates token stats."""
        chunks = [
            {
                "choices": [{"delta": {"content": "test"}}],
                "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}
            },
        ]
        self.mock_streaming_client.stream_request.return_value = iter(chunks)

        is_processing = Mock(return_value=True)
        process_chunk = Mock()

        self.processor.process_stream(
            [{"role": "user", "content": "hi"}],
            is_processing,
            process_chunk
        )

        # Verify token stats were updated
        self.mock_streaming_client.update_token_stats.assert_called_once_with({
            "prompt_tokens": 10,
            "completion_tokens": 5,
            "total_tokens": 15
        })

    def test_process_stream_error_handling(self):
        """Test processing stream handles errors."""
        self.mock_streaming_client.stream_request.side_effect = Exception("Connection error")

        is_processing = Mock(return_value=True)
        process_chunk = Mock()

        result = self.processor.process_stream(
            [{"role": "user", "content": "hi"}],
            is_processing,
            process_chunk
        )

        assert result["should_continue"] == False
        assert result["error"] == "Connection error"
        assert result["full_response"] == ""


class TestAccumulateToolCall:
    """Test accumulate_tool_call method."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_streaming_client = Mock()
        self.processor = StreamProcessor(self.mock_streaming_client)

    def test_accumulate_new_tool_call(self):
        """Test accumulating a new tool call."""
        tool_call = {
            "index": 0,
            "id": "call_1",
            "type": "function",
            "function": {"name": "read_file", "arguments": "path=\"/test\""}
        }
        accumulated = {}

        self.processor.accumulate_tool_call(tool_call, accumulated)

        assert 0 in accumulated
        assert accumulated[0]["function"]["name"] == "read_file"
        assert accumulated[0]["function"]["arguments"] == "path=\"/test\""

    def test_accumulate_arguments(self):
        """Test accumulating arguments for existing tool call."""
        tool_call1 = {
            "index": 0,
            "id": "call_1",
            "type": "function",
            "function": {"name": "run_shell_command", "arguments": "echo "}
        }
        tool_call2 = {
            "index": 0,
            "function": {"arguments": "hello"}
        }

        accumulated = {}
        self.processor.accumulate_tool_call(tool_call1, accumulated)
        self.processor.accumulate_tool_call(tool_call2, accumulated)

        assert accumulated[0]["function"]["arguments"] == "echo hello"

    def test_accumulate_multiple_tool_calls(self):
        """Test accumulating multiple tool calls."""
        tool_call1 = {
            "index": 0,
            "id": "call_1",
            "type": "function",
            "function": {"name": "read_file", "arguments": "path"}
        }
        tool_call2 = {
            "index": 1,
            "id": "call_2",
            "type": "function",
            "function": {"name": "run_shell_command", "arguments": "cmd"}
        }

        accumulated = {}
        self.processor.accumulate_tool_call(tool_call1, accumulated)
        self.processor.accumulate_tool_call(tool_call2, accumulated)

        assert len(accumulated) == 2
        assert 0 in accumulated
        assert 1 in accumulated

    def test_accumulate_invalid_tool_call(self):
        """Test accumulating invalid tool call (not dict)."""
        accumulated = {}
        result = self.processor.accumulate_tool_call("not a dict", accumulated)
        # Should not raise exception, just return
        assert accumulated == {}

    def test_accumulate_missing_function_name(self):
        """Test accumulating tool call without function name."""
        tool_call = {
            "index": 0,
            "id": "call_1",
            "type": "function",
            "function": {}  # No name
        }
        accumulated = {}

        # Should not raise exception
        self.processor.accumulate_tool_call(tool_call, accumulated)
        # Empty accumulated since no name
        assert 0 not in accumulated or "name" not in accumulated[0].get("function", {})
