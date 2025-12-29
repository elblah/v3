"""
Test StreamingClient class
Simple tests for API existence
"""

import pytest
from unittest.mock import MagicMock
from aicoder.core.streaming_client import StreamingClient


@pytest.fixture
def streaming_client():
    """Create streaming client instance"""
    return StreamingClient()


@pytest.fixture
def sample_messages():
    """Sample messages for testing"""
    return [
        {"role": "system", "content": "You are helpful"},
        {"role": "user", "content": "Hello"}
    ]


def test_streaming_client_initialization(streaming_client):
    """Test streaming client initialization"""
    assert streaming_client is not None


def test_stream_request_exists(streaming_client):
    """Test stream_request method exists"""
    assert hasattr(streaming_client, "stream_request")


def test_stream_request_is_generator(streaming_client, sample_messages):
    """Test stream_request is a generator function"""
    result = streaming_client.stream_request(sample_messages)
    assert hasattr(result, "__iter__")


def test_process_with_colorization(streaming_client):
    """Test markdown colorization"""
    text = "Hello **world**"
    result = streaming_client.process_with_colorization(text)

    # Should process through colorizer
    assert isinstance(result, str)


def test_reset_colorizer(streaming_client):
    """Test reset colorizer"""
    # Should not crash
    streaming_client.reset_colorizer()


def test_update_token_stats(streaming_client):
    """Test token stats update"""
    usage = {
        "prompt_tokens": 100,
        "completion_tokens": 50,
        "total_tokens": 150
    }

    # Should not crash
    streaming_client.update_token_stats(usage)


def test_update_token_stats_with_none(streaming_client):
    """Test token stats update with None"""
    # Should not crash with None usage
    streaming_client.update_token_stats(None)


def test_colorization(streaming_client):
    """Test colorization methods"""
    # Test with empty string
    result = streaming_client.process_with_colorization("")
    assert result == ""

    # Test with plain text
    result = streaming_client.process_with_colorization("plain text")
    assert result is not None
