"""Unit tests for CommandHandler."""

import pytest
from unittest.mock import MagicMock

import sys
sys.path.insert(0, '/home/blah/storage/ai-worktree-storage/feat_test_coverage__20260117_062928')

from aicoder.core.command_handler import CommandHandler
from aicoder.core.message_history import MessageHistory
from aicoder.core.input_handler import InputHandler
from aicoder.core.stats import Stats


class TestCommandHandler:
    """Test CommandHandler class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.message_history = MagicMock(spec=MessageHistory)
        self.input_handler = MagicMock(spec=InputHandler)
        self.stats = MagicMock(spec=Stats)

    def test_initialization(self):
        """Test CommandHandler initializes correctly."""
        handler = CommandHandler(
            self.message_history,
            self.input_handler,
            self.stats
        )
        assert handler.context is not None
        assert handler.registry is not None

    def test_context_has_references(self):
        """Test context has all required references."""
        handler = CommandHandler(
            self.message_history,
            self.input_handler,
            self.stats
        )
        assert handler.context.message_history is self.message_history
        assert handler.context.input_handler is self.input_handler
        assert handler.context.stats is self.stats

    def test_command_handler_set_in_context(self):
        """Test command_handler reference is set in context."""
        handler = CommandHandler(
            self.message_history,
            self.input_handler,
            self.stats
        )
        assert handler.context.command_handler is handler

    def test_handle_unknown_command(self):
        """Test handling unknown command returns proper result."""
        handler = CommandHandler(
            self.message_history,
            self.input_handler,
            self.stats
        )
        result = handler.handle_command("unknown_command_xyz")
        assert result.should_quit is False
        assert result.run_api_call is False

    def test_handle_empty_command(self):
        """Test handling empty command returns proper result."""
        handler = CommandHandler(
            self.message_history,
            self.input_handler,
            self.stats
        )
        result = handler.handle_command("")
        assert result.should_quit is False
        assert result.run_api_call is False

    def test_handle_whitespace_command(self):
        """Test handling whitespace-only command returns proper result."""
        handler = CommandHandler(
            self.message_history,
            self.input_handler,
            self.stats
        )
        result = handler.handle_command("   ")
        assert result.should_quit is False
        assert result.run_api_call is False

    def test_get_all_commands_returns_dict(self):
        """Test get_all_commands returns dictionary."""
        handler = CommandHandler(
            self.message_history,
            self.input_handler,
            self.stats
        )
        commands = handler.get_all_commands()
        assert isinstance(commands, dict)
        # Should have built-in commands registered
        assert len(commands) > 0

    def test_get_all_commands_has_help(self):
        """Test help command is registered."""
        handler = CommandHandler(
            self.message_history,
            self.input_handler,
            self.stats
        )
        commands = handler.get_all_commands()
        assert "help" in commands

    def test_get_all_commands_has_quit(self):
        """Test quit command is registered."""
        handler = CommandHandler(
            self.message_history,
            self.input_handler,
            self.stats
        )
        commands = handler.get_all_commands()
        assert "quit" in commands

    def test_get_all_commands_has_stats(self):
        """Test stats command is registered."""
        handler = CommandHandler(
            self.message_history,
            self.input_handler,
            self.stats
        )
        commands = handler.get_all_commands()
        assert "stats" in commands

    def test_get_all_commands_has_save(self):
        """Test save command is registered."""
        handler = CommandHandler(
            self.message_history,
            self.input_handler,
            self.stats
        )
        commands = handler.get_all_commands()
        assert "save" in commands

    def test_get_all_commands_has_load(self):
        """Test load command is registered."""
        handler = CommandHandler(
            self.message_history,
            self.input_handler,
            self.stats
        )
        commands = handler.get_all_commands()
        assert "load" in commands

    def test_get_all_commands_has_compact(self):
        """Test compact command is registered."""
        handler = CommandHandler(
            self.message_history,
            self.input_handler,
            self.stats
        )
        commands = handler.get_all_commands()
        assert "compact" in commands

    def test_get_all_commands_returns_copy(self):
        """Test get_all_commands returns a copy, not the original."""
        handler = CommandHandler(
            self.message_history,
            self.input_handler,
            self.stats
        )
        commands1 = handler.get_all_commands()
        commands1["test_modification"] = "modified"
        commands2 = handler.get_all_commands()
        assert "test_modification" not in commands2
