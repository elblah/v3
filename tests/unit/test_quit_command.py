"""Unit tests for quit command."""

import pytest
from unittest.mock import MagicMock, patch
import sys

sys.path.insert(0, '/home/blah/storage/ai-worktree-storage/feat_test_coverage__20260117_062928')

from aicoder.core.commands.quit import QuitCommand
from aicoder.core.commands.base import CommandResult


class TestQuitCommand:
    """Test QuitCommand class."""

    def test_get_name(self):
        """Test returns correct command name."""
        context = MagicMock()
        command = QuitCommand(context)
        assert command.get_name() == "quit"

    def test_get_description(self):
        """Test returns correct description."""
        context = MagicMock()
        command = QuitCommand(context)
        assert command.get_description() == "Exit the application"

    def test_get_aliases(self):
        """Test returns correct aliases."""
        context = MagicMock()
        command = QuitCommand(context)
        assert command.get_aliases() == ["q"]

    def test_execute_returns_should_quit_true(self):
        """Test execute returns CommandResult with should_quit=True."""
        context = MagicMock()
        command = QuitCommand(context)

        with patch('aicoder.core.commands.quit.LogUtils.success'):
            result = command.execute()

        assert isinstance(result, CommandResult)
        assert result.should_quit is True
        assert result.run_api_call is False

    def test_execute_logs_goodbye_message(self):
        """Test execute logs goodbye message."""
        context = MagicMock()
        command = QuitCommand(context)

        with patch('aicoder.core.commands.quit.LogUtils.success') as mock_success:
            command.execute()

        mock_success.assert_called_once_with("Goodbye!")

    def test_execute_ignores_args(self):
        """Test execute ignores any arguments."""
        context = MagicMock()
        command = QuitCommand(context)

        with patch('aicoder.core.commands.quit.LogUtils.success'):
            result1 = command.execute()
            result2 = command.execute(["arg1", "arg2"])

        # Both should return same result
        assert result1.should_quit is result2.should_quit
        assert result1.run_api_call is result2.run_api_call

    def test_execute_with_none_args(self):
        """Test execute works with None args."""
        context = MagicMock()
        command = QuitCommand(context)

        with patch('aicoder.core.commands.quit.LogUtils.success'):
            result = command.execute(None)

        assert result.should_quit is True
        assert result.run_api_call is False

    def test_command_inherits_from_base_command(self):
        """Test command inherits from BaseCommand."""
        context = MagicMock()
        command = QuitCommand(context)
        # Check that it's an instance of BaseCommand
        from aicoder.core.commands.base import BaseCommand
        assert isinstance(command, BaseCommand)
