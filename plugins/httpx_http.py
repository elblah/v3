#!/usr/bin/env python3
"""
httpx HTTP plugin - replaces urllib with httpx for connection pooling

Provides ~1s speedup per request after first (SSL handshake bypass)
Supports streaming (SSE) via stream=True

Requires: httpx package
Install: pip install httpx

Defer import until first actual HTTP call to save ~1s startup time.
"""

import sys
import time
import os

from aicoder.core.config import Config


# Shared httpx client with connection pooling
_http_client = None
_httpx_installed = False


def _get_client():
    """Get or create shared httpx client - lazy import"""
    global _http_client
    if _http_client is None:
        import httpx
        _http_client = httpx.Client(
            http2=False,  # AI APIs typically don't support HTTP/2 well
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )
    return _http_client


class HttpxResponse:
    """Wrapper around httpx response to match Response interface"""

    def __init__(self, httpx_response, deadline: float = 0, streaming: bool = False):
        self._resp = httpx_response
        self.status = httpx_response.status_code
        self.reason = httpx_response.reason_phrase
        self.headers = dict(httpx_response.headers)
        self._content = None
        self._line_iter = None
        self.deadline = deadline
        self._streaming = streaming
        
        # For non-streaming responses, read content immediately
        if not streaming:
            self._content = httpx_response.content

    def ok(self) -> bool:
        return 200 <= self.status < 300

    def json(self) -> dict:
        import json
        try:
            if self._content is None:
                self._content = self._resp.content
            return json.loads(self._content)
        except Exception as e:
            return {"error": f"Failed to parse JSON: {e}", "raw_content": str(self._content) if self._content else "None"}

    def read(self) -> bytes:
        if self._content is None:
            self._content = self._resp.content
        return self._content

    def readline(self) -> bytes:
        """Read one line - uses streaming for SSE"""
        if self._content is not None:
            # Content already read, split from cache
            if b"\n" in self._content:
                line, self._content = self._content.split(b"\n", 1)
                return line + b"\n"
            return self._content

        # Stream line by line
        if self._line_iter is None:
            self._line_iter = self._resp.iter_lines()
        try:
            line = next(self._line_iter)
            # iter_lines returns str, convert to bytes and add newline
            if isinstance(line, str):
                return (line + "\n").encode("utf-8")
            return line + b"\n"
        except StopIteration:
            return b""
        except Exception:
            return b""

    def close(self) -> None:
        try:
            self._resp.close()
        except Exception:
            pass


def httpx_fetch(url: str, options: dict = None) -> HttpxResponse:
    """
    httpx-based fetch with connection pooling and streaming support
    """
    if options is None:
        options = {}

    method = options.get("method", "GET")
    headers = options.get("headers", {})
    body = options.get("body")
    total_timeout = options.get("timeout", Config.total_timeout())

    deadline = time.monotonic() + total_timeout

    # Convert body
    if body:
        body_bytes = body.encode("utf-8") if isinstance(body, str) else body
    else:
        body_bytes = None

    client = _get_client()

    try:
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("Total timeout exceeded before connection")

        # Build request with timeout
        request = client.build_request(
            method=method,
            url=url,
            headers=headers,
            content=body_bytes,
            timeout=remaining,
        )

        # For now, always use non-streaming
        # SSE works fine - we read all content, then split with readline()
        # streaming=True would cause issues with non-streaming responses
        response = client.send(request, stream=False)
        return HttpxResponse(response, deadline=deadline, streaming=False)
    except Exception as e:
        # Import httpx exception types lazily
        import httpx
        if isinstance(e, httpx.HTTPStatusError):
            # Return error as Response-like object
            return HttpxResponse(e.response, deadline=deadline)
        raise Exception(f"Request failed: {e}")


def create_plugin(ctx):
    """Install httpx fetch as replacement - deferred until first HTTP call"""
    global _httpx_installed
    
    # Check if disabled via env var
    if os.environ.get("PERF_DISABLE", "0") == "1":
        return
    if os.environ.get("HTTPX_DISABLE", "0") == "1":
        return
    
    def _install_httpx(*args, **kwargs):
        """Install httpx on first API request, not at startup"""
        global _httpx_installed
        if _httpx_installed:
            return
        
        # Check httpx available
        try:
            import httpx
        except ImportError:
            return  # Skip, urllib will be used
        
        import aicoder.utils.http_utils as http_utils
        http_utils._fetch_impl = httpx_fetch
        _httpx_installed = True
        
        # Register cleanup
        def cleanup():
            global _http_client
            if _http_client:
                _http_client.close()
                _http_client = None
        ctx.register_hook("on_cleanup", cleanup)

    # Defer httpx installation to first API request
    ctx.register_hook("before_api_request", _install_httpx)

    if Config.debug():
        print(f"[httpx_http] Connection pooling enabled (deferred)")