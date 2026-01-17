"""
Mock API Server for Integration Testing

A local HTTP server that simulates AI API responses (OpenAI-compatible).
Useful for testing aicoder-v3 without real API calls or credits.

Features:
- Dynamic free port selection
- Configurable responses per request pattern
- SSE (Server-Sent Events) format support
- Thread-safe for parallel test execution
"""

import json
import threading
import time
from http.server import HTTPServer, BaseHTTPRequestHandler
from typing import Any
import socket


class MockServer:
    """
    Mock API server for integration testing.

    Usage:
        mock = MockServer()
        mock.set_response("hello", {"choices": [{"message": {"content": "Hello!"}}]})
        mock.set_tool_response("exec uname", {"name": "run_shell_command", "arguments": {"command": "uname -a"}})

        port = mock.get_port()
        url = mock.get_url()

        # Server runs until stop() is called
        mock.start()
        # ... run tests ...
        mock.stop()

        # Or use as context manager:
        with MockServer() as mock:
            ...
    """

    def __init__(self):
        self._server = None
        self._thread = None
        self._port = None
        self._responses: dict[str, Any] = {}
        self._tool_responses: dict[str, Any] = {}
        self._request_log: list[dict] = []
        self._lock = threading.Lock()

    def get_port(self) -> int:
        """Get the current port the server is listening on."""
        if self._port is None:
            raise RuntimeError("Server not started yet. Call start() first.")
        return self._port

    def get_url(self, path: str = "/v1/chat/completions") -> str:
        """Get the full URL for an endpoint."""
        return f"http://localhost:{self._port}{path}"

    def get_api_base(self) -> str:
        """Get the API base URL (without path)."""
        return f"http://localhost:{self._port}"

    def start(self, port: int | None = None) -> None:
        """Start the mock server on a free port."""
        if self._server is not None:
            raise RuntimeError("Server already running")

        # Find a free port if none specified
        if port is None:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(("localhost", 0))
            self._port = sock.getsockname()[1]
            sock.close()
        else:
            self._port = port

        self._server = _MockHTTPServer(
            port=self._port,
            responses=self._responses,
            tool_responses=self._tool_responses,
            request_log=self._request_log,
            lock=self._lock,
        )

        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

        # Wait for server to be ready
        max_wait = 5
        start_time = time.time()
        while time.time() - start_time < max_wait:
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(1)
                sock.connect(("localhost", self._port))
                sock.close()
                return
            except (ConnectionRefusedError, socket.timeout):
                time.sleep(0.05)
        raise RuntimeError(f"Server failed to start within {max_wait}s")

    def stop(self) -> None:
        """Stop the mock server."""
        if self._server is not None:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
            self._thread = None
            self._port = None

    def set_response(self, pattern: str, response: dict) -> None:
        """
        Set a response for a request whose body contains the pattern.

        Args:
            pattern: String to match in request body (e.g., "hello")
            response: JSON-serializable response dict
        """
        with self._lock:
            self._responses[pattern] = response

    def set_tool_response(self, pattern: str, tool_call: dict) -> None:
        """
        Set a tool call response for a request whose body contains the pattern.

        Args:
            pattern: String to match in request body
            tool_call: Tool call dict with 'name' and 'arguments' keys
        """
        with self._lock:
            self._tool_responses[pattern] = tool_call

    def clear_responses(self) -> None:
        """Clear all configured responses."""
        with self._lock:
            self._responses.clear()
            self._tool_responses.clear()

    def get_requests(self) -> list[dict]:
        """Get list of all requests made to the server."""
        with self._lock:
            return list(self._request_log)

    def clear_requests(self) -> None:
        """Clear request log."""
        with self._lock:
            self._request_log.clear()

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


class _MockHTTPServer(HTTPServer):
    """HTTP server that handles mock API requests."""

    allow_reuse_address = True

    def __init__(self, port: int, responses: dict, tool_responses: dict,
                 request_log: list, lock: threading.Lock):
        super().__init__(("localhost", port), _MockRequestHandler)
        self.responses = responses
        self.tool_responses = tool_responses
        self.request_log = request_log
        self.lock = lock


class _MockRequestHandler(BaseHTTPRequestHandler):
    """Request handler for mock API responses."""

    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        pass  # Silence logging

    def do_POST(self):
        """Handle POST requests (chat completions)."""
        content_length = int(self.headers.get("Content-Length", 0))
        if content_length > 0:
            body = self.rfile.read(content_length).decode("utf-8")
        else:
            body = ""

        # Log the request
        with self.server.lock:
            self.server.request_log.append({
                "path": self.path,
                "body": body,
                "time": time.time(),
            })

        # Find matching response
        response = None
        tool_response = None

        with self.server.lock:
            for pattern, resp in self.server.responses.items():
                if pattern in body:
                    response = resp
                    break

            for pattern, resp in self.server.tool_responses.items():
                if pattern in body:
                    tool_response = resp
                    break

        # Default response if no pattern matched
        if response is None:
            response = {
                "choices": [{
                    "message": {
                        "content": "Default mock response"
                    }
                }]
            }

        if tool_response:
            response["choices"][0]["message"]["tool_calls"] = [tool_response]

        # Send SSE response
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        # Format as SSE
        json_response = json.dumps(response)
        self.wfile.write(f"data: {json_response}\n\n".encode("utf-8"))
        self.wfile.write(b"data: [DONE]\n\n")

    def do_GET(self):
        """Handle GET requests (health check, etc.)."""
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(b'{"status": "ok"}')


def make_tool_response(name: str, arguments: dict) -> dict:
    """Helper to create a tool call response dict."""
    return {
        "id": "call_123",
        "type": "function",
        "function": {
            "name": name,
            "arguments": json.dumps(arguments),
        }
    }


def make_sse_response(content: str, tool_calls: list[dict] | None = None) -> dict:
    """Helper to create a complete SSE-compatible response dict."""
    response = {
        "id": "chatcmpl-123",
        "object": "chat.completion",
        "created": 1234567890,
        "model": "gpt-4",
        "choices": [{
            "index": 0,
            "message": {
                "role": "assistant",
                "content": content,
            },
            "finish_reason": "stop",
        }],
        "usage": {
            "prompt_tokens": 10,
            "completion_tokens": 20,
            "total_tokens": 30,
        }
    }

    if tool_calls:
        response["choices"][0]["finish_reason"] = "tool_calls"
        response["choices"][0]["message"]["tool_calls"] = tool_calls

    return response
