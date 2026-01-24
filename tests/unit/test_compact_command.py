"""Unit tests for CompactCommand."""

import pytest
from unittest.mock import MagicMock, patch
import sys
sys.path.insert(0, '/home/blah/storage/ai-worktree-storage/feat_test_coverage__20260117_062928')

from aicoder.core.commands.base import CommandContext, CommandResult
from aicoder.core.commands.compact import CompactCommand


class MockMessageHistory:
    """Mock MessageHistory for testing."""
    def __init__(self):
        self._messages = []
        self._compaction_count = 0
        self._stats = {"count": 0, "tokens": 0, "bytes": 0}
        self._prompt_size = 0

    def get_messages(self):
        return self._messages

    def set_messages(self, messages):
        self._messages = messages

    def estimate_context(self):
        pass

    def get_round_count(self):
        return len([m for m in self._messages if m.get("role") == "user"])

    def get_message_count(self):
        return len(self._messages)

    def get_compaction_count(self):
        return self._compaction_count

    def get_tool_call_stats(self):
        return self._stats.copy()  # Return a copy to avoid modification

    def compact_memory(self):
        self._compaction_count += 1

    def force_compact_rounds(self, n):
        pass

    def force_compact_messages(self, n):
        pass

    def prune_all_tool_results(self):
        return 0

    def prune_oldest_tool_results(self, n):
        return min(n, self._stats["count"])

    def prune_keep_newest_tool_results(self, keep_count):
        if keep_count >= self._stats["count"]:
            return 0
        return self._stats["count"] - keep_count


class MockInputHandler:
    """Mock InputHandler for testing."""
    pass


class MockStats:
    """Mock Stats for testing."""
    def __init__(self):
        self.current_prompt_size = 1000

    def print_stats(self):
        pass


@pytest.fixture
def mock_context():
    """Create a mock CommandContext."""
    return CommandContext(
        message_history=MockMessageHistory(),
        input_handler=MockInputHandler(),
        stats=MockStats()
    )


@pytest.fixture
def compact_command(mock_context):
    """Create CompactCommand instance."""
    return CompactCommand(mock_context)


class TestCompactCommandBasics:
    """Test CompactCommand basic properties."""

    def test_get_name(self, compact_command):
        """Test command name."""
        assert compact_command.get_name() == "compact"

    def test_get_description(self, compact_command):
        """Test command description."""
        assert "compact" in compact_command.get_description().lower()

    def test_get_aliases(self, compact_command):
        """Test command aliases."""
        aliases = compact_command.get_aliases()
        assert "c" in aliases

    def test_usage_format(self, compact_command):
        """Test usage string format."""
        assert "/compact" in compact_command.usage


class TestCompactCommandExecute:
    """Test CompactCommand execute method."""

    def test_execute_no_args(self, compact_command, mock_context):
        """Test execute with no arguments."""
        with patch('aicoder.core.commands.compact.Config') as mock_config:
            mock_config.auto_compact_enabled.return_value = True
            mock_config.auto_compact_threshold.return_value = 10000
            mock_config.colors = {
                "green": "\033[32m",
                "yellow": "\033[33m",
                "cyan": "\033[36m",
                "dim": "\033[2m",
                "reset": "\033[0m"
            }

            result = compact_command.execute([])
            assert result.should_quit is False
            assert result.run_api_call is False

    def test_execute_with_none_args(self, compact_command, mock_context):
        """Test execute with None arguments."""
        with patch('aicoder.core.commands.compact.Config') as mock_config:
            mock_config.auto_compact_enabled.return_value = True
            mock_config.auto_compact_threshold.return_value = 10000
            mock_config.colors = {
                "green": "\033[32m",
                "yellow": "\033[33m",
                "cyan": "\033[36m",
                "dim": "\033[2m",
                "reset": "\033[0m"
            }

            result = compact_command.execute(None)
            assert result.should_quit is False
            assert result.run_api_call is False


class TestCompactCommandForce:
    """Test CompactCommand force options."""

    def test_force_compact_rounds(self, compact_command, mock_context):
        """Test force compact rounds."""
        mock_context.message_history._messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ]

        with patch('aicoder.core.commands.compact.Config') as mock_config:
            mock_config.auto_compact_enabled.return_value = True
            mock_config.auto_compact_threshold.return_value = 10000
            mock_config.colors = {
                "green": "\033[32m",
                "yellow": "\033[33m",
                "cyan": "\033[36m",
                "dim": "\033[2m",
                "reset": "\033[0m"
            }
            mock_context.message_history.force_compact_rounds = MagicMock()

            result = compact_command.execute(["force", "3"])
            assert result.should_quit is False
            mock_context.message_history.force_compact_rounds.assert_called_with(3)

    def test_force_compact_rounds_negative(self, compact_command, mock_context):
        """Test force compact rounds with negative count (-3 means keep 3 newest)."""
        mock_context.message_history._messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ]

        with patch('aicoder.core.commands.compact.Config') as mock_config:
            mock_config.auto_compact_enabled.return_value = True
            mock_config.auto_compact_threshold.return_value = 10000
            mock_config.colors = {
                "green": "\033[32m",
                "yellow": "\033[33m",
                "cyan": "\033[36m",
                "dim": "\033[2m",
                "reset": "\033[0m"
            }
            mock_context.message_history.force_compact_rounds = MagicMock()

            result = compact_command.execute(["force", "-3"])
            assert result.should_quit is False
            mock_context.message_history.force_compact_rounds.assert_called_with(-3)

    def test_force_compact_messages(self, compact_command, mock_context):
        """Test force compact messages."""
        mock_context.message_history._messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ]

        with patch('aicoder.core.commands.compact.Config') as mock_config:
            mock_config.auto_compact_enabled.return_value = True
            mock_config.auto_compact_threshold.return_value = 10000
            mock_config.colors = {
                "green": "\033[32m",
                "yellow": "\033[33m",
                "cyan": "\033[36m",
                "dim": "\033[2m",
                "reset": "\033[0m"
            }
            mock_context.message_history.force_compact_messages = MagicMock()

            result = compact_command.execute(["force-messages", "5"])
            assert result.should_quit is False
            mock_context.message_history.force_compact_messages.assert_called_with(5)

    def test_force_compact_messages_negative(self, compact_command, mock_context):
        """Test force compact messages with negative count (-15 means keep 15 newest)."""
        mock_context.message_history._messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ]

        with patch('aicoder.core.commands.compact.Config') as mock_config:
            mock_config.auto_compact_enabled.return_value = True
            mock_config.auto_compact_threshold.return_value = 10000
            mock_config.colors = {
                "green": "\033[32m",
                "yellow": "\033[33m",
                "cyan": "\033[36m",
                "dim": "\033[2m",
                "reset": "\033[0m"
            }
            mock_context.message_history.force_compact_messages = MagicMock()

            result = compact_command.execute(["force-messages", "-15"])
            assert result.should_quit is False
            mock_context.message_history.force_compact_messages.assert_called_with(-15)


class TestCompactCommandPrune:
    """Test CompactCommand prune options."""

    def test_prune_all(self, compact_command, mock_context):
        """Test prune all tool results."""
        mock_context.message_history._stats["count"] = 5
        mock_context.message_history._stats["tokens"] = 1000
        mock_context.message_history._stats["bytes"] = 50000
        mock_context.message_history._messages = [
            {"role": "tool", "content": "result1", "tool_call_id": "1"},
            {"role": "tool", "content": "result2", "tool_call_id": "2"},
        ]

        with patch('aicoder.core.commands.compact.Config') as mock_config:
            mock_config.colors = {
                "green": "\033[32m",
                "yellow": "\033[33m",
                "cyan": "\033[36m",
                "dim": "\033[2m",
                "reset": "\033[0m"
            }
            mock_context.message_history.prune_all_tool_results = MagicMock(return_value=2)

            result = compact_command.execute(["prune", "all"])
            assert result.should_quit is False
            assert result.run_api_call is False

    def test_prune_stats(self, compact_command, mock_context):
        """Test prune stats."""
        mock_context.message_history._stats["count"] = 3
        mock_context.message_history._stats["tokens"] = 500
        mock_context.message_history._stats["bytes"] = 10000

        with patch('aicoder.core.commands.compact.Config') as mock_config:
            mock_config.colors = {
                "green": "\033[32m",
                "yellow": "\033[33m",
                "cyan": "\033[36m",
                "dim": "\033[2m",
                "reset": "\033[0m"
            }

            result = compact_command.execute(["prune", "stats"])
            assert result.should_quit is False
            assert result.run_api_call is False

    def test_prune_count(self, compact_command, mock_context):
        """Test prune specific count."""
        mock_context.message_history._stats["count"] = 10
        mock_context.message_history._stats["tokens"] = 2000
        mock_context.message_history._stats["bytes"] = 100000

        with patch('aicoder.core.commands.compact.Config') as mock_config:
            mock_config.colors = {
                "green": "\033[32m",
                "yellow": "\033[33m",
                "cyan": "\033[36m",
                "dim": "\033[2m",
                "reset": "\033[0m"
            }
            mock_context.message_history.prune_oldest_tool_results = MagicMock(return_value=3)

            result = compact_command.execute(["prune", "3"])
            assert result.should_quit is False
            assert result.run_api_call is False

    def test_prune_no_tool_results(self, compact_command, mock_context):
        """Test prune when no tool results available."""
        mock_context.message_history._stats["count"] = 0
        mock_context.message_history._stats["tokens"] = 0
        mock_context.message_history._stats["bytes"] = 0

        with patch('aicoder.core.commands.compact.Config') as mock_config:
            mock_config.colors = {
                "green": "\033[32m",
                "yellow": "\033[33m",
                "cyan": "\033[36m",
                "dim": "\033[2m",
                "reset": "\033[0m"
            }

            result = compact_command.execute(["prune", "all"])
            assert result.should_quit is False
            assert result.run_api_call is False

    def test_prune_negative_count(self, compact_command, mock_context):
        """Test prune with negative count - keep only N newest."""
        mock_context.message_history._stats["count"] = 10
        mock_context.message_history._stats["tokens"] = 2000
        mock_context.message_history._stats["bytes"] = 100000
        mock_context.message_history.prune_keep_newest_tool_results = MagicMock(return_value=8)

        with patch('aicoder.core.commands.compact.Config') as mock_config:
            mock_config.colors = {
                "green": "\033[32m",
                "yellow": "\033[33m",
                "cyan": "\033[36m",
                "dim": "\033[2m",
                "reset": "\033[0m"
            }

            result = compact_command.execute(["prune", "-2"])
            assert result.should_quit is False
            assert result.run_api_call is False
            mock_context.message_history.prune_keep_newest_tool_results.assert_called_with(2)

    def test_prune_negative_count_no_prune(self, compact_command, mock_context):
        """Test prune with negative count when nothing needs pruning."""
        mock_context.message_history._stats["count"] = 3
        mock_context.message_history._stats["tokens"] = 600
        mock_context.message_history._stats["bytes"] = 30000
        mock_context.message_history.prune_keep_newest_tool_results = MagicMock(return_value=0)

        with patch('aicoder.core.commands.compact.Config') as mock_config:
            mock_config.colors = {
                "green": "\033[32m",
                "yellow": "\033[33m",
                "cyan": "\033[36m",
                "dim": "\033[2m",
                "reset": "\033[0m"
            }

            result = compact_command.execute(["prune", "-5"])
            assert result.should_quit is False
            assert result.run_api_call is False
            mock_context.message_history.prune_keep_newest_tool_results.assert_called_with(5)


class TestCompactCommandStats:
    """Test CompactCommand stats option."""

    def test_stats(self, compact_command, mock_context):
        """Test stats display."""
        mock_context.message_history._messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ]
        mock_context.message_history._compaction_count = 2
        mock_context.stats.current_prompt_size = 5000

        with patch('aicoder.core.commands.compact.Config') as mock_config:
            mock_config.auto_compact_threshold.return_value = 10000
            mock_config.colors = {
                "green": "\033[32m",
                "yellow": "\033[33m",
                "cyan": "\033[36m",
                "dim": "\033[2m",
                "reset": "\033[0m"
            }
            mock_config.auto_compact_enabled.return_value = True

            result = compact_command.execute(["stats"])
            assert result.should_quit is False
            assert result.run_api_call is False


class TestCompactCommandHelp:
    """Test CompactCommand help option."""

    def test_help(self, compact_command, mock_context):
        """Test help display."""
        with patch('aicoder.core.commands.compact.Config') as mock_config:
            mock_config.colors = {
                "green": "\033[32m",
                "yellow": "\033[33m",
                "cyan": "\033[36m",
                "dim": "\033[2m",
                "reset": "\033[0m"
            }

            result = compact_command.execute(["help"])
            # Help should return CommandResult
            assert isinstance(result, CommandResult)


class TestCompactCommandUnknown:
    """Test CompactCommand unknown command handling."""

    def test_unknown_command(self, compact_command, mock_context):
        """Test unknown command shows error."""
        with patch('aicoder.core.commands.compact.Config') as mock_config:
            mock_config.colors = {
                "green": "\033[32m",
                "yellow": "\033[33m",
                "cyan": "\033[36m",
                "dim": "\033[2m",
                "reset": "\033[0m"
            }

            result = compact_command.execute(["unknown_command"])
            # Returns CommandResult for unknown command
            assert isinstance(result, CommandResult)
            assert result.should_quit is False
            assert result.run_api_call is False


class TestCompactCommandAutoCompactDisabled:
    """Test CompactCommand when auto-compaction is disabled."""

    def test_auto_compact_disabled(self, compact_command, mock_context):
        """Test auto-compact when disabled."""
        mock_context.message_history._messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ]
        mock_context.stats.current_prompt_size = 1000

        with patch('aicoder.core.commands.compact.Config') as mock_config:
            mock_config.auto_compact_enabled.return_value = False
            mock_config.auto_compact_threshold.return_value = 10000
            mock_config.colors = {
                "green": "\033[32m",
                "yellow": "\033[33m",
                "cyan": "\033[36m",
                "dim": "\033[2m",
                "reset": "\033[0m"
            }

            result = compact_command.execute([])
            assert result.should_quit is False
            assert result.run_api_call is False

    def test_auto_compact_not_needed(self, compact_command, mock_context):
        """Test auto-compact when not needed (below 80% threshold)."""
        mock_context.message_history._messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ]
        mock_context.stats.current_prompt_size = 500  # 5% of 10000

        with patch('aicoder.core.commands.compact.Config') as mock_config:
            mock_config.auto_compact_enabled.return_value = True
            mock_config.auto_compact_threshold.return_value = 10000
            mock_config.colors = {
                "green": "\033[32m",
                "yellow": "\033[33m",
                "cyan": "\033[36m",
                "dim": "\033[2m",
                "reset": "\033[0m"
            }

            result = compact_command.execute([])
            assert result.should_quit is False
            assert result.run_api_call is False


class TestCompactCommandNoMessages:
    """Test CompactCommand when no messages available."""

    def test_no_messages_to_compact(self, compact_command, mock_context):
        """Test compact when no messages available."""
        mock_context.message_history._messages = []
        mock_context.stats.current_prompt_size = 0

        with patch('aicoder.core.commands.compact.Config') as mock_config:
            mock_config.auto_compact_enabled.return_value = True
            mock_config.auto_compact_threshold.return_value = 10000
            mock_config.colors = {
                "green": "\033[32m",
                "yellow": "\033[33m",
                "cyan": "\033[36m",
                "dim": "\033[2m",
                "reset": "\033[0m"
            }

            result = compact_command.execute([])
            assert result.should_quit is False
            assert result.run_api_call is False


class TestCompactCommandParseArgs:
    """Test CompactCommand argument parsing."""

    def test_parse_empty_args(self, compact_command):
        """Test parsing empty args."""
        result = compact_command._parse_args([])
        assert result == {}

    def test_parse_force_with_count(self, compact_command):
        """Test parsing force with count."""
        result = compact_command._parse_args(["force", "5"])
        assert result.get("force") is True
        assert result.get("count") == 5

    def test_parse_force_negative_count(self, compact_command):
        """Test parsing force with negative count (-3 means keep 3 newest)."""
        result = compact_command._parse_args(["force", "-3"])
        assert result.get("force") is True
        assert result.get("count") == -3

    def test_parse_force_messages_negative_count(self, compact_command):
        """Test parsing force-messages with negative count (-15 means keep 15 newest)."""
        result = compact_command._parse_args(["force-messages", "-15"])
        assert result.get("force_messages") is True
        assert result.get("count") == -15

    def test_parse_force_without_count(self, compact_command):
        """Test parsing force without count - returns error flag."""
        result = compact_command._parse_args(["force"])
        # Without count argument, returns error flag (shows error)
        assert result == {"error": True}

    def test_parse_force_messages_with_count(self, compact_command):
        """Test parsing force-messages with count."""
        result = compact_command._parse_args(["force-messages", "10"])
        assert result.get("force_messages") is True
        assert result.get("count") == 10

    def test_parse_stats(self, compact_command):
        """Test parsing stats."""
        result = compact_command._parse_args(["stats"])
        assert result.get("stats") is True

    def test_parse_case_insensitive(self, compact_command):
        """Test that command parsing is case insensitive."""
        result = compact_command._parse_args(["FORCE", "3"])
        assert result.get("force") is True
        assert result.get("count") == 3

    def test_parse_force_messages_case_insensitive(self, compact_command):
        """Test that force-messages parsing is case insensitive."""
        result = compact_command._parse_args(["FORCE-MESSAGES", "5"])
        assert result.get("force_messages") is True
        assert result.get("count") == 5

    def test_parse_force_messages_invalid_count(self, compact_command):
        """Test parsing force-messages with invalid count - returns count=1."""
        result = compact_command._parse_args(["force-messages", "invalid"])
        # When ValueError occurs, count defaults to 1
        assert result.get("force_messages") is True
        assert result.get("count") == 1

    def test_parse_force_invalid_count(self, compact_command):
        """Test parsing force with invalid count - returns count=1."""
        result = compact_command._parse_args(["force", "invalid"])
        # When ValueError occurs, count defaults to 1
        assert result.get("force") is True
        assert result.get("count") == 1


class TestCompactCommandHandleCompact:
    """Test CompactCommand _handle_compact method."""

    def test_handle_compact_with_prune_stats(self, compact_command, mock_context):
        """Test _handle_compact when prune=stats returns CommandResult."""
        mock_context.message_history._stats["count"] = 5
        mock_context.message_history._stats["tokens"] = 1000
        mock_context.message_history._stats["bytes"] = 50000

        with patch('aicoder.core.commands.compact.Config') as mock_config:
            mock_config.auto_compact_enabled.return_value = True
            mock_config.auto_compact_threshold.return_value = 10000
            mock_config.colors = {
                "green": "\033[32m",
                "yellow": "\033[33m",
                "cyan": "\033[36m",
                "dim": "\033[2m",
                "reset": "\033[0m"
            }

            result = compact_command._parse_args(["prune", "stats"])
            # prune stats returns dict, not CommandResult
            assert isinstance(result, dict)

    def test_handle_compact_prune_all_no_results(self, compact_command, mock_context):
        """Test _handle_compact prune all with no tool results."""
        mock_context.message_history._stats["count"] = 0

        with patch('aicoder.core.commands.compact.Config') as mock_config:
            mock_config.colors = {
                "green": "\033[32m",
                "yellow": "\033[33m",
                "cyan": "\033[36m",
                "dim": "\033[2m",
                "reset": "\033[0m"
            }

            result = compact_command.execute(["prune", "all"])
            assert result.should_quit is False

    def test_handle_compact_force_messages_with_messages(self, compact_command, mock_context):
        """Test _handle_compact force-messages with messages."""
        mock_context.message_history._messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
            {"role": "user", "content": "How are you?"},
            {"role": "assistant", "content": "Fine!"},
        ]

        with patch('aicoder.core.commands.compact.Config') as mock_config:
            mock_config.auto_compact_enabled.return_value = True
            mock_config.auto_compact_threshold.return_value = 10000
            mock_config.colors = {
                "green": "\033[32m",
                "yellow": "\033[33m",
                "cyan": "\033[36m",
                "dim": "\033[2m",
                "reset": "\033[0m"
            }
            mock_context.message_history.force_compact_messages = MagicMock()

            result = compact_command.execute(["force-messages", "2"])
            assert result.should_quit is False
            mock_context.message_history.force_compact_messages.assert_called_with(2)

    def test_parse_prune_count_less_than_one(self, compact_command):
        """Test parsing prune with count less than 1 returns error flag."""
        result = compact_command._parse_args(["prune", "0"])
        # Count 0 is invalid, returns error flag
        assert result == {"error": True}

    def test_parse_prune_negative_count(self, compact_command):
        """Test parsing prune with negative count works correctly."""
        result = compact_command._parse_args(["prune", "-5"])
        # Negative count should now be valid for keeping newest results
        assert result.get("prune") == "-5"
        assert result.get("count") == -5

    def test_parse_prune_empty_second_arg(self, compact_command):
        """Test parsing prune with empty second arg defaults to 'all'."""
        # This tests the branch: args[1].lower() if len(args) > 1 else "all"
        result = compact_command._parse_args(["prune"])
        # When args = ["prune"] without second arg, it defaults to "all"
        expected = {"prune": "all", "is_prune_operation": True}
        assert result == expected

    def test_parse_prune_non_numeric_string(self, compact_command):
        """Test parsing prune with non-numeric string triggers ValueError."""
        # This tests the ValueError exception handler
        result = compact_command._parse_args(["prune", "abc"])
        # ValueError causes return error flag
        assert result == {"error": True}

    def test_handle_compact_exception(self, compact_command, mock_context):
        """Test _handle_compact when compaction raises exception."""
        mock_context.message_history._messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ]
        mock_context.stats.current_prompt_size = 9000  # 90% of threshold

        with patch('aicoder.core.commands.compact.Config') as mock_config:
            mock_config.auto_compact_enabled.return_value = True
            mock_config.auto_compact_threshold.return_value = 10000
            mock_config.colors = {
                "green": "\033[32m",
                "yellow": "\033[33m",
                "cyan": "\033[36m",
                "dim": "\033[2m",
                "reset": "\033[0m"
            }
            mock_context.message_history.estimate_context = MagicMock()
            mock_context.message_history.compact_memory = MagicMock(
                side_effect=Exception("Compaction failed")
            )

            result = compact_command.execute([])
            # Should not raise, should handle exception gracefully
            assert result.should_quit is False

    def test_execute_prune_all_with_results(self, compact_command, mock_context):
        """Test prune all when tool results exist."""
        mock_context.message_history._stats["count"] = 5
        mock_context.message_history._stats["tokens"] = 1000
        mock_context.message_history._stats["bytes"] = 50000
        mock_context.message_history.prune_all_tool_results = MagicMock(return_value=5)

        with patch('aicoder.core.commands.compact.Config') as mock_config:
            mock_config.colors = {
                "green": "\033[32m",
                "yellow": "\033[33m",
                "cyan": "\033[36m",
                "dim": "\033[2m",
                "reset": "\033[0m"
            }

            result = compact_command.execute(["prune", "all"])
            assert result.should_quit is False

    def test_execute_prune_count_with_results(self, compact_command, mock_context):
        """Test prune with count when tool results exist."""
        mock_context.message_history._stats["count"] = 10
        mock_context.message_history._stats["tokens"] = 2000
        mock_context.message_history._stats["bytes"] = 100000
        mock_context.message_history.prune_oldest_tool_results = MagicMock(return_value=3)

        with patch('aicoder.core.commands.compact.Config') as mock_config:
            mock_config.colors = {
                "green": "\033[32m",
                "yellow": "\033[33m",
                "cyan": "\033[36m",
                "dim": "\033[2m",
                "reset": "\033[0m"
            }

            result = compact_command.execute(["prune", "5"])
            assert result.should_quit is False
