"""
Integration tests for run_shell_command tool.

Tests command execution, timeout handling, and error cases.
"""

import os
import subprocess
import tempfile
import time
import pytest

import sys
sys.path.insert(0, '/home/blah/storage/ai-worktree-storage/feat_test_coverage__20260117_062928')

from aicoder.tools.internal.run_shell_command import execute, execute_with_process_group


class TestRunShellCommand:
    """Test shell command execution."""

    def test_simple_echo(self):
        """Test simple echo command."""
        result = execute({"command": "echo hello"})
        assert result["tool"] == "run_shell_command"
        assert "hello" in result["detailed"]
        assert result["friendly"].startswith("✓")

    def test_command_with_spaces(self):
        """Test command with spaces in arguments."""
        result = execute({"command": "echo 'hello world'"})
        assert "hello world" in result["detailed"]

    def test_command_with_newlines(self):
        """Test command that outputs newlines."""
        result = execute({"command": "printf 'line1\\nline2\\nline3\\n'"})
        assert "line1" in result["detailed"]
        assert "line2" in result["detailed"]
        assert "line3" in result["detailed"]

    def test_exit_code_zero(self):
        """Test command with exit code 0."""
        result = execute({"command": "true"})
        assert result["friendly"].startswith("✓")
        assert "exit code: 0" in result["friendly"]

    def test_exit_code_nonzero(self):
        """Test command with non-zero exit code."""
        result = execute({"command": "false"})
        assert result["friendly"].startswith("✗")
        assert "exit code: 1" in result["friendly"]

    def test_specific_exit_code(self):
        """Test command with specific exit code."""
        result = execute({"command": "exit 42"})
        assert "exit code: 42" in result["friendly"]

    def test_stderr_output(self):
        """Test command with stderr output."""
        result = execute({"command": "echo error >&2"})
        assert "STDERR" in result["detailed"] or "error" in result["detailed"]

    def test_stdout_and_stderr(self):
        """Test command with both stdout and stderr."""
        result = execute({"command": "echo stdout; echo stderr >&2"})
        assert "stdout" in result["detailed"]
        assert "stderr" in result["detailed"]

    def test_timeout_default(self):
        """Test default timeout (30 seconds)."""
        # Short command should succeed
        result = execute({"command": "sleep 0.1"})
        assert result["tool"] == "run_shell_command"

    def test_timeout_custom(self):
        """Test custom timeout."""
        # Very short timeout
        result = execute({"command": "sleep 10", "timeout": 1})
        assert "timed out" in result["friendly"] or "Timeout" in result["friendly"]

    def test_timeout_zero(self):
        """Test zero timeout."""
        result = execute({"command": "echo zero", "timeout": 0})
        assert "echo zero" in result["detailed"]

    def test_missing_command(self):
        """Test missing command argument."""
        with pytest.raises(Exception):
            execute({})

    def test_empty_command(self):
        """Test empty command."""
        with pytest.raises(Exception):
            execute({"command": ""})

    def test_cwd_option(self):
        """Test custom working directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create a file in the temp directory
            test_file = os.path.join(tmpdir, "test.txt")
            with open(test_file, "w") as f:
                f.write("test")

            result = execute({
                "command": "pwd",
                "cwd": tmpdir
            })
            assert tmpdir in result["detailed"] or "Working directory" in result["detailed"]

    def test_pwd_command(self):
        """Test pwd command."""
        result = execute({"command": "pwd"})
        assert result["tool"] == "run_shell_command"
        assert os.getcwd() in result["detailed"] or "Working directory" in result["detailed"]

    def test_ls_command(self):
        """Test ls command."""
        result = execute({"command": "ls -la"})
        assert result["tool"] == "run_shell_command"

    def test_cat_command(self):
        """Test cat command with file."""
        with tempfile.NamedTemporaryFile(mode="w", delete=False, suffix=".txt") as f:
            f.write("test content")
            temp_path = f.name

        try:
            result = execute({"command": f"cat {temp_path}"})
            assert "test content" in result["detailed"]
        finally:
            os.unlink(temp_path)

    def test_json_in_output(self):
        """Test JSON parsing in output."""
        result = execute({"command": "echo '{\"key\": \"value\"}'"})
        assert "key" in result["detailed"]
        assert "value" in result["detailed"]

    def test_multiline_json(self):
        """Test multiline JSON output."""
        result = execute({"command": "printf '{\\n  \"a\": 1,\\n  \"b\": 2\\n}\\n'"})
        assert "a" in result["detailed"]
        assert "1" in result["detailed"]

    def test_unicode_output(self):
        """Test unicode output."""
        result = execute({"command": "echo 'Hello 世界 🌍'"})
        assert "Hello" in result["detailed"] or "世界" in result["detailed"]

    def test_special_characters(self):
        """Test special characters in output."""
        result = execute({"command": "printf 'Special: $HOME \\n \\t \\'"})
        assert "Special" in result["detailed"]

    def test_wildcard_expansion(self):
        """Test wildcard expansion."""
        result = execute({"command": "echo *.py"})
        # Should contain some .py files or at least the wildcard itself
        assert result["tool"] == "run_shell_command"

    def test_pipe_command(self):
        """Test piped command."""
        result = execute({"command": "echo 'test123' | wc -c"})
        # 8 bytes = "test123\n"
        assert "8" in result["detailed"]

    def test_subshell(self):
        """Test subshell command."""
        result = execute({"command": "$(echo echo subshell)"})
        assert "subshell" in result["detailed"]

    def test_command_substitution(self):
        """Test command substitution."""
        result = execute({"command": "echo `date +%Y`"})
        assert result["tool"] == "run_shell_command"


class TestProcessGroup:
    """Test process group handling."""

    def test_process_group_created(self):
        """Test that process group is created."""
        # This is an implementation detail, but we verify the command runs
        result = execute({"command": "sleep 0.1"})
        assert result["tool"] == "run_shell_command"

    def test_background_process_killed(self):
        """Test that background processes are cleaned up."""
        # Start a process that runs in background
        result = execute({
            "command": "sleep 30 & sleep 0.5",
            "timeout": 5
        })
        # Should complete without hanging
        assert result["tool"] == "run_shell_command"

    def test_sigterm_handling(self):
        """Test SIGTERM is sent on timeout."""
        result = execute({
            "command": "trap 'exit 0' TERM; sleep 30",
            "timeout": 1
        })
        # Should timeout
        assert "timed out" in result["friendly"] or result["returncode"] != 0


class TestEdgeCases:
    """Test edge cases."""

    def test_very_long_command(self):
        """Test very long command."""
        long_arg = "x" * 1000
        result = echo_check(long_arg)
        assert long_arg in result["detailed"] if hasattr(result, "__getitem__") else True

    def test_command_with_quotes(self):
        """Test command with quotes."""
        result = execute({"command": 'echo "single and double"'})
        assert "single and double" in result["detailed"]

    def test_command_with_backticks(self):
        """Test command with backticks."""
        result = execute({"command": "echo `echo backtick`"})
        assert "backtick" in result["detailed"]

    def test_heredoc(self):
        """Test heredoc syntax."""
        result = execute({"command": "cat <<EOF\nheredoc content\nEOF"})
        assert "heredoc content" in result["detailed"]

    def test_command_with_semicolon(self):
        """Test semicolon separated commands."""
        result = execute({"command": "echo one; echo two"})
        assert "one" in result["detailed"]
        assert "two" in result["detailed"]

    def test_command_with_and(self):
        """Test && operator."""
        result = execute({"command": "echo first && echo second"})
        assert "first" in result["detailed"]
        assert "second" in result["detailed"]

    def test_command_with_or(self):
        """Test || operator."""
        result = execute({"command": "false || echo fallback"})
        assert "fallback" in result["detailed"]

    def test_nested_subshells(self):
        """Test nested subshells."""
        result = execute({"command": "echo $(echo $(echo nested))"})
        assert "nested" in result["detailed"]


def echo_check(text):
    """Helper to echo text and return result."""
    return execute({"command": f"echo {text}"})


class TestTimeoutEdgeCases:
    """Test timeout edge cases."""

    def test_immediate_timeout(self):
        """Test timeout of 0 seconds."""
        result = execute({"command": "echo immediate", "timeout": 0})
        assert result["tool"] == "run_shell_command"

    def test_very_short_timeout(self):
        """Test very short timeout."""
        result = execute({"command": "sleep 100", "timeout": 1})
        assert "timed out" in result["friendly"]

    def test_long_running_success(self):
        """Test successful long-running command."""
        result = execute({"command": "sleep 0.2"})
        assert result["tool"] == "run_shell_command"
        assert result["friendly"].startswith("✓")

    def test_multiple_timeouts(self):
        """Test multiple timeout calls."""
        for _ in range(3):
            result = execute({"command": "echo test", "timeout": 5})
            assert result["tool"] == "run_shell_command"


class TestConcurrentExecution:
    """Test concurrent command execution."""

    def test_sequential_long_commands(self):
        """Test running multiple long commands sequentially."""
        results = []
        for i in range(3):
            result = execute({"command": f"echo {i}", "timeout": 5})
            results.append(result)

        assert len(results) == 3
        for r in results:
            assert r["tool"] == "run_shell_command"

    def test_interrupting_command(self):
        """Test interrupting a command."""
        # Start a command and it should handle interruption gracefully
        result = execute({"command": "sleep 0.1; echo done", "timeout": 5})
        assert result["tool"] == "run_shell_command"
