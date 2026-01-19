"""Unit tests for new command."""

import pytest
from unittest.mock import MagicMock, patch
import sys

sys.path.insert(0, '/home/blah/storage/ai-worktree-storage/feat_test_coverage__20260117_062928')

from aicoder.core.commands.new import NewCommand
from aicoder.core.commands.base import CommandResult


class TestNewCommand:
    """Test NewCommand class."""

    def test_get_name(self):
        """Test returns correct command name."""
        context = MagicMock()
        command = NewCommand(context)
        assert command.get_name() == "new"

    def test_get_description(self):
        """Test returns correct description."""
        context = MagicMock()
        command = NewCommand(context)
        assert command.get_description() == "Reset the entire session"

    def test_get_aliases(self):
        """Test returns correct aliases."""
        context = MagicMock()
        command = NewCommand(context)
        assert command.get_aliases() == ["n"]

    def test_execute_returns_should_quit_false(self):
        """Test execute returns CommandResult with should_quit=False."""
        context = MagicMock()
        command = NewCommand(context)

        with patch('aicoder.core.commands.new.LogUtils.success'):
            result = command.execute()

        assert isinstance(result, CommandResult)
        assert result.should_quit is False
        assert result.run_api_call is False

    def test_execute_resets_stats(self):
        """Test execute resets context stats."""
        context = MagicMock()
        command = NewCommand(context)

        with patch('aicoder.core.commands.new.LogUtils.success'):
            command.execute()

        context.stats.reset.assert_called_once()

    def test_execute_clears_message_history(self):
        """Test execute clears message history."""
        context = MagicMock()
        command = NewCommand(context)

        with patch('aicoder.core.commands.new.LogUtils.success'):
            command.execute()

        context.message_history.clear.assert_called_once()

    def test_execute_logs_success_message(self):
        """Test execute logs success message."""
        context = MagicMock()
        command = NewCommand(context)

        with patch('aicoder.core.commands.new.LogUtils.success') as mock_success:
            command.execute()

        mock_success.assert_called_once_with("Session reset. Starting fresh.")

    def test_execute_ignores_args(self):
        """Test execute ignores any arguments."""
        context = MagicMock()
        command = NewCommand(context)

        with patch('aicoder.core.commands.new.LogUtils.success'):
            result1 = command.execute()
            result2 = command.execute(["arg1", "arg2"])

        # Both should return same result
        assert result1.should_quit is result2.should_quit
        assert result1.run_api_call is result2.run_api_call

    def test_execute_with_none_args(self):
        """Test execute works with None args."""
        context = MagicMock()
        command = NewCommand(context)

        with patch('aicoder.core.commands.new.LogUtils.success'):
            result = command.execute(None)

        assert result.should_quit is False
        assert result.run_api_call is False

    def test_command_inherits_from_base_command(self):
        """Test command inherits from BaseCommand."""
        context = MagicMock()
        command = NewCommand(context)
        # Check that it's an instance of BaseCommand
        from aicoder.core.commands.base import BaseCommand
        assert isinstance(command, BaseCommand)

    def test_execute_resets_stats_before_clearing_history(self):
        """Test execute resets stats before clearing message history."""
        context = MagicMock()
        command = NewCommand(context)

        with patch('aicoder.core.commands.new.LogUtils.success'):
            command.execute()

        # Check call order
        calls = [call for call in context.method_calls if call[0] in ['stats.reset', 'message_history.clear']]
        assert calls[0][0] == 'stats.reset'
        assert calls[1][0] == 'message_history.clear'
