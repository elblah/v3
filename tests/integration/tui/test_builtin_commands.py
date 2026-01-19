"""
Integration tests for built-in commands through TUI using pexpect.

Tests verify all commands work correctly. Excludes /edit and /memory which open tmux windows.
"""

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


class TestBuiltInCommands:
    """Test built-in commands."""

    def test_help_command(self, aicoder_env, tmp_path):
        """Test /help command."""
        child = spawn_aicoder(aicoder_env, tmp_path, timeout=15)

        try:
            child.expect(r"> ")
            child.sendline("/help")

            # Should see help output
            child.expect(r"Available commands|help")
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

    def test_stats_command(self, aicoder_env, tmp_path):
        """Test /stats command."""
        child = spawn_aicoder(aicoder_env, tmp_path, timeout=15)

        try:
            child.expect(r"> ")
            child.sendline("/stats")

            # Should see stats output (just check we return to prompt)
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

    def test_quit_command(self, aicoder_env, tmp_path):
        """Test /quit command."""
        child = spawn_aicoder(aicoder_env, tmp_path, timeout=15)

        try:
            child.expect(r"> ")
            child.sendline("/quit")
            child.expect(pexpect.EOF, timeout=10)
        except (pexpect_exceptions.TIMEOUT, pexpect_exceptions.EOF):
            try:
                child.terminate()
                child.wait()
            except Exception:
                child.close(force=True)

    def test_new_command(self, aicoder_env, tmp_path):
        """Test /new command."""
        child = spawn_aicoder(aicoder_env, tmp_path, timeout=15)

        try:
            child.expect(r"> ")
            child.sendline("/new")

            # Should see confirmation and new prompt
            child.expect(r"Session|cleared|reset")
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
