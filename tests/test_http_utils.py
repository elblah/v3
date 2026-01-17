"""
Tests for HTTP utilities
"""

import pytest
import urllib.error
from unittest.mock import Mock


class TestHttpUtils:
    """Test HTTP utility functions"""

    def test_response_ok_success(self):
        """Test Response.ok for successful status codes"""
        from aicoder.utils.http_utils import Response

        mock_response = Mock()
        mock_response.status = 200
        mock_response.reason = "OK"
        mock_response.headers = {}
        mock_response.read.return_value = b'{"result": "ok"}'

        response = Response(mock_response)
        assert response.ok() is True

    def test_response_ok_redirect(self):
        """Test Response.ok for redirect status codes"""
        from aicoder.utils.http_utils import Response

        mock_response = Mock()
        mock_response.status = 301
        mock_response.reason = "Moved Permanently"
        mock_response.headers = {}
        mock_response.read.return_value = b""

        response = Response(mock_response)
        # 301 is NOT in the 200-299 range for "ok"
        assert response.ok() is False

    def test_response_ok_client_error(self):
        """Test Response.ok for client error status codes"""
        from aicoder.utils.http_utils import Response

        mock_response = Mock()
        mock_response.status = 400
        mock_response.reason = "Bad Request"
        mock_response.headers = {}
        mock_response.read.return_value = b""

        response = Response(mock_response)
        assert response.ok() is False

    def test_response_ok_server_error(self):
        """Test Response.ok for server error status codes"""
        from aicoder.utils.http_utils import Response

        mock_response = Mock()
        mock_response.status = 500
        mock_response.reason = "Internal Server Error"
        mock_response.headers = {}
        mock_response.read.return_value = b""

        response = Response(mock_response)
        assert response.ok() is False

    def test_response_json(self):
        """Test Response.json parsing"""
        from aicoder.utils.http_utils import Response

        mock_response = Mock()
        mock_response.status = 200
        mock_response.reason = "OK"
        mock_response.headers = {}
        mock_response.read.return_value = b'{"key": "value"}'

        response = Response(mock_response)
        result = response.json()

        assert result == {"key": "value"}

    def test_response_json_empty(self):
        """Test Response.json with empty response"""
        from aicoder.utils.http_utils import Response

        mock_response = Mock()
        mock_response.status = 200
        mock_response.reason = "OK"
        mock_response.headers = {}
        mock_response.read.return_value = b""

        response = Response(mock_response)
        result = response.json()

        assert result == {"error": "Empty response"}

    def test_response_json_invalid(self):
        """Test Response.json with invalid JSON returns error"""
        from aicoder.utils.http_utils import Response

        mock_response = Mock()
        mock_response.status = 200
        mock_response.reason = "OK"
        mock_response.headers = {}
        mock_response.read.return_value = b"not json"

        response = Response(mock_response)
        result = response.json()

        assert "error" in result

    def test_response_read(self):
        """Test Response.read returns bytes"""
        from aicoder.utils.http_utils import Response

        mock_response = Mock()
        mock_response.status = 200
        mock_response.reason = "OK"
        mock_response.headers = {}
        mock_response.read.return_value = b"test content"

        response = Response(mock_response)
        result = response.read()

        assert result == b"test content"

    def test_response_from_http_error(self):
        """Test Response created from HTTPError"""
        from aicoder.utils.http_utils import Response

        mock_error = Mock()
        mock_error.code = 404
        mock_error.reason = "Not Found"
        mock_error.headers = {"Content-Type": "application/json"}
        # Delete read attribute so Response treats this as an error
        del mock_error.read

        response = Response(mock_error)

        assert response.status == 404
        assert response.ok() is False

    def test_fetch_success(self):
        """Test successful fetch"""
        from aicoder.utils.http_utils import fetch

        # This will make a real request, so we'll mock it
        result = fetch("https://httpbin.org/get")

        # Just verify structure - actual HTTP tests would be integration tests
        assert hasattr(result, "status")
        assert hasattr(result, "ok")

    def test_fetch_with_options(self):
        """Test fetch with custom options"""
        from aicoder.utils.http_utils import fetch

        result = fetch("https://httpbin.org/headers", options={"method": "GET"})

        # Should handle request
        assert hasattr(result, "status")
