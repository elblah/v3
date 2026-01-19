"""
Integration tests for edge cases through TUI using pexpect.

Tests verify edge cases, special inputs, and boundary conditions.
"""

import json
import os
import pytest

import sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))))

try:
    import pexpect
    from pexpect import exceptions as pexpect_exceptions
except ImportError:
    pexpect = None
    pexpect_exceptions = None
    pytest.skip("pexpect not installed", allow_module_level=True)

from tests.integration.mock_server import MockServer, make_sse_response


def spawn_aicoder(env, cwd, timeout=15):
    """Spawn aicoder process with proper configuration.

    Args:
        env: Environment variables including PYTHONPATH
        cwd: Working directory
        timeout: Timeout for spawn operation

    Returns:
        pexpect.spawn instance
    """
    # Get project root and main.py path
    project_root = env.get("PYTHONPATH", os.getcwd())
    main_script = os.path.join(project_root, "main.py")

    return pexpect.spawn(
        f"python {main_script}",
        env=env,
        cwd=cwd,
        timeout=timeout,
        encoding='utf-8'
    )


@pytest.fixture
def mock_server():
    """Provide mock API server for tests."""
    server = MockServer()
    server.start()
    yield server
    server.stop()


@pytest.fixture
def aicoder_env(mock_server, tmp_path):
    """Set up environment for aicoder with mock API.

    CRITICAL: All API requests MUST go to local mock server, not real APIs.
    """
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

    env = os.environ.copy()
    env["PYTHONPATH"] = project_root
    env["API_BASE_URL"] = mock_server.get_api_base()
    env["API_MODEL"] = "test-model"
    env["API_KEY"] = "mock-key"
    env["OPENAI_BASE_URL"] = mock_server.get_api_base()
    env["OPENAI_MODEL"] = "test-model"
    env["OPENAI_API_KEY"] = "mock-key"
    env["MINI_SANDBOX"] = "1"
    env["YOLO_MODE"] = "0"
    return env


class TestEdgeCases:
    """Test edge cases."""

    def test_empty_input(self, mock_server, aicoder_env, tmp_path):
        """Test empty user input."""
        child = spawn_aicoder(aicoder_env, tmp_path, timeout=15)

        try:
            child.expect(r"> ")
            child.sendline("")  # Empty input
            child.expect(r"> ", timeout=10)
        finally:
            try:
                child.sendline("/quit")
                child.expect(pexpect.EOF, timeout=10)
            except (pexpect_exceptions.TIMEOUT, pexpect_exceptions.EOF):
                try:
                    child.terminate()
                    child.wait()
                except Exception:
                    child.close(force=True)

    def test_special_chars_in_file(self, mock_server, aicoder_env, tmp_path):
        """Test file with special characters."""
        test_file = tmp_path / "special.txt"
        test_file.write_text("Hello <world> & [test]")

        mock_server.set_sequential_responses([
            make_sse_response(
                "Reading file",
                tool_calls=[{
                    "name": "read_file",
                    "arguments": json.dumps({"path": str(test_file)})
                }]
            ),
            make_sse_response("File read successfully")
        ])

        child = spawn_aicoder(aicoder_env, tmp_path, timeout=15)

        try:
            child.expect(r"> ")
            child.sendline("read file")

            # read_file is auto-approved
            child.expect(r"File read successfully")
            child.expect(r"> ", timeout=10)
        finally:
            try:
                child.sendline("/quit")
                child.expect(pexpect.EOF, timeout=10)
            except (pexpect_exceptions.TIMEOUT, pexpect_exceptions.EOF):
                try:
                    child.terminate()
                    child.wait()
                except Exception:
                    child.close(force=True)
