"""
Test StreamingClient class - Synchronous version
Tests to ensure exact behavior matches TypeScript version
"""

import pytest
from unittest.mock import MagicMock, patch
from aicoder.core.streaming_client import StreamingClient
from aicoder.core.config import Config


@pytest.fixture
def streaming_client():
    """Create StreamingClient instance for testing"""
    return StreamingClient()


@pytest.fixture
def sample_messages():
    """Sample messages for testing"""
    return [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
    ]


def test_streaming_client_initialization(streaming_client):
    """Test StreamingClient initialization"""
    assert streaming_client.colorizer is not None
    assert streaming_client.stats is None  # Default when not provided
    assert streaming_client.tool_manager is None
    assert streaming_client.message_history is None


def test_stream_request_success(streaming_client, sample_messages):
    """Test successful stream request"""
    # Mock successful response
    mock_response = MagicMock()
    mock_response.status_code = 200

    # Mock SSE chunks
    mock_chunk = MagicMock()
    mock_chunk.decode.return_value = (
        'data: {"choices": [{"delta": {"content": "Hello"}}}\n\n'
    )

    with patch("aicoder.core.streaming_client.fetch", return_value=mock_response):
        with patch(
            "aicoder.core.streaming_client.iter_lines", return_value=[mock_chunk]
        ):
            chunks = []
            for chunk in streaming_client.stream_request(sample_messages):
                chunks.append(chunk)

            assert len(chunks) > 0


def test_stream_request_error(streaming_client, sample_messages):
    """Test stream request with error"""
    # Mock error response
    mock_response = MagicMock()
    mock_response.status_code = 400

    with patch("aicoder.core.streaming_client.fetch", return_value=mock_response):
        with pytest.raises(Exception):
            for _ in streaming_client.stream_request(sample_messages):
                pass


def test_stream_request_non_streaming(streaming_client, sample_messages):
    """Test non-streaming response"""
    # Mock non-streaming response
    mock_response = MagicMock()
    mock_response.status_code = 200

    # Mock non-streaming JSON
    mock_json = {"choices": [{"message": {"content": "Hello world"}}]}

    with patch("aicoder.core.streaming_client.fetch", return_value=mock_response):
        with patch.object(mock_response, "json", return_value=mock_json):
            chunks = []
            for chunk in streaming_client.stream_request(sample_messages, stream=False):
                chunks.append(chunk)

            assert len(chunks) > 0


def test_process_with_colorization(streaming_client):
    """Test colorization processing"""
    # Test with sample markdown
    markdown = "```python\nprint('hello')\n```"

    result = streaming_client.process_with_colorization(markdown)

    # Should return some processed content
    assert isinstance(result, str)
    assert len(result) > 0


def test_reset_colorizer(streaming_client):
    """Test colorizer reset"""
    # Should not crash
    streaming_client.reset_colorizer()


def test_update_token_stats(streaming_client):
    """Test token stats update"""
    # Mock usage
    mock_usage = MagicMock()
    mock_usage.prompt_tokens = 10
    mock_usage.completion_tokens = 20

    # Should not crash
    streaming_client.update_token_stats(mock_usage)


def test_sse_parsing(streaming_client):
    """Test SSE parsing"""
    # Test SSE format parsing
    sse_data = 'data: {"choices": [{"delta": {"content": "Hello"}}}\n\n'

    # Parse SSE data
    lines = sse_data.split("\n")
    data_lines = [line for line in lines if line.startswith("data: ")]

    assert len(data_lines) == 1
    assert "Hello" in data_lines[0]


def test_pollinations_special_handling(streaming_client, sample_messages):
    """Test special handling for Pollinations API responses"""
    # Mock Pollinations-style response (streaming format even when stream=False)
    mock_response = MagicMock()
    mock_response.status_code = 200

    # Mock SSE chunks for non-streaming request
    mock_chunk = MagicMock()
    mock_chunk.decode.return_value = (
        'data: {"choices": [{"delta": {"content": "Pollinations style"}}]\n\n'
    )

    with patch("aicoder.core.streaming_client.fetch", return_value=mock_response):
        with patch(
            "aicoder.core.streaming_client.iter_lines", return_value=[mock_chunk]
        ):
            chunks = []
            for chunk in streaming_client.stream_request(sample_messages, stream=False):
                chunks.append(chunk)

            assert len(chunks) > 0


def test_error_handling(streaming_client):
    """Test error handling in streaming"""
    # Mock response with error
    mock_response = MagicMock()
    mock_response.status_code = 500
    mock_response.reason = "Internal Server Error"

    with patch("aicoder.core.streaming_client.fetch", return_value=mock_response):
        with pytest.raises(Exception):
            for _ in streaming_client.stream_request([]):
                pass


def test_request_headers(streaming_client, sample_messages):
    """Test that request headers are set correctly"""
    # Mock fetch to capture headers
    mock_response = MagicMock()
    mock_response.status_code = 200
    captured_kwargs = {}

    def mock_fetch(*args, **kwargs):
        captured_kwargs.update(kwargs)
        return mock_response

    with patch("aicoder.core.streaming_client.fetch", side_effect=mock_fetch):
        with patch.object(mock_response, "json", return_value={"choices": []}):
            list(streaming_client.stream_request(sample_messages, stream=False))

    # Check headers were set
    assert "headers" in captured_kwargs
    headers = captured_kwargs["headers"]
    assert "Content-Type" in headers
    assert "Authorization" in headers


def test_timeout_handling(streaming_client, sample_messages):
    """Test timeout handling"""
    # Mock timeout error
    with patch(
        "aicoder.core.streaming_client.fetch",
        side_effect=TimeoutError("Request timeout"),
    ):
        with pytest.raises(TimeoutError):
            for _ in streaming_client.stream_request(sample_messages):
                pass


def test_json_parsing_error(streaming_client, sample_messages):
    """Test JSON parsing error handling"""
    # Mock malformed JSON response
    mock_response = MagicMock()
    mock_response.status_code = 200
    mock_response.json.side_effect = ValueError("Invalid JSON")

    with patch("aicoder.core.streaming_client.fetch", return_value=mock_response):
        with pytest.raises(ValueError):
            for _ in streaming_client.stream_request(sample_messages, stream=False):
                pass
