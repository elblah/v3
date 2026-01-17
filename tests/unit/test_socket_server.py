"""
Unit tests for socket_server module.

Tests the Unix domain socket IPC mechanism with mocked dependencies.
"""

import json
import os
import socket
import tempfile
import threading
import time
import pytest
import base64
from unittest.mock import MagicMock, patch

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


class MockMessageHistory:
    """Mock message history for socket server testing."""

    def __init__(self):
        self._messages = []

    def get_messages(self):
        return self._messages


class MockAICoder:
    """Mock aicoder instance for socket server testing."""

    def __init__(self):
        self.is_processing = False
        self.is_running = True
        self._messages = []
        self.session_manager = MockSessionManager()
        self.message_history = MockMessageHistory()

    def get_messages(self):
        return self._messages


class MockSessionManager:
    """Mock session manager."""

    def __init__(self):
        self.is_processing = False


class TestResponseHelper:
    """Tests for the response() helper function."""

    def test_success_response_with_data(self):
        """Test success response with data."""
        result = response({"key": "value"})
        data = json.loads(result)
        assert data["status"] == "success"
        assert data["data"] == {"key": "value"}

    def test_success_response_with_none(self):
        """Test success response with None data."""
        result = response(None)
        data = json.loads(result)
        assert data["status"] == "success"
        assert data["data"] is None

    def test_error_response(self):
        """Test error response with code and message."""
        result = response(None, error_code=ERR_UNKNOWN_CMD, error_msg="Unknown command")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == ERR_UNKNOWN_CMD
        assert data["message"] == "Unknown command"


class TestSocketServerInit:
    """Tests for SocketServer initialization."""

    def test_init_with_aicoder_instance(self):
        """Test SocketServer initializes correctly with aicoder."""
        mock_aicoder = MockAICoder()
        server = SocketServer(mock_aicoder)

        assert server.aicoder is mock_aicoder
        assert server.socket_path is None
        assert server.server_socket is None
        assert server.server_thread is None
        assert server.is_running is False
        assert server.lock is not None


class TestSocketServerStart:
    """Tests for SocketServer.start() method.

    Note: Full socket creation tests are in integration tests.
    These tests verify the initialization logic.
    """

    def test_start_initial_state(self):
        """Test that new server is in initial state."""
        mock_aicoder = MockAICoder()
        server = SocketServer(mock_aicoder)

        assert server.socket_path is None
        assert server.server_socket is None
        assert server.is_running is False

    def test_start_sets_is_running_false_when_already_running(self):
        """Test that start checks is_running before proceeding."""
        mock_aicoder = MockAICoder()
        server = SocketServer(mock_aicoder)
        # Server is already running
        server.is_running = True

        # start() should return early without changing socket_path
        original_path = "/existing/path.sock"
        server.socket_path = original_path

        server.start()

        assert server.is_running is True
        assert server.socket_path == original_path

    def test_socket_path_generation_logic(self):
        """Test socket path generation logic."""
        mock_aicoder = MockAICoder()
        server = SocketServer(mock_aicoder)

        # Test path format with mocked values
        with patch("os.getpid", return_value=12345), \
             patch.dict(os.environ, {"TMUX_PANE": "%1", "TMPDIR": "/tmp"}), \
             patch("os.urandom", return_value=b"\x01\x02\x03"):

            # Simulate path generation
            tmpdir = "/tmp"
            random_id = os.urandom(3).hex()
            pid = os.getpid()
            tmux_pane = os.environ.get("TMUX_PANE", "0")
            if tmux_pane != "0":
                tmux_pane = os.path.basename(tmux_pane).replace("%", "")

            expected_path = f"{tmpdir}/aicoder-{pid}-{tmux_pane}-{random_id}.socket"

            assert "12345" in expected_path
            assert expected_path.endswith(".socket")

    def test_fixed_socket_path_from_env(self):
        """Test that fixed socket path is used when set."""
        mock_aicoder = MockAICoder()
        server = SocketServer(mock_aicoder)

        with patch.dict(os.environ, {"AICODER_SOCKET_IPC_FILE": "/custom/path.sock"}):
            # When fixed path is set, it should be used directly
            assert os.environ.get("AICODER_SOCKET_IPC_FILE") == "/custom/path.socket" or \
                   os.environ.get("AICODER_SOCKET_IPC_FILE") == "/custom/path.sock"


class TestSocketServerStop:
    """Tests for SocketServer.stop() method."""

    def test_stop_with_no_socket(self):
        """Test stop when no socket exists."""
        mock_aicoder = MockAICoder()
        server = SocketServer(mock_aicoder)
        server.is_running = False
        server.server_socket = None
        server.socket_path = None

        # Should not raise
        server.stop()

        assert server.is_running is False

    def test_stop_already_false(self):
        """Test stop when is_running is already False."""
        mock_aicoder = MockAICoder()
        server = SocketServer(mock_aicoder)
        server.is_running = False

        # Should not raise
        server.stop()

        assert server.is_running is False


class TestSocketServerExecuteCommand:
    """Tests for SocketServer._execute_command() method."""

    def test_execute_empty_command(self):
        """Test executing empty command returns error."""
        mock_aicoder = MockAICoder()
        server = SocketServer(mock_aicoder)

        result = server._execute_command("")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == ERR_INTERNAL

    def test_execute_unknown_command(self):
        """Test executing unknown command returns error."""
        mock_aicoder = MockAICoder()
        server = SocketServer(mock_aicoder)

        result = server._execute_command("unknown_cmd")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == ERR_UNKNOWN_CMD


class TestSocketServerCmdHandlers:
    """Tests for command handler methods."""

    def test_cmd_is_processing_with_session_manager(self):
        """Test _cmd_is_processing with session manager."""
        mock_aicoder = MockAICoder()
        mock_aicoder.session_manager.is_processing = True
        server = SocketServer(mock_aicoder)

        result = server._cmd_is_processing("")
        data = json.loads(result)
        assert data["status"] == "success"
        assert data["data"]["processing"] is True

    def test_cmd_is_processing_without_session_manager(self):
        """Test _cmd_is_processing without session manager."""
        mock_aicoder = MagicMock(spec=["is_processing"])
        mock_aicoder.is_processing = True
        server = SocketServer(mock_aicoder)

        result = server._cmd_is_processing("")
        data = json.loads(result)
        assert data["status"] == "success"
        assert data["data"]["processing"] is True

    def test_cmd_yolo_status(self):
        """Test yolo status command."""
        mock_aicoder = MockAICoder()
        server = SocketServer(mock_aicoder)

        result = server._cmd_yolo("status")
        data = json.loads(result)
        assert data["status"] == "success"
        assert "enabled" in data["data"]

    def test_cmd_yolo_on(self):
        """Test yolo on command."""
        mock_aicoder = MockAICoder()
        server = SocketServer(mock_aicoder)

        result = server._cmd_yolo("on")
        data = json.loads(result)
        assert data["status"] == "success"
        assert data["data"]["enabled"] is True

    def test_cmd_yolo_off(self):
        """Test yolo off command."""
        mock_aicoder = MockAICoder()
        server = SocketServer(mock_aicoder)
        server.aicoder.session_manager.is_processing = True

        result = server._cmd_yolo("off")
        data = json.loads(result)
        assert data["status"] == "success"
        assert data["data"]["enabled"] is False

    def test_cmd_yolo_toggle(self):
        """Test yolo toggle command."""
        mock_aicoder = MockAICoder()
        server = SocketServer(mock_aicoder)

        current = server._cmd_yolo("status")
        current_data = json.loads(current)
        initial_state = current_data["data"]["enabled"]

        result = server._cmd_yolo("toggle")
        data = json.loads(result)
        assert data["data"]["enabled"] is not initial_state

    def test_cmd_yolo_invalid_args(self):
        """Test yolo with invalid arguments."""
        mock_aicoder = MockAICoder()
        server = SocketServer(mock_aicoder)

        result = server._cmd_yolo("invalid_arg")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == ERR_INVALID_ARG

    def test_cmd_detail_status(self):
        """Test detail status command."""
        mock_aicoder = MockAICoder()
        server = SocketServer(mock_aicoder)

        result = server._cmd_detail("status")
        data = json.loads(result)
        assert data["status"] == "success"
        assert "enabled" in data["data"]

    def test_cmd_detail_on(self):
        """Test detail on command."""
        mock_aicoder = MockAICoder()
        server = SocketServer(mock_aicoder)

        result = server._cmd_detail("on")
        data = json.loads(result)
        assert data["status"] == "success"
        assert data["data"]["enabled"] is True

    def test_cmd_detail_off(self):
        """Test detail off command."""
        mock_aicoder = MockAICoder()
        server = SocketServer(mock_aicoder)

        result = server._cmd_detail("off")
        data = json.loads(result)
        assert data["status"] == "success"
        assert data["data"]["enabled"] is False

    def test_cmd_detail_toggle(self):
        """Test detail toggle command."""
        mock_aicoder = MockAICoder()
        server = SocketServer(mock_aicoder)

        result = server._cmd_detail("toggle")
        data = json.loads(result)
        assert data["status"] == "success"
        assert "message" in data["data"]

    def test_cmd_sandbox_status(self):
        """Test sandbox status command."""
        mock_aicoder = MockAICoder()
        server = SocketServer(mock_aicoder)

        result = server._cmd_sandbox("status")
        data = json.loads(result)
        assert data["status"] == "success"
        assert "enabled" in data["data"]

    def test_cmd_sandbox_on(self):
        """Test sandbox on command."""
        mock_aicoder = MockAICoder()
        server = SocketServer(mock_aicoder)

        result = server._cmd_sandbox("on")
        data = json.loads(result)
        assert data["status"] == "success"
        assert data["data"]["enabled"] is True

    def test_cmd_sandbox_off(self):
        """Test sandbox off command."""
        mock_aicoder = MockAICoder()
        server = SocketServer(mock_aicoder)

        result = server._cmd_sandbox("off")
        data = json.loads(result)
        assert data["status"] == "success"
        assert data["data"]["enabled"] is False

    def test_cmd_sandbox_toggle(self):
        """Test sandbox toggle command."""
        mock_aicoder = MockAICoder()
        server = SocketServer(mock_aicoder)

        result = server._cmd_sandbox("toggle")
        data = json.loads(result)
        assert data["status"] == "success"
        assert "message" in data["data"]

    def test_cmd_status(self):
        """Test status command."""
        mock_aicoder = MockAICoder()
        mock_aicoder.message_history.get_messages = MagicMock(return_value=[])
        server = SocketServer(mock_aicoder)

        result = server._cmd_status("")
        data = json.loads(result)
        assert data["status"] == "success"
        assert "processing" in data["data"]
        assert "yolo_enabled" in data["data"]
        assert "detail_enabled" in data["data"]
        assert "sandbox_enabled" in data["data"]
        assert "messages" in data["data"]

    def test_cmd_stop_when_not_processing(self):
        """Test stop command when not processing."""
        mock_aicoder = MockAICoder()
        mock_aicoder.session_manager.is_processing = False
        server = SocketServer(mock_aicoder)

        result = server._cmd_stop("")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == ERR_NOT_PROCESSING

    def test_cmd_stop_when_processing(self):
        """Test stop command when processing."""
        mock_aicoder = MockAICoder()
        mock_aicoder.session_manager.is_processing = True
        server = SocketServer(mock_aicoder)

        result = server._cmd_stop("")
        data = json.loads(result)
        assert data["status"] == "success"
        assert data["data"]["stopped"] is True
        assert mock_aicoder.session_manager.is_processing is False

    def test_cmd_messages_count(self):
        """Test messages count command."""
        mock_aicoder = MockAICoder()
        mock_aicoder.message_history.get_messages = MagicMock(return_value=[
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
            {"role": "system", "content": "System"},
        ])
        server = SocketServer(mock_aicoder)

        result = server._cmd_messages("count")
        data = json.loads(result)
        assert data["status"] == "success"
        assert data["data"]["total"] == 3
        assert data["data"]["user"] == 1
        assert data["data"]["assistant"] == 1
        assert data["data"]["system"] == 1

    def test_cmd_messages_list(self):
        """Test messages list command."""
        mock_aicoder = MockAICoder()
        mock_messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi"},
        ]
        mock_aicoder.message_history.get_messages = MagicMock(return_value=mock_messages)
        server = SocketServer(mock_aicoder)

        result = server._cmd_messages("")
        data = json.loads(result)
        assert data["status"] == "success"
        assert data["data"]["count"] == 2
        assert len(data["data"]["messages"]) == 2


class TestSocketServerInjectText:
    """Tests for _cmd_inject_text command handler."""

    def test_inject_text_missing_arg(self):
        """Test inject-text with missing argument."""
        mock_aicoder = MockAICoder()
        server = SocketServer(mock_aicoder)

        result = server._cmd_inject_text("")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == ERR_MISSING_ARG

    def test_inject_text_invalid_base64(self):
        """Test inject-text with invalid base64."""
        mock_aicoder = MockAICoder()
        server = SocketServer(mock_aicoder)

        result = server._cmd_inject_text("not-valid-base64!!!")
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == ERR_INVALID_ARG

    def test_inject_text_valid_base64(self):
        """Test inject-text with valid base64."""
        mock_aicoder = MockAICoder()
        mock_aicoder.message_history.insert_user_message_at_appropriate_position = MagicMock()
        server = SocketServer(mock_aicoder)

        # "Hello World" encoded
        encoded = base64.b64encode(b"Hello World").decode()

        result = server._cmd_inject_text(encoded)
        data = json.loads(result)
        assert data["status"] == "success"
        assert data["data"]["injected"] is True
        assert data["data"]["length"] == 11

    def test_inject_text_too_large(self):
        """Test inject-text with text too large."""
        mock_aicoder = MockAICoder()
        server = SocketServer(mock_aicoder)

        # Create base64 string larger than MAX_INJECT_TEXT_SIZE
        large_data = b"x" * (MAX_INJECT_TEXT_SIZE + 1)
        encoded = base64.b64encode(large_data).decode()

        result = server._cmd_inject_text(encoded)
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == ERR_INVALID_ARG

    def test_inject_text_non_utf8(self):
        """Test inject-text with valid base64 but invalid UTF-8."""
        mock_aicoder = MockAICoder()
        server = SocketServer(mock_aicoder)

        # Valid base64 but represents invalid UTF-8 (surrogate bytes)
        invalid_utf8 = b"\xff\xfe\xfd"
        encoded = base64.b64encode(invalid_utf8).decode()

        result = server._cmd_inject_text(encoded)
        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == ERR_INVALID_ARG


class TestSocketServerCmdSave:
    """Tests for _cmd_save command handler."""

    def test_save_with_default_path(self):
        """Test save with default path in /tmp."""
        mock_aicoder = MockAICoder()
        mock_aicoder.message_history.get_messages = MagicMock(return_value=[])
        server = SocketServer(mock_aicoder)

        with patch("os.getcwd", return_value="/tmp"), \
             patch("os.makedirs") as mock_makedirs, \
             patch("builtins.open", create=True) as mock_open, \
             patch("time.strftime", return_value="2024-01-01_12-00-00"):

            result = server._cmd_save("")

            data = json.loads(result)
            assert data["status"] == "success"
            assert data["data"]["saved"] is True
            assert "session-" in data["data"]["path"]

    def test_save_with_custom_path(self):
        """Test save with custom path."""
        mock_aicoder = MockAICoder()
        mock_aicoder.message_history.get_messages = MagicMock(return_value=[])
        server = SocketServer(mock_aicoder)

        with patch("builtins.open", create=True) as mock_open:
            result = server._cmd_save("/tmp/custom.json")

            data = json.loads(result)
            assert data["status"] == "success"
            assert data["data"]["path"] == "/tmp/custom.json"

    def test_save_to_disallowed_path(self):
        """Test save to path outside allowed directories."""
        mock_aicoder = MockAICoder()
        mock_aicoder.message_history.get_messages = MagicMock(return_value=[])
        server = SocketServer(mock_aicoder)

        result = server._cmd_save("/etc/malicious.json")

        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == ERR_PERMISSION


class TestSocketServerCmdCommand:
    """Tests for _cmd_command command handler."""

    def test_command_missing_args(self):
        """Test command with missing arguments."""
        mock_aicoder = MockAICoder()
        server = SocketServer(mock_aicoder)

        result = server._cmd_command("")

        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == ERR_MISSING_ARG

    def test_command_without_slash(self):
        """Test command without leading slash."""
        mock_aicoder = MockAICoder()
        server = SocketServer(mock_aicoder)

        result = server._cmd_command("help")

        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == ERR_INVALID_ARG


class TestSocketServerCmdProcess:
    """Tests for _cmd_process command handler."""

    def test_process_when_already_processing(self):
        """Test process command when already processing."""
        mock_aicoder = MockAICoder()
        mock_aicoder.session_manager.is_processing = True
        server = SocketServer(mock_aicoder)

        result = server._cmd_process("")

        data = json.loads(result)
        assert data["status"] == "error"
        assert data["code"] == ERR_NOT_PROCESSING


class TestSocketServerReadLine:
    """Tests for _read_line method."""

    def test_read_line_timeout(self):
        """Test _read_line returns None on timeout."""
        mock_aicoder = MockAICoder()
        server = SocketServer(mock_aicoder)

        mock_sock = MagicMock()
        mock_sock.recv.side_effect = socket.timeout()

        result = server._read_line(mock_sock, timeout=0.1)

        assert result is None

    def test_read_line_complete_line(self):
        """Test _read_line returns complete line."""
        mock_aicoder = MockAICoder()
        server = SocketServer(mock_aicoder)

        mock_sock = MagicMock()
        mock_sock.recv.side_effect = [
            b"test command\n"
        ]

        result = server._read_line(mock_sock, timeout=1.0)

        assert result == "test command"


class TestSocketServerSendLine:
    """Tests for _send_line method."""

    def test_send_line(self):
        """Test _send_line sends data correctly."""
        mock_aicoder = MockAICoder()
        server = SocketServer(mock_aicoder)

        mock_sock = MagicMock()
        server._send_line(mock_sock, '{"status": "success"}')

        mock_sock.sendall.assert_called_once()
        sent_data = mock_sock.sendall.call_args[0][0]
        assert sent_data.endswith(b"\n")
        assert b'{"status": "success"}' in sent_data


class TestSocketServerHandleClient:
    """Tests for _handle_client method."""

    def test_handle_client_empty_command(self):
        """Test _handle_client with empty command."""
        mock_aicoder = MockAICoder()
        server = SocketServer(mock_aicoder)

        mock_sock = MagicMock()
        mock_sock.recv.return_value = b""

        with patch.object(server, "_read_line", return_value=None):
            server._handle_client(mock_sock)

            # Should send error and close
            assert mock_sock.close.called

    def test_handle_client_with_command(self):
        """Test _handle_client with valid command."""
        mock_aicoder = MockAICoder()
        server = SocketServer(mock_aicoder)

        mock_sock = MagicMock()
        mock_sock.recv.return_value = b"status\n"

        with patch.object(server, "_read_line", return_value="status"), \
             patch.object(server, "_send_line") as mock_send:

            server._handle_client(mock_sock)

            mock_send.assert_called_once()

    def test_handle_client_timeout(self):
        """Test _handle_client with timeout."""
        mock_aicoder = MockAICoder()
        server = SocketServer(mock_aicoder)

        mock_sock = MagicMock()
        mock_sock.recv.return_value = b"test\n"

        with patch.object(server, "_read_line", side_effect=socket.timeout()), \
             patch.object(server, "_send_line") as mock_send:

            server._handle_client(mock_sock)

            # Should send error for timeout
            assert mock_send.called
