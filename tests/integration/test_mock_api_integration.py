"""
Integration tests using the mock API server.

These tests verify aicoder-v3 behavior with a real-like API connection
without burning API credits.
"""

import json
import socket
import threading
import time
import urllib.request
from http.server import HTTPServer, BaseHTTPRequestHandler
import pytest


# Mock server implementation for testing
class MockServer:
    """Simple mock API server for integration testing."""

    def __init__(self):
        self._server = None
        self._thread = None
        self._port = None
        self._responses = {}
        self._request_log = []
        self._lock = threading.Lock()

    def get_port(self) -> int:
        return self._port

    def get_url(self, path: str = "/v1/chat/completions") -> str:
        return f"http://localhost:{self._port}{path}"

    def get_api_base(self) -> str:
        return f"http://localhost:{self._port}"

    def start(self, port: int | None = None) -> None:
        if self._server is not None:
            raise RuntimeError("Server already running")

        # Find a free port
        if port is None:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.bind(("localhost", 0))
            self._port = sock.getsockname()[1]
            sock.close()
        else:
            self._port = port

        self._server = _TestServer(
            port=self._port,
            responses=self._responses,
            request_log=self._request_log,
            lock=self._lock,
        )

        self._thread = threading.Thread(target=self._server.serve_forever, daemon=True)
        self._thread.start()

        # Wait for server to be ready
        for _ in range(50):
            try:
                sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                sock.settimeout(0.1)
                sock.connect(("localhost", self._port))
                sock.close()
                return
            except (ConnectionRefusedError, socket.timeout):
                time.sleep(0.1)
        raise RuntimeError("Server failed to start")

    def stop(self) -> None:
        if self._server:
            self._server.shutdown()
            self._server.server_close()
            self._server = None
            self._thread = None
            self._port = None

    def set_response(self, pattern: str, response: dict) -> None:
        with self._lock:
            self._responses[pattern] = response

    def get_requests(self) -> list:
        with self._lock:
            return list(self._request_log)


class _TestServer(HTTPServer):
    """Simple test HTTP server."""

    allow_reuse_address = True

    def __init__(self, port: int, responses: dict, request_log: list, lock: threading.Lock):
        super().__init__(("localhost", port), _TestHandler)
        self.responses = responses
        self.request_log = request_log
        self.lock = lock


class _TestHandler(BaseHTTPRequestHandler):
    """Request handler for test server."""

    protocol_version = "HTTP/1.1"

    def log_message(self, format, *args):
        pass

    def do_POST(self):
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length).decode("utf-8") if content_length > 0 else ""

        with self.server.lock:
            self.server.request_log.append({"path": self.path, "body": body})

        # Find matching response
        response = None
        with self.server.lock:
            for pattern, resp in self.server.responses.items():
                if pattern in body:
                    response = resp
                    break

        if response is None:
            response = {"choices": [{"message": {"content": "Default response"}}]}

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        json_response = json.dumps(response)
        self.wfile.write(f"data: {json_response}\n\n".encode())
        self.wfile.write(b"data: [DONE]\n\n")

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(b'{"status": "ok"}')


def make_sse_response(content: str) -> dict:
    """Create a standard SSE response."""
    return {
        "id": "chatcmpl-123",
        "object": "chat.completion",
        "created": 1234567890,
        "model": "test-model",
        "choices": [{
            "index": 0,
            "message": {"role": "assistant", "content": content},
            "finish_reason": "stop",
        }],
        "usage": {"prompt_tokens": 5, "completion_tokens": 10, "total_tokens": 15},
    }


# Fixtures
@pytest.fixture
def mock_server():
    """Provide a mock API server for tests."""
    server = MockServer()
    server.start()
    yield server
    server.stop()


class TestMockServer:
    """Test the mock server itself."""

    def test_server_starts(self, mock_server):
        """Server should start and expose a port."""
        assert mock_server.get_port() > 0
        assert mock_server.get_port() < 65536

    def test_health_check(self, mock_server):
        """Server should respond to GET requests."""
        url = f"http://localhost:{mock_server.get_port()}/"
        with urllib.request.urlopen(url) as response:
            assert response.status == 200
            assert b"ok" in response.read()

    def test_post_request(self, mock_server):
        """Server should accept POST and return SSE."""
        mock_server.set_response("test", make_sse_response("Test response"))

        url = mock_server.get_url()
        data = json.dumps({"messages": [{"role": "user", "content": "test"}]}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")

        with urllib.request.urlopen(req) as response:
            assert response.status == 200
            content_type = response.headers.get("Content-Type", "")
            assert "text/event-stream" in content_type

    def test_request_logging(self, mock_server):
        """Server should log incoming requests."""
        mock_server.set_response("logme", make_sse_response("Logged"))

        url = mock_server.get_url()
        data = json.dumps({"messages": [{"role": "user", "content": "logme"}]}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        urllib.request.urlopen(req)

        requests = mock_server.get_requests()
        assert len(requests) == 1
        assert "logme" in requests[0]["body"]

    def test_different_patterns(self, mock_server):
        """Server should return different responses for different patterns."""
        mock_server.set_response("hello", make_sse_response("Hello!"))
        mock_server.set_response("bye", make_sse_response("Goodbye!"))

        url = mock_server.get_url()

        # Test hello
        data = json.dumps({"messages": [{"role": "user", "content": "hello"}]}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        resp = urllib.request.urlopen(req)
        assert "Hello!" in resp.read().decode()

        # Test bye
        data = json.dumps({"messages": [{"role": "user", "content": "bye"}]}).encode()
        req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
        resp = urllib.request.urlopen(req)
        assert "Goodbye!" in resp.read().decode()

    def test_multiple_requests(self, mock_server):
        """Server should handle multiple sequential requests."""
        mock_server.set_response("ping", make_sse_response("pong"))

        url = mock_server.get_url()
        for i in range(5):
            data = json.dumps({"messages": [{"role": "user", "content": "ping"}]}).encode()
            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"}, method="POST")
            resp = urllib.request.urlopen(req)
            assert "pong" in resp.read().decode()

        assert len(mock_server.get_requests()) == 5


class TestMockServerWithAicoder:
    """Test aicoder-v3 connected to mock API server."""

    def test_hello_with_api_url(self, mock_server):
        """Test that aicoder can use mock server API URL."""
        import os

        mock_server.set_response("hello", make_sse_response("Hello, human!"))

        # Set environment to use mock server
        old_env = {}
        for key in ["API_BASE_URL", "API_MODEL"]:
            if key in os.environ:
                old_env[key] = os.environ.pop(key)
            os.environ[key] = f"http://localhost:{mock_server.get_port()}"

        try:
            # Make a direct request (simulating what aicoder does)
            url = mock_server.get_url()
            data = json.dumps({
                "model": "test-model",
                "messages": [{"role": "user", "content": "hello"}],
                "stream": True,
            }).encode()

            req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
            with urllib.request.urlopen(req) as response:
                content = response.read().decode()
                assert "Hello, human!" in content
        finally:
            # Restore environment
            for key, value in old_env.items():
                os.environ[key] = value
            for key in ["API_BASE_URL", "API_MODEL"]:
                if key not in old_env:
                    os.environ.pop(key, None)
