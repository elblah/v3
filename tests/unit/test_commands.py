"""Unit tests for command implementations."""

import pytest
from unittest.mock import MagicMock, patch, mock_open
import os
import tempfile
import json

import sys
sys.path.insert(0, '/home/blah/storage/ai-worktree-storage/feat_test_coverage__20260117_062928')

from aicoder.core.commands.base import CommandContext, CommandResult
from aicoder.core.commands.debug import DebugCommand
from aicoder.core.commands.detail import DetailCommand
from aicoder.core.commands.yolo import YoloCommand
from aicoder.core.commands.sandbox import SandboxCommand
from aicoder.core.commands.edit import EditCommand
from aicoder.core.commands.memory import MemoryCommand
from aicoder.core.commands.help import HelpCommand
from aicoder.core.commands.save import SaveCommand
from aicoder.core.commands.load import LoadCommand
from aicoder.core.commands.stats import StatsCommand


class MockMessageHistory:
    """Mock MessageHistory for testing."""
    def __init__(self):
        self._messages = []

    def get_messages(self):
        return self._messages

    def set_messages(self, messages):
        self._messages = messages


class MockInputHandler:
    """Mock InputHandler for testing."""
    pass


class MockStats:
    """Mock Stats for testing."""
    def __init__(self):
        self.current_prompt_size = 0

    def print_stats(self):
        pass


@pytest.fixture
def mock_context():
    """Create a mock CommandContext."""
    mock_command_handler = MagicMock()
    mock_plugin_system = MagicMock()
    mock_command_handler.plugin_system = mock_plugin_system
    
    return CommandContext(
        message_history=MockMessageHistory(),
        input_handler=MockInputHandler(),
        stats=MockStats(),
        command_handler=mock_command_handler
    )


class TestDebugCommand:
    """Test DebugCommand."""

    def test_debug_command_name(self, mock_context):
        """Test debug command has correct name."""
        cmd = DebugCommand(mock_context)
        assert cmd.get_name() == "debug"

    def test_debug_command_description(self, mock_context):
        """Test debug command has correct description."""
        cmd = DebugCommand(mock_context)
        assert "debug" in cmd.get_description().lower()

    def test_debug_command_aliases(self, mock_context):
        """Test debug command has aliases."""
        cmd = DebugCommand(mock_context)
        aliases = cmd.get_aliases()
        assert "dbg" in aliases

    def test_debug_show_status(self, mock_context):
        """Test debug status display."""
        with patch('aicoder.core.commands.debug.Config') as mock_config:
            mock_config.debug.return_value = False
            mock_config.colors = {
                "green": "\033[32m",
                "yellow": "\033[33m",
                "cyan": "\033[36m",
                "dim": "\033[2m",
                "reset": "\033[0m"
            }
            cmd = DebugCommand(mock_context)
            result = cmd.execute([])
            assert result.should_quit is False
            assert result.run_api_call is False

    def test_debug_enable(self, mock_context):
        """Test enabling debug mode."""
        with patch('aicoder.core.commands.debug.Config') as mock_config:
            mock_config.debug.return_value = False
            mock_config.colors = {
                "green": "\033[32m",
                "yellow": "\033[33m",
                "cyan": "\033[36m",
                "dim": "\033[2m",
                "reset": "\033[0m"
            }
            mock_config.set_debug = MagicMock()
            cmd = DebugCommand(mock_context)
            result = cmd.execute(["on"])
            assert result.should_quit is False
            mock_config.set_debug.assert_called_with(True)

    def test_debug_disable(self, mock_context):
        """Test disabling debug mode."""
        with patch('aicoder.core.commands.debug.Config') as mock_config:
            mock_config.debug.return_value = True
            mock_config.colors = {
                "green": "\033[32m",
                "yellow": "\033[33m",
                "cyan": "\033[36m",
                "dim": "\033[2m",
                "reset": "\033[0m"
            }
            mock_config.set_debug = MagicMock()
            cmd = DebugCommand(mock_context)
            result = cmd.execute(["off"])
            assert result.should_quit is False
            mock_config.set_debug.assert_called_with(False)


class TestDetailCommand:
    """Test DetailCommand."""

    def test_detail_command_name(self, mock_context):
        """Test detail command has correct name."""
        cmd = DetailCommand(mock_context)
        assert cmd.get_name() == "detail"

    def test_detail_command_description(self, mock_context):
        """Test detail command has correct description."""
        cmd = DetailCommand(mock_context)
        assert "detail" in cmd.get_description().lower()

    def test_detail_command_aliases(self, mock_context):
        """Test detail command has aliases."""
        cmd = DetailCommand(mock_context)
        aliases = cmd.get_aliases()
        assert "d" in aliases

    def test_detail_status(self, mock_context):
        """Test detail status display."""
        with patch('aicoder.core.commands.detail.Config') as mock_config:
            mock_config.detail_mode.return_value = False
            mock_config.colors = {
                "green": "\033[32m",
                "yellow": "\033[33m",
                "cyan": "\033[36m",
                "dim": "\033[2m",
                "reset": "\033[0m"
            }
            cmd = DetailCommand(mock_context)
            result = cmd.execute([])
            assert result.should_quit is False

    def test_detail_toggle_on(self, mock_context):
        """Test turning detail mode on."""
        with patch('aicoder.core.commands.detail.Config') as mock_config:
            mock_config.detail_mode.return_value = False
            mock_config.colors = {
                "green": "\033[32m",
                "yellow": "\033[33m",
                "cyan": "\033[36m",
                "dim": "\033[2m",
                "reset": "\033[0m"
            }
            mock_config.set_detail_mode = MagicMock()
            cmd = DetailCommand(mock_context)
            result = cmd.execute(["on"])
            assert result.should_quit is False
            mock_config.set_detail_mode.assert_called_with(True)


class TestYoloCommand:
    """Test YoloCommand."""

    def test_yolo_command_name(self, mock_context):
        """Test yolo command has correct name."""
        cmd = YoloCommand(mock_context)
        assert cmd.get_name() == "yolo"

    def test_yolo_command_description(self, mock_context):
        """Test yolo command has correct description."""
        cmd = YoloCommand(mock_context)
        assert "yolo" in cmd.get_description().lower()

    def test_yolo_command_aliases(self, mock_context):
        """Test yolo command has aliases."""
        cmd = YoloCommand(mock_context)
        aliases = cmd.get_aliases()
        assert "y" in aliases

    def test_yolo_toggle_on(self, mock_context):
        """Test turning yolo mode on."""
        with patch('aicoder.core.commands.yolo.Config') as mock_config:
            mock_config.yolo_mode.return_value = False
            mock_config.colors = {
                "green": "\033[32m",
                "yellow": "\033[33m",
                "red": "\033[31m",
                "cyan": "\033[36m",
                "dim": "\033[2m",
                "reset": "\033[0m",
                "bold": "\033[1m"
            }
            mock_config.set_yolo_mode = MagicMock()
            cmd = YoloCommand(mock_context)
            result = cmd.execute(["on"])
            assert result.should_quit is False
            mock_config.set_yolo_mode.assert_called_with(True)

    def test_yolo_status(self, mock_context):
        """Test yolo status display."""
        with patch('aicoder.core.commands.yolo.Config') as mock_config:
            mock_config.yolo_mode.return_value = True
            mock_config.colors = {
                "green": "\033[32m",
                "yellow": "\033[33m",
                "red": "\033[31m",
                "cyan": "\033[36m",
                "dim": "\033[2m",
                "reset": "\033[0m",
                "bold": "\033[1m"
            }
            cmd = YoloCommand(mock_context)
            result = cmd.execute([])
            assert result.should_quit is False


class TestSandboxCommand:
    """Test SandboxCommand."""

    def test_sandbox_command_name(self, mock_context):
        """Test sandbox command has correct name."""
        cmd = SandboxCommand(mock_context)
        assert cmd.get_name() == "sandbox-fs"

    def test_sandbox_command_description(self, mock_context):
        """Test sandbox command has correct description."""
        cmd = SandboxCommand(mock_context)
        assert "sandbox" in cmd.get_description().lower()

    def test_sandbox_command_aliases(self, mock_context):
        """Test sandbox command has aliases."""
        cmd = SandboxCommand(mock_context)
        aliases = cmd.get_aliases()
        assert "sfs" in aliases

    def test_sandbox_status(self, mock_context):
        """Test sandbox status display."""
        with patch('aicoder.core.commands.sandbox.Config') as mock_config:
            mock_config.sandbox_disabled.return_value = False
            mock_config.colors = {
                "green": "\033[32m",
                "yellow": "\033[33m",
                "red": "\033[31m",
                "cyan": "\033[36m",
                "dim": "\033[2m",
                "reset": "\033[0m",
                "bold": "\033[1m"
            }
            with patch('aicoder.core.commands.sandbox.os.getcwd', return_value="/tmp"):
                cmd = SandboxCommand(mock_context)
                result = cmd.execute([])
                assert result.should_quit is False

    def test_sandbox_off(self, mock_context):
        """Test turning sandbox off."""
        with patch('aicoder.core.commands.sandbox.Config') as mock_config:
            mock_config.sandbox_disabled.return_value = False
            mock_config.colors = {
                "green": "\033[32m",
                "yellow": "\033[33m",
                "red": "\033[31m",
                "cyan": "\033[36m",
                "dim": "\033[2m",
                "reset": "\033[0m",
                "bold": "\033[1m"
            }
            mock_config.set_sandbox_disabled = MagicMock()
            cmd = SandboxCommand(mock_context)
            result = cmd.execute(["off"])
            assert result.should_quit is False
            mock_config.set_sandbox_disabled.assert_called_with(True)


class TestStatsCommand:
    """Test StatsCommand."""

    def test_stats_command_name(self, mock_context):
        """Test stats command has correct name."""
        cmd = StatsCommand(mock_context)
        assert cmd.get_name() == "stats"

    def test_stats_command_description(self, mock_context):
        """Test stats command has correct description."""
        cmd = StatsCommand(mock_context)
        assert "statistics" in cmd.get_description().lower()

    def test_stats_execute(self, mock_context):
        """Test stats command execution."""
        with patch('aicoder.core.commands.stats.Config') as mock_config:
            mock_config.colors = {
                "green": "\033[32m",
                "yellow": "\033[33m",
                "cyan": "\033[36m",
                "dim": "\033[2m",
                "reset": "\033[0m"
            }
            mock_context.stats.current_prompt_size = 0
            mock_context.stats.print_stats = MagicMock()
            cmd = StatsCommand(mock_context)
            result = cmd.execute([])
            assert result.should_quit is False
            mock_context.stats.print_stats.assert_called_once()


class TestHelpCommand:
    """Test HelpCommand."""

    def test_help_command_name(self, mock_context):
        """Test help command has correct name."""
        cmd = HelpCommand(mock_context)
        assert cmd.get_name() == "help"

    def test_help_command_description(self, mock_context):
        """Test help command has correct description."""
        cmd = HelpCommand(mock_context)
        assert "help" in cmd.get_description().lower()

    def test_help_command_aliases(self, mock_context):
        """Test help command has aliases."""
        cmd = HelpCommand(mock_context)
        aliases = cmd.get_aliases()
        assert "?" in aliases or "h" in aliases

    def test_help_execute_no_handler(self, mock_context):
        """Test help command when command handler is not available."""
        mock_context.command_handler = None
        cmd = HelpCommand(mock_context)
        result = cmd.execute([])
        assert result.should_quit is False
        assert result.run_api_call is False

    def test_help_execute_with_commands(self, mock_context):
        """Test help command execution with commands available."""
        # Create a mock command handler
        mock_handler = MagicMock()
        mock_handler.get_all_commands.return_value = {
            "debug": DebugCommand(mock_context),
            "help": HelpCommand(mock_context)
        }
        mock_context.command_handler = mock_handler

        with patch('aicoder.core.commands.help.Config') as mock_config:
            mock_config.colors = {
                "green": "\033[32m",
                "yellow": "\033[33m",
                "cyan": "\033[36m",
                "dim": "\033[2m",
                "reset": "\033[0m",
                "bold": "\033[1m"
            }
            mock_config.in_tmux.return_value = True
            cmd = HelpCommand(mock_context)
            result = cmd.execute([])
            assert result.should_quit is False
            assert result.run_api_call is False


class TestMemoryCommand:
    """Test MemoryCommand."""

    def test_memory_command_name(self, mock_context):
        """Test memory command has correct name."""
        cmd = MemoryCommand(mock_context)
        assert cmd.get_name() == "memory"

    def test_memory_command_description(self, mock_context):
        """Test memory command has correct description."""
        cmd = MemoryCommand(mock_context)
        assert "memory" in cmd.get_description().lower()

    def test_memory_command_aliases(self, mock_context):
        """Test memory command has aliases."""
        cmd = MemoryCommand(mock_context)
        aliases = cmd.get_aliases()
        assert "m" in aliases

    def test_memory_execute_no_tmux(self, mock_context):
        """Test memory command fails gracefully outside tmux."""
        with patch('aicoder.core.commands.memory.Config') as mock_config:
            mock_config.in_tmux.return_value = False
            cmd = MemoryCommand(mock_context)
            result = cmd.execute([])
            assert result.should_quit is False
            assert result.run_api_call is False

    def test_memory_execute_with_messages(self, mock_context):
        """Test memory command with messages in history."""
        # Setup mock messages
        mock_context.message_history._messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"}
        ]

        with patch('aicoder.core.commands.memory.Config') as mock_config:
            mock_config.in_tmux.return_value = True
            mock_config.colors = {
                "green": "\033[32m",
                "yellow": "\033[33m",
                "cyan": "\033[36m",
                "dim": "\033[2m",
                "reset": "\033[0m"
            }
            with patch('aicoder.core.commands.memory.create_temp_file', return_value='/tmp/test.json'):
                with patch('builtins.open', mock_open(read_data='[{"role": "user", "content": "Updated"}]')):
                    with patch('aicoder.core.commands.memory.os.path.exists', return_value=True):
                        with patch('aicoder.core.commands.memory.os.unlink'):
                            with patch('aicoder.core.commands.memory.os.system'):
                                cmd = MemoryCommand(mock_context)
                                result = cmd.execute([])
                                assert result.should_quit is False
                                assert result.run_api_call is False


class TestEditCommand:
    """Test EditCommand - extended tests."""

    def test_edit_command_name(self, mock_context):
        """Test edit command has correct name."""
        cmd = EditCommand(mock_context)
        assert cmd.get_name() == "edit"

    def test_edit_command_description(self, mock_context):
        """Test edit command has correct description."""
        cmd = EditCommand(mock_context)
        assert "edit" in cmd.get_description().lower()

    def test_edit_command_aliases(self, mock_context):
        """Test edit command has aliases."""
        cmd = EditCommand(mock_context)
        aliases = cmd.get_aliases()
        assert "e" in aliases

    def test_edit_execute_no_tmux(self, mock_context):
        """Test edit command fails gracefully outside tmux."""
        with patch.dict(os.environ, {}, clear=False):
            with patch('aicoder.core.commands.edit.Config') as mock_config:
                mock_config.colors = {
                    "green": "\033[32m",
                    "yellow": "\033[33m",
                    "cyan": "\033[36m",
                    "dim": "\033[2m",
                    "reset": "\033[0m"
                }
                # Remove TMUX env var
                if 'TMUX' in os.environ:
                    del os.environ['TMUX']

                cmd = EditCommand(mock_context)
                result = cmd.execute([])
                assert result.should_quit is False
                assert result.run_api_call is False

    def test_edit_execute_empty_content(self, mock_context):
        """Test edit command with empty content returns no API call."""
        with patch.dict(os.environ, {"TMUX": "1", "EDITOR": "nano"}, clear=False):
            with patch('aicoder.core.commands.edit.Config') as mock_config:
                mock_config.colors = {
                    "green": "\033[32m",
                    "yellow": "\033[33m",
                    "cyan": "\033[36m",
                    "dim": "\033[2m",
                    "reset": "\033[0m"
                }
                with patch('aicoder.core.commands.edit.create_temp_file', return_value='/tmp/test.md'):
                    with patch('builtins.open', mock_open(read_data='')):
                        with patch('subprocess.run'):
                            with patch('aicoder.core.commands.edit.os.remove'):
                                cmd = EditCommand(mock_context)
                                result = cmd.execute([])
                                assert result.should_quit is False
                                assert result.run_api_call is False


class TestSaveCommand:
    """Test SaveCommand."""

    def test_save_command_name(self, mock_context):
        """Test save command has correct name."""
        cmd = SaveCommand(mock_context)
        assert cmd.get_name() == "save"

    def test_save_command_description(self, mock_context):
        """Test save command has correct description."""
        cmd = SaveCommand(mock_context)
        assert "save" in cmd.get_description().lower()

    def test_save_command_aliases(self, mock_context):
        """Test save command has aliases."""
        cmd = SaveCommand(mock_context)
        aliases = cmd.get_aliases()
        assert "s" in aliases

    def test_save_execute_default_filename(self, mock_context):
        """Test save command with default filename."""
        mock_context.message_history._messages = [
            {"role": "user", "content": "Hello"}
        ]

        with patch('aicoder.core.commands.save.Config') as mock_config:
            mock_config.colors = {
                "green": "\033[32m",
                "yellow": "\033[33m",
                "cyan": "\033[36m",
                "dim": "\033[2m",
                "reset": "\033[0m"
            }
            with patch('aicoder.core.commands.save.write_file') as mock_write:
                cmd = SaveCommand(mock_context)
                result = cmd.execute([])
                assert result.should_quit is False
                assert result.run_api_call is False
                mock_write.assert_called_once()

    def test_save_execute_jsonl_format(self, mock_context):
        """Test save command with JSONL format."""
        mock_context.message_history._messages = [
            {"role": "user", "content": "Hello"}
        ]

        with patch('aicoder.core.commands.save.Config') as mock_config:
            mock_config.colors = {
                "green": "\033[32m",
                "yellow": "\033[33m",
                "cyan": "\033[36m",
                "dim": "\033[2m",
                "reset": "\033[0m"
            }
            with patch('aicoder.core.commands.save.write_jsonl') as mock_write:
                with patch('aicoder.core.commands.save.Path') as mock_path:
                    mock_path.return_value.suffix.lower.return_value = '.jsonl'
                    cmd = SaveCommand(mock_context)
                    result = cmd.execute(["session.jsonl"])
                    assert result.should_quit is False
                    assert result.run_api_call is False
                    mock_write.assert_called_once()


class TestLoadCommand:
    """Test LoadCommand."""

    def test_load_command_name(self, mock_context):
        """Test load command has correct name."""
        cmd = LoadCommand(mock_context)
        assert cmd.get_name() == "load"

    def test_load_command_description(self, mock_context):
        """Test load command has correct description."""
        cmd = LoadCommand(mock_context)
        assert "load" in cmd.get_description().lower()

    def test_load_command_aliases(self, mock_context):
        """Test load command has aliases."""
        cmd = LoadCommand(mock_context)
        aliases = cmd.get_aliases()
        assert "l" in aliases

    def test_load_execute_file_not_found(self, mock_context):
        """Test load command when file doesn't exist."""
        with patch('aicoder.core.commands.load.file_exists', return_value=False):
            cmd = LoadCommand(mock_context)
            result = cmd.execute(["nonexistent.json"])
            assert result.should_quit is False
            assert result.run_api_call is False

    def test_load_execute_json_format(self, mock_context):
        """Test load command with JSON format."""
        test_messages = [{"role": "user", "content": "Hello"}]

        with patch('aicoder.core.commands.load.file_exists', return_value=True):
            with patch('aicoder.core.commands.load.read_file', return_value=test_messages):
                with patch('aicoder.core.commands.load.Path') as mock_path:
                    mock_path.return_value.suffix.lower.return_value = '.json'
                    cmd = LoadCommand(mock_context)
                    result = cmd.execute(["session.json"])
                    assert result.should_quit is False
                    assert result.run_api_call is False

    def test_load_execute_jsonl_format(self, mock_context):
        """Test load command with JSONL format."""
        test_messages = [{"role": "user", "content": "Hello"}]

        with patch('aicoder.core.commands.load.file_exists', return_value=True):
            with patch('aicoder.core.commands.load.read_jsonl', return_value=test_messages):
                with patch('aicoder.core.commands.load.Path') as mock_path:
                    mock_path.return_value.suffix.lower.return_value = '.jsonl'
                    cmd = LoadCommand(mock_context)
                    result = cmd.execute(["session.jsonl"])
                    assert result.should_quit is False
                    assert result.run_api_call is False
