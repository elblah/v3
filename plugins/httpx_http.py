#!/usr/bin/env python3
"""
httpx HTTP plugin - replaces urllib with httpx for connection pooling

Provides ~1s speedup per request after first (SSL handshake bypass)

Requires: httpx package
Install: pip install httpx
"""

import sys
import time

# Check httpx availability
try:
    import httpx
except ImportError:
    print("ERROR: httpx_http plugin requires 'httpx' package")
    print("Install with: pip install httpx")
    sys.exit(1)

from aicoder.core.config import Config
from aicoder.utils.http_utils import _fetch_impl, Response as UrllibResponse


# Shared httpx client with connection pooling
_http_client = None


def _get_client() -> httpx.Client:
    """Get or create shared httpx client"""
    global _http_client
    if _http_client is None:
        _http_client = httpx.Client(
            http2=False,  # AI APIs typically don't support HTTP/2 well
            limits=httpx.Limits(max_keepalive_connections=10, max_connections=20),
        )
    return _http_client


class HttpxResponse:
    """Wrapper around httpx response to match Response interface"""

    def __init__(self, httpx_response: httpx.Response, deadline: float = 0):
        self._resp = httpx_response
        self.status = httpx_response.status_code
        self.reason = httpx_response.reason_phrase
        self.headers = dict(httpx_response.headers)
        self._content = None
        self.deadline = deadline

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
        # httpx doesn't support readline, but we can iterate the text
        # For SSE, we typically read all content and split lines
        if self._content is None:
            self._content = self._resp.content
        # Return first line, cache remainder
        if b"\n" in self._content:
            line, self._content = self._content.split(b"\n", 1)
            return line + b"\n"
        return self._content

    def close(self) -> None:
        # httpx response doesn't need explicit close for sync client
        pass


def httpx_fetch(url: str, options: dict = None) -> HttpxResponse:
    """
    httpx-based fetch with connection pooling
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

        response = client.request(
            method=method,
            url=url,
            headers=headers,
            content=body_bytes,
            timeout=remaining,
        )
        return HttpxResponse(response, deadline=deadline)
    except httpx.HTTPStatusError as e:
        # Return error as Response-like object
        return HttpxResponse(e.response, deadline=deadline)
    except Exception as e:
        raise Exception(f"Request failed: {e}")


def create_plugin(ctx):
    """Install httpx fetch as replacement"""
    import aicoder.utils.http_utils as http_utils

    # Patch _fetch_impl
    http_utils._fetch_impl = httpx_fetch

    # Cleanup on exit
    def cleanup():
        global _http_client
        if _http_client:
            _http_client.close()
            _http_client = None

    ctx.register_hook("on_cleanup", cleanup)

    if Config.debug():
        print(f"[httpx_http] Connected pooling enabled")