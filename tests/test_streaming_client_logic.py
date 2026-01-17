"""
Test streaming_client module
"""

import pytest
from unittest.mock import Mock, patch
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
