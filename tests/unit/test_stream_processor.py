"""
Unit tests for stream processor.
"""

import pytest
from unittest.mock import Mock, MagicMock, patch

import sys

from aicoder.core.stream_processor import StreamProcessor

class TestStreamProcessor:
    """Test StreamProcessor class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.mock_streaming_client = Mock()
        self.processor = StreamProcessor(self.mock_streaming_client)

        # Mock Config reasoning methods to avoid env var interference
        self._patches = [
            patch('aicoder.core.stream_processor.Config.get_reasoning_field', return_value=None),
            patch('aicoder.core.stream_processor.Config.get_possible_reasoning_fields',
                  return_value=['reasoning_content', 'reasoning', 'thinking', 'reasoning_text']),
        ]
        for p in self._patches:
            p.start()

    def teardown_method(self):
        """Tear down test fixtures."""
        for p in self._patches:
            p.stop()

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

    def test_process_stream_with_reasoning_content_field(self):
        """Test processing stream with reasoning_content field (GLM, llama.cpp)."""
        chunks = [
            {
                "choices": [{
                    "delta": {
                        "reasoning_content": "Let me think about this carefully..."
                    }
                }],
                "usage": None
            },
            {
                "choices": [{
                    "delta": {
                        "content": "Here's the answer."
                    }
                }],
                "usage": None
            },
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
        assert result["full_response"] == "Here's the answer."
        assert result["reasoning_content"] == "Let me think about this carefully..."

    def test_process_stream_with_reasoning_field(self):
        """Test processing stream with reasoning field (some OpenAI-compatible endpoints)."""
        chunks = [
            {
                "choices": [{
                    "delta": {
                        "reasoning": "Analyzing the request..."
                    }
                }],
                "usage": None
            },
            {
                "choices": [{
                    "delta": {
                        "content": "Response."
                    }
                }],
                "usage": None
            },
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
        assert result["full_response"] == "Response."
        assert result["reasoning_content"] == "Analyzing the request..."

    def test_process_stream_with_reasoning_text_field(self):
        """Test processing stream with reasoning_text field (other providers)."""
        chunks = [
            {
                "choices": [{
                    "delta": {
                        "reasoning_text": "Thinking..."
                    }
                }],
                "usage": None
            },
            {
                "choices": [{
                    "delta": {
                        "content": "Done."
                    }
                }],
                "usage": None
            },
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
        assert result["full_response"] == "Done."
        assert result["reasoning_content"] == "Thinking..."

    def test_process_stream_uses_first_non_empty_reasoning_field(self):
        """Test that only first non-empty reasoning field is used (avoid duplication)."""
        chunks = [
            {
                "choices": [{
                    "delta": {
                        "reasoning_content": "Reasoning from field 1",
                        "reasoning": "Reasoning from field 2"
                    }
                }],
                "usage": None
            },
            {
                "choices": [{
                    "delta": {
                        "content": "Response."
                    }
                }],
                "usage": None
            },
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
        # Should only capture first field (reasoning_content), not both
        assert result["reasoning_content"] == "Reasoning from field 1"

    def test_process_stream_accumulates_reasoning_across_chunks(self):
        """Test that reasoning content is accumulated across multiple chunks."""
        chunks = [
            {
                "choices": [{
                    "delta": {
                        "reasoning": "Thinking part 1"
                    }
                }],
                "usage": None
            },
            {
                "choices": [{
                    "delta": {
                        "reasoning": "Thinking part 2"
                    }
                }],
                "usage": None
            },
            {
                "choices": [{
                    "delta": {
                        "content": "Answer."
                    }
                }],
                "usage": None
            },
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
        assert result["reasoning_content"] == "Thinking part 1Thinking part 2"

    def test_process_stream_ignores_empty_reasoning_field(self):
        """Test that empty/whitespace-only reasoning fields are skipped."""
        chunks = [
            {
                "choices": [{
                    "delta": {
                        "reasoning_content": "   ",  # Only whitespace
                        "reasoning": None
                    }
                }],
                "usage": None
            },
            {
                "choices": [{
                    "delta": {
                        "reasoning_text": "Actual reasoning"
                    }
                }],
                "usage": None
            },
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
        # Should skip empty fields and use reasoning_text
        assert result["reasoning_content"] == "Actual reasoning"

    def test_process_stream_handles_reasoning_with_content(self):
        """Test processing stream with both reasoning and content in same chunk."""
        chunks = [
            {
                "choices": [{
                    "delta": {
                        "reasoning_content": "Reasoning...",
                        "content": "Content..."
                    }
                }],
                "usage": None
            },
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
        assert result["reasoning_content"] == "Reasoning..."
        assert result["full_response"] == "Content..."

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

        assert "call_1" in accumulated
        assert accumulated["call_1"]["function"]["name"] == "read_file"
        assert accumulated["call_1"]["function"]["arguments"] == "path=\"/test\""

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

        assert accumulated["call_1"]["function"]["arguments"] == "echo hello"

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
        assert "call_1" in accumulated
        assert "call_2" in accumulated

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

        # Should not raise exception; entry created with empty name
        self.processor.accumulate_tool_call(tool_call, accumulated)
        assert accumulated["call_1"]["function"]["name"] == ""

    def test_zen_proxy_parallel_calls_same_index(self):
        """Regression: opencode zen sends index=0 on every chunk. Parallel
        calls must key by id, not index, or args concatenate into one call."""
        chunks = [
            {"index": 0, "id": "fc_tmp_a", "type": "function", "function": {"name": "grep", "arguments": ""}},
            {"index": 0, "function": {"arguments": '{"text":"one"'}},
            {"index": 0, "id": "fc_tmp_b", "type": "function", "function": {"name": "grep", "arguments": ""}},
            {"index": 0, "function": {"arguments": ',"path":"a"}'}},
            {"index": 0, "id": "fc_tmp_c", "type": "function", "function": {"name": "grep", "arguments": ""}},
            {"index": 0, "function": {"arguments": '{"text":"two"'}},
        ]
        accumulated = {}
        for c in chunks:
            self.processor.accumulate_tool_call(c, accumulated)

        assert len(accumulated) == 3
        assert accumulated["fc_tmp_a"]["function"]["arguments"] == '{"text":"one"'
        assert accumulated["fc_tmp_a"]["function"]["name"] == "grep"
        assert accumulated["fc_tmp_b"]["function"]["arguments"] == ',"path":"a"}'
        assert accumulated["fc_tmp_b"]["function"]["name"] == "grep"
        assert accumulated["fc_tmp_c"]["function"]["arguments"] == '{"text":"two"'

    def test_args_delta_unmapped_index_goes_to_last_active(self):
        """Args delta with an index never seen falls back to the most
        recently touched call."""
        tool_call1 = {
            "index": 0,
            "id": "call_1",
            "type": "function",
            "function": {"name": "read_file", "arguments": ""}
        }
        args_delta = {"index": 5, "function": {"arguments": '{"path":"x"}'}}

        accumulated = {}
        self.processor.accumulate_tool_call(tool_call1, accumulated)
        self.processor.accumulate_tool_call(args_delta, accumulated)

        assert accumulated["call_1"]["function"]["arguments"] == '{"path":"x"}'

    def test_id_less_provider_name_starts_new_call(self):
        """Providers without ids: name-bearing chunk starts a new call."""
        tool_call1 = {"index": 0, "type": "function", "function": {"name": "grep", "arguments": ""}}
        tool_call2 = {"index": 0, "type": "function", "function": {"name": "ls", "arguments": ""}}

        accumulated = {}
        self.processor.accumulate_tool_call(tool_call1, accumulated)
        self.processor.accumulate_tool_call(tool_call2, accumulated)

        assert len(accumulated) == 2
        assert list(accumulated) == ["tool_call_0", "tool_call_1"]
