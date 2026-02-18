"""
Simple HTTP utilities - Python version of fetch-like functionality
"""

import json
import socket
import time
import urllib.request
import urllib.error
from typing import Dict, Any, Optional
from aicoder.core.config import Config


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
        extension = Config.total_timeout_extension()
        
        # Activity-based extension: if data was flowing recently, grant more time
        if extension > 0 and remaining <= extension:
            time_since_last_read = time.monotonic() - self._last_read_time
            if time_since_last_read < extension:
                # Recent activity - extend tolerance
                remaining += extension
        
        if remaining <= 0:
            raise socket.timeout("Total timeout exceeded")
        
        if hasattr(self.response, "fileno"):
            sock = socket.fromfd(self.response.fileno(), socket.AF_INET, socket.SOCK_STREAM)
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
                    self._enforce_timeout()
                    self._content = self.response.read()
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
        """Read raw response bytes"""
        if self._content is None:
            if hasattr(self.response, "read"):
                self._enforce_timeout()
                self._content = self.response.read()
                self._last_read_time = time.monotonic()
            else:
                self._content = b""
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


def fetch(url: str, options: Optional[Dict[str, Any]] = None) -> Response:
    """
    Simple fetch-like function with total timeout enforcement.
    """
    if options is None:
        options = {}

    method = options.get("method", "GET")
    headers = options.get("headers", {})
    body = options.get("body")
    total_timeout = options.get("timeout", Config.total_timeout())

    # Calculate deadline for total timeout enforcement
    deadline = time.monotonic() + total_timeout

    # Create request
    if body:
        body_bytes = body.encode("utf-8") if isinstance(body, str) else body
    else:
        body_bytes = None

    req = urllib.request.Request(url, data=body_bytes, headers=headers, method=method)

    try:
        # Use remaining time for connection timeout
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise socket.timeout("Total timeout exceeded before connection")
        response = urllib.request.urlopen(req, timeout=remaining)
        return Response(response, deadline=deadline)
    except urllib.error.HTTPError as e:
        # Return error as Response object
        return Response(e, deadline=deadline)
    except Exception as e:
        # For connection errors etc., raise as exception
        raise Exception(f"Request failed: {e}")
