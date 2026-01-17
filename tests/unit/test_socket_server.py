"""Unit tests for socket server - response helpers and command handlers."""

import pytest
from unittest.mock import MagicMock, patch
import json
import sys
sys.path.insert(0, '/home/blah/storage/ai-worktree-storage/feat_test_coverage__20260117_062928')

from aicoder.core.socket_server import (
    SocketServer,
    response,
    ERR_NOT_PROCESSING,
    ERR_UNKNOWN_CMD,
    ERR_MISSING_ARG,
    ERR_INVALID_ARG,
    ERR_PERMISSION,
    ERR_IO_ERROR,
    ERR_INTERNAL,
    MAX_INJECT_TEXT_SIZE,
)


class TestResponseHelper:
    """Test the response helper function."""

    def test_response_success(self):
        """Test successful response."""
        result = response({"key": "value"})
        data = json.loads(result)
        assert data["status"] == "success"
        assert data["data"] == {"key": "value"}

    def test_response_success_none(self):
        """Test successful response with no data."""
        result = response()
        data = json.loads(result)
        assert data["status"] == "success"
        assert data["data"] is None

    def test_response_error_with_code(self):
        """Test error response with code."""
        result = response(None, error_code=ERR_UNKNOWN_CMD, error_msg="Unknown command")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == ERR_UNKNOWN_CMD
        assert data["message"] == "Unknown command"

    def test_response_error_not_processing(self):
        """Test not processing error response."""
        result = response(None, error_code=ERR_NOT_PROCESSING, error_msg="Not processing")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == ERR_NOT_PROCESSING

    def test_response_error_missing_arg(self):
        """Test missing argument error response."""
        result = response(None, error_code=ERR_MISSING_ARG, error_msg="Missing arg")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == ERR_MISSING_ARG

    def test_response_error_invalid_arg(self):
        """Test invalid argument error response."""
        result = response(None, error_code=ERR_INVALID_ARG, error_msg="Invalid arg")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == ERR_INVALID_ARG

    def test_response_error_permission(self):
        """Test permission error response."""
        result = response(None, error_code=ERR_PERMISSION, error_msg="Permission denied")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == ERR_PERMISSION

    def test_response_error_io(self):
        """Test IO error response."""
        result = response(None, error_code=ERR_IO_ERROR, error_msg="IO error")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == ERR_IO_ERROR

    def test_response_error_internal(self):
        """Test internal error response."""
        result = response(None, error_code=ERR_INTERNAL, error_msg="Internal error")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == ERR_INTERNAL


class TestSocketServerInit:
    """Test SocketServer initialization."""

    def test_init_sets_aicoder(self):
        """Test initialization sets aicoder instance."""
        mock_aicoder = MagicMock()
        server = SocketServer(mock_aicoder)
        assert server.aicoder == mock_aicoder

    def test_init_defaults(self):
        """Test initialization sets default values."""
        mock_aicoder = MagicMock()
        server = SocketServer(mock_aicoder)
        assert server.socket_path is None
        assert server.server_socket is None
        assert server.server_thread is None
        assert server.is_running is False


class TestSocketServerCommandHandlers:
    """Test SocketServer command handlers."""

    def _create_server(self):
        """Create a test server instance."""
        mock_aicoder = MagicMock()
        mock_aicoder.session_manager = MagicMock()
        mock_aicoder.session_manager.is_processing = False
        server = SocketServer(mock_aicoder)
        server.lock = MagicMock()
        server.lock.__enter__ = MagicMock()
        server.lock.__exit__ = MagicMock()
        return server

    def test_cmd_is_processing_true(self):
        """Test is_processing when processing."""
        server = self._create_server()
        server.aicoder.session_manager.is_processing = True

        with patch.object(server, 'lock'):
            result = server._cmd_is_processing("")
            data = json.loads(result)
            assert data["status"] == "success"
            assert data["data"]["processing"] is True

    def test_cmd_is_processing_false(self):
        """Test is_processing when not processing."""
        server = self._create_server()
        server.aicoder.session_manager.is_processing = False

        with patch.object(server, 'lock'):
            result = server._cmd_is_processing("")
            data = json.loads(result)
            assert data["status"] == "success"
            assert data["data"]["processing"] is False

    def test_cmd_yolo_status(self):
        """Test yolo status command."""
        server = self._create_server()

        with patch('aicoder.core.socket_server.Config') as mock_config:
            mock_config.yolo_mode.return_value = False
            result = server._cmd_yolo("")
            data = json.loads(result)
            assert data["status"] == "success"
            assert "enabled" in data["data"]

    def test_cmd_yolo_on(self):
        """Test yolo on command."""
        server = self._create_server()

        with patch('aicoder.core.socket_server.Config') as mock_config:
            mock_config.yolo_mode.return_value = False
            with patch.object(mock_config, 'set_yolo_mode'):
                result = server._cmd_yolo("on")
                data = json.loads(result)
                assert data["status"] == "success"
                assert data["data"]["enabled"] is True

    def test_cmd_yolo_off(self):
        """Test yolo off command."""
        server = self._create_server()

        with patch('aicoder.core.socket_server.Config') as mock_config:
            mock_config.yolo_mode.return_value = True
            with patch.object(mock_config, 'set_yolo_mode'):
                result = server._cmd_yolo("off")
                data = json.loads(result)
                assert data["status"] == "success"
                assert data["data"]["enabled"] is False

    def test_cmd_yolo_toggle(self):
        """Test yolo toggle command."""
        server = self._create_server()

        with patch('aicoder.core.socket_server.Config') as mock_config:
            mock_config.yolo_mode.return_value = False
            with patch.object(mock_config, 'set_yolo_mode'):
                result = server._cmd_yolo("toggle")
                data = json.loads(result)
                assert data["status"] == "success"
                assert "enabled" in data["data"]

    def test_cmd_yolo_invalid(self):
        """Test yolo with invalid argument."""
        server = self._create_server()

        result = server._cmd_yolo("invalid")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == ERR_INVALID_ARG

    def test_cmd_detail_status(self):
        """Test detail status command."""
        server = self._create_server()

        with patch('aicoder.core.socket_server.Config') as mock_config:
            mock_config.detail_mode.return_value = True
            result = server._cmd_detail("")
            data = json.loads(result)
            assert data["status"] == "success"
            assert data["data"]["enabled"] is True

    def test_cmd_detail_on(self):
        """Test detail on command."""
        server = self._create_server()

        with patch('aicoder.core.socket_server.Config') as mock_config:
            mock_config.detail_mode.return_value = False
            with patch.object(mock_config, 'set_detail_mode'):
                result = server._cmd_detail("on")
                data = json.loads(result)
                assert data["status"] == "success"
                assert data["data"]["enabled"] is True

    def test_cmd_detail_off(self):
        """Test detail off command."""
        server = self._create_server()

        with patch('aicoder.core.socket_server.Config') as mock_config:
            mock_config.detail_mode.return_value = True
            with patch.object(mock_config, 'set_detail_mode'):
                result = server._cmd_detail("off")
                data = json.loads(result)
                assert data["status"] == "success"
                assert data["data"]["enabled"] is False

    def test_cmd_sandbox_status(self):
        """Test sandbox status command."""
        server = self._create_server()

        with patch('aicoder.core.socket_server.Config') as mock_config:
            mock_config.sandbox_disabled.return_value = False
            result = server._cmd_sandbox("")
            data = json.loads(result)
            assert data["status"] == "success"
            assert data["data"]["enabled"] is True

    def test_cmd_sandbox_disabled(self):
        """Test sandbox when disabled."""
        server = self._create_server()

        with patch('aicoder.core.socket_server.Config') as mock_config:
            mock_config.sandbox_disabled.return_value = True
            result = server._cmd_sandbox("")
            data = json.loads(result)
            assert data["status"] == "success"
            assert data["data"]["enabled"] is False

    def test_cmd_status(self):
        """Test status command."""
        server = self._create_server()
        server.aicoder.message_history.get_messages.return_value = []

        with patch.object(server, 'lock'):
            with patch('aicoder.core.socket_server.Config') as mock_config:
                mock_config.yolo_mode.return_value = False
                mock_config.detail_mode.return_value = False
                mock_config.sandbox_disabled.return_value = False
                result = server._cmd_status("")
                data = json.loads(result)
                assert data["status"] == "success"
                assert "processing" in data["data"]
                assert "yolo_enabled" in data["data"]
                assert "sandbox_enabled" in data["data"]
                assert "messages" in data["data"]

    def test_cmd_stop_when_processing(self):
        """Test stop command when processing."""
        server = self._create_server()
        server.aicoder.session_manager.is_processing = True

        with patch.object(server, 'lock'):
            result = server._cmd_stop("")
            data = json.loads(result)
            assert data["status"] == "success"
            assert data["data"]["stopped"] is True

    def test_cmd_stop_when_not_processing(self):
        """Test stop command when not processing."""
        server = self._create_server()
        server.aicoder.session_manager.is_processing = False

        with patch.object(server, 'lock'):
            result = server._cmd_stop("")
            data = json.loads(result)
            assert data["status"] == "error"
            assert data["code"] == ERR_NOT_PROCESSING

    def test_cmd_messages_count(self):
        """Test messages count command."""
        server = self._create_server()
        server.aicoder.message_history.get_messages.return_value = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
            {"role": "user", "content": "How are you?"},
            {"role": "assistant", "content": "Good"},
        ]

        result = server._cmd_messages("count")
        data = json.loads(result)
        assert data["status"] == "success"
        assert data["data"]["total"] == 4
        assert data["data"]["user"] == 2
        assert data["data"]["assistant"] == 2

    def test_cmd_messages_all(self):
        """Test messages command returns all messages."""
        server = self._create_server()
        messages = [{"role": "user", "content": "Hello"}]
        server.aicoder.message_history.get_messages.return_value = messages

        result = server._cmd_messages("")
        data = json.loads(result)
        assert data["status"] == "success"
        assert data["data"]["messages"] == messages
        assert data["data"]["count"] == 1


class TestSocketServerExecuteCommand:
    """Test SocketServer command execution."""

    def _create_server(self):
        """Create a test server instance."""
        mock_aicoder = MagicMock()
        mock_aicoder.session_manager = MagicMock()
        mock_aicoder.session_manager.is_processing = False
        server = SocketServer(mock_aicoder)
        server.lock = MagicMock()
        server.lock.__enter__ = MagicMock()
        server.lock.__exit__ = MagicMock()
        return server

    def test_execute_empty_command(self):
        """Test executing empty command."""
        server = self._create_server()

        result = server._execute_command("")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == ERR_INTERNAL

    def test_execute_unknown_command(self):
        """Test executing unknown command."""
        server = self._create_server()

        result = server._execute_command("unknown_command")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == ERR_UNKNOWN_CMD

    def test_execute_yolo_command(self):
        """Test executing yolo command."""
        server = self._create_server()

        with patch('aicoder.core.socket_server.Config') as mock_config:
            mock_config.yolo_mode.return_value = False
            result = server._execute_command("yolo status")
            data = json.loads(result)
            assert data["status"] == "success"

    def test_execute_detail_command(self):
        """Test executing detail command."""
        server = self._create_server()

        with patch('aicoder.core.socket_server.Config') as mock_config:
            mock_config.detail_mode.return_value = True
            result = server._execute_command("detail status")
            data = json.loads(result)
            assert data["status"] == "success"

    def test_execute_sandbox_command(self):
        """Test executing sandbox command."""
        server = self._create_server()

        with patch('aicoder.core.socket_server.Config') as mock_config:
            mock_config.sandbox_disabled.return_value = False
            result = server._execute_command("sandbox status")
            data = json.loads(result)
            assert data["status"] == "success"


class TestInjectTextCommand:
    """Test inject-text command handler."""

    def _create_server(self):
        """Create a test server instance."""
        mock_aicoder = MagicMock()
        mock_aicoder.session_manager = MagicMock()
        mock_aicoder.message_history = MagicMock()
        server = SocketServer(mock_aicoder)
        server.lock = MagicMock()
        server.lock.__enter__ = MagicMock()
        server.lock.__exit__ = MagicMock()
        return server

    def test_inject_text_empty(self):
        """Test inject-text with empty argument."""
        server = self._create_server()

        result = server._cmd_inject_text("")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == ERR_MISSING_ARG

    def test_inject_text_invalid_base64(self):
        """Test inject-text with invalid base64."""
        server = self._create_server()

        result = server._cmd_inject_text("not-valid-base64")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == ERR_INVALID_ARG

    def test_inject_text_valid(self):
        """Test inject-text with valid base64."""
        server = self._create_server()
        text = "Hello World"
        encoded = __import__('base64').b64encode(text.encode()).decode()

        with patch('aicoder.core.socket_server.LogUtils'):
            with patch('aicoder.core.socket_server.Config') as mock_config:
                mock_config.debug.return_value = False
                result = server._cmd_inject_text(encoded)
                data = json.loads(result)
                assert data["status"] == "success"
                assert data["data"]["injected"] is True
                assert data["data"]["length"] == len(text)

    def test_inject_text_too_large(self):
        """Test inject-text with text too large."""
        server = self._create_server()
        # Create text larger than MAX_INJECT_TEXT_SIZE
        large_text = "x" * (MAX_INJECT_TEXT_SIZE + 1)
        encoded = __import__('base64').b64encode(large_text.encode()).decode()

        result = server._cmd_inject_text(encoded)
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == ERR_INVALID_ARG

    def test_inject_text_non_utf8(self):
        """Test inject-text with valid base64 but invalid UTF-8."""
        server = self._create_server()
        # Create valid base64 that isn't valid UTF-8
        # This is tricky - let's just test error handling
        import base64
        # Invalid UTF-8 sequence
        invalid_utf8 = b'\xff\xfe\xfd'
        encoded = base64.b64encode(invalid_utf8).decode()

        result = server._cmd_inject_text(encoded)
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == ERR_INVALID_ARG


class TestMaxInjectTextSize:
    """Test MAX_INJECT_TEXT_SIZE constant."""

    def test_max_inject_text_size_value(self):
        """Test max inject text size is 10MB."""
        assert MAX_INJECT_TEXT_SIZE == 10 * 1024 * 1024
        assert MAX_INJECT_TEXT_SIZE == 10485760


class TestSocketServerExecuteCommandExtended:
    """Extended tests for command execution."""

    def _create_server(self):
        """Create a test server instance."""
        mock_aicoder = MagicMock()
        mock_aicoder.session_manager = MagicMock()
        mock_aicoder.session_manager.is_processing = False
        mock_aicoder.message_history = MagicMock()
        mock_aicoder.message_history.get_messages.return_value = []
        server = SocketServer(mock_aicoder)
        server.lock = MagicMock()
        server.lock.__enter__ = MagicMock()
        server.lock.__exit__ = MagicMock()
        return server

    def test_execute_command_with_args(self):
        """Test executing command with arguments."""
        server = self._create_server()

        with patch('aicoder.core.socket_server.Config') as mock_config:
            mock_config.yolo_mode.return_value = False
            result = server._execute_command("yolo on")
            data = json.loads(result)
            assert data["status"] == "success"
            assert data["data"]["enabled"] is True

    def test_execute_command_sandbox_toggle(self):
        """Test sandbox toggle command."""
        server = self._create_server()

        with patch('aicoder.core.socket_server.Config') as mock_config:
            mock_config.sandbox_disabled.return_value = False
            with patch.object(mock_config, 'set_sandbox_disabled'):
                result = server._execute_command("sandbox toggle")
                data = json.loads(result)
                assert data["status"] == "success"
                assert "enabled" in data["data"]

    def test_execute_command_status(self):
        """Test status command execution."""
        server = self._create_server()

        with patch.object(server, 'lock'):
            with patch('aicoder.core.socket_server.Config') as mock_config:
                mock_config.yolo_mode.return_value = False
                mock_config.detail_mode.return_value = False
                mock_config.sandbox_disabled.return_value = False
                result = server._execute_command("status")
                data = json.loads(result)
                assert data["status"] == "success"

    def test_execute_command_process(self):
        """Test process command execution."""
        server = self._create_server()
        server.aicoder.session_manager.process_with_ai = MagicMock()

        result = server._execute_command("process")
        data = json.loads(result)
        assert data["status"] == "success"
        assert data["data"]["processing"] is True

    def test_execute_command_process_already_running(self):
        """Test process command when already processing."""
        server = self._create_server()
        server.aicoder.session_manager.is_processing = True

        result = server._execute_command("process")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == ERR_NOT_PROCESSING

    def test_execute_command_messages_count(self):
        """Test messages count command."""
        server = self._create_server()
        server.aicoder.message_history.get_messages.return_value = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]

        result = server._execute_command("messages count")
        data = json.loads(result)
        assert data["status"] == "success"
        assert data["data"]["total"] == 2

    def test_execute_command_messages_list(self):
        """Test messages list command."""
        server = self._create_server()
        messages = [{"role": "user", "content": "Hello"}]
        server.aicoder.message_history.get_messages.return_value = messages

        result = server._execute_command("messages")
        data = json.loads(result)
        assert data["status"] == "success"
        assert data["data"]["messages"] == messages


class TestSocketServerCommandHandlerDetails:
    """Test command handler details (detail command)."""

    def _create_server(self):
        """Create a test server instance."""
        mock_aicoder = MagicMock()
        mock_aicoder.session_manager = MagicMock()
        mock_aicoder.session_manager.is_processing = False
        server = SocketServer(mock_aicoder)
        server.lock = MagicMock()
        server.lock.__enter__ = MagicMock()
        server.lock.__exit__ = MagicMock()
        return server

    def test_cmd_detail_invalid_arg(self):
        """Test detail with invalid argument."""
        server = self._create_server()

        result = server._cmd_detail("invalid")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == ERR_INVALID_ARG

    def test_cmd_sandbox_on(self):
        """Test sandbox on command."""
        server = self._create_server()

        with patch('aicoder.core.socket_server.Config') as mock_config:
            mock_config.sandbox_disabled.return_value = True
            with patch.object(mock_config, 'set_sandbox_disabled'):
                result = server._cmd_sandbox("on")
                data = json.loads(result)
                assert data["status"] == "success"
                assert data["data"]["enabled"] is True

    def test_cmd_sandbox_off(self):
        """Test sandbox off command."""
        server = self._create_server()

        with patch('aicoder.core.socket_server.Config') as mock_config:
            mock_config.sandbox_disabled.return_value = False
            with patch.object(mock_config, 'set_sandbox_disabled'):
                result = server._cmd_sandbox("off")
                data = json.loads(result)
                assert data["status"] == "success"
                assert data["data"]["enabled"] is False

    def test_cmd_stop_with_alternative_interface(self):
        """Test stop with is_processing on aicoder directly."""
        server = self._create_server()
        server.aicoder.is_processing = True
        del server.aicoder.session_manager  # Remove session_manager

        with patch.object(server, 'lock'):
            result = server._cmd_stop("")
            data = json.loads(result)
            assert data["status"] == "success"
            assert data["data"]["stopped"] is True
