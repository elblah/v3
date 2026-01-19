"""
Integration tests for AI Coder TUI using pexpect.

Tests the real user interface and workflow end-to-end with a mock API server.
These tests verify actual behavior, not just component interactions.
"""

import json
import os
import time
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
    env["MINI_SANDBOX"] = "1"  # Enable sandbox for tests
    env["YOLO_MODE"] = "0"  # Disable auto-approve to test approval flow
    return env


class TestBasicConversation:
    """Test basic conversation flow through TUI."""

    def test_hello_conversation(self, mock_server, aicoder_env, tmp_path):
        """Test simple conversation: user types hello, AI responds."""
        # Set up mock response
        mock_server.set_response(
            "hello",
            make_sse_response("Hello! How can I help you today?")
        )

        # Start aicoder - use main.py entry point
        child = spawn_aicoder(aicoder_env, tmp_path, timeout=15)

        try:
            # Wait for initial prompt
            child.expect(r"> ", timeout=10)

            # Send user message
            child.sendline("hello")

            # Wait for AI response
            child.expect(r"Hello! How can I help you today\?", timeout=10)

            # Verify we got back to prompt
            child.expect(r"> ", timeout=5)

        finally:
            # Clean up: try to quit gracefully, then force close
            try:
                child.sendline("/quit")
                child.expect(pexpect.EOF, timeout=10)
            except (pexpect_exceptions.TIMEOUT, pexpect_exceptions.EOF):
                try:
                    child.terminate()
                    child.wait()
                except Exception:
                    child.close(force=True)

    def test_multiple_turns(self, mock_server, aicoder_env, tmp_path):
        """Test multiple conversation turns."""
        # Set up mock responses
        mock_server.set_response(
            "first",
            make_sse_response("First response")
        )
        mock_server.set_response(
            "second",
            make_sse_response("Second response")
        )
        mock_server.set_response(
            "third",
            make_sse_response("Third response")
        )

        child = spawn_aicoder(aicoder_env, tmp_path, timeout=15)

        try:
            child.expect(r"> ")
            child.sendline("first")
            child.expect(r"First response")
            child.expect(r"> ")

            child.sendline("second")
            child.expect(r"Second response")
            child.expect(r"> ")

            child.sendline("third")
            child.expect(r"Third response")
            child.expect(r"> ")

        finally:
            # Clean up: try to quit gracefully, then force close
            try:
                child.sendline("/quit")
                child.expect(pexpect.EOF, timeout=10)
            except (pexpect_exceptions.TIMEOUT, pexpect_exceptions.EOF):
                try:
                    child.terminate()
                    child.wait()
                except Exception:
                    child.close(force=True)


class TestToolExecution:
    """Test tool execution through TUI."""

    def test_simple_tool_call(self, mock_server, aicoder_env, tmp_path):
        """Test simple tool execution with approval (using write_file which requires approval)."""
        # Use sequential responses for multi-turn conversation
        mock_server.set_sequential_responses([
            # First response: AI wants to write a file
            make_sse_response(
                "I'll create a file for you",
                tool_calls=[{
                    "name": "write_file",
                    "arguments": json.dumps({
                        "path": "test.txt",
                        "content": "Hello World"
                    })
                }]
            ),
            # Second response: AI confirms after tool execution
            make_sse_response("File created successfully!")
        ])

        child = spawn_aicoder(aicoder_env, tmp_path, timeout=20)

        try:
            child.expect(r"> ")
            child.sendline("write file")

            # Should see tool approval prompt (write_file requires approval)
            child.expect(r"Tool: write_file", timeout=10)
            child.expect(r"Approve \[Y/n\]", timeout=5)

            # Approve tool execution
            child.sendline("y")

            # Should see AI's final response
            child.expect(r"File created successfully!", timeout=10)
            child.expect(r"> ", timeout=10)

        finally:
            # Clean up: try to quit gracefully, then force close
            try:
                child.sendline("/quit")
                child.expect(pexpect.EOF, timeout=10)
            except (pexpect_exceptions.TIMEOUT, pexpect_exceptions.EOF):
                try:
                    child.terminate()
                    child.wait()
                except Exception:
                    child.close(force=True)

    def test_write_file_workflow(self, mock_server, aicoder_env, tmp_path):
        """Test complete read -> process -> write workflow."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Original content")

        # Use sequential responses for multi-turn conversation
        mock_server.set_sequential_responses([
            # First: read file (auto-approved, no prompt)
            make_sse_response(
                "I'll read the file first",
                tool_calls=[{
                    "name": "read_file",
                    "arguments": json.dumps({"path": str(test_file)})
                }]
            ),
            # After reading, write updated content (requires approval)
            make_sse_response(
                "Now I'll update it",
                tool_calls=[{
                    "name": "write_file",
                    "arguments": json.dumps({
                        "path": str(test_file),
                        "content": "Updated content"
                    })
                }]
            ),
            # Final confirmation
            make_sse_response("File updated successfully!")
        ])

        child = spawn_aicoder(aicoder_env, tmp_path, timeout=30)

        try:
            child.expect(r"> ")
            child.sendline("update file")

            # Approve write_file (read_file is auto-approved, no prompt)
            child.expect(r"Tool: write_file")
            child.expect(r"Approve \[Y/n\]")
            child.sendline("y")

            # Verify success
            child.expect(r"File updated successfully!")
            child.expect(r"> ", timeout=10)

            # Verify file was actually updated
            assert test_file.read_text() == "Updated content"

        finally:
            # Clean up: try to quit gracefully, then force close
            try:
                child.sendline("/quit")
                child.expect(pexpect.EOF, timeout=10)
            except (pexpect_exceptions.TIMEOUT, pexpect_exceptions.EOF):
                try:
                    child.terminate()
                    child.wait()
                except Exception:
                    child.close(force=True)


class TestCommandExecution:
    """Test shell command execution through TUI."""

    def test_simple_command(self, mock_server, aicoder_env, tmp_path):
        """Test simple shell command execution."""
        mock_server.set_sequential_responses([
            # First response: AI wants to list files
            make_sse_response(
                "I'll list the files",
                tool_calls=[{
                    "name": "run_shell_command",
                    "arguments": json.dumps({"command": "echo test"})
                }]
            ),
            # Second response: AI confirms after command execution
            make_sse_response("Command executed successfully")
        ])

        child = spawn_aicoder(aicoder_env, tmp_path, timeout=20)

        try:
            child.expect(r"> ")
            child.sendline("list files")

            # Approve command
            child.expect(r"Tool: run_shell_command")
            child.expect(r"Approve \[Y/n\]")
            child.sendline("y")

            # Should see command output or AI response
            child.expect(r"(test|successfully|>)", timeout=10)
            child.expect(r"> ", timeout=10)

        finally:
            # Clean up: try to quit gracefully, then force close
            try:
                child.sendline("/quit")
                child.expect(pexpect.EOF, timeout=10)
            except (pexpect_exceptions.TIMEOUT, pexpect_exceptions.EOF):
                try:
                    child.terminate()
                    child.wait()
                except Exception:
                    child.close(force=True)


class TestErrorHandling:
    """Test error handling and recovery."""

    def test_file_not_found_error(self, mock_server, aicoder_env, tmp_path):
        """Test error when file doesn't exist."""
        mock_server.set_sequential_responses([
            # First response: AI tries to write to invalid path
            make_sse_response(
                "I'll write a file",
                tool_calls=[{
                    "name": "write_file",
                    "arguments": json.dumps({
                        "path": "/nonexistent/path/file.txt",
                        "content": "test"
                    })
                }]
            ),
            # AI should handle the error gracefully
            make_sse_response("I see that directory doesn't exist. Would you like me to create it?")
        ])

        child = spawn_aicoder(aicoder_env, tmp_path, timeout=20)

        try:
            child.expect(r"> ")
            child.sendline("write test")

            # Approve tool execution
            child.expect(r"Tool: write_file")
            child.expect(r"Approve \[Y/n\]")
            child.sendline("y")

            # Should see error message
            child.expect(r"error|Error|failed", timeout=10)

            # AI should respond to the error
            child.expect(r"doesn't exist|directory")
            child.expect(r"> ", timeout=10)

        finally:
            # Clean up: try to quit gracefully, then force close
            try:
                child.sendline("/quit")
                child.expect(pexpect.EOF, timeout=10)
            except (pexpect_exceptions.TIMEOUT, pexpect_exceptions.EOF):
                try:
                    child.terminate()
                    child.wait()
                except Exception:
                    child.close(force=True)

    def test_tool_rejection(self, mock_server, aicoder_env, tmp_path):
        """Test user rejecting a tool call."""
        mock_server.set_sequential_responses([
            # First response: AI wants to write a file
            make_sse_response(
                "I'll write a file",
                tool_calls=[{
                    "name": "write_file",
                    "arguments": json.dumps({"path": "test.txt", "content": "test"})
                }]
            ),
            # AI should handle rejection gracefully
            make_sse_response("Okay, I won't write the file. What else would you like?")
        ])

        child = spawn_aicoder(aicoder_env, tmp_path, timeout=20)

        try:
            child.expect(r"> ")
            child.sendline("test")

            # Reject tool execution
            child.expect(r"Tool: write_file")
            child.expect(r"Approve \[Y/n\]")
            child.sendline("n")

            # AI should respond to rejection
            child.expect(r"won't write|cancelled")
            child.expect(r"> ", timeout=10)

        finally:
            # Clean up: try to quit gracefully, then force close
            try:
                child.sendline("/quit")
                child.expect(pexpect.EOF, timeout=10)
            except (pexpect_exceptions.TIMEOUT, pexpect_exceptions.EOF):
                try:
                    child.terminate()
                    child.wait()
                except Exception:
                    child.close(force=True)


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
            # Clean up: try to quit gracefully, then force close
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
            # Clean up: try to quit gracefully, then force close
            try:
                child.sendline("/quit")
                child.expect(pexpect.EOF, timeout=10)
            except (pexpect_exceptions.TIMEOUT, pexpect_exceptions.EOF):
                try:
                    child.terminate()
                    child.wait()
                except Exception:
                    child.close(force=True)
