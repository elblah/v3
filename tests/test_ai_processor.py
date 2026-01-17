"""
Test ai_processor module
"""

import pytest
from unittest.mock import Mock
from aicoder.core.ai_processor import AIProcessor, AIProcessorConfig


class TestAIProcessorConfig:
    """Test AIProcessorConfig"""

    def test_default_values(self):
        config = AIProcessorConfig()
        assert config.system_prompt is None
        assert config.max_retries is None
        assert config.timeout is None

    def test_custom_values(self):
        config = AIProcessorConfig(
            system_prompt="You are helpful",
            max_retries=5,
            timeout=120
        )
        assert config.system_prompt == "You are helpful"
        assert config.max_retries == 5
        assert config.timeout == 120


class TestAIProcessor:
    """Test AIProcessor"""

    def test_initialization_with_config(self):
        mock_client = Mock()
        config = {"max_retries": 3}
        processor = AIProcessor(mock_client, config)
        assert processor.streaming_client is mock_client
        assert processor.config == config

    def test_initialization_without_config(self):
        mock_client = Mock()
        processor = AIProcessor(mock_client)
        assert processor.streaming_client is mock_client
        assert processor.config == {}

    def test_empty_messages(self):
        mock_client = Mock()
        mock_client.stream_request.return_value = iter([
            {"choices": [{"delta": {"content": "Response"}}]}
        ])
        
        processor = AIProcessor(mock_client)
        result = processor.process_messages([], "Test prompt")
        
        assert result == "Response"
        mock_client.stream_request.assert_called_once()
        call_args = mock_client.stream_request.call_args
        messages = call_args.kwargs.get('messages', call_args.args[0] if call_args.args else [])
        assert len(messages) == 1
        assert messages[0]["content"] == "Test prompt"

    def test_existing_messages(self):
        mock_client = Mock()
        mock_client.stream_request.return_value = iter([
            {"choices": [{"delta": {"content": "New response"}}]}
        ])
        
        processor = AIProcessor(mock_client)
        existing_messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there"}
        ]
        result = processor.process_messages(existing_messages, "Continue")
        
        assert result == "New response"
        mock_client.stream_request.assert_called_once()
        call_args = mock_client.stream_request.call_args
        messages = call_args.kwargs.get('messages', call_args.args[0] if call_args.args else [])
        assert len(messages) == 3

    def test_multiple_chunks(self):
        mock_client = Mock()
        mock_client.stream_request.return_value = iter([
            {"choices": [{"delta": {"content": "Hello"}}]},
            {"choices": [{"delta": {"content": " "}}]},
            {"choices": [{"delta": {"content": "World"}}]},
        ])
        
        processor = AIProcessor(mock_client)
        result = processor.process_messages([], "Say hello")
        assert result == "Hello World"

    def test_empty_chunks(self):
        mock_client = Mock()
        mock_client.stream_request.return_value = iter([
            {"choices": [{}]},
            {"choices": [{"delta": {}}]},
            {"choices": [{"delta": {"content": "Content"}}]},
        ])
        
        processor = AIProcessor(mock_client)
        result = processor.process_messages([], "Test")
        assert result == "Content"

    def test_malformed_chunks(self):
        mock_client = Mock()
        mock_client.stream_request.return_value = iter([
            {"not_choices": "malformed"},
            {"choices": [{"delta": {"content": "Valid"}}]},
        ])
        
        processor = AIProcessor(mock_client)
        result = processor.process_messages([], "Test")
        assert result == "Valid"

    def test_api_error(self):
        mock_client = Mock()
        mock_client.stream_request.side_effect = ConnectionError("Network failed")
        
        processor = AIProcessor(mock_client)
        
        with pytest.raises(Exception) as exc_info:
            processor.process_messages([{"role": "user", "content": "test"}], "prompt")
        
        assert "AI Processor failed: Network failed" in str(exc_info.value)

    def test_convenience_method(self):
        mock_client = Mock()
        mock_client.stream_request.return_value = iter([
            {"choices": [{"delta": {"content": "Result"}}]}
        ])
        
        processor = AIProcessor(mock_client)
        result = processor.process([{"role": "user", "content": "test"}], "prompt")
        assert result == "Result"

    def test_send_tools_flag(self):
        mock_client = Mock()
        mock_client.stream_request.return_value = iter([
            {"choices": [{"delta": {"content": "Response"}}]}
        ])
        
        processor = AIProcessor(mock_client)
        processor.process_messages([], "test", send_tools=False)
        
        args, kwargs = mock_client.stream_request.call_args
        assert kwargs.get("send_tools") is False

    def test_whitespace_stripping(self):
        mock_client = Mock()
        mock_client.stream_request.return_value = iter([
            {"choices": [{"delta": {"content": "  spaced content  \n"}}]}
        ])
        
        processor = AIProcessor(mock_client)
        result = processor.process_messages([], "test")
        assert result == "spaced content"
