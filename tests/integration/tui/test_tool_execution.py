"""
Integration tests for tool execution through TUI using pexpect.

Tests verify all tools execute correctly with proper approval flow.
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


class TestReadFileTool:
    """Test read_file tool execution."""

    def test_read_simple_file(self, mock_server, aicoder_env, tmp_path):
        """Test reading a simple text file."""
        test_file = tmp_path / "test.txt"
        test_file.write_text("Hello World\nLine 2\nLine 3")

        # Use sequential responses for multi-turn conversation
        mock_server.set_sequential_responses([
            make_sse_response(
                "I'll read the file",
                tool_calls=[{
                    "name": "read_file",
                    "arguments": json.dumps({"path": str(test_file)})
                }]
            ),
            make_sse_response("File has 3 lines")
        ])

        child = spawn_aicoder(aicoder_env, tmp_path, timeout=15)

        try:
            child.expect(r"> ")
            child.sendline("read test")

            # read_file is auto-approved, no prompt needed
            # Just wait for AI response after tool execution
            child.expect(r"File has 3 lines")
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

    def test_read_with_offset(self, mock_server, aicoder_env, tmp_path):
        """Test reading file with offset."""
        test_file = tmp_path / "large.txt"
        lines = [f"Line {i}" for i in range(20)]
        test_file.write_text("\n".join(lines))

        # Use sequential responses for multi-turn conversation
        mock_server.set_sequential_responses([
            make_sse_response(
                "Reading from line 10",
                tool_calls=[{
                    "name": "read_file",
                    "arguments": json.dumps({"path": str(test_file), "offset": 10, "limit": 5})
                }]
            ),
            make_sse_response("Read 5 lines")
        ])

        child = spawn_aicoder(aicoder_env, tmp_path, timeout=15)

        try:
            child.expect(r"> ")
            child.sendline("read from line 10")

            # read_file is auto-approved, no prompt needed
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


class TestWriteFileTool:
    """Test write_file tool execution."""

    def test_write_new_file(self, mock_server, aicoder_env, tmp_path):
        """Test writing to a new file."""
        test_file = tmp_path / "new.txt"

        # Use sequential responses for multi-turn conversation
        mock_server.set_sequential_responses([
            make_sse_response(
                "Creating new file",
                tool_calls=[{
                    "name": "write_file",
                    "arguments": json.dumps({
                        "path": str(test_file),
                        "content": "New content"
                    })
                }]
            ),
            make_sse_response("File created successfully")
        ])

        child = spawn_aicoder(aicoder_env, tmp_path, timeout=15)

        try:
            child.expect(r"> ")
            child.sendline("create file")

            child.expect(r"write_file")
            child.sendline("y")

            child.expect(r"File created successfully")
            child.expect(r"> ")

            # Verify file was actually written
            assert test_file.exists()
            assert test_file.read_text() == "New content"
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

    def test_write_update_existing_file(self, mock_server, aicoder_env, tmp_path):
        """Test writing to an existing file."""
        test_file = tmp_path / "existing.txt"
        test_file.write_text("Old content")

        # Use sequential responses for multi-turn conversation
        mock_server.set_sequential_responses([
            make_sse_response(
                "I'll read it first, then update",
                tool_calls=[{
                    "name": "read_file",
                    "arguments": json.dumps({"path": str(test_file)})
                }]
            ),
            make_sse_response(
                "Now updating",
                tool_calls=[{
                    "name": "write_file",
                    "arguments": json.dumps({
                        "path": str(test_file),
                        "content": "Updated content"
                    })
                }]
            ),
            make_sse_response("File updated")
        ])

        child = spawn_aicoder(aicoder_env, tmp_path, timeout=20)

        try:
            child.expect(r"> ")
            child.sendline("update file")

            # read_file is auto-approved, no prompt needed
            # write_file requires approval
            child.expect(r"write_file")
            child.sendline("y")

            child.expect(r"File updated")
            child.expect(r"> ", timeout=10)

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


class TestEditFileTool:
    """Test edit_file tool execution."""

    def test_edit_file_replace(self, mock_server, aicoder_env, tmp_path):
        """Test editing file with text replacement."""
        test_file = tmp_path / "edit.txt"
        test_file.write_text("Hello World\nGoodbye World")

        # Use sequential responses for multi-turn conversation
        # Note: edit_file requires reading the file first
        mock_server.set_sequential_responses([
            make_sse_response(
                "I'll read the file first",
                tool_calls=[{
                    "name": "read_file",
                    "arguments": json.dumps({"path": str(test_file)})
                }]
            ),
            make_sse_response(
                "Replacing 'World' with 'Universe'",
                tool_calls=[{
                    "name": "edit_file",
                    "arguments": json.dumps({
                        "path": str(test_file),
                        "old_string": "World",
                        "new_string": "Universe"
                    })
                }]
            ),
            make_sse_response("Replaced successfully")
        ])

        child = spawn_aicoder(aicoder_env, tmp_path, timeout=15)

        try:
            child.expect(r"> ")
            child.sendline("replace World")

            # read_file is auto-approved
            # edit_file requires approval
            child.expect(r"edit_file")
            child.sendline("y")

            child.expect(r"Replaced successfully")
            child.expect(r"> ", timeout=10)

            content = test_file.read_text()
            assert "Universe" in content
            assert "World" not in content
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


class TestGrepTool:
    """Test grep tool execution."""

    def test_grep_simple_search(self, mock_server, aicoder_env, tmp_path):
        """Test simple grep search."""
        test_file = tmp_path / "search.txt"
        test_file.write_text("apple\nbanana\napple pie\ncherry")

        # Use sequential responses for multi-turn conversation
        mock_server.set_sequential_responses([
            make_sse_response(
                "Searching for 'apple'",
                tool_calls=[{
                    "name": "grep",
                    "arguments": json.dumps({
                        "text": "apple",
                        "path": str(tmp_path)
                    })
                }]
            ),
            make_sse_response("Found 2 matches")
        ])

        child = spawn_aicoder(aicoder_env, tmp_path, timeout=15)

        try:
            child.expect(r"> ")
            child.sendline("find apple")

            # grep is auto-approved, no prompt needed
            child.expect(r"Found 2 matches")
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


class TestListDirectoryTool:
    """Test list_directory tool execution."""

    def test_list_current_dir(self, mock_server, aicoder_env, tmp_path):
        """Test listing current directory."""
        (tmp_path / "file1.txt").write_text("content1")
        (tmp_path / "file2.txt").write_text("content2")
        (tmp_path / "subdir").mkdir()

        # Use sequential responses for multi-turn conversation
        mock_server.set_sequential_responses([
            make_sse_response(
                "Listing directory",
                tool_calls=[{
                    "name": "list_directory",
                    "arguments": json.dumps({"path": str(tmp_path)})
                }]
            ),
            make_sse_response("Found 2 files and 1 directory")
        ])

        child = spawn_aicoder(aicoder_env, tmp_path, timeout=15)

        try:
            child.expect(r"> ")
            child.sendline("list files")

            # list_directory is auto-approved, no prompt needed
            child.expect(r"Found 2 files|file1\.txt|subdir")
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


class TestRunShellCommandTool:
    """Test run_shell_command tool execution."""

    def test_simple_command(self, mock_server, aicoder_env, tmp_path):
        """Test simple shell command."""
        # Use sequential responses for multi-turn conversation
        mock_server.set_sequential_responses([
            make_sse_response(
                "Running echo",
                tool_calls=[{
                    "name": "run_shell_command",
                    "arguments": json.dumps({"command": "echo hello"})
                }]
            ),
            make_sse_response("Command executed")
        ])

        child = spawn_aicoder(aicoder_env, tmp_path, timeout=15)

        try:
            child.expect(r"> ")
            child.sendline("echo hello")

            # run_shell_command requires approval
            child.expect(r"run_shell_command")
            child.sendline("y")

            child.expect(r"Command executed")
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

    def test_command_with_pipes(self, mock_server, aicoder_env, tmp_path):
        """Test command with pipes."""
        # Use sequential responses for multi-turn conversation
        mock_server.set_sequential_responses([
            make_sse_response(
                "Counting files",
                tool_calls=[{
                    "name": "run_shell_command",
                    "arguments": json.dumps({"command": "ls | wc -l"})
                }]
            ),
            make_sse_response("Done counting")
        ])

        child = spawn_aicoder(aicoder_env, tmp_path, timeout=15)

        try:
            child.expect(r"> ")
            child.sendline("count lines")

            # run_shell_command requires approval
            child.expect(r"run_shell_command")
            child.sendline("y")

            child.expect(r"Done counting")
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


class TestMultipleTools:
    """Test multiple tools in one conversation."""

    def test_read_write_chain(self, mock_server, aicoder_env, tmp_path):
        """Test chain: read -> process -> write."""
        test_file = tmp_path / "chain.txt"
        test_file.write_text("original")

        # Use sequential responses for multi-turn conversation
        mock_server.set_sequential_responses([
            make_sse_response(
                "Reading file",
                tool_calls=[{
                    "name": "read_file",
                    "arguments": json.dumps({"path": str(test_file)})
                }]
            ),
            make_sse_response(
                "Processing",
                tool_calls=[{
                    "name": "run_shell_command",
                    "arguments": json.dumps({"command": "echo processed"})
                }]
            ),
            make_sse_response(
                "Writing back",
                tool_calls=[{
                    "name": "write_file",
                    "arguments": json.dumps({
                        "path": str(test_file),
                        "content": "processed"
                    })
                }]
            ),
            make_sse_response("All done")
        ])

        child = spawn_aicoder(aicoder_env, tmp_path, timeout=30)

        try:
            child.expect(r"> ")
            child.sendline("process file")

            # Read file (auto-approved)
            # Run command (requires approval)
            child.expect(r"run_shell_command")
            child.sendline("y")

            # Write file (requires approval)
            child.expect(r"write_file")
            child.sendline("y")

            # Done
            child.expect(r"All done")
            child.expect(r"> ")

            assert test_file.read_text() == "processed"
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

    def test_multiple_commands(self, mock_server, aicoder_env, tmp_path):
        """Test multiple independent commands."""
        # Use sequential responses for multi-turn conversation
        mock_server.set_sequential_responses([
            make_sse_response(
                "Listing",
                tool_calls=[{
                    "name": "run_shell_command",
                    "arguments": json.dumps({"command": "ls -la"})
                }]
            ),
            make_sse_response(
                "Now counting",
                tool_calls=[{
                    "name": "run_shell_command",
                    "arguments": json.dumps({"command": "ls | wc -l"})
                }]
            ),
            make_sse_response("Done")
        ])

        child = spawn_aicoder(aicoder_env, tmp_path, timeout=30)

        try:
            child.expect(r"> ")
            child.sendline("list and count")

            child.expect(r"run_shell_command.*ls -la")
            child.sendline("y")

            child.expect(r"run_shell_command.*ls \| wc -l")
            child.sendline("y")

            child.expect(r"Done")
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
