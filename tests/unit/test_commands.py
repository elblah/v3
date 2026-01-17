"""Unit tests for command implementations."""

import pytest
from unittest.mock import MagicMock, patch
import os

import sys
sys.path.insert(0, '/home/blah/storage/ai-worktree-storage/feat_test_coverage__20260117_062928')

from aicoder.core.commands.base import CommandContext, CommandResult
from aicoder.core.commands.debug import DebugCommand
from aicoder.core.commands.detail import DetailCommand
from aicoder.core.commands.yolo import YoloCommand
from aicoder.core.commands.sandbox import SandboxCommand
from aicoder.core.commands.edit import EditCommand
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
    return CommandContext(
        message_history=MockMessageHistory(),
        input_handler=MockInputHandler(),
        stats=MockStats()
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


class TestEditCommand:
    """Test EditCommand."""

    def test_edit_command_name(self, mock_context):
        """Test edit command has correct name."""
        cmd = EditCommand(mock_context)
        assert cmd.get_name() == "edit"

    def test_edit_command_description(self, mock_context):
        """Test edit command has correct description."""
        cmd = EditCommand(mock_context)
        assert "edit" in cmd.get_description().lower()


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
