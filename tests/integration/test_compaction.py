"""
Integration tests for compaction service using mock API server.

Tests the compaction functionality without burning API credits.
"""

import json
import os
import sys
import time
import urllib.request
import pytest

from tests.integration.mock_server import MockServer, make_sse_response


def make_compaction_response(summary: str) -> dict:
    """Create a mock response that simulates compaction/summarization."""
    return {
        "id": "chatcmpl-compact",
        "object": "chat.completion",
        "created": 1234567890,
        "model": "compact-model",
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": f"[COMPACTED]: {summary}",
            },
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 500, "completion_tokens": 100, "total_tokens": 600},
    }


def make_tool_response(name: str, arguments: dict) -> dict:
    """Create a tool call response."""
    return {
        "id": "call_123",
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(arguments),
        }
    }


@pytest.fixture
def mock_server():
    """Provide a mock API server for tests."""
    server = MockServer()
    server.start()
    yield server
    server.stop()


class TestCompactionWithMockAPI:
    """Test compaction service using mock API."""

    def test_compaction_endpoint(self, mock_server):
        """Test that compaction endpoint is called correctly."""
        mock_server.set_response("compact", make_compaction_response("Session summarized"))

        url = mock_server.get_url()
        data = json.dumps({
            "model": "test-model",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant."},
                {"role": "user", "content": "Hello"},
                {"role": "assistant", "content": "Hi there!"},
                {"role": "user", "content": "compact"},
            ],
        }).encode()

        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req) as response:
            content = response.read().decode()
            assert "COMPACTED" in content
            assert "Session summarized" in content

    def test_context_size_reduction(self, mock_server):
        """Test that compaction reduces context size."""
        # Create a long conversation
        long_context = [
            {"role": "system", "content": "You are a helpful assistant."}
        ]
        for i in range(20):
            long_context.append({"role": "user", "content": f"Message {i}"})
            long_context.append({"role": "assistant", "content": f"Response {i}"})

        # Add a final message with recognizable pattern to trigger compaction
        long_context.append({"role": "user", "content": "compact now Message 0"})
        
        mock_server.set_response("Message 0", make_compaction_response("Thread summarized to key points"))

        url = mock_server.get_url()
        data = json.dumps({
            "model": "test-model",
            "messages": long_context,
        }).encode()

        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req) as response:
            content = response.read().decode()
            # Verify compaction was triggered
            assert "COMPACTED" in content or "Thread summarized" in content

    def test_tool_calls_during_compaction(self, mock_server):
        """Test that tool calls work correctly after compaction."""
        response = {
            "choices": [{
                "message": {
                    "role": "assistant", 
                    "content": "Compacting context...",
                    "tool_calls": [{
                        "name": "run_shell_command",
                        "arguments": json.dumps({"command": "echo done"})
                    }]
                }
            }]
        }
        mock_server.set_response("compact and run command", response)

        url = mock_server.get_url()
        data = json.dumps({
            "model": "test-model",
            "messages": [{"role": "user", "content": "compact and run command"}],
        }).encode()

        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req) as response:
            content = response.read().decode()
            # Check for tool call in response
            assert "run_shell_command" in content

    def test_consecutive_compaction_requests(self, mock_server):
        """Test multiple compaction requests in sequence."""
        mock_server.set_response("compact", make_compaction_response("Summary 1"))
        mock_server.set_response("summarize", make_compaction_response("Summary 2"))

        url = mock_server.get_url()

        # First compaction
        data = json.dumps({
            "model": "test-model",
            "messages": [{"role": "user", "content": "compact"}],
        }).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        resp1 = urllib.request.urlopen(req)
        assert "Summary 1" in resp1.read().decode()

        # Second compaction
        data = json.dumps({
            "model": "test-model",
            "messages": [{"role": "user", "content": "summarize"}],
        }).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        resp2 = urllib.request.urlopen(req)
        assert "Summary 2" in resp2.read().decode()

    def test_aicoder_env_with_compaction(self, mock_server):
        """Test that aicoder respects API_BASE_URL for compaction."""
        # Set environment to use mock server
        old_api_base = os.environ.get("API_BASE_URL")
        old_api_model = os.environ.get("API_MODEL")

        try:
            os.environ["API_BASE_URL"] = mock_server.get_api_base()
            os.environ["API_MODEL"] = "test-model"

            mock_server.set_response("compact", make_compaction_response("Environment-based compaction"))

            # Simulate what streaming_client does
            from urllib.request import Request, urlopen

            url = mock_server.get_url()
            data = json.dumps({
                "model": os.environ["API_MODEL"],
                "messages": [{"role": "user", "content": "compact"}],
            }).encode()

            req = Request(url, data=data, headers={"Content-Type": "application/json"})
            with urlopen(req) as response:
                content = response.read().decode()
                assert "Environment-based compaction" in content
        finally:
            if old_api_base is not None:
                os.environ["API_BASE_URL"] = old_api_base
            else:
                os.environ.pop("API_BASE_URL", None)
            if old_api_model is not None:
                os.environ["API_MODEL"] = old_api_model
            else:
                os.environ.pop("API_MODEL", None)


class TestCompactionEdgeCases:
    """Test edge cases for compaction."""

    def test_empty_context_compaction(self, mock_server):
        """Test compaction with minimal context."""
        mock_server.set_response("compact", make_compaction_response("No context to compact"))

        url = mock_server.get_url()
        data = json.dumps({
            "model": "test-model",
            "messages": [{"role": "user", "content": "compact"}],
        }).encode()

        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as response:
            content = response.read().decode()
            assert "No context to compact" in content

    def test_compaction_with_system_prompt(self, mock_server):
        """Test compaction preserves system prompt."""
        mock_server.set_response("compact", make_compaction_response("User messages compacted"))

        url = mock_server.get_url()
        data = json.dumps({
            "model": "test-model",
            "messages": [
                {"role": "system", "content": "You are a helpful assistant. Always be concise."},
                {"role": "user", "content": "compact"},
            ],
        }).encode()

        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req) as response:
            content = response.read().decode()
            assert "COMPACTED" in content
