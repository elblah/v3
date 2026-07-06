"""
Simple HTTP utilities - Python version of fetch-like functionality

Note: urllib.request is lazily imported to avoid 300ms startup cost.
Only imported when fetch() is actually called.
"""

import json
import socket
import time
from typing import Dict, Any, Optional

# Lazy imports to avoid startup cost
_urllib_request = None
_gzip = None
_zlib = None

def _get_urllib():
    global _urllib_request
    if _urllib_request is None:
        global urllib
        import urllib.request
        _urllib_request = urllib.request
    return _urllib_request

def _get_gzip():
    global _gzip
    if _gzip is None:
        import gzip as _gzip_mod
        _gzip = _gzip_mod
    return _gzip

def _get_zlib():
    global _zlib
    if _zlib is None:
        import zlib as _zlib_mod
        _zlib = _zlib_mod
    return _zlib


class Response:
    """Simple response object mimicking fetch Response"""

    def __init__(self, response_or_error: Any, deadline: float = 0):
        # Handle both successful responses and HTTPError
        if hasattr(response_or_error, "read"):
            # Regular response
            self.response = response_or_error
            self.status = getattr(response_or_error, "status", 200)
            self.reason = getattr(response_or_error, "reason", "OK")
            self.headers = dict(getattr(response_or_error, "headers", {}))
            self._content = None
        else:
            # HTTPError or other error
            self.response = response_or_error
            self.status = getattr(response_or_error, "code", 500)
            self.reason = getattr(response_or_error, "reason", "Error")
            self.headers = dict(getattr(response_or_error, "headers", {}))

            # Try to read error content if available
            self._content = None
            if hasattr(response_or_error, "read"):
                try:
                    self._content = response_or_error.read()
                except:
                    self._content = b""

        self.deadline = deadline
        self._last_read_time = 0.0  # Track when we last received data

    def _enforce_timeout(self):
        """Set socket timeout with activity-based extension for streaming"""
        if self.deadline <= 0:
            return
        
        remaining = self.deadline - time.monotonic()
        from aicoder.core.config import Config
        extension = Config.total_timeout_extension()
        
        # Activity-based extension: if data was flowing recently, grant more time
        if extension > 0 and remaining <= extension:
            time_since_last_read = time.monotonic() - self._last_read_time
            if time_since_last_read < extension:
                # Recent activity - extend tolerance
                remaining += extension
        
        if remaining <= 0:
            raise socket.timeout("Total timeout exceeded")
        
        if hasattr(self.response, "fileno") and hasattr(self.response, "fp") and self.response.fp is not None:
            fn = self.response.fileno()
            sock = socket.fromfd(fn, socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(remaining)

    def ok(self) -> bool:
        """Check if response is successful"""
        return 200 <= self.status < 300

    def json(self) -> Dict[str, Any]:
        """Parse response as JSON - simple"""
        try:
            # Use cached content or read it
            if self._content is None:
                if hasattr(self.response, "read"):
                    self._content = self.read()
                else:
                    self._content = b""

            # Parse JSON
            if isinstance(self._content, bytes):
                content_str = self._content.decode("utf-8")
            else:
                content_str = str(self._content)

            if not content_str.strip():
                return {"error": "Empty response"}

            return json.loads(content_str)
        except Exception as e:
            # Return error structure for better debugging
            return {
                "error": f"Failed to parse JSON: {e}",
                "raw_content": str(self._content) if self._content else "None",
            }

    def read(self) -> bytes:
        """Read raw response bytes (auto-decompresses gzip/deflate)"""
        if self._content is None:
            if hasattr(self.response, "read"):
                self._enforce_timeout()
                self._content = self.response.read()
                self._last_read_time = time.monotonic()
            else:
                self._content = b""

        # Decompress if needed
        if self._content:
            content_encoding = self.headers.get("Content-Encoding", "").lower()
            if content_encoding == "gzip":
                self._content = _get_gzip().decompress(self._content)
            elif content_encoding == "deflate":
                try:
                    self._content = _get_zlib().decompress(self._content, -15)
                except Exception:
                    self._content = _get_zlib().decompress(self._content)

        return self._content

    def readline(self) -> bytes:
        """Read one line from response - needed for SSE streaming"""
        if hasattr(self.response, "readline"):
            self._enforce_timeout()
            line = self.response.readline()
            self._last_read_time = time.monotonic()
            return line
        else:
            # Fallback to reading all and finding first line
            content = self.read()
            if b"\n" in content:
                line, remainder = content.split(b"\n", 1)
                # Put remainder back in content for next reads
                self._content = remainder
                return line + b"\n"
            else:
                return content

    def close(self) -> None:
        """Close the underlying response if possible"""
        if hasattr(self.response, "close"):
            try:
                self.response.close()
            except:
                pass


def fetch(url: str, options: Optional[Dict[str, Any]] = None) -> Response:
    """
    Simple fetch-like function with total timeout enforcement.
    """
    return _fetch_impl(url, options)

def _fetch_impl(url: str, options: Optional[Dict[str, Any]] = None) -> Response:
    if options is None:
        options = {}

    method = options.get("method", "GET")
    headers = options.get("headers", {})
    if "Accept-Encoding" not in headers:
        headers["Accept-Encoding"] = "gzip, deflate"
    body = options.get("body")
    from aicoder.core.config import Config
    total_timeout = options.get("timeout", Config.total_timeout())

    # Calculate deadline for total timeout enforcement
    deadline = time.monotonic() + total_timeout

    # Create request
    if body:
        body_bytes = body.encode("utf-8") if isinstance(body, str) else body
    else:
        body_bytes = None

    urllib_req = _get_urllib()
    req = urllib_req.Request(url, data=body_bytes, headers=headers, method=method)

    try:
        # Use remaining time for connection timeout
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise socket.timeout("Total timeout exceeded before connection")
        response = urllib_req.urlopen(req, timeout=remaining)
        return Response(response, deadline=deadline)
    except Exception as e:
        # Import urllib.error here to avoid startup cost
        import urllib.error
        if isinstance(e, urllib.error.HTTPError):
            # Return error as Response object
            return Response(e, deadline=deadline)
        # For connection errors etc., raise as exception
        raise Exception(f"Request failed: {e}")
