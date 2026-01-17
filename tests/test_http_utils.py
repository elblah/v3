"""
Test http_utils module
Tests for HTTP utilities and Response class
"""

import pytest
from unittest.mock import Mock, patch
from aicoder.utils.http_utils import Response, fetch


class MockHeaders(dict):
    """Mock headers that behave like HTTP response headers"""
    def __iter__(self):
        return iter(self.keys())


class TestResponse:
    """Test Response class"""

    def test_successful_response(self):
        mock_response = Mock()
        mock_response.status = 200
        mock_response.reason = "OK"
        mock_response.headers = MockHeaders({"Content-Type": "application/json"})
        
        response = Response(mock_response)
        assert response.status == 200
        assert response.ok() is True

    def test_error_response(self):
        mock_response = Mock()
        mock_response.code = 404
        mock_response.reason = "Not Found"
        mock_response.headers = MockHeaders({})
        # Response uses getattr with "status" default, but our mock has "code"
        # So Response will use the default value of 200, not 404
        # We need to set status attribute to match the code
        mock_response.status = 404  # Set status to match code
        
        response = Response(mock_response)
        assert response.status == 404
        assert response.ok() is False

    def test_json_parsing(self):
        mock_response = Mock()
        mock_response.read.return_value = b'{"key": "value"}'
        mock_response.status = 200
        mock_response.reason = "OK"
        mock_response.headers = MockHeaders({})
        
        response = Response(mock_response)
        result = response.json()
        assert result["key"] == "value"

    def test_json_empty_response(self):
        mock_response = Mock()
        mock_response.read.return_value = b""
        mock_response.status = 200
        mock_response.reason = "OK"
        mock_response.headers = MockHeaders({})
        
        response = Response(mock_response)
        result = response.json()
        assert "error" in result

    def test_json_invalid_json(self):
        mock_response = Mock()
        mock_response.read.return_value = b'invalid { json'
        mock_response.status = 200
        mock_response.reason = "OK"
        mock_response.headers = MockHeaders({})
        
        response = Response(mock_response)
        result = response.json()
        assert "error" in result

    def test_read_returns_bytes(self):
        mock_response = Mock()
        mock_response.read.return_value = b"test content"
        mock_response.status = 200
        mock_response.reason = "OK"
        mock_response.headers = MockHeaders({})
        
        response = Response(mock_response)
        result = response.read()
        assert result == b"test content"

    def test_read_caches_content(self):
        mock_response = Mock()
        mock_response.read.return_value = b"content"
        mock_response.status = 200
        mock_response.reason = "OK"
        mock_response.headers = MockHeaders({})
        
        response = Response(mock_response)
        response.read()
        response.read()  # Second call should use cache
        mock_response.read.assert_called_once()


class TestFetch:
    """Test fetch function"""

    def test_basic_get(self):
        mock_response = Mock()
        mock_response.status = 200
        mock_response.reason = "OK"
        mock_response.headers = MockHeaders({})

        with patch('urllib.request.Request') as mock_request, \
             patch('urllib.request.urlopen', return_value=mock_response):
            result = fetch("http://example.com")
            assert isinstance(result, Response)
            assert result.status == 200

    def test_post_with_body(self):
        mock_response = Mock()
        mock_response.status = 201
        mock_response.reason = "Created"
        mock_response.headers = MockHeaders({})

        with patch('urllib.request.Request') as mock_request, \
             patch('urllib.request.urlopen', return_value=mock_response):
            result = fetch("http://example.com", {
                "method": "POST",
                "body": '{"key": "value"}'
            })
            assert result.status == 201

    def test_timeout_passed(self):
        mock_response = Mock()
        mock_response.status = 200
        mock_response.reason = "OK"
        mock_response.headers = MockHeaders({})

        with patch('urllib.request.Request'), \
             patch('urllib.request.urlopen', return_value=mock_response):
            fetch("http://example.com", {"timeout": 60})

    def test_handles_http_error(self):
        from urllib.error import HTTPError
        mock_error = HTTPError("url", 404, "Not Found", {}, None)

        with patch('urllib.request.Request'), \
             patch('urllib.request.urlopen', side_effect=mock_error):
            result = fetch("http://example.com")
            assert result.status == 404

    def test_raises_connection_error(self):
        with patch('urllib.request.Request'), \
             patch('urllib.request.urlopen', side_effect=Exception("Connection refused")):
            with pytest.raises(Exception) as exc_info:
                fetch("http://example.com")
            assert "Request failed" in str(exc_info.value)
