"""
Integration tests for approval system through TUI using pexpect.

Tests verify tool approval flow: prompts, approvals, rejections, YOLO mode.
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
    # Get project root directory (3 levels up from this file)
    project_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

    env = os.environ.copy()
    env["PYTHONPATH"] = project_root  # CRITICAL: Add project root to path
    env["API_BASE_URL"] = mock_server.get_api_base()  # LOCAL mock server
    env["API_MODEL"] = "test-model"
    env["API_KEY"] = "mock-key"  # Mock key for local server
    env["OPENAI_BASE_URL"] = mock_server.get_api_base()  # Alternate var
    env["OPENAI_MODEL"] = "test-model"
    env["OPENAI_API_KEY"] = "mock-key"  # Alternate var
    env["MINI_SANDBOX"] = "1"
    env["YOLO_MODE"] = "0"  # Require approval
    return env


@pytest.fixture
def aicoder_env_yolo(mock_server, tmp_path):
    """Environment with YOLO mode enabled (auto-approve)."""
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
    env["YOLO_MODE"] = "1"  # Auto-approve all tools
    return env


class TestApproveTool:
    """Test approving tool execution."""

    def test_approve_with_y(self, mock_server, aicoder_env, tmp_path):
        """Test approving tool with 'y'."""
        test_file = tmp_path / "test.txt"

        # Use sequential responses for multi-turn conversation
        mock_server.set_sequential_responses([
            make_sse_response(
                "Creating file",
                tool_calls=[{
                    "name": "write_file",
                    "arguments": json.dumps({
                        "path": str(test_file),
                        "content": "test content"
                    })
                }]
            ),
            make_sse_response("File created successfully")
        ])

        child = spawn_aicoder(aicoder_env, tmp_path, timeout=15)

        try:
            child.expect(r"> ")
            child.sendline("create file")

            # Should see approval prompt
            child.expect(r"write_file")
            child.sendline("y")

            child.expect(r"File created successfully")
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


class TestRejectTool:
    """Test rejecting tool execution."""

    def test_reject_with_n(self, mock_server, aicoder_env, tmp_path):
        """Test rejecting tool with 'n'."""
        test_file = tmp_path / "test.txt"

        mock_server.set_sequential_responses([
            make_sse_response(
                "Creating file",
                tool_calls=[{
                    "name": "write_file",
                    "arguments": json.dumps({
                        "path": str(test_file),
                        "content": "test content"
                    })
                }]
            ),
            make_sse_response("won't create the file")
        ])

        child = spawn_aicoder(aicoder_env, tmp_path, timeout=15)

        try:
            child.expect(r"> ")
            child.sendline("create file")

            # Should see approval prompt
            child.expect(r"write_file")
            child.sendline("n")

            # AI should respond to rejection
            child.expect(r"won't create|cancelled")
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
