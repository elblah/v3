"""
Unit tests for http_utils module
"""

from unittest.mock import patch

import sys
sys.path.insert(0, '.')

from aicoder.utils.http_utils import Response, fetch


class MockResponse:
    """Mock response object that behaves like urllib response"""

    def __init__(self, status=200, reason="OK", body=b"", headers=None):
        self.status = status
        self.reason = reason
        self._body = body
        self.headers = headers or {}
        self._read_called = False
        self.code = status  # For HTTPError compatibility

    def read(self):
        if not self._read_called:
            self._read_called = True
            return self._body
        return b""

    def readline(self):
        if b'\n' in self._body:
            line, remainder = self._body.split(b'\n', 1)
            self._body = remainder
            return line + b'\n'
        return self._body


class MockHTTPError:
    """Mock HTTPError that doesn't have read() method to trigger error path"""

    def __init__(self, code=404, reason="Not Found", headers=None):
        self.code = code
        self.reason = reason
        self.headers = headers or {}


class TestResponse:
    """Test Response class behavior"""

    def test_init_with_successful_response(self):
        """Test initialization with successful HTTP response"""
        mock_response = MockResponse(status=200, reason="OK", headers={"content-type": "application/json"})

        response = Response(mock_response)

        assert response.status == 200
        assert response.reason == "OK"
        assert response.headers == {"content-type": "application/json"}
        assert response._content is None

    def test_init_with_http_error(self):
        """Test initialization with HTTPError"""
        mock_error = MockHTTPError(code=404, reason="Not Found")

        response = Response(mock_error)

        assert response.status == 404
        assert response.reason == "Not Found"
        assert response.headers == {}

    def test_ok_returns_true_for_2xx_status(self):
        """Test ok() returns True for 2xx status codes"""
        mock_response = MockResponse(status=200)
        response = Response(mock_response)

        assert response.ok() is True

    def test_ok_returns_true_for_299_status(self):
        """Test ok() returns True for 299 status code"""
        mock_response = MockResponse(status=299)
        response = Response(mock_response)

        assert response.ok() is True

    def test_ok_returns_false_for_300_status(self):
        """Test ok() returns False for 300 status code"""
        mock_response = MockResponse(status=300)
        response = Response(mock_response)

        assert response.ok() is False

    def test_ok_returns_false_for_199_status(self):
        """Test ok() returns False for 199 status code"""
        mock_response = MockResponse(status=199)
        response = Response(mock_response)

        assert response.ok() is False

    def test_ok_returns_false_for_error_status(self):
        """Test ok() returns False for error status codes"""
        mock_response = MockResponse(status=404)
        response = Response(mock_response)

        assert response.ok() is False

    def test_ok_returns_false_for_server_error(self):
        """Test ok() returns False for 500 status code"""
        mock_response = MockResponse(status=500)
        response = Response(mock_response)

        assert response.ok() is False

    def test_json_parses_valid_json(self):
        """Test json() parses valid JSON response"""
        mock_response = MockResponse(status=200, body=b'{"key": "value", "number": 42}')

        response = Response(mock_response)
        result = response.json()

        assert result == {"key": "value", "number": 42}

    def test_json_parses_json_array(self):
        """Test json() parses JSON array"""
        mock_response = MockResponse(status=200, body=b'[{"id": 1}, {"id": 2}]')

        response = Response(mock_response)
        result = response.json()

        assert result == [{"id": 1}, {"id": 2}]

    def test_json_handles_empty_response(self):
        """Test json() handles empty response body"""
        mock_response = MockResponse(status=200, body=b'')

        response = Response(mock_response)
        result = response.json()

        assert result == {"error": "Empty response"}

    def test_json_handles_whitespace_only(self):
        """Test json() handles whitespace-only response"""
        mock_response = MockResponse(status=200, body=b'   \n\t  ')

        response = Response(mock_response)
        result = response.json()

        assert result == {"error": "Empty response"}

    def test_json_handles_invalid_json(self):
        """Test json() handles invalid JSON"""
        mock_response = MockResponse(status=200, body=b'not valid json')

        response = Response(mock_response)
        result = response.json()

        assert "error" in result
        assert "Failed to parse JSON" in result["error"]

    def test_json_caches_content(self):
        """Test json() caches content after first read"""
        mock_response = MockResponse(status=200, body=b'{"key": "value"}')

        response = Response(mock_response)

        # First read
        result1 = response.json()
        # Second read (should use cached content)
        result2 = response.json()

        assert result1 == {"key": "value"}
        assert result2 == {"key": "value"}
        # Read should only be called once due to caching
        assert mock_response._read_called is True

    def test_json_handles_unicode_content(self):
        """Test json() handles unicode characters"""
        mock_response = MockResponse(status=200, body='{"message": "你好世界"}'.encode('utf-8'))

        response = Response(mock_response)
        result = response.json()

        assert result == {"message": "你好世界"}

    def test_read_returns_raw_bytes(self):
        """Test read() returns raw response bytes"""
        test_bytes = b'raw binary data'
        mock_response = MockResponse(status=200, body=test_bytes)

        response = Response(mock_response)
        result = response.read()

        assert result == test_bytes

    def test_read_caches_content(self):
        """Test read() caches content after first read"""
        test_bytes = b'test data'
        mock_response = MockResponse(status=200, body=test_bytes)

        response = Response(mock_response)

        # First read
        result1 = response.read()
        # Second read (should use cached content)
        result2 = response.read()

        assert result1 == test_bytes
        assert result2 == test_bytes
        # Read should only be called once due to caching
        assert mock_response._read_called is True

    def test_readline_calls_response_readline(self):
        """Test readline() delegates to response.readline()"""
        mock_response = MockResponse(status=200, body=b'first line\nsecond line\n')

        response = Response(mock_response)
        result = response.readline()

        assert result == b'first line\n'

    def test_readline_multiple_calls(self):
        """Test readline() can be called multiple times"""
        mock_response = MockResponse(status=200, body=b'line1\nline2\nline3\n')

        response = Response(mock_response)

        lines = []
        for _ in range(3):
            line = response.readline()
            lines.append(line)

        assert lines == [b'line1\n', b'line2\n', b'line3\n']

    def test_response_with_missing_attributes_uses_defaults(self):
        """Test Response handles missing attributes gracefully"""
        # Create a minimal mock object with read() method (treated as regular response)
        class MinimalMock:
            def __init__(self):
                self.headers = {}
            def read(self):
                return b""

        mock_response = MinimalMock()

        response = Response(mock_response)

        # getattr with defaults will use the provided defaults for regular response
        assert response.status == 200  # Default from getattr for regular response
        assert response.reason == "OK"  # Default from getattr for regular response
        assert response.headers == {}  # Empty headers dict


class TestFetch:
    """Test fetch function behavior"""

    @patch('aicoder.utils.http_utils.urllib.request.urlopen')
    def test_fetch_get_request(self, mock_urlopen):
        """Test fetch() makes GET request by default"""
        mock_response = MockResponse(status=200)
        mock_urlopen.return_value = mock_response

        result = fetch("http://example.com")

        assert result.status == 200
        mock_urlopen.assert_called_once()

    @patch('aicoder.utils.http_utils.urllib.request.urlopen')
    def test_fetch_with_options_headers(self, mock_urlopen):
        """Test fetch() passes headers in options"""
        mock_response = MockResponse(status=200)
        mock_urlopen.return_value = mock_response

        options = {
            "headers": {"Authorization": "Bearer token", "Content-Type": "application/json"}
        }
        result = fetch("http://example.com", options)

        assert result.status == 200
        # Check that Request was created with headers
        call_args = mock_urlopen.call_args[0]
        request = call_args[0]
        # urllib.Request keeps header case
        assert request.headers.get("Authorization") == "Bearer token"

    @patch('aicoder.utils.http_utils.urllib.request.urlopen')
    def test_fetch_with_post_method(self, mock_urlopen):
        """Test fetch() makes POST request"""
        mock_response = MockResponse(status=201)
        mock_urlopen.return_value = mock_response

        options = {"method": "POST", "body": '{"test": "data"}'}
        result = fetch("http://example.com", options)

        assert result.status == 201
        call_args = mock_urlopen.call_args[0]
        request = call_args[0]
        assert request.method == "POST"
        assert request.data == b'{"test": "data"}'

    @patch('aicoder.utils.http_utils.urllib.request.urlopen')
    def test_fetch_with_put_method(self, mock_urlopen):
        """Test fetch() makes PUT request"""
        mock_response = MockResponse(status=200)
        mock_urlopen.return_value = mock_response

        options = {"method": "PUT", "body": "updated data"}
        result = fetch("http://example.com", options)

        assert result.status == 200
        call_args = mock_urlopen.call_args[0]
        request = call_args[0]
        assert request.method == "PUT"
        assert request.data == b"updated data"

    @patch('aicoder.utils.http_utils.urllib.request.urlopen')
    def test_fetch_with_bytes_body(self, mock_urlopen):
        """Test fetch() handles bytes body"""
        mock_response = MockResponse(status=200)
        mock_urlopen.return_value = mock_response

        options = {"method": "POST", "body": b"binary data"}
        result = fetch("http://example.com", options)

        assert result.status == 200
        call_args = mock_urlopen.call_args[0]
        request = call_args[0]
        assert request.data == b"binary data"

    @patch('aicoder.utils.http_utils.urllib.request.urlopen')
    def test_fetch_with_custom_timeout(self, mock_urlopen):
        """Test fetch() uses custom timeout from options"""
        mock_response = MockResponse(status=200)
        mock_urlopen.return_value = mock_response

        options = {"timeout": 60}
        result = fetch("http://example.com", options)

        assert result.status == 200
        mock_urlopen.assert_called_once()
        # Check timeout in call kwargs
        call_kwargs = mock_urlopen.call_args[1]
        assert call_kwargs["timeout"] == 60

    @patch('aicoder.utils.http_utils.urllib.request.urlopen')
    def test_fetch_default_timeout(self, mock_urlopen):
        """Test fetch() uses default timeout from Config"""
        from aicoder.core.config import Config
        mock_response = MockResponse(status=200)
        mock_urlopen.return_value = mock_response

        result = fetch("http://example.com")

        assert result.status == 200
        call_kwargs = mock_urlopen.call_args[1]
        assert call_kwargs["timeout"] == Config.socket_timeout()

    @patch('aicoder.utils.http_utils.urllib.request.urlopen')
    def test_fetch_handles_http_error(self, mock_urlopen):
        """Test fetch() returns Response for HTTP errors"""
        from urllib.error import HTTPError

        # Create a real HTTPError
        error = HTTPError("http://example.com", 404, "Not Found", {}, None)
        mock_urlopen.side_effect = error

        result = fetch("http://example.com")

        assert result.status == 404
        assert result.reason == "Not Found"

    @patch('aicoder.utils.http_utils.urllib.request.urlopen')
    def test_fetch_handles_connection_error(self, mock_urlopen):
        """Test fetch() raises exception for connection errors"""
        mock_urlopen.side_effect = Exception("Connection failed")

        try:
            fetch("http://example.com")
            assert False, "Should have raised exception"
        except Exception as e:
            assert "Request failed" in str(e)
            assert "Connection failed" in str(e)

    @patch('aicoder.utils.http_utils.urllib.request.urlopen')
    def test_fetch_handles_timeout_error(self, mock_urlopen):
        """Test fetch() raises exception for timeout errors"""
        mock_urlopen.side_effect = Exception("timeout")

        try:
            fetch("http://example.com")
            assert False, "Should have raised exception"
        except Exception as e:
            assert "Request failed" in str(e)

    @patch('aicoder.utils.http_utils.urllib.request.urlopen')
    def test_fetch_with_none_options(self, mock_urlopen):
        """Test fetch() handles None options (default behavior)"""
        mock_response = MockResponse(status=200)
        mock_urlopen.return_value = mock_response

        result = fetch("http://example.com", None)

        assert result.status == 200
        mock_urlopen.assert_called_once()

    @patch('aicoder.utils.http_utils.urllib.request.urlopen')
    def test_fetch_with_empty_options(self, mock_urlopen):
        """Test fetch() handles empty options dict"""
        mock_response = MockResponse(status=200)
        mock_urlopen.return_value = mock_response

        result = fetch("http://example.com", {})

        assert result.status == 200
        mock_urlopen.assert_called_once()


# Note: We removed MockErrorWithRead because objects with read() method are
# always treated as regular responses by Response class, not errors.


class MockResponseWithoutReadline:
    """Mock response without readline() method"""

    def __init__(self, body=b""):
        self.status = 200
        self.reason = "OK"
        self.headers = {}
        self._body = body

    def read(self):
        return self._body


class MockErrorWithRead:
    """Mock HTTPError that has read() method to test error content reading"""

    def __init__(self, code=500, reason="Server Error", headers=None, body=b""):
        self.code = code
        self.reason = reason
        self.headers = headers or {}
        self._body = body
        self._read_exception = None

    def read(self):
        if self._read_exception:
            raise self._read_exception
        return self._body


class TestResponseIntegration:
    """Integration tests for Response with realistic scenarios"""

    def test_response_json_then_read(self):
        """Test calling json() then read() on same response"""
        mock_response = MockResponse(status=200, body=b'{"key": "value"}')

        response = Response(mock_response)

        # First call json()
        json_result = response.json()
        assert json_result == {"key": "value"}

        # Then call read() (should use cached content)
        read_result = response.read()
        assert read_result == b'{"key": "value"}'

        # Mock read should only be called once
        assert mock_response._read_called is True

    def test_response_read_then_json(self):
        """Test calling read() then json() on same response"""
        mock_response = MockResponse(status=200, body=b'{"key": "value"}')

        response = Response(mock_response)

        # First call read()
        read_result = response.read()
        assert read_result == b'{"key": "value"}'

        # Then call json() (should use cached content)
        json_result = response.json()
        assert json_result == {"key": "value"}

        # Mock read should only be called once
        assert mock_response._read_called is True

    def test_response_sse_streaming_simulation(self):
        """Test Response with SSE-like streaming data"""
        mock_response = MockResponse(
            status=200,
            body=b'data: message 1\ndata: message 2\ndata: message 3\n\n'
        )

        response = Response(mock_response)

        lines = []
        for _ in range(4):
            line = response.readline()
            lines.append(line)

        assert lines == [
            b'data: message 1\n',
            b'data: message 2\n',
            b'data: message 3\n',
            b'\n',
        ]

    def test_response_with_http_error_content(self):
        """Test Response created from HTTPError without read method"""
        # HTTPError objects don't have read() method in urllib.error
        # So content remains None (no attempt to read)
        mock_error = MockHTTPError(code=500, reason="Internal Server Error")

        response = Response(mock_error)

        assert response.status == 500
        assert response.reason == "Internal Server Error"
        assert response.headers == {}
        # Content remains None for HTTPError without read method
        assert response._content is None

    def test_response_empty_json_multiple_reads(self):
        """Test that empty JSON response returns error structure consistently"""
        mock_response = MockResponse(status=200, body=b'')

        response = Response(mock_response)

        # First call
        result1 = response.json()
        # Second call (should use cached result)
        result2 = response.json()

        assert result1 == {"error": "Empty response"}
        assert result2 == {"error": "Empty response"}

    def test_response_json_without_read_method(self):
        """Test json() when response doesn't have read() method"""
        # Error response that doesn't have read() method
        mock_error = MockHTTPError(code=500)

        response = Response(mock_error)
        result = response.json()

        # Should return empty response error since no content can be read
        assert result == {"error": "Empty response"}

    def test_response_json_non_bytes_content(self):
        """Test json() when content is not bytes"""
        mock_response = MockResponse(status=200)
        # Manually set _content to non-bytes value
        mock_response._read_called = True

        response = Response(mock_response)
        response._content = "string content"

        result = response.json()

        # Should convert to string and try to parse as JSON
        # "string content" is not valid JSON, so it returns error structure
        assert "error" in result
        assert "Failed to parse JSON" in result["error"]
        assert "string content" in result["raw_content"]

    def test_response_readline_fallback(self):
        """Test readline() fallback when response has no readline()"""
        mock_response = MockResponseWithoutReadline(body=b'line1\nline2\n')

        response = Response(mock_response)
        line = response.readline()

        assert line == b'line1\n'

    def test_response_readline_fallback_no_newline(self):
        """Test readline() fallback when content has no newline"""
        mock_response = MockResponseWithoutReadline(body=b'single line')

        response = Response(mock_response)
        line = response.readline()

        assert line == b'single line'

    def test_response_readline_fallback_multiple_calls(self):
        """Test readline() fallback with multiple calls"""
        mock_response = MockResponseWithoutReadline(body=b'line1\nline2\nline3')

        response = Response(mock_response)

        line1 = response.readline()
        line2 = response.readline()

        assert line1 == b'line1\n'
        assert line2 == b'line2\n'
        # After first split, remainder is stored in _content
        # Second readline reads the stored _content
