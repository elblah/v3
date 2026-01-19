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
import sys
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
        self._sequential_responses: list[Any] = []
        self._sequential_index = 0
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
            sequential_responses=self._sequential_responses,
            sequential_index=[self._sequential_index],  # Wrap in list for mutability
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
    
    def set_sequential_responses(self, responses: list[Any]) -> None:
        """
        Set sequential responses that will be returned in order.
        
        Useful for multi-turn conversations where the same pattern might appear
        in multiple requests but should return different responses.
        
        Args:
            responses: List of response dicts to return in sequence
        """
        with self._lock:
            self._sequential_responses.clear()
            self._sequential_responses.extend(responses)
            self._sequential_index = 0
            # Reset server index if server is already running
            if self._server:
                self._server._sequential_index[0] = 0
    
    def clear_sequential_responses(self) -> None:
        """Clear sequential responses and reset index."""
        with self._lock:
            self._sequential_responses.clear()
            self._sequential_index = 0

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()


class _MockHTTPServer(HTTPServer):
    """HTTP server that handles mock API requests."""

    allow_reuse_address = True

    def __init__(self, port: int, responses: dict, tool_responses: dict,
                 request_log: list, lock: threading.Lock,
                 sequential_responses: list, sequential_index: list):
        super().__init__(("localhost", port), _MockRequestHandler)
        self.responses = responses
        self.tool_responses = tool_responses
        self.request_log = request_log
        self.lock = lock
        self._sequential_responses = sequential_responses
        self._sequential_index = sequential_index


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

        # Find matching response - check sequential first, then pattern matching
        response = None
        tool_response = None
        
        # Extract last user message content for matching (used by both paths)
        last_user_content = ""
        try:
            data = json.loads(body)
            messages = data.get("messages", [])
            # Find last user message
            for msg in reversed(messages):
                if msg.get("role") == "user":
                    last_user_content = msg.get("content", "")
                    break
        except (json.JSONDecodeError, KeyError):
            last_user_content = body  # Fallback to full body
        
        # Check sequential responses first
        with self.server.lock:
            # DEBUG
            import os
            if os.environ.get("MOCK_SERVER_DEBUG"):
                print(f"[MockServer] Sequential responses: {len(self.server._sequential_responses) if self.server._sequential_responses else 0}, Index: {self.server._sequential_index[0] if self.server._sequential_responses else 'N/A'}", file=sys.stderr)
            
            if (self.server._sequential_responses and 
                self.server._sequential_index[0] < len(self.server._sequential_responses)):
                response = self.server._sequential_responses[self.server._sequential_index[0]]
                self.server._sequential_index[0] += 1
                if os.environ.get("MOCK_SERVER_DEBUG"):
                    print(f"[MockServer] Using sequential response {self.server._sequential_index[0] - 1}", file=sys.stderr)
            else:
                # Fall back to pattern matching
                for pattern, resp in self.server.responses.items():
                    if pattern in last_user_content:
                        response = resp
                        break

                for pattern, resp in self.server.tool_responses.items():
                    if pattern in last_user_content:
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
        
        # DEBUG: Log which pattern was matched
        import os
        if os.environ.get("MOCK_SERVER_DEBUG"):
            print(f"[MockServer] Last user content: {last_user_content[:100]}", file=sys.stderr)
            matched_pattern = None
            with self.server.lock:
                if not (self.server._sequential_responses and self.server._sequential_index[0] <= len(self.server._sequential_responses)):
                    for pattern, resp in self.server.responses.items():
                        if pattern in last_user_content:
                            matched_pattern = pattern
                            break
            print(f"[MockServer] Matched pattern: {matched_pattern}", file=sys.stderr)

        # Send SSE response
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()

        # Convert non-streaming response to streaming chunks
        # The streaming client expects delta.content, not message.content
        if "choices" in response and response["choices"]:
            choice = response["choices"][0]
            message = choice.get("message", {})
            content = message.get("content", "")
            role = message.get("role", "assistant")
            tool_calls = message.get("tool_calls")
            finish_reason = choice.get("finish_reason", "stop")
            
            # Send streaming chunk with delta format
            # First chunk: role
            chunk1 = {
                "id": response.get("id", "chatcmpl-123"),
                "object": "chat.completion.chunk",
                "created": response.get("created", 1234567890),
                "model": response.get("model", "gpt-4"),
                "choices": [{
                    "index": 0,
                    "delta": {"role": role},
                    "finish_reason": None
                }]
            }
            self.wfile.write(f"data: {json.dumps(chunk1)}\n\n".encode("utf-8"))
            
            # Second chunk: content (if any)
            if content:
                chunk2 = {
                    "id": response.get("id", "chatcmpl-123"),
                    "object": "chat.completion.chunk",
                    "created": response.get("created", 1234567890),
                    "model": response.get("model", "gpt-4"),
                    "choices": [{
                        "index": 0,
                        "delta": {"content": content},
                        "finish_reason": None
                    }]
                }
                self.wfile.write(f"data: {json.dumps(chunk2)}\n\n".encode("utf-8"))
            
            # Third chunk: tool_calls (if any)
            if tool_calls:
                # Convert tool_calls to proper streaming format with index
                formatted_tool_calls = []
                for idx, tc in enumerate(tool_calls):
                    # tc should be like: {"name": "read_file", "arguments": "{...}"}
                    # Convert to streaming format: {"index": 0, "id": "...", "type": "function", "function": {...}}
                    formatted_tc = {
                        "index": idx,
                        "id": f"call_{idx}_{int(time.time())}",
                        "type": "function",
                        "function": {
                            "name": tc.get("name"),
                            "arguments": tc.get("arguments", "")
                        }
                    }
                    formatted_tool_calls.append(formatted_tc)
                
                chunk3 = {
                    "id": response.get("id", "chatcmpl-123"),
                    "object": "chat.completion.chunk",
                    "created": response.get("created", 1234567890),
                    "model": response.get("model", "gpt-4"),
                    "choices": [{
                        "index": 0,
                        "delta": {"tool_calls": formatted_tool_calls},
                        "finish_reason": None
                    }]
                }
                self.wfile.write(f"data: {json.dumps(chunk3)}\n\n".encode("utf-8"))
            
            # Final chunk: finish_reason
            chunk_final = {
                "id": response.get("id", "chatcmpl-123"),
                "object": "chat.completion.chunk",
                "created": response.get("created", 1234567890),
                "model": response.get("model", "gpt-4"),
                "choices": [{
                    "index": 0,
                    "delta": {},
                    "finish_reason": finish_reason
                }]
            }
            # Include usage stats if present
            if "usage" in response:
                chunk_final["usage"] = response["usage"]
            self.wfile.write(f"data: {json.dumps(chunk_final)}\n\n".encode("utf-8"))
        else:
            # Fallback: send as-is if no choices
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
