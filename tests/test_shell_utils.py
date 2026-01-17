"""
Tests for shell utilities
"""

import pytest


class TestShellUtils:
    """Test shell utility functions"""

    def test_shell_result_dataclass(self):
        """Test ShellResult dataclass creation"""
        from aicoder.utils.shell_utils import ShellResult

        result = ShellResult(success=True, exit_code=0, stdout="output", stderr="")

        assert result.success is True
        assert result.exit_code == 0
        assert result.stdout == "output"
        assert result.stderr == ""

    def test_execute_command_sync_success(self):
        """Test successful command execution"""
        from aicoder.utils.shell_utils import execute_command_sync

        result = execute_command_sync("echo hello")

        assert result.success is True
        assert result.exit_code == 0
        assert "hello" in result.stdout

    def test_execute_command_sync_failure(self):
        """Test failed command execution"""
        from aicoder.utils.shell_utils import execute_command_sync

        result = execute_command_sync("exit 1")

        assert result.success is False
        assert result.exit_code == 1

    def test_execute_command_sync_timeout(self):
        """Test command timeout handling"""
        from aicoder.utils.shell_utils import execute_command_sync

        # Use a command that sleeps longer than default timeout
        result = execute_command_sync("sleep 60")

        assert result.success is False
        assert result.exit_code == 124

    def test_execute_command_with_timeout(self):
        """Test command with custom timeout"""
        from aicoder.utils.shell_utils import execute_command_with_timeout

        result = execute_command_with_timeout("echo test", timeout_seconds=5)

        assert result.success is True
        assert "test" in result.stdout

    def test_execute_command_with_timeout_longer(self):
        """Test command that exceeds custom timeout"""
        from aicoder.utils.shell_utils import execute_command_with_timeout

        result = execute_command_with_timeout("sleep 10", timeout_seconds=1)

        assert result.success is False
        # Should have timed out or been killed
        assert result.exit_code != 0
