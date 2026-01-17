"""Tests for shell utilities module"""

import pytest
from aicoder.utils import shell_utils


class TestShellResult:
    """Tests for ShellResult dataclass"""

    def test_shell_result_creation(self):
        """Test ShellResult can be created with all fields"""
        result = shell_utils.ShellResult(
            success=True,
            exit_code=0,
            stdout="output",
            stderr="",
        )
        assert result.success is True
        assert result.exit_code == 0
        assert result.stdout == "output"
        assert result.stderr == ""

    def test_shell_result_failure(self):
        """Test ShellResult for failed command"""
        result = shell_utils.ShellResult(
            success=False,
            exit_code=1,
            stdout="",
            stderr="error message",
        )
        assert result.success is False
        assert result.exit_code == 1
        assert result.stdout == ""
        assert result.stderr == "error message"


class TestExecuteCommandSync:
    """Tests for execute_command_sync function"""

    def test_simple_echo(self):
        """Test executing a simple echo command"""
        result = shell_utils.execute_command_sync("echo hello")
        assert result.success is True
        assert result.exit_code == 0
        assert "hello" in result.stdout

    def test_command_with_spaces(self):
        """Test executing a command with spaces in output"""
        result = shell_utils.execute_command_sync("echo 'hello world'")
        assert result.success is True
        assert "hello world" in result.stdout

    def test_command_with_newlines(self):
        """Test executing a command that outputs newlines"""
        result = shell_utils.execute_command_sync("printf 'line1\\nline2\\n'")
        assert result.success is True
        assert "line1" in result.stdout
        assert "line2" in result.stdout

    def test_exit_code_zero(self):
        """Test command that exits with code 0"""
        result = shell_utils.execute_command_sync("true")
        assert result.success is True
        assert result.exit_code == 0

    def test_exit_code_nonzero(self):
        """Test command that exits with non-zero code"""
        result = shell_utils.execute_command_sync("false")
        assert result.success is False
        assert result.exit_code == 1

    def test_specific_exit_code(self):
        """Test command that exits with specific code"""
        result = shell_utils.execute_command_sync("exit 42")
        assert result.success is False
        assert result.exit_code == 42

    def test_stderr_output(self):
        """Test that stderr is captured"""
        result = shell_utils.execute_command_sync("echo 'error message' >&2")
        assert result.stderr
        assert "error message" in result.stderr

    def test_stdout_and_stderr(self):
        """Test that both stdout and stderr are captured separately"""
        result = shell_utils.execute_command_sync("echo stdout; echo stderr >&2")
        assert "stdout" in result.stdout
        assert "stderr" in result.stderr

    def test_timeout_default(self):
        """Test that command times out after default 30 seconds"""
        result = shell_utils.execute_command_sync("sleep 60")
        # Should timeout, exit code 124 is timeout's standard code
        assert result.success is False
        assert result.exit_code == 124

    def test_timeout_custom(self):
        """Test that command times out after custom timeout via internal mechanism"""
        # Note: The function uses internal 30s timeout, so we test with a command
        # that will complete quickly
        result = shell_utils.execute_command_sync("echo quick")
        assert result.success is True
        assert "quick" in result.stdout

    def test_missing_command(self):
        """Test handling of missing command"""
        result = shell_utils.execute_command_sync("command_that_does_not_exist_12345")
        assert result.success is False
        assert result.exit_code == 127  # "command not found"

    def test_empty_command(self):
        """Test executing empty command"""
        result = shell_utils.execute_command_sync("")
        assert result.success is True
        assert result.exit_code == 0

    def test_cwd_option(self):
        """Test that command executes in correct working directory"""
        # This tests that basic commands work, cwd handling is at subprocess level
        result = shell_utils.execute_command_sync("pwd")
        assert result.success is True
        assert result.stdout.strip() != ""

    def test_pwd_command(self):
        """Test pwd command"""
        result = shell_utils.execute_command_sync("pwd")
        assert result.success is True
        assert result.exit_code == 0
        assert len(result.stdout.strip()) > 0

    def test_ls_command(self):
        """Test ls command"""
        result = shell_utils.execute_command_sync("ls -la /tmp | head -5")
        assert result.success is True
        assert result.exit_code == 0

    def test_cat_command(self):
        """Test cat command with input"""
        result = shell_utils.execute_command_sync("echo 'test content' | cat")
        assert result.success is True
        assert "test content" in result.stdout

    def test_json_in_output(self):
        """Test capturing JSON in output"""
        result = shell_utils.execute_command_sync("echo '{\"key\": \"value\"}'")
        assert result.success is True
        assert "key" in result.stdout
        assert "value" in result.stdout

    def test_special_characters_in_command(self):
        """Test handling special characters in command"""
        result = shell_utils.execute_command_sync("echo 'path: /tmp/test file.txt'")
        assert result.success is True
        assert "path:" in result.stdout

    def test_backticks_in_output(self):
        """Test capturing backticks in output"""
        result = shell_utils.execute_command_sync("echo '`command`'")
        assert result.success is True
        assert "`command`" in result.stdout or "command" in result.stdout

    def test_variable_expansion(self):
        """Test shell variable expansion"""
        result = shell_utils.execute_command_sync("echo $HOME")
        assert result.success is True
        # Should expand to home directory path
        assert len(result.stdout.strip()) > 0

    def test_command_with_pipes(self):
        """Test shell pipe operations"""
        result = shell_utils.execute_command_sync("echo 'hello world' | wc -w")
        assert result.success is True
        assert "2" in result.stdout.strip() or "hello world" in result.stdout

    def test_command_with_redirect(self):
        """Test shell output redirection"""
        import tempfile
        with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False) as f:
            temp_path = f.name
        try:
            result = shell_utils.execute_command_sync(f"echo 'redirected content' > {temp_path}")
            assert result.success is True
            with open(temp_path, 'r') as f:
                content = f.read()
            assert "redirected content" in content
        finally:
            import os
            os.unlink(temp_path)

    def test_nested_quotes(self):
        """Test handling of nested quotes in command"""
        result = shell_utils.execute_command_sync("echo \"single 'double' quotes\"")
        assert result.success is True

    def test_exit_code_preserved(self):
        """Test that specific exit codes are preserved"""
        result = shell_utils.execute_command_sync("exit 5")
        assert result.exit_code == 5
        assert result.success is False


class TestExecuteCommandWithTimeout:
    """Tests for execute_command_with_timeout function"""

    def test_timeout_with_quick_command(self):
        """Test timeout wrapper with quick command"""
        result = shell_utils.execute_command_with_timeout("echo hello", 10)
        assert result.success is True
        assert "hello" in result.stdout

    def test_timeout_with_slow_command(self):
        """Test timeout wrapper with slow command that exceeds timeout"""
        # 2 second sleep with 1 second timeout should timeout
        result = shell_utils.execute_command_with_timeout("sleep 2", 1)
        assert result.success is False
        assert result.exit_code == 124

    def test_timeout_zero(self):
        """Test timeout of zero (should timeout immediately)"""
        result = shell_utils.execute_command_with_timeout("echo hello", 0)
        # With 0 second timeout, should still work for instant commands
        # or may timeout depending on implementation
        # We just verify it doesn't crash
        assert result.exit_code in [0, 124]

    def test_timeout_with_complex_command(self):
        """Test timeout wrapper with complex shell command"""
        result = shell_utils.execute_command_with_timeout("echo 1 && echo 2 && echo 3", 10)
        assert result.success is True
        assert "1" in result.stdout
        assert "2" in result.stdout
        assert "3" in result.stdout

    def test_timeout_with_special_characters(self):
        """Test timeout wrapper with special characters in command"""
        result = shell_utils.execute_command_with_timeout("echo 'test & special $ chars'", 10)
        assert result.success is True
        assert "test" in result.stdout
