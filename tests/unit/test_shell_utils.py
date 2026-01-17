"""Unit tests for shell utilities."""

import pytest
from unittest.mock import patch, MagicMock
import subprocess

import sys
sys.path.insert(0, '/home/blah/storage/ai-worktree-storage/feat_test_coverage__20260117_062928')

from aicoder.utils.shell_utils import (
    ShellResult,
    execute_command_sync,
    execute_command_with_timeout,
)


class TestShellResult:
    """Test ShellResult dataclass."""

    def test_shell_result_creation(self):
        """Test creating ShellResult."""
        result = ShellResult(success=True, exit_code=0, stdout="output", stderr="")
        assert result.success is True
        assert result.exit_code == 0
        assert result.stdout == "output"
        assert result.stderr == ""

    def test_shell_result_failure(self):
        """Test ShellResult with failure."""
        result = ShellResult(success=False, exit_code=1, stdout="", stderr="error")
        assert result.success is False
        assert result.exit_code == 1


class TestExecuteCommandSync:
    """Test execute_command_sync function."""

    def test_successful_echo(self):
        """Test executing successful echo command."""
        result = execute_command_sync("echo hello")
        assert result.success is True
        assert result.exit_code == 0
        assert "hello" in result.stdout

    def test_failed_command(self):
        """Test executing failing command."""
        result = execute_command_sync("exit 1")
        assert result.success is False
        assert result.exit_code == 1

    def test_specific_exit_code(self):
        """Test command with specific exit code."""
        result = execute_command_sync("exit 42")
        assert result.success is False
        assert result.exit_code == 42

    def test_stderr_captured(self):
        """Test stderr is captured."""
        result = execute_command_sync("echo error message >&2")
        assert result.exit_code == 0
        assert "error message" in result.stderr

    def test_stdout_and_stderr(self):
        """Test both stdout and stderr are captured."""
        result = execute_command_sync("echo out; echo err >&2")
        assert result.success is True
        assert "out" in result.stdout
        assert "err" in result.stderr

    def test_empty_command(self):
        """Test empty command."""
        result = execute_command_sync("")
        # Empty command should succeed (no-op in bash)
        assert result.exit_code == 0

    def test_json_output(self):
        """Test JSON in output."""
        result = execute_command_sync('echo \'{"key": "value"}\'')
        assert result.success is True
        assert '{"key": "value"}' in result.stdout

    def test_unicode_output(self):
        """Test unicode in output."""
        result = execute_command_sync("echo '你好世界'")
        assert result.success is True
        assert "你好世界" in result.stdout

    def test_special_characters(self):
        """Test special characters in output."""
        result = execute_command_sync("echo '!@#$%^&*()[]{}'")
        assert result.success is True
        assert "!@#$%^&*()[]{}" in result.stdout

    def test_wildcard_expansion(self):
        """Test wildcard expansion works."""
        result = execute_command_sync("echo *.txt")
        assert result.success is True
        # Should expand to something (might be empty if no txt files)

    def test_pipe_command(self):
        """Test piped command."""
        result = execute_command_sync("echo 'test' | wc -c")
        assert result.success is True
        # 5 characters: t, e, s, t, newline

    def test_command_substitution(self):
        """Test command substitution."""
        result = execute_command_sync("echo $(echo hello)")
        assert result.success is True
        assert "hello" in result.stdout


class TestExecuteCommandWithTimeout:
    """Test execute_command_with_timeout function."""

    def test_quick_command(self):
        """Test quick command with timeout."""
        result = execute_command_with_timeout("echo done", 10)
        assert result.success is True
        assert "done" in result.stdout

    def test_timeout_short(self):
        """Test command that times out."""
        result = execute_command_with_timeout("sleep 10", 1)
        assert result.success is False
        assert result.exit_code == 124  # timeout exit code

    def test_very_short_timeout(self):
        """Test very short timeout with long-running command."""
        # With a very short timeout, a sleep command should timeout
        result = execute_command_with_timeout("sleep 2", 1)
        # Should timeout and return exit code 124
        assert result.exit_code == 124

    def test_long_running_success(self):
        """Test long running command that succeeds."""
        result = execute_command_with_timeout("sleep 0.1 && echo done", 5)
        assert result.success is True
        assert "done" in result.stdout


class TestExecuteCommandSyncEdgeCases:
    """Test edge cases for execute_command_sync."""

    def test_command_with_spaces(self):
        """Test command with multiple spaces."""
        result = execute_command_sync("echo 'hello    world'")
        assert result.success is True
        assert "hello    world" in result.stdout

    def test_command_with_newlines(self):
        """Test command with newlines."""
        result = execute_command_sync("echo -e 'line1\\nline2'")
        assert result.success is True
        assert "line1" in result.stdout
        assert "line2" in result.stdout

    def test_missing_command(self):
        """Test nonexistent command."""
        result = execute_command_sync("nonexistent_command_12345")
        assert result.success is False
        assert result.exit_code != 0
