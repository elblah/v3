"""
Simple HTTP utilities - Python version of fetch-like functionality
"""

import json
import urllib.request
import urllib.error
from typing import Dict, Any, Optional


class Response:
    """Simple response object mimicking fetch Response"""

    def __init__(self, response_or_error: Any):
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

    def ok(self) -> bool:
        """Check if response is successful"""
        return 200 <= self.status < 300

    def json(self) -> Dict[str, Any]:
        """Parse response as JSON - simple like TypeScript"""
        try:
            # Use cached content or read it
            if self._content is None:
                if hasattr(self.response, "read"):
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
                self._content = self.response.read()
            else:
                self._content = b""
        return self._content

    def readline(self) -> bytes:
        """Read one line from response - needed for SSE streaming"""
        if hasattr(self.response, "readline"):
            return self.response.readline()
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
    Simple fetch-like function - just like TypeScript version
    """
    if options is None:
        options = {}

    method = options.get("method", "GET")
    headers = options.get("headers", {})
    body = options.get("body")
    timeout = options.get("timeout", 30)

    # Create request
    if body:
        body_bytes = body.encode("utf-8") if isinstance(body, str) else body
    else:
        body_bytes = None

    req = urllib.request.Request(url, data=body_bytes, headers=headers, method=method)

    try:
        response = urllib.request.urlopen(req, timeout=timeout)
        return Response(response)
    except urllib.error.HTTPError as e:
        # Return error as Response object - just like TypeScript fetch
        return Response(e)
    except Exception as e:
        # For connection errors etc., raise as exception
        raise Exception(f"Request failed: {e}")
