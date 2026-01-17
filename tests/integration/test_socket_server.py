"""
Integration tests for socket server.

Tests Unix socket IPC mechanism with a mock aicoder instance.
"""

import json
import os
import socket
import tempfile
import threading
import time
import pytest
import base64

from tests.integration.mock_server import MockServer


class MockAICoder:
    """Mock aicoder instance for socket server testing."""

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


class MockSocketServer:
    """Minimal mock of socket server for testing."""

    def __init__(self, mock_aicoder):
        self.aicoder = mock_aicoder
        self.socket_path = None
        self.server_socket = None
        self.server_thread = None
        self.is_running = False

    def start(self, socket_path=None):
        """Start the socket server."""
        if self.is_running:
            return

        if socket_path is None:
            tmpdir = tempfile.gettempdir()
            random_id = os.urandom(3).hex()
            pid = os.getpid()
            self.socket_path = f"{tmpdir}/test-aicoder-{pid}-{random_id}.socket"
        else:
            self.socket_path = socket_path

        # Clean up old socket
        if os.path.exists(self.socket_path):
            os.unlink(self.socket_path)

        # Create Unix socket
        self.server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        self.server_socket.bind(self.socket_path)
        self.server_socket.listen(1)
        os.chmod(self.socket_path, 0o600)

        self.is_running = True
        self.server_thread = threading.Thread(target=self._server_loop, daemon=True)
        self.server_thread.start()

    def stop(self):
        """Stop the socket server."""
        self.is_running = False
        if self.server_socket:
            self.server_socket.close()
            self.server_socket = None
        if self.socket_path and os.path.exists(self.socket_path):
            os.unlink(self.socket_path)
            self.socket_path = None

    def _server_loop(self):
        """Main server loop."""
        while self.is_running:
            try:
                self.server_socket.settimeout(0.5)
                try:
                    client_socket, _ = self.server_socket.accept()
                except socket.timeout:
                    continue
                self._handle_client(client_socket)
            except Exception:
                pass

    def _handle_client(self, client_socket):
        """Handle one client connection."""
        try:
            # Read command
            data = b""
            while True:
                chunk = client_socket.recv(1024)
                if not chunk:
                    break
                data += chunk
                if b"\n" in data:
                    break

            if not data:
                client_socket.sendall(b'{"status":"error","code":1001,"message":"Empty command"}\n')
                client_socket.close()
                return

            command = data.decode("utf-8").strip()

            # Execute command
            response = self._execute_command(command)
            client_socket.sendall((response + "\n").encode("utf-8"))

        except Exception as e:
            client_socket.sendall(f'{{"status":"error","code":1301,"message":"{str(e)}"}}\n'.encode())
        finally:
            client_socket.close()

    def _execute_command(self, command):
        """Execute command and return JSON response."""
        if not command:
            return '{"status":"error","code":1001,"message":"Empty command"}'

        parts = command.split(None, 1)
        cmd = parts[0]
        args = parts[1] if len(parts) > 1 else ""

        # is_processing
        if cmd == "is_processing":
            return json.dumps({
                "status": "success",
                "data": {"processing": self.aicoder.is_processing}
            })

        # yolo
        if cmd == "yolo":
            if not args or args == "status":
                return json.dumps({"status": "success", "data": {"enabled": False}})
            if args == "on":
                return json.dumps({"status": "success", "data": {"enabled": True, "message": "YOLO enabled"}})
            if args == "off":
                return json.dumps({"status": "success", "data": {"enabled": False, "message": "YOLO disabled"}})
            return '{"status":"error","code":1004,"message":"Invalid args"}'

        # status
        if cmd == "status":
            return json.dumps({
                "status": "success",
                "data": {
                    "processing": self.aicoder.is_processing,
                    "yolo_enabled": False,
                    "detail_enabled": False,
                    "sandbox_enabled": True,
                    "messages": 0,
                }
            })

        # messages
        if cmd == "messages":
            if args == "count":
                return json.dumps({
                    "status": "success",
                    "data": {"total": 0, "user": 0, "assistant": 0, "system": 0, "tool": 0}
                })
            return json.dumps({"status": "success", "data": {"messages": [], "count": 0}})

        # stop
        if cmd == "stop":
            if self.aicoder.is_processing:
                self.aicoder.is_processing = False
                return json.dumps({"status": "success", "data": {"stopped": True}})
            return '{"status":"error","code":1001,"message":"Not currently processing"}'

        # detail
        if cmd == "detail":
            if not args or args == "status":
                return json.dumps({"status": "success", "data": {"enabled": False}})
            if args == "on":
                return json.dumps({"status": "success", "data": {"enabled": True}})
            if args == "off":
                return json.dumps({"status": "success", "data": {"enabled": False}})
            return '{"status":"error","code":1004,"message":"Invalid args"}'

        # sandbox
        if cmd == "sandbox":
            if not args or args == "status":
                return json.dumps({"status": "success", "data": {"enabled": True}})
            if args == "toggle":
                return json.dumps({"status": "success", "data": {"enabled": True}})
            return '{"status":"success","data":{"enabled":True}}'

        # inject-text
        if cmd == "inject-text":
            if not args:
                return '{"status":"error","code":1003,"message":"Missing base64 encoded text"}'
            try:
                decoded = base64.b64decode(args, validate=True)
                decoded.decode("utf-8")
                return json.dumps({"status": "success", "data": {"injected": True, "length": len(decoded)}})
            except Exception:
                return '{"status":"error","code":1004,"message":"Invalid base64"}'

        return '{"status":"error","code":1002,"message":"Unknown command"}'


@pytest.fixture
def socket_server():
    """Provide a socket server for tests."""
    mock_aicoder = MockAICoder()
    server = MockSocketServer(mock_aicoder)
    server.start()
    yield server
    server.stop()


class TestSocketServerBasic:
    """Test basic socket server functionality."""

    def test_server_starts(self, socket_server):
        """Server should start and create socket file."""
        assert socket_server.is_running
        assert socket_server.socket_path is not None
        assert os.path.exists(socket_server.socket_path)

    def test_server_listens(self, socket_server):
        """Server should accept connections."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(socket_server.socket_path)
        sock.close()

    def test_server_responds(self, socket_server):
        """Server should respond to commands."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(socket_server.socket_path)
        sock.sendall(b"status\n")
        response = sock.recv(4096).decode()
        sock.close()

        data = json.loads(response)
        assert data["status"] == "success"

    def test_empty_command(self, socket_server):
        """Server should handle empty command."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(socket_server.socket_path)
        sock.sendall(b"\n")
        response = sock.recv(4096).decode()
        sock.close()

        data = json.loads(response)
        assert data["status"] == "error"
        assert data["code"] == 1001


class TestSocketCommands:
    """Test socket command handlers."""

    def test_is_processing_command(self, socket_server):
        """Test is_processing command."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(socket_server.socket_path)
        sock.sendall(b"is_processing\n")
        response = sock.recv(4096).decode()
        sock.close()

        data = json.loads(response)
        assert data["status"] == "success"
        assert "processing" in data["data"]

    def test_status_command(self, socket_server):
        """Test status command."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(socket_server.socket_path)
        sock.sendall(b"status\n")
        response = sock.recv(4096).decode()
        sock.close()

        data = json.loads(response)
        assert data["status"] == "success"
        assert "processing" in data["data"]
        assert "yolo_enabled" in data["data"]
        assert "sandbox_enabled" in data["data"]

    def test_yolo_on_command(self, socket_server):
        """Test yolo on command."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(socket_server.socket_path)
        sock.sendall(b"yolo on\n")
        response = sock.recv(4096).decode()
        sock.close()

        data = json.loads(response)
        assert data["status"] == "success"
        assert data["data"]["enabled"] == True

    def test_yolo_off_command(self, socket_server):
        """Test yolo off command."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(socket_server.socket_path)
        sock.sendall(b"yolo off\n")
        response = sock.recv(4096).decode()
        sock.close()

        data = json.loads(response)
        assert data["status"] == "success"
        assert data["data"]["enabled"] == False

    def test_yolo_status_command(self, socket_server):
        """Test yolo status command."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(socket_server.socket_path)
        sock.sendall(b"yolo status\n")
        response = sock.recv(4096).decode()
        sock.close()

        data = json.loads(response)
        assert data["status"] == "success"
        assert "enabled" in data["data"]

    def test_detail_on_command(self, socket_server):
        """Test detail on command."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(socket_server.socket_path)
        sock.sendall(b"detail on\n")
        response = sock.recv(4096).decode()
        sock.close()

        data = json.loads(response)
        assert data["status"] == "success"

    def test_sandbox_status_command(self, socket_server):
        """Test sandbox status command."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(socket_server.socket_path)
        sock.sendall(b"sandbox status\n")
        response = sock.recv(4096).decode()
        sock.close()

        data = json.loads(response)
        assert data["status"] == "success"
        assert "enabled" in data["data"]

    def test_messages_count_command(self, socket_server):
        """Test messages count command."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(socket_server.socket_path)
        sock.sendall(b"messages count\n")
        response = sock.recv(4096).decode()
        sock.close()

        data = json.loads(response)
        assert data["status"] == "success"
        assert "total" in data["data"]
        assert "user" in data["data"]
        assert "assistant" in data["data"]

    def test_stop_when_not_processing(self, socket_server):
        """Test stop command when not processing."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(socket_server.socket_path)
        sock.sendall(b"stop\n")
        response = sock.recv(4096).decode()
        sock.close()

        data = json.loads(response)
        assert data["status"] == "error"
        assert data["code"] == 1001

    def test_stop_when_processing(self, socket_server):
        """Test stop command when processing."""
        socket_server.aicoder.is_processing = True

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(socket_server.socket_path)
        sock.sendall(b"stop\n")
        response = sock.recv(4096).decode()
        sock.close()

        data = json.loads(response)
        assert data["status"] == "success"
        assert data["data"]["stopped"] == True


class TestInjectText:
    """Test inject-text command."""

    def test_inject_text_missing_arg(self, socket_server):
        """Test inject-text without arguments."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(socket_server.socket_path)
        sock.sendall(b"inject-text\n")
        response = sock.recv(4096).decode()
        sock.close()

        data = json.loads(response)
        assert data["status"] == "error"
        assert data["code"] == 1003

    def test_inject_text_invalid_base64(self, socket_server):
        """Test inject-text with invalid base64."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(socket_server.socket_path)
        sock.sendall(b"inject-text not-valid-base64!!!\n")
        response = sock.recv(4096).decode()
        sock.close()

        data = json.loads(response)
        assert data["status"] == "error"
        assert data["code"] == 1004

    def test_inject_text_valid_base64(self, socket_server):
        """Test inject-text with valid base64."""
        # "Hello World" encoded
        encoded = base64.b64encode(b"Hello World").decode()

        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(socket_server.socket_path)
        sock.sendall(f"inject-text {encoded}\n".encode())
        response = sock.recv(4096).decode()
        sock.close()

        data = json.loads(response)
        assert data["status"] == "success"
        assert data["data"]["injected"] == True
        assert data["data"]["length"] == 11


class TestUnknownCommand:
    """Test unknown command handling."""

    def test_unknown_command(self, socket_server):
        """Test unknown command returns error."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(socket_server.socket_path)
        sock.sendall(b"unknown_command\n")
        response = sock.recv(4096).decode()
        sock.close()

        data = json.loads(response)
        assert data["status"] == "error"
        assert data["code"] == 1002


class TestSocketConcurrency:
    """Test socket server concurrency."""

    def test_sequential_requests(self, socket_server):
        """Test multiple sequential requests."""
        for i in range(5):
            sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            sock.connect(socket_server.socket_path)
            sock.sendall(b"status\n")
            response = sock.recv(4096).decode()
            data = json.loads(response)
            assert data["status"] == "success"
            sock.close()

    def test_connection_cleanup(self, socket_server):
        """Test that connections are cleaned up properly."""
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(socket_server.socket_path)
        sock.sendall(b"status\n")
        sock.recv(4096)
        sock.close()

        # Should be able to make another connection
        sock2 = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock2.connect(socket_server.socket_path)
        sock2.sendall(b"is_processing\n")
        response = sock2.recv(4096).decode()
        sock2.close()

        data = json.loads(response)
        assert data["status"] == "success"
