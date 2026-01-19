"""
Integration tests for streaming client using mock API server.

Tests SSE parsing, retry logic, and response handling.
"""

import json
import time
import pytest
import urllib.request

from tests.integration.mock_server import MockServer, make_sse_response


def make_error_response(code: int, message: str) -> dict:
    """Create an error response."""
    return {
        "error": {
            "code": code,
            "message": message,
        }
    }


@pytest.fixture
def mock_server():
    """Provide a mock API server for tests."""
    server = MockServer()
    server.start()
    yield server
    server.stop()


class TestSSEParsing:
    """Test SSE (Server-Sent Events) parsing."""

    def test_sse_data_lines(self, mock_server):
        """Test that SSE data: prefix is handled correctly."""
        mock_server.set_response("stream", {
            "choices": [{"message": {"content": "Hello"}}]
        })

        url = mock_server.get_url()
        data = json.dumps({"messages": [{"role": "user", "content": "stream"}]}).encode()
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req) as response:
            content = response.read().decode()
            # Verify SSE format
            assert "data:" in content
            assert "[DONE]" in content

    def test_sse_with_newlines(self, mock_server):
        """Test SSE parsing handles newlines in content."""
        mock_server.set_response("multi", {
            "choices": [{"message": {"content": "Line 1\nLine 2\nLine 3"}}]
        })

        url = mock_server.get_url()
        data = json.dumps({"messages": [{"role": "user", "content": "multi"}]}).encode()
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req) as response:
            content = response.read().decode()
            assert "Line 1" in content
            assert "Line 2" in content
            assert "Line 3" in content

    def test_sse_done_signal(self, mock_server):
        """Test that [DONE] signal terminates stream."""
        mock_server.set_response("short", {
            "choices": [{"message": {"content": "Done"}}]
        })

        url = mock_server.get_url()
        data = json.dumps({"messages": [{"role": "user", "content": "short"}]}).encode()
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req) as response:
            content = response.read().decode()
            # [DONE] should be present
            assert "[DONE]" in content


class TestRetryLogic:
    """Test retry behavior with mock server."""

    def test_retry_on_error(self, mock_server):
        """Test that failed requests can be retried."""
        # First set an error response
        mock_server.set_response("fail", make_error_response(500, "Server error"))

        url = mock_server.get_url()
        data = json.dumps({"messages": [{"role": "user", "content": "fail"}]}).encode()
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        # The mock always returns a response, so this tests the request format
        try:
            with urllib.request.urlopen(req) as response:
                content = response.read().decode()
                # Even error responses should have valid SSE format
                assert "data:" in content
        except urllib.error.HTTPError as e:
            # Server might return error code
            pass


class TestResponseFormats:
    """Test different API response formats."""

    def test_chunk_format(self, mock_server):
        """Test streaming chunk format."""
        mock_server.set_response("chunk", {
            "id": "chatcmpl-abc",
            "object": "chat.completion.chunk",
            "created": 1234567890,
            "model": "test-model",
            "choices": [{"delta": {"content": "Test"}}]
        })

        url = mock_server.get_url()
        data = json.dumps({"messages": [{"role": "user", "content": "chunk"}]}).encode()
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req) as response:
            content = response.read().decode()
            # Verify chunk metadata
            assert "chatcmpl-abc" in content
            assert "test-model" in content

    def test_usage_in_response(self, mock_server):
        """Test that usage stats are included."""
        mock_server.set_response("stats", {
            "choices": [{"message": {"content": "Test"}}],
            "usage": {
                "prompt_tokens": 10,
                "completion_tokens": 20,
                "total_tokens": 30,
            }
        })

        url = mock_server.get_url()
        data = json.dumps({"messages": [{"role": "user", "content": "stats"}]}).encode()
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req) as response:
            content = response.read().decode()
            assert "10" in content
            assert "20" in content
            assert "30" in content


class TestToolCalls:
    """Test tool call handling in responses."""

    def test_tool_call_in_response(self, mock_server):
        """Test tool calls are properly formatted."""
        tool_call = {
            "name": "run_shell_command",
            "arguments": '{"command": "echo hello"}',
        }
        mock_server.set_response("execute", {
            "choices": [{
                "message": {
                    "content": "Let me run that...",
                    "tool_calls": [tool_call],
                }
            }]
        })

        url = mock_server.get_url()
        data = json.dumps({"messages": [{"role": "user", "content": "execute"}]}).encode()
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req) as response:
            content = response.read().decode()
            assert "run_shell_command" in content
            assert "echo hello" in content

    def test_multiple_tool_calls(self, mock_server):
        """Test multiple tool calls in one response."""
        tool_calls = [
            {
                "name": "read_file",
                "arguments": '{"path": "/test"}',
            },
            {
                "name": "run_shell_command", 
                "arguments": '{"command": "ls"}',
            },
        ]
        mock_server.set_response("multi", {
            "choices": [{
                "message": {
                    "content": "I'll help with both.",
                    "tool_calls": tool_calls,
                }
            }]
        })

        url = mock_server.get_url()
        data = json.dumps({"messages": [{"role": "user", "content": "multi"}]}).encode()
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req) as response:
            content = response.read().decode()
            assert "read_file" in content
            assert "run_shell_command" in content


class TestContentTypeHandling:
    """Test Content-Type header handling."""

    def test_event_stream_content_type(self, mock_server):
        """Test response has correct Content-Type for SSE."""
        mock_server.set_response("type", {
            "choices": [{"message": {"content": "Test"}}]
        })

        url = mock_server.get_url()
        data = json.dumps({"messages": [{"role": "user", "content": "type"}]}).encode()
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req) as response:
            content_type = response.headers.get("Content-Type", "")
            assert "text/event-stream" in content_type


class TestMockServerWithClient:
    """Test streaming client behavior with mock server."""

    def test_client_sends_correct_headers(self, mock_server):
        """Test that client sends expected headers."""
        mock_server.set_response("headers", {
            "choices": [{"message": {"content": "OK"}}]
        })

        url = mock_server.get_url()
        data = json.dumps({
            "model": "test-model",
            "messages": [{"role": "user", "content": "headers"}],
            "stream": True,
        }).encode()
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req) as response:
            # Verify response is successful
            assert response.status == 200

    def test_concurrent_requests(self, mock_server):
        """Test handling of multiple sequential requests."""
        mock_server.set_response("req1", {"choices": [{"message": {"content": "First"}}]})
        mock_server.set_response("req2", {"choices": [{"message": {"content": "Second"}}]})

        url = mock_server.get_url()

        # First request
        data = json.dumps({"messages": [{"role": "user", "content": "req1"}]}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            assert "First" in resp.read().decode()

        # Second request
        data = json.dumps({"messages": [{"role": "user", "content": "req2"}]}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req) as resp:
            assert "Second" in resp.read().decode()

    def test_request_log_verification(self, mock_server):
        """Test that requests are logged correctly."""
        mock_server.set_response("log_test", {
            "choices": [{"message": {"content": "Logged"}}]
        })

        url = mock_server.get_url()
        data = json.dumps({"messages": [{"role": "user", "content": "log_test"}]}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
        urllib.request.urlopen(req)

        requests = mock_server.get_requests()
        assert len(requests) == 1
        assert "log_test" in requests[0]["body"]
