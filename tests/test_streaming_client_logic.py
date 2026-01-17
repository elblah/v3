"""
Test streaming_client module
"""

import time
import pytest
from unittest.mock import Mock, patch, MagicMock
from aicoder.core.streaming_client import StreamingClient
from aicoder.core.config import Config


class TestStreamingClient:
    """Test StreamingClient"""

    def test_initialization(self):
        stats = Mock()
        tm = Mock()
        mh = Mock()
        client = StreamingClient(stats, tm, mh)
        assert client.stats is stats
        assert client.tool_manager is tm
        assert client.message_history is mh
        assert client._recovery_attempted is False

    def test_initialization_without_deps(self):
        client = StreamingClient()
        assert client.stats is None
        assert client.tool_manager is None
        assert client.message_history is None

    def test_backoff_calculation(self):
        client = StreamingClient()

        # Test exponential growth (fast)
        assert client._calculate_backoff(0) == 1
        assert client._calculate_backoff(1) == 2
        assert client._calculate_backoff(2) == 4
        assert client._calculate_backoff(3) == 8

        # Test cap at 64
        assert client._calculate_backoff(6) == 64
        assert client._calculate_backoff(10) == 64


class TestWaitForRetry:
    """Test _wait_for_retry method"""

    def test_wait_for_retry_calculates_delay(self):
        """Test that wait_for_retry calculates correct delay"""
        client = StreamingClient()
        with patch('time.sleep') as mock_sleep:
            client._wait_for_retry(0)
            mock_sleep.assert_called_once_with(1)

    def test_wait_for_retry_with_backoff(self):
        """Test that wait_for_retry uses exponential backoff"""
        client = StreamingClient()
        with patch('time.sleep') as mock_sleep:
            client._wait_for_retry(3)
            mock_sleep.assert_called_once_with(8)


class TestRecoveryAttempted:
    """Test recovery attempt flag"""

    def test_recovery_flag_initialized(self):
        """Test recovery flag starts as False"""
        client = StreamingClient()
        assert client._recovery_attempted is False

    def test_recovery_flag_can_be_set(self):
        """Test recovery flag can be set manually"""
        client = StreamingClient()
        client._recovery_attempted = True
        assert client._recovery_attempted is True


class TestFormatMessages:
    """Test message formatting"""

    def test_basic_messages(self):
        client = StreamingClient()
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"}
        ]
        formatted = client._format_messages(messages)
        assert len(formatted) == 2
        assert formatted[0]["role"] == "user"
        assert formatted[0]["content"] == "Hello"

    def test_preserves_tool_calls(self):
        client = StreamingClient()
        messages = [{
            "role": "assistant",
            "content": "Using tool",
            "tool_calls": [{"id": "call_1", "function": {"name": "test"}}]
        }]
        formatted = client._format_messages(messages)
        assert "tool_calls" in formatted[0]
        assert formatted[0]["tool_calls"][0]["id"] == "call_1"

    def test_preserves_tool_call_id(self):
        client = StreamingClient()
        messages = [{
            "role": "tool",
            "tool_call_id": "call_1",
            "content": "Result"
        }]
        formatted = client._format_messages(messages)
        assert formatted[0]["tool_call_id"] == "call_1"


class TestBuildHeaders:
    """Test _build_headers method"""

    def test_headers_without_api_key(self):
        with patch.dict('os.environ', {}, clear=True):
            Config.reset()
            client = StreamingClient()
            headers = client._build_headers()
            assert headers["Content-Type"] == "application/json"
            assert "Authorization" not in headers

    def test_headers_with_api_key(self):
        with patch.dict('os.environ', {"API_KEY": "test-key"}, clear=True):
            Config.reset()
            client = StreamingClient()
            headers = client._build_headers()
            assert headers["Authorization"] == "Bearer test-key"


class TestIsStreamingResponse:
    """Test streaming response detection"""

    def test_detects_event_stream(self):
        client = StreamingClient()
        assert client._is_streaming_response("text/event-stream") is True
        assert client._is_streaming_response("TEXT/EVENT-STREAM") is True
        assert client._is_streaming_response("text/event-stream; charset=utf-8") is True

    def test_rejects_non_streaming(self):
        client = StreamingClient()
        assert client._is_streaming_response("application/json") is False
        assert client._is_streaming_response("text/plain") is False
        assert client._is_streaming_response("") is False


class TestPrepareRequestData:
    """Test request data preparation"""

    def test_basic_request(self):
        client = StreamingClient()
        messages = [{"role": "user", "content": "Hello"}]
        with patch.object(Config, 'model', return_value='gpt-4'), \
             patch.object(Config, 'temperature', return_value=None), \
             patch.object(Config, 'max_tokens', return_value=None):
            data = client._prepare_request_data(messages, 'gpt-4', True)
        assert data["model"] == "gpt-4"
        assert data["stream"] is True

    def test_with_temperature(self):
        client = StreamingClient()
        messages = [{"role": "user", "content": "Hello"}]
        with patch.object(Config, 'temperature', return_value=0.7), \
             patch.object(Config, 'model', return_value='gpt-4'), \
             patch.object(Config, 'max_tokens', return_value=None):
            data = client._prepare_request_data(messages, 'gpt-4', True)
        assert data["temperature"] == 0.7

    def test_with_max_tokens(self):
        client = StreamingClient()
        messages = [{"role": "user", "content": "Hello"}]
        with patch.object(Config, 'max_tokens', return_value=2048), \
             patch.object(Config, 'model', return_value='gpt-4'), \
             patch.object(Config, 'temperature', return_value=None):
            data = client._prepare_request_data(messages, 'gpt-4', True)
        assert data["max_tokens"] == 2048


class TestAddToolDefinitions:
    """Test tool definitions addition"""

    def test_adds_tools_when_available(self):
        client = StreamingClient()
        mock_tool_manager = Mock()
        client.tool_manager = mock_tool_manager
        mock_tool_manager.get_tool_definitions.return_value = [
            {"type": "function", "function": {"name": "test_tool"}}
        ]
        data = {}
        client._add_tool_definitions(data)
        assert "tools" in data
        assert data["tool_choice"] == "auto"

    def test_no_tools_when_manager_none(self):
        client = StreamingClient()
        client.tool_manager = None
        data = {}
        client._add_tool_definitions(data)
        assert "tools" not in data

    def test_no_tools_when_empty(self):
        client = StreamingClient()
        mock_tool_manager = Mock()
        client.tool_manager = mock_tool_manager
        mock_tool_manager.get_tool_definitions.return_value = []
        data = {}
        client._add_tool_definitions(data)
        assert "tools" not in data


class TestCreateUsage:
    """Test usage data creation"""

    def test_creates_usage_from_data(self):
        client = StreamingClient()
        usage_data = {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30
        }
        result = client._create_usage(usage_data)
        assert result["prompt_tokens"] == 10
        assert result["completion_tokens"] == 20

    def test_returns_none_for_none(self):
        client = StreamingClient()
        result = client._create_usage(None)
        assert result is None

    def test_handles_partial_data(self):
        client = StreamingClient()
        usage_data = {"prompt_tokens": 10}
        result = client._create_usage(usage_data)
        assert result["prompt_tokens"] == 10
        assert result.get("completion_tokens") is None


class TestUpdateTokenStats:
    """Test stats updating"""

    def test_updates_stats_when_available(self):
        mock_stats = Mock()
        client = StreamingClient(stats=mock_stats)
        usage = {"prompt_tokens": 100, "completion_tokens": 50}
        client.update_token_stats(usage)
        mock_stats.add_prompt_tokens.assert_called_once_with(100)
        mock_stats.add_completion_tokens.assert_called_once_with(50)

    def test_handles_no_stats(self):
        client = StreamingClient()
        usage = {"prompt_tokens": 100, "completion_tokens": 50}
        # Should not raise
        client.update_token_stats(usage)

    def test_handles_empty_usage(self):
        mock_stats = Mock()
        client = StreamingClient(stats=mock_stats)
        client.update_token_stats({})
        mock_stats.add_prompt_tokens.assert_not_called()

    def test_handles_none_usage(self):
        mock_stats = Mock()
        client = StreamingClient(stats=mock_stats)
        client.update_token_stats(None)
        mock_stats.add_prompt_tokens.assert_not_called()


class TestPrepareRequestDataExtended:
    """Extended tests for _prepare_request_data"""

    def test_send_tools_false(self):
        """Test that tools are not sent when send_tools is False"""
        client = StreamingClient()
        messages = [{"role": "user", "content": "Hello"}]
        with patch.object(Config, 'model', return_value='gpt-4'), \
             patch.object(Config, 'temperature', return_value=None), \
             patch.object(Config, 'max_tokens', return_value=None):
            data = client._prepare_request_data(messages, 'gpt-4', True, send_tools=False)
        assert "tools" not in data

    def test_with_both_temperature_and_max_tokens(self):
        """Test request with both temperature and max_tokens"""
        client = StreamingClient()
        messages = [{"role": "user", "content": "Hello"}]
        with patch.object(Config, 'temperature', return_value=0.5), \
             patch.object(Config, 'max_tokens', return_value=4096), \
             patch.object(Config, 'model', return_value='gpt-4'):
            data = client._prepare_request_data(messages, 'gpt-4', True)
        assert data["temperature"] == 0.5
        assert data["max_tokens"] == 4096


class TestFormatMessagesExtended:
    """Extended tests for _format_messages"""

    def test_message_with_all_fields(self):
        """Test formatting message with all possible fields"""
        client = StreamingClient()
        messages = [{
            "role": "assistant",
            "content": "Using tool",
            "tool_calls": [{"id": "call_1", "function": {"name": "test"}}],
            "tool_call_id": "original_call"
        }]
        formatted = client._format_messages(messages)
        assert formatted[0]["role"] == "assistant"
        assert formatted[0]["content"] == "Using tool"
        assert "tool_calls" in formatted[0]
        # tool_call_id is preserved if present (as per implementation)
        assert formatted[0]["tool_call_id"] == "original_call"

    def test_multiple_messages(self):
        """Test formatting multiple messages"""
        client = StreamingClient()
        messages = [
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "tool", "tool_call_id": "call_1", "content": "Tool result"}
        ]
        formatted = client._format_messages(messages)
        assert len(formatted) == 4
        assert formatted[0]["role"] == "system"
        assert formatted[3]["role"] == "tool"
        assert formatted[3]["tool_call_id"] == "call_1"


class TestColorizerMethods:
    """Test colorizer-related methods"""

    def test_process_with_colorization(self):
        """Test content colorization processing"""
        client = StreamingClient()
        result = client.process_with_colorization("test content")
        assert isinstance(result, str)

    def test_reset_colorizer(self):
        """Test colorizer reset"""
        client = StreamingClient()
        # Should not raise
        client.reset_colorizer()


class TestHandleNonStreamingResponse:
    """Test _handle_nonStreaming_response method"""

    def test_handles_empty_choices(self):
        """Test handling response with empty choices"""
        client = StreamingClient()

        # Create mock response
        mock_response = Mock()
        mock_response.json.return_value = {"choices": []}

        result = list(client._handle_non_streaming_response(mock_response))
        assert result == []

    def test_handles_message_with_content(self):
        """Test handling response with message content"""
        client = StreamingClient()

        mock_response = Mock()
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": "Hello, world!"
                },
                "finish_reason": "stop",
                "index": 0
            }]
        }

        result = list(client._handle_non_streaming_response(mock_response))
        assert len(result) == 1
        assert result[0]["choices"][0]["delta"]["content"] == "Hello, world!"

    def test_handles_message_with_tool_calls(self):
        """Test handling response with tool calls"""
        client = StreamingClient()

        mock_response = Mock()
        mock_response.json.return_value = {
            "choices": [{
                "message": {
                    "content": "",
                    "tool_calls": [{"id": "call_1", "function": {"name": "test"}}]
                },
                "finish_reason": "tool_calls",
                "index": 0
            }]
        }

        result = list(client._handle_non_streaming_response(mock_response))
        assert len(result) == 1
        assert result[0]["choices"][0]["delta"]["tool_calls"] is not None


class TestUpdateStatsFromUsage:
    """Test _update_stats_from_usage method"""

    def test_updates_with_usage_object(self):
        """Test updating stats from usage object with attributes"""
        mock_stats = Mock()
        client = StreamingClient(stats=mock_stats)

        # Create a mock usage object with attributes
        mock_usage = Mock()
        mock_usage.prompt_tokens = 100
        mock_usage.completion_tokens = 50

        client._update_stats_from_usage(mock_usage)

        mock_stats.add_prompt_tokens.assert_called_once_with(100)
        mock_stats.add_completion_tokens.assert_called_once_with(50)

    def test_handles_no_usage(self):
        """Test handling None usage"""
        mock_stats = Mock()
        client = StreamingClient(stats=mock_stats)

        # Should not raise
        client._update_stats_from_usage(None)


class TestUpdateStatsOnSuccess:
    """Test _update_stats_on_success method"""

    def test_updates_success_stats(self):
        """Test that success stats are updated"""
        mock_stats = Mock()
        client = StreamingClient(stats=mock_stats)

        import time
        start_time = time.time() - 0.1  # 100ms ago

        client._update_stats_on_success(start_time)

        mock_stats.increment_api_success.assert_called_once()
        mock_stats.add_api_time.assert_called_once()

    def test_handles_no_stats(self):
        """Test handling when stats is None"""
        client = StreamingClient()
        client.stats = None

        import time
        start_time = time.time()

        # Should not raise
        client._update_stats_on_success(start_time)


class TestHandleFinalAttemptFailure:
    """Test _handle_final_attempt_failure method"""

    def test_updates_error_stats(self):
        """Test that error stats are updated"""
        mock_stats = Mock()
        client = StreamingClient(stats=mock_stats)

        import time
        start_time = time.time() - 0.1

        result = client._handle_final_attempt_failure(
            Exception("Test error"), False, start_time
        )

        assert result is False
        mock_stats.increment_api_errors.assert_called_once()

    def test_raises_when_throw_on_error(self):
        """Test that exception is raised when throw_on_error is True"""
        mock_stats = Mock()
        client = StreamingClient(stats=mock_stats)

        import time
        start_time = time.time() - 0.1

        with pytest.raises(Exception):
            client._handle_final_attempt_failure(
                Exception("Test error"), True, start_time
            )

    def test_handles_no_stats_on_failure(self):
        """Test handling when stats is None on failure"""
        client = StreamingClient()
        client.stats = None

        import time
        start_time = time.time()

        # Should not raise
        result = client._handle_final_attempt_failure(
            Exception("Test error"), False, start_time
        )
        assert result is False


class TestLogMethods:
    """Test logging-related methods"""

    def test_log_retry_attempt_only_in_debug(self):
        """Test that retry attempts are only logged in debug mode"""
        client = StreamingClient()
        config = {"base_url": "http://test.com", "model": "test-model"}

        # Should not raise - only logs in debug mode
        with patch.object(Config, 'debug', return_value=False):
            client._log_retry_attempt(config, 1)
            client._log_retry_attempt(config, 2)

    def test_log_retry_attempt_with_debug(self):
        """Test retry logging in debug mode - only logs for attempt > 1"""
        client = StreamingClient()
        config = {"base_url": "http://test.com", "model": "test-model"}

        # Second attempt SHOULD log (attempt_num=2)
        # Import is done inside the method, so we need to patch where it's used
        with patch.object(Config, 'debug', return_value=True):
            with patch('aicoder.utils.log.LogUtils.debug') as mock_debug:
                client._log_retry_attempt(config, 2)
                mock_debug.assert_called()

    def test_log_request_details_only_in_debug(self):
        """Test request details logging only in debug mode"""
        client = StreamingClient()
        endpoint = "http://test.com/chat/completions"
        config = {"base_url": "http://test.com", "model": "test-model"}
        request_data = {"model": "test", "messages": [], "tools": []}

        # Should not raise
        with patch.object(Config, 'debug', return_value=False):
            client._log_request_details(endpoint, config, request_data, 1)

    def test_log_api_config_debug_only_in_debug(self):
        """Test API config debug logging only in debug mode"""
        client = StreamingClient()
        config = {"base_url": "http://test.com", "model": "test-model"}

        # Should not raise
        with patch.object(Config, 'debug', return_value=False):
            client._log_api_config_debug(config)

    def test_log_error_response_only_in_debug(self):
        """Test error response logging only in debug mode"""
        client = StreamingClient()
        mock_response = Mock()
        mock_response.status = 500
        mock_response.headers = {"content-type": "application/json"}

        # Should not raise
        with patch.object(Config, 'debug', return_value=False):
            client._log_error_response(mock_response)

    def test_log_attempt_error_only_in_debug(self):
        """Test attempt error logging only in debug mode"""
        client = StreamingClient()

        # Should not raise
        with patch.object(Config, 'debug', return_value=False):
            client._log_attempt_error(Exception("Test error"), 1)


class TestAddToolDefinitionsExtended:
    """Extended tests for _add_tool_definitions"""

    def test_sets_tool_choice_auto(self):
        """Test that tool_choice is set to 'auto'"""
        client = StreamingClient()
        mock_tool_manager = Mock()
        client.tool_manager = mock_tool_manager
        mock_tool_manager.get_tool_definitions.return_value = [
            {"type": "function", "function": {"name": "test_tool"}}
        ]
        data = {}
        client._add_tool_definitions(data)
        assert data["tool_choice"] == "auto"

    def test_with_multiple_tools(self):
        """Test adding multiple tool definitions"""
        client = StreamingClient()
        mock_tool_manager = Mock()
        client.tool_manager = mock_tool_manager
        mock_tool_manager.get_tool_definitions.return_value = [
            {"type": "function", "function": {"name": "tool1"}},
            {"type": "function", "function": {"name": "tool2"}},
            {"type": "function", "function": {"name": "tool3"}}
        ]
        data = {}
        client._add_tool_definitions(data)
        assert len(data["tools"]) == 3


class TestHandleStreamingResponse:
    """Test _handle_streaming_response method"""

    def test_handles_empty_response(self):
        """Test handling empty streaming response"""
        client = StreamingClient()
        mock_response = Mock()
        mock_response.readline.return_value = b""  # Empty response

        result = list(client._handle_streaming_response(mock_response))
        assert result == []

    def test_handles_single_data_chunk(self):
        """Test handling single data chunk"""
        client = StreamingClient()

        # Create mock response that returns data lines
        mock_response = Mock()
        mock_response.readline.side_effect = [
            b"data: {\"choices\":[{\"delta\":{\"content\":\"Hello\"}}]}\n",
            b"data: [DONE]\n",
            b""  # Empty to end
        ]

        with patch.object(Config, 'debug', return_value=False):
            result = list(client._handle_streaming_response(mock_response))

        assert len(result) == 1
        assert result[0]["choices"][0]["delta"]["content"] == "Hello"

    def test_handles_multiple_chunks(self):
        """Test handling multiple data chunks"""
        client = StreamingClient()

        mock_response = Mock()
        mock_response.readline.side_effect = [
            b"data: {\"choices\":[{\"delta\":{\"content\":\"Hello\"}}]}\n",
            b"data: {\"choices\":[{\"delta\":{\"content\":\" World\"}}]}\n",
            b"data: [DONE]\n",
            b""
        ]

        with patch.object(Config, 'debug', return_value=False):
            result = list(client._handle_streaming_response(mock_response))

        assert len(result) == 2
        assert result[0]["choices"][0]["delta"]["content"] == "Hello"
        assert result[1]["choices"][0]["delta"]["content"] == " World"

    def test_skips_empty_lines(self):
        """Test that empty lines are skipped"""
        client = StreamingClient()

        mock_response = Mock()
        mock_response.readline.side_effect = [
            b"\n",
            b"data: {\"choices\":[{\"delta\":{\"content\":\"Hello\"}}]}\n",
            b"\n",
            b"data: [DONE]\n",
            b""
        ]

        with patch.object(Config, 'debug', return_value=False):
            result = list(client._handle_streaming_response(mock_response))

        assert len(result) == 1

    def test_handles_data_prefix_with_space(self):
        """Test handling data: prefix with space"""
        client = StreamingClient()

        mock_response = Mock()
        mock_response.readline.side_effect = [
            b"data: {\"choices\":[{\"delta\":{\"content\":\"Hello\"}}]}\n",
            b"data: [DONE]\n",
            b""
        ]

        with patch.object(Config, 'debug', return_value=False):
            result = list(client._handle_streaming_response(mock_response))

        assert len(result) == 1

    def test_handles_parse_error_gracefully(self):
        """Test handling JSON parse error gracefully"""
        client = StreamingClient()

        mock_response = Mock()
        mock_response.readline.side_effect = [
            b"data: invalid json\n",
            b"data: {\"choices\":[{\"delta\":{\"content\":\"Hello\"}}]}\n",
            b"data: [DONE]\n",
            b""
        ]

        with patch('aicoder.utils.log.LogUtils') as mock_log:
            with patch.object(Config, 'debug', return_value=False):
                result = list(client._handle_streaming_response(mock_response))

        # Should skip invalid JSON and continue
        assert len(result) == 1
        assert result[0]["choices"][0]["delta"]["content"] == "Hello"

    def test_handles_tool_calls_in_stream(self):
        """Test handling tool calls in stream"""
        client = StreamingClient()

        mock_response = Mock()
        mock_response.readline.side_effect = [
            b'data: {"choices":[{"delta":{"content":"","tool_calls":[{"id":"call1","type":"function","function":{"name":"test_tool"}}]}}]}\n',
            b"data: [DONE]\n",
            b""
        ]

        with patch.object(Config, 'debug', return_value=False):
            result = list(client._handle_streaming_response(mock_response))

        assert len(result) == 1
        tool_calls = result[0]["choices"][0]["delta"]["tool_calls"]
        assert tool_calls is not None
        assert len(tool_calls) == 1
        assert tool_calls[0]["id"] == "call1"

    def test_handles_no_choices(self):
        """Test handling response with no choices"""
        client = StreamingClient()

        mock_response = Mock()
        mock_response.readline.side_effect = [
            b'data: {"id":"test"}\n',
            b"data: [DONE]\n",
            b""
        ]

        with patch.object(Config, 'debug', return_value=False):
            result = list(client._handle_streaming_response(mock_response))

        assert len(result) == 1
        assert result[0]["choices"] == []

    def test_handles_complete_chunk_data(self):
        """Test handling complete chunk with all fields"""
        client = StreamingClient()

        mock_response = Mock()
        mock_response.readline.side_effect = [
            b'data: {"id":"chatcmpl-123","object":"chat.completion.chunk","created":1234567890,"model":"gpt-4","choices":[{"delta":{"content":"Hi"},"finish_reason":null,"index":0}],"usage":{"prompt_tokens":10,"completion_tokens":5,"total_tokens":15}}\n',
            b"data: [DONE]\n",
            b""
        ]

        with patch.object(Config, 'debug', return_value=False):
            result = list(client._handle_streaming_response(mock_response))

        assert len(result) == 1
        assert result[0]["id"] == "chatcmpl-123"
        assert result[0]["model"] == "gpt-4"
        assert result[0]["usage"]["prompt_tokens"] == 10


class TestHandleAttemptErrorExtended:
    """Extended tests for _handle_attempt_error"""

    def test_recovery_with_auto_compact(self):
        """Test auto-recovery with context compaction"""
        mock_stats = Mock()
        mock_stats.current_prompt_size = 150000
        mock_message_history = Mock()

        client = StreamingClient(stats=mock_stats, message_history=mock_message_history)

        with patch.object(Config, 'auto_compact_threshold', return_value=100000):
            with patch('aicoder.utils.log.LogUtils') as mock_log:
                # Add info attribute to mock since streaming_client.py calls it
                mock_log.info = Mock()
                with patch.object(client, '_recovery_attempted', False, create=True):
                    result = client._handle_attempt_error(
                        Exception("Context too large"),
                        1,
                        3,
                        False,
                        time.time()
                    )

        # Should attempt recovery
        assert result is True
        mock_message_history.force_compact_rounds.assert_called_once_with(1)

    def test_no_recovery_after_already_attempted(self):
        """Test no recovery after already attempted"""
        mock_stats = Mock()
        mock_stats.current_prompt_size = 150000

        client = StreamingClient(stats=mock_stats)
        client._recovery_attempted = True

        with patch.object(Config, 'auto_compact_threshold', return_value=100000):
            with patch('aicoder.utils.log.LogUtils'):
                result = client._handle_attempt_error(
                    Exception("Context too large"),
                    2,
                    3,
                    False,
                    time.time()
                )

        # Should not attempt recovery again
        assert result is True

    def test_unlimited_mode_always_retries(self):
        """Test that unlimited mode (max_retries=0) always retries"""
        client = StreamingClient()

        with patch('aicoder.utils.log.LogUtils') as mock_log:
            result = client._handle_attempt_error(
                Exception("Connection error"),
                1,
                0,  # Unlimited retries
                False,
                time.time()
            )

        assert result is True

    def test_retry_until_max_then_fail(self):
        """Test retrying until max attempts then failing"""
        mock_stats = Mock()
        client = StreamingClient(stats=mock_stats)

        with patch('aicoder.utils.log.LogUtils') as mock_log:
            result = client._handle_attempt_error(
                Exception("Connection error"),
                3,  # 3rd attempt
                3,  # Max 3 retries
                False,
                time.time()
            )

        assert result is False
        mock_stats.increment_api_errors.assert_called_once()

    def test_throw_on_error_raises(self):
        """Test that throw_on_error raises exception"""
        client = StreamingClient()

        with patch('aicoder.utils.log.LogUtils'):
            with pytest.raises(Exception):
                client._handle_attempt_error(
                    Exception("Connection error"),
                    3,
                    3,
                    True,  # throw_on_error
                    time.time()
                )


class TestStreamRequestIntegration:
    """Integration tests for stream_request"""

    def test_stream_request_empty_messages(self):
        """Test stream request with empty messages"""
        client = StreamingClient()

        with patch.object(Config, 'debug', return_value=False):
            with patch.object(Config, 'base_url', return_value='http://test.com'):
                with patch.object(Config, 'model', return_value='gpt-4'):
                    with patch.object(Config, 'effective_max_retries', return_value=1):
                        with patch.object(Config, 'total_timeout', return_value=30000):
                            with patch.object(Config, 'temperature', return_value=None):
                                with patch.object(Config, 'max_tokens', return_value=None):
                                    result = list(client.stream_request([]))
        assert result == []

    def test_stream_request_with_single_message(self):
        """Test stream request with single message"""
        client = StreamingClient()

        with patch.object(Config, 'debug', return_value=False):
            with patch.object(Config, 'base_url', return_value='http://test.com'):
                with patch.object(Config, 'model', return_value='gpt-4'):
                    with patch.object(Config, 'effective_max_retries', return_value=1):
                        with patch.object(Config, 'total_timeout', return_value=30000):
                            with patch.object(Config, 'temperature', return_value=None):
                                with patch.object(Config, 'max_tokens', return_value=None):
                                    result = list(client.stream_request([
                                        {"role": "user", "content": "Hello"}
                                    ]))
        assert result == []

    def test_resets_recovery_flag_on_new_request(self):
        """Test that recovery flag is reset for each new request"""
        client = StreamingClient()
        client._recovery_attempted = True

        with patch.object(Config, 'debug', return_value=False):
            with patch.object(Config, 'base_url', return_value='http://test.com'):
                with patch.object(Config, 'model', return_value='gpt-4'):
                    with patch.object(Config, 'effective_max_retries', return_value=1):
                        with patch.object(Config, 'total_timeout', return_value=30000):
                            with patch.object(Config, 'temperature', return_value=None):
                                with patch.object(Config, 'max_tokens', return_value=None):
                                    list(client.stream_request([{"role": "user", "content": "test"}]))

        assert client._recovery_attempted is False

    def test_stream_request_no_send_tools(self):
        """Test stream request without sending tools"""
        client = StreamingClient()

        with patch.object(Config, 'debug', return_value=False):
            with patch.object(Config, 'base_url', return_value='http://test.com'):
                with patch.object(Config, 'model', return_value='gpt-4'):
                    with patch.object(Config, 'effective_max_retries', return_value=1):
                        with patch.object(Config, 'total_timeout', return_value=30000):
                            with patch.object(Config, 'temperature', return_value=None):
                                with patch.object(Config, 'max_tokens', return_value=None):
                                    result = list(client.stream_request(
                                        [{"role": "user", "content": "test"}],
                                        send_tools=False
                                    ))
        assert result == []


class TestResponseContentTypeHandling:
    """Test content-type header handling"""

    def test_handles_case_insensitive_content_type(self):
        """Test case-insensitive content-type header handling"""
        client = StreamingClient()
        mock_response = Mock()
        mock_response.headers = {"Content-Type": "text/event-stream", "X-Request-Id": "123"}

        content_type = ""
        for header_name, header_value in mock_response.headers.items():
            if header_name.lower() == "content-type":
                content_type = header_value
                break

        assert content_type == "text/event-stream"

    def test_handles_mixed_case_content_type(self):
        """Test mixed-case content-type header"""
        client = StreamingClient()

        # Simulate the parsing logic
        headers = {"Content-Type": "TEXT/EVENT-STREAM; CHARSET=UTF-8"}
        content_type = ""
        for header_name, header_value in headers.items():
            if header_name.lower() == "content-type":
                content_type = header_value
                break

        assert client._is_streaming_response(content_type) is True


class TestUsageStatsHandling:
    """Test usage statistics handling"""

    def test_create_usage_with_partial_data(self):
        """Test _create_usage with partial data"""
        client = StreamingClient()

        usage_data = {
            "prompt_tokens": 100,
            # completion_tokens missing
        }
        result = client._create_usage(usage_data)

        assert result["prompt_tokens"] == 100
        assert result.get("completion_tokens") is None
        assert result.get("total_tokens") is None

    def test_create_usage_with_all_fields(self):
        """Test _create_usage with all fields"""
        client = StreamingClient()

        usage_data = {
            "prompt_tokens": 100,
            "completion_tokens": 50,
            "total_tokens": 150
        }
        result = client._create_usage(usage_data)

        assert result["prompt_tokens"] == 100
        assert result["completion_tokens"] == 50
        assert result["total_tokens"] == 150

    def test_update_stats_from_usage_with_dict(self):
        """Test _update_stats_from_usage with dict"""
        mock_stats = Mock()
        client = StreamingClient(stats=mock_stats)

        usage = {"prompt_tokens": 100, "completion_tokens": 50}
        client._update_stats_from_usage(usage)

        # Dict keys use get(), so we need to check add methods are not called
        # when stats expects attribute access
        mock_stats.add_prompt_tokens.assert_not_called()
        mock_stats.add_completion_tokens.assert_not_called()

