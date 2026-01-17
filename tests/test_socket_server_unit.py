"""
Unit tests for socket_server module.
Tests the actual SocketServer class and response helper function.
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
)


class TestResponseHelper:
    """Test the response() helper function."""

    def test_response_success_with_data(self):
        """Test success response with data."""
        result = response({"key": "value"})
        parsed = json.loads(result)
        assert parsed["status"] == "success"
        assert parsed["data"] == {"key": "value"}

    def test_response_success_none_data(self):
        """Test success response with None data."""
        result = response(None)
        parsed = json.loads(result)
        assert parsed["status"] == "success"
        assert parsed["data"] is None

    def test_response_error_with_code_and_message(self):
        """Test error response with code and message."""
        result = response(None, error_code=ERR_UNKNOWN_CMD, error_msg="Unknown command")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["code"] == ERR_UNKNOWN_CMD
        assert parsed["message"] == "Unknown command"

    def test_response_error_all_codes(self):
        """Test all error codes are correctly defined."""
        assert ERR_NOT_PROCESSING == 1001
        assert ERR_UNKNOWN_CMD == 1002
        assert ERR_MISSING_ARG == 1003
        assert ERR_INVALID_ARG == 1004
        assert ERR_PERMISSION == 1101
        assert ERR_IO_ERROR == 1201
        assert ERR_INTERNAL == 1301


class MockAICoder:
    """Mock aicoder instance for testing."""

    def __init__(self):
        self.is_processing = False
        self.is_running = True
        self._messages = []
        self.session_manager = MockSessionManager()

    def get_messages(self):
        return self._messages


class MockSessionManager:
    """Mock session manager."""

    def __init__(self):
        self.is_processing = False


class MockMessageHistory:
    """Mock message history."""

    def __init__(self, messages=None):
        self._messages = messages or []

    def get_messages(self):
        return self._messages

    def insert_user_message_at_appropriate_position(self, content):
        self._messages.append({"role": "user", "content": content})


class TestSocketServerInit:
    """Test SocketServer initialization."""

    def test_init_with_aicoder_instance(self):
        """Test SocketServer initializes correctly."""
        mock_aicoder = MockAICoder()
        server = SocketServer(mock_aicoder)

        assert server.aicoder is mock_aicoder
        assert server.socket_path is None
        assert server.server_socket is None
        assert server.server_thread is None
        assert server.is_running is False

    def test_init_has_lock(self):
        """Test SocketServer has a threading lock."""
        mock_aicoder = MockAICoder()
        server = SocketServer(mock_aicoder)
        assert server.lock is not None


class TestSocketServerStart:
    """Test SocketServer start() method."""

    @pytest.fixture
    def server_with_mock_aicoder(self):
        """Create a server with mock aicoder for testing."""
        mock_aicoder = MockAICoder()
        mock_aicoder.message_history = MockMessageHistory()
        return SocketServer(mock_aicoder)

    @patch('aicoder.core.socket_server.LogUtils.print')
    def test_start_creates_socket_path(self, mock_print, server_with_mock_aicoder):
        """Test that start() creates a socket path."""
        server = server_with_mock_aicoder
        server.start()

        assert server.is_running is True
        assert server.socket_path is not None
        assert server.socket_path.endswith('.socket')
        assert os.path.exists(server.socket_path)

        # Cleanup
        server.stop()

    @patch('aicoder.core.socket_server.LogUtils.print')
    def test_start_idempotent(self, mock_print, server_with_mock_aicoder):
        """Test that calling start() multiple times is safe."""
        server = server_with_mock_aicoder
        socket_path_1 = None

        server.start()
        socket_path_1 = server.socket_path

        # Second start should not change socket path
        server.start()
        socket_path_2 = server.socket_path

        assert socket_path_1 == socket_path_2
        assert server.is_running

        # Cleanup
        server.stop()


class TestSocketServerStop:
    """Test SocketServer stop() method."""

    @pytest.fixture
    def running_server(self):
        """Create a running server for testing."""
        mock_aicoder = MockAICoder()
        mock_aicoder.message_history = MockMessageHistory()
        server = SocketServer(mock_aicoder)
        with patch('aicoder.core.socket_server.LogUtils.print'):
            server.start()
        yield server
        server.stop()

    def test_stop_sets_running_false(self, running_server):
        """Test that stop() sets is_running to False."""
        running_server.stop()
        assert running_server.is_running is False

    def test_stop_cleans_up_socket_file(self, running_server):
        """Test that stop() removes the socket file."""
        socket_path = running_server.socket_path
        assert os.path.exists(socket_path)

        running_server.stop()

        # Socket file should be removed
        assert not os.path.exists(socket_path)

    def test_stop_idempotent(self, running_server):
        """Test that calling stop() multiple times is safe."""
        socket_path = running_server.socket_path

        running_server.stop()
        running_server.stop()  # Second stop should not raise

        assert not os.path.exists(socket_path)


class TestSocketServerExecuteCommand:
    """Test SocketServer command execution."""

    @pytest.fixture
    def server(self):
        """Create a server for testing."""
        mock_aicoder = MockAICoder()
        mock_aicoder.message_history = MockMessageHistory()
        return SocketServer(mock_aicoder)

    def test_execute_empty_command(self, server):
        """Test executing an empty command."""
        result = server._execute_command("")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["code"] == ERR_INTERNAL

    def test_execute_whitespace_command(self, server):
        """Test executing a whitespace-only command."""
        result = server._execute_command("   ")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["code"] == ERR_INTERNAL

    def test_execute_unknown_command(self, server):
        """Test executing an unknown command."""
        result = server._execute_command("unknown_command")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["code"] == ERR_UNKNOWN_CMD
        assert "unknown_command" in parsed["message"]


class TestSocketServerIsProcessing:
    """Test is_processing command."""

    @pytest.fixture
    def server(self):
        """Create a server with mock aicoder."""
        mock_aicoder = MockAICoder()
        mock_aicoder.message_history = MockMessageHistory()
        return SocketServer(mock_aicoder)

    def test_is_processing_false_by_default(self, server):
        """Test is_processing returns False when not processing."""
        result = server._cmd_is_processing("")
        parsed = json.loads(result)
        assert parsed["status"] == "success"
        assert parsed["data"]["processing"] is False

    def test_is_processing_true_when_set(self, server):
        """Test is_processing returns True when processing via session_manager."""
        # The code checks session_manager.is_processing first
        server.aicoder.session_manager.is_processing = True
        result = server._cmd_is_processing("")
        parsed = json.loads(result)
        assert parsed["status"] == "success"
        assert parsed["data"]["processing"] is True

    def test_is_processing_uses_session_manager(self, server):
        """Test is_processing uses session_manager if available."""
        server.aicoder.session_manager.is_processing = True
        result = server._cmd_is_processing("")
        parsed = json.loads(result)
        assert parsed["status"] == "success"
        assert parsed["data"]["processing"] is True


class TestSocketServerYolo:
    """Test yolo command."""

    @pytest.fixture
    def server(self):
        """Create a server."""
        mock_aicoder = MockAICoder()
        mock_aicoder.message_history = MockMessageHistory()
        return SocketServer(mock_aicoder)

    def test_yolo_status(self, server):
        """Test yolo status returns current state."""
        result = server._cmd_yolo("")
        parsed = json.loads(result)
        assert parsed["status"] == "success"
        assert "enabled" in parsed["data"]

    def test_yolo_on(self, server):
        """Test yolo on enables YOLO mode."""
        result = server._cmd_yolo("on")
        parsed = json.loads(result)
        assert parsed["status"] == "success"
        assert parsed["data"]["enabled"] is True

    def test_yolo_off(self, server):
        """Test yolo off disables YOLO mode."""
        # First enable it
        server._cmd_yolo("on")
        # Then disable
        result = server._cmd_yolo("off")
        parsed = json.loads(result)
        assert parsed["status"] == "success"
        assert parsed["data"]["enabled"] is False

    def test_yolo_toggle(self, server):
        """Test yolo toggle switches state."""
        initial = json.loads(server._cmd_yolo(""))["data"]["enabled"]

        result = server._cmd_yolo("toggle")
        parsed = json.loads(result)
        assert parsed["data"]["enabled"] is not initial

    def test_yolo_invalid_arg(self, server):
        """Test yolo with invalid argument."""
        result = server._cmd_yolo("invalid")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["code"] == ERR_INVALID_ARG


class TestSocketServerDetail:
    """Test detail command."""

    @pytest.fixture
    def server(self):
        """Create a server."""
        mock_aicoder = MockAICoder()
        mock_aicoder.message_history = MockMessageHistory()
        return SocketServer(mock_aicoder)

    def test_detail_status(self, server):
        """Test detail status returns current state."""
        result = server._cmd_detail("")
        parsed = json.loads(result)
        assert parsed["status"] == "success"
        assert "enabled" in parsed["data"]

    def test_detail_on(self, server):
        """Test detail on enables detail mode."""
        result = server._cmd_detail("on")
        parsed = json.loads(result)
        assert parsed["status"] == "success"
        assert parsed["data"]["enabled"] is True

    def test_detail_off(self, server):
        """Test detail off disables detail mode."""
        server._cmd_detail("on")
        result = server._cmd_detail("off")
        parsed = json.loads(result)
        assert parsed["status"] == "success"
        assert parsed["data"]["enabled"] is False

    def test_detail_invalid_arg(self, server):
        """Test detail with invalid argument."""
        result = server._cmd_detail("invalid")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["code"] == ERR_INVALID_ARG


class TestSocketServerSandbox:
    """Test sandbox command."""

    @pytest.fixture
    def server(self):
        """Create a server."""
        mock_aicoder = MockAICoder()
        mock_aicoder.message_history = MockMessageHistory()
        return SocketServer(mock_aicoder)

    def test_sandbox_status(self, server):
        """Test sandbox status returns current state."""
        result = server._cmd_sandbox("")
        parsed = json.loads(result)
        assert parsed["status"] == "success"
        assert "enabled" in parsed["data"]

    def test_sandbox_on(self, server):
        """Test sandbox on enables sandbox."""
        result = server._cmd_sandbox("on")
        parsed = json.loads(result)
        assert parsed["status"] == "success"
        assert parsed["data"]["enabled"] is True

    def test_sandbox_off(self, server):
        """Test sandbox off disables sandbox."""
        result = server._cmd_sandbox("off")
        parsed = json.loads(result)
        assert parsed["status"] == "success"
        assert parsed["data"]["enabled"] is False

    def test_sandbox_toggle(self, server):
        """Test sandbox toggle switches state."""
        initial = json.loads(server._cmd_sandbox(""))["data"]["enabled"]
        result = server._cmd_sandbox("toggle")
        parsed = json.loads(result)
        assert parsed["data"]["enabled"] is not initial

    def test_sandbox_invalid_arg(self, server):
        """Test sandbox with invalid argument."""
        result = server._cmd_sandbox("invalid")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["code"] == ERR_INVALID_ARG


class TestSocketServerStopCommand:
    """Test stop command."""

    @pytest.fixture
    def server(self):
        """Create a server."""
        mock_aicoder = MockAICoder()
        mock_aicoder.message_history = MockMessageHistory()
        return SocketServer(mock_aicoder)

    def test_stop_when_not_processing(self, server):
        """Test stop when not processing returns error."""
        result = server._cmd_stop("")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["code"] == ERR_NOT_PROCESSING

    def test_stop_when_processing(self, server):
        """Test stop when processing returns success via session_manager."""
        # The code checks session_manager.is_processing first
        server.aicoder.session_manager.is_processing = True
        result = server._cmd_stop("")
        parsed = json.loads(result)
        assert parsed["status"] == "success"
        assert parsed["data"]["stopped"] is True
        assert server.aicoder.session_manager.is_processing is False


class TestSocketServerMessages:
    """Test messages command."""

    @pytest.fixture
    def server(self):
        """Create a server with messages."""
        mock_aicoder = MockAICoder()
        mock_aicoder.message_history = MockMessageHistory([
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"},
            {"role": "system", "content": "You are helpful."},
        ])
        return SocketServer(mock_aicoder)

    def test_messages_returns_all(self, server):
        """Test messages returns all messages."""
        result = server._cmd_messages("")
        parsed = json.loads(result)
        assert parsed["status"] == "success"
        assert parsed["data"]["count"] == 4
        assert len(parsed["data"]["messages"]) == 4

    def test_messages_count(self, server):
        """Test messages count returns counts by role."""
        result = server._cmd_messages("count")
        parsed = json.loads(result)
        assert parsed["status"] == "success"
        assert parsed["data"]["total"] == 4
        assert parsed["data"]["user"] == 2
        assert parsed["data"]["assistant"] == 1
        assert parsed["data"]["system"] == 1
        assert parsed["data"]["tool"] == 0


class TestSocketServerInjectText:
    """Test inject-text command."""

    @pytest.fixture
    def server(self):
        """Create a server."""
        mock_aicoder = MockAICoder()
        mock_aicoder.message_history = MockMessageHistory()
        return SocketServer(mock_aicoder)

    def test_inject_text_missing_arg(self, server):
        """Test inject-text with missing argument."""
        result = server._cmd_inject_text("")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["code"] == ERR_MISSING_ARG

    def test_inject_text_invalid_base64(self, server):
        """Test inject-text with invalid base64."""
        result = server._cmd_inject_text("not-valid-base64!!!")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["code"] == ERR_INVALID_ARG

    def test_inject_text_valid_base64(self, server):
        """Test inject-text with valid base64."""
        encoded = base64.b64encode(b"Hello World").decode()
        result = server._cmd_inject_text(encoded)
        parsed = json.loads(result)
        assert parsed["status"] == "success"
        assert parsed["data"]["injected"] is True
        assert parsed["data"]["length"] == 11

        # Verify message was inserted
        messages = server.aicoder.message_history.get_messages()
        assert len(messages) == 1
        assert messages[0]["content"] == "Hello World"

    def test_inject_text_valid_utf8(self, server):
        """Test inject-text with UTF-8 text."""
        text = "Hello, 世界! 🌍"
        encoded = base64.b64encode(text.encode("utf-8")).decode()
        result = server._cmd_inject_text(encoded)
        parsed = json.loads(result)
        assert parsed["status"] == "success"
        assert parsed["data"]["injected"] is True


class TestSocketServerCommand:
    """Test command command."""

    @pytest.fixture
    def server(self):
        """Create a server with mock command handler."""
        mock_aicoder = MockAICoder()
        mock_aicoder.message_history = MockMessageHistory()
        mock_aicoder.command_handler = MagicMock()
        mock_result = MagicMock()
        mock_result.should_quit = False
        mock_result.run_api_call = True
        mock_aicoder.command_handler.handle_command.return_value = mock_result
        return SocketServer(mock_aicoder)

    def test_command_missing_arg(self, server):
        """Test command with missing argument."""
        result = server._cmd_command("")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["code"] == ERR_MISSING_ARG

    def test_command_missing_slash(self, server):
        """Test command without leading slash."""
        result = server._cmd_command("help")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["code"] == ERR_INVALID_ARG

    def test_command_success(self, server):
        """Test successful command execution."""
        result = server._cmd_command("/help")
        parsed = json.loads(result)
        assert parsed["status"] == "success"
        assert parsed["data"]["executed"] == "/help"

    def test_command_calls_handler(self, server):
        """Test that command calls the handler."""
        server._cmd_command("/save")
        server.aicoder.command_handler.handle_command.assert_called_once_with("/save")


class TestSocketServerProcess:
    """Test process command."""

    @pytest.fixture
    def server(self):
        """Create a server."""
        mock_aicoder = MockAICoder()
        mock_aicoder.message_history = MockMessageHistory()
        return SocketServer(mock_aicoder)

    def test_process_when_already_processing(self, server):
        """Test process returns error when already processing via session_manager."""
        # The code checks session_manager.is_processing first
        server.aicoder.session_manager.is_processing = True
        result = server._cmd_process("")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["code"] == ERR_NOT_PROCESSING

    @patch('aicoder.core.socket_server.LogUtils.error')
    def test_process_starts_processing(self, mock_error, server):
        """Test process starts background processing."""
        result = server._cmd_process("")
        parsed = json.loads(result)
        assert parsed["status"] == "success"
        assert parsed["data"]["processing"] is True


class TestSocketServerSave:
    """Test save command."""

    @pytest.fixture
    def server(self):
        """Create a server."""
        mock_aicoder = MockAICoder()
        mock_aicoder.message_history = MockMessageHistory([
            {"role": "user", "content": "Hello"}
        ])
        return SocketServer(mock_aicoder)

    def test_save_with_path(self, server):
        """Test save with explicit path."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            path = f.name

        try:
            result = server._cmd_save(path)
            parsed = json.loads(result)
            assert parsed["status"] == "success"
            assert parsed["data"]["saved"] is True
            assert parsed["data"]["path"] == path

            # Verify file was created
            with open(path) as f:
                data = json.load(f)
                assert "messages" in data
        finally:
            if os.path.exists(path):
                os.unlink(path)

    def test_save_path_outside_allowed(self, server):
        """Test save with path outside allowed directories."""
        result = server._cmd_save("/etc/test.json")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["code"] == ERR_PERMISSION


class TestSocketServerStatus:
    """Test status command."""

    @pytest.fixture
    def server(self):
        """Create a server."""
        mock_aicoder = MockAICoder()
        mock_aicoder.message_history = MockMessageHistory([
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ])
        return SocketServer(mock_aicoder)

    def test_status_returns_all_info(self, server):
        """Test status returns all status information."""
        result = server._cmd_status("")
        parsed = json.loads(result)
        assert parsed["status"] == "success"
        data = parsed["data"]
        assert "processing" in data
        assert "yolo_enabled" in data
        assert "detail_enabled" in data
        assert "sandbox_enabled" in data
        assert "messages" in data
        assert data["messages"] == 2


class TestSocketServerStartEnvVars:
    """Test start() with environment variables."""

    @pytest.fixture
    def server(self):
        """Create a server."""
        mock_aicoder = MockAICoder()
        mock_aicoder.message_history = MockMessageHistory()
        return SocketServer(mock_aicoder)

    @patch.dict(os.environ, {"AICODER_SOCKET_IPC_FILE": "/tmp/test.sock"})
    @patch('aicoder.core.socket_server.LogUtils.print')
    def test_start_with_fixed_path(self, mock_print, server):
        """Test start() uses fixed path from environment."""
        server.start()
        assert server.socket_path == "/tmp/test.sock"
        assert os.path.exists(server.socket_path)
        server.stop()

    @patch('aicoder.core.socket_server.LogUtils.print')
    def test_start_with_custom_tmpdir(self, mock_print, server):
        """Test start() uses custom TMPDIR when AICODER_SOCKET_IPC_FILE is not set."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Clear both env vars that take precedence over TMPDIR
            old_ipc = os.environ.pop("AICODER_SOCKET_IPC_FILE", None)
            old_socket_dir = os.environ.pop("AICODER_SOCKET_DIR", None)
            old_tmux_pane = os.environ.get("TMUX_PANE")

            try:
                # Ensure TMUX_PANE is set to "0" to use the default path
                os.environ["TMUX_PANE"] = "0"
                os.environ["TMPDIR"] = tmpdir

                server.start()
                assert server.socket_path.startswith(tmpdir), f"Expected path starting with {tmpdir}, got {server.socket_path}"
                server.stop()
            finally:
                # Restore original environment
                if old_ipc:
                    os.environ["AICODER_SOCKET_IPC_FILE"] = old_ipc
                if old_socket_dir:
                    os.environ["AICODER_SOCKET_DIR"] = old_socket_dir
                if old_tmux_pane:
                    os.environ["TMUX_PANE"] = old_tmux_pane
                elif "TMUX_PANE" in os.environ:
                    del os.environ["TMUX_PANE"]


class TestSocketServerExecuteCommandErrors:
    """Test error handling in _execute_command."""

    @pytest.fixture
    def server(self):
        """Create a server with mock command handler that raises."""
        mock_aicoder = MockAICoder()
        mock_aicoder.message_history = MockMessageHistory()
        mock_aicoder.command_handler = MagicMock()
        mock_aicoder.command_handler.handle_command.side_effect = Exception("Test error")
        return SocketServer(mock_aicoder)

    def test_execute_command_exception(self, server):
        """Test that exceptions in handlers are caught."""
        result = server._cmd_command("/test")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["code"] == ERR_INTERNAL


class TestSocketServerReadLine:
    """Test _read_line method."""

    @pytest.fixture
    def server(self):
        """Create a server."""
        mock_aicoder = MockAICoder()
        mock_aicoder.message_history = MockMessageHistory()
        return SocketServer(mock_aicoder)

    def test_read_line_empty(self, server):
        """Test reading empty data returns None."""
        import socket as sock
        mock_sock = MagicMock()
        mock_sock.recv.return_value = b""  # Empty data, no newline
        result = server._read_line(mock_sock, timeout=1.0)
        assert result is None

    def test_read_line_with_newline(self, server):
        """Test reading data with newline."""
        import socket as sock
        mock_sock = MagicMock()
        mock_sock.recv.side_effect = [
            b"hello world\n",
            b""  # Empty to break loop
        ]
        result = server._read_line(mock_sock, timeout=1.0)
        assert result == "hello world"


class TestSocketServerSendLine:
    """Test _send_line method."""

    @pytest.fixture
    def server(self):
        """Create a server."""
        mock_aicoder = MockAICoder()
        mock_aicoder.message_history = MockMessageHistory()
        return SocketServer(mock_aicoder)

    def test_send_line_success(self, server):
        """Test sending a line successfully."""
        import socket as sock
        mock_sock = MagicMock()
        server._send_line(mock_sock, '{"status":"success"}')
        mock_sock.sendall.assert_called_once()
        call_args = mock_sock.sendall.call_args[0][0]
        assert b'\n' in call_args


class TestSocketServerDetailToggle:
    """Test detail toggle."""

    @pytest.fixture
    def server(self):
        """Create a server."""
        mock_aicoder = MockAICoder()
        mock_aicoder.message_history = MockMessageHistory()
        return SocketServer(mock_aicoder)

    def test_detail_toggle(self, server):
        """Test detail toggle switches state."""
        initial = json.loads(server._cmd_detail(""))["data"]["enabled"]
        result = server._cmd_detail("toggle")
        parsed = json.loads(result)
        assert parsed["data"]["enabled"] is not initial


class TestSocketServerInjectTextSize:
    """Test inject-text size limit."""

    @pytest.fixture
    def server(self):
        """Create a server."""
        mock_aicoder = MockAICoder()
        mock_aicoder.message_history = MockMessageHistory()
        return SocketServer(mock_aicoder)

    def test_inject_text_too_large(self, server):
        """Test inject-text rejects text that's too large."""
        # Create text larger than MAX_INJECT_TEXT_SIZE (10MB)
        large_text = "x" * (10 * 1024 * 1024 + 1)
        encoded = base64.b64encode(large_text.encode()).decode()
        result = server._cmd_inject_text(encoded)
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["code"] == ERR_INVALID_ARG
        assert "too large" in parsed["message"]


class TestSocketServerStatusFallback:
    """Test status command fallback to aicoder.is_processing."""

    @pytest.fixture
    def server(self):
        """Create a server without session_manager."""
        mock_aicoder = MockAICoder()
        mock_aicoder.message_history = MockMessageHistory()
        del mock_aicoder.session_manager  # Remove session_manager
        mock_aicoder.is_processing = True
        return SocketServer(mock_aicoder)

    def test_status_uses_aicoder_is_processing(self, server):
        """Test status uses aicoder.is_processing when no session_manager."""
        result = server._cmd_status("")
        parsed = json.loads(result)
        assert parsed["status"] == "success"
        assert parsed["data"]["processing"] is True


class TestSocketServerStopFallback:
    """Test stop command fallback to aicoder.is_processing."""

    @pytest.fixture
    def server(self):
        """Create a server without session_manager."""
        mock_aicoder = MockAICoder()
        mock_aicoder.message_history = MockMessageHistory()
        del mock_aicoder.session_manager  # Remove session_manager
        mock_aicoder.is_processing = True
        return SocketServer(mock_aicoder)

    def test_stop_uses_aicoder_is_processing(self, server):
        """Test stop uses aicoder.is_processing when no session_manager."""
        result = server._cmd_stop("")
        parsed = json.loads(result)
        assert parsed["status"] == "success"
        assert parsed["data"]["stopped"] is True
        assert server.aicoder.is_processing is False


class TestSocketServerProcessFallback:
    """Test process command fallback."""

    @pytest.fixture
    def server(self):
        """Create a server without session_manager."""
        mock_aicoder = MockAICoder()
        mock_aicoder.message_history = MockMessageHistory()
        del mock_aicoder.session_manager  # Remove session_manager
        return SocketServer(mock_aicoder)

    def test_process_when_already_processing_no_session_manager(self, server):
        """Test process when already processing (no session_manager)."""
        server.aicoder.is_processing = True
        result = server._cmd_process("")
        parsed = json.loads(result)
        assert parsed["status"] == "error"
        assert parsed["code"] == ERR_NOT_PROCESSING


class TestSocketServerCommandShouldQuit:
    """Test command that triggers should_quit."""

    @pytest.fixture
    def server(self):
        """Create a server with mock command handler."""
        mock_aicoder = MockAICoder()
        mock_aicoder.message_history = MockMessageHistory()
        mock_aicoder.command_handler = MagicMock()
        mock_result = MagicMock()
        mock_result.should_quit = True
        mock_result.run_api_call = False
        mock_aicoder.command_handler.handle_command.return_value = mock_result
        return SocketServer(mock_aicoder)

    def test_command_should_quit_triggers_quit(self, server):
        """Test that should_quit=True triggers the quit mechanism."""
        result = server._cmd_command("/quit")
        parsed = json.loads(result)
        assert parsed["status"] == "success"
        assert parsed["data"]["should_quit"] is True


class TestSocketServerSaveDefault:
    """Test save command with default path."""

    @pytest.fixture
    def server(self):
        """Create a server."""
        mock_aicoder = MockAICoder()
        mock_aicoder.message_history = MockMessageHistory([
            {"role": "user", "content": "Hello"}
        ])
        return SocketServer(mock_aicoder)

    def test_save_without_path(self, server):
        """Test save without explicit path uses default."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Temporarily change working directory
            old_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                result = server._cmd_save("")
                parsed = json.loads(result)
                assert parsed["status"] == "success"
                assert parsed["data"]["saved"] is True
                assert ".aicoder/sessions" in parsed["data"]["path"]
            finally:
                os.chdir(old_cwd)
