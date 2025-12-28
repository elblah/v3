"""
Test InputHandler class - Synchronous version
Tests for
"""

import os
import tempfile
from unittest.mock import patch, MagicMock
from aicoder.core.input_handler import InputHandler
from aicoder.core.stats import Stats


def test_input_handler_initialization():
    """Test InputHandler initialization"""
    handler = InputHandler()

    assert handler.history == []
    assert handler.history_index == -1
    assert handler.stats is None
    assert handler.message_history is None
    assert handler.context_bar is None


def test_set_stats_context():
    """Test setting stats context"""
    handler = InputHandler()
    stats = Stats()

    handler.set_stats_context(stats)
    assert handler.stats == stats


def test_set_message_history():
    """Test setting message history"""
    handler = InputHandler()
    mock_history = MagicMock()

    handler.set_message_history(mock_history)
    assert handler.message_history == mock_history


def test_add_to_history():
    """Test adding commands to history"""
    handler = InputHandler()

    # Add command
    handler.add_to_history("test command")
    assert handler.history == ["test command"]
    assert handler.history_index == 0

    # Add another command
    handler.add_to_history("another command")
    assert handler.history == ["another command", "test command"]

    # Add duplicate command (should move to front)
    handler.add_to_history("test command")
    assert handler.history == ["test command", "another command"]

    # Test empty command
    handler.add_to_history("")
    assert len(handler.history) == 2  # Should not add empty


def test_get_history():
    """Test getting history copy"""
    handler = InputHandler()
    handler.history = ["cmd1", "cmd2", "cmd3"]

    history = handler.get_history()
    assert history == ["cmd1", "cmd2", "cmd3"]

    # Should be a copy, not reference
    history.append("cmd4")
    assert handler.history == ["cmd1", "cmd2", "cmd3"]


def test_history_size_limit():
    """Test history size limit"""
    handler = InputHandler()

    # Add more than 100 commands
    for i in range(150):
        handler.add_to_history(f"command_{i}")

    # Should only keep last 100
    assert len(handler.history) == 100
    assert handler.history[0] == "command_149"  # Last added
    assert handler.history[-1] == "command_50"  # 100th from end


def test_menu_handlers():
    """Test menu handler methods"""
    handler = InputHandler()

    # Test toggle detail
    with patch("aicoder.core.input_handler.Config.detail_mode", return_value=False):
        with patch("aicoder.core.input_handler.Config.set_detail_mode") as mock_set:
            handler._handle_toggle_detail()
            mock_set.assert_called_once_with(True)

    # Test toggle YOLO
    with patch("aicoder.core.input_handler.Config.yolo_mode", return_value=False):
        with patch("aicoder.core.input_handler.Config.set_yolo_mode") as mock_set:
            handler._handle_toggle_yolo()
            mock_set.assert_called_once_with(True)

    # Test toggle sandbox
    with patch(
        "aicoder.core.input_handler.Config.sandbox_disabled", return_value=False
    ):
        with patch(
            "aicoder.core.input_handler.Config.set_sandbox_disabled"
        ) as mock_set:
            handler._handle_toggle_fs_sandbox()
            mock_set.assert_called_once_with(True)


def test_process_menu_selection():
    """Test menu selection processing"""
    handler = InputHandler()

    # Mock handler methods
    handler._handle_toggle_detail = MagicMock()
    handler._handle_unknown_selection = MagicMock()

    # Test 'd' selection
    handler._process_menu_selection("d")
    handler._handle_toggle_detail.assert_called_once()

    # Test unknown selection
    handler._process_menu_selection("x")
    handler._handle_unknown_selection.assert_called_once()


def test_handle_show_stats():
    """Test show stats handler"""
    handler = InputHandler()
    mock_stats = MagicMock()
    handler.stats = mock_stats

    handler._handle_show_stats()
    mock_stats.print_stats.assert_called_once()

    # Test with no stats
    handler.stats = None
    handler._handle_show_stats()  # Should not crash


def test_handle_prune_context():
    """Test prune context handler"""
    handler = InputHandler()

    # Test with no message history
    handler._handle_prune_context()  # Should not crash

    # Test with message history
    mock_history = MagicMock()
    handler.message_history = mock_history

    handler._handle_prune_context()


def test_handle_save_session():
    """Test save session handler"""
    handler = InputHandler()

    # Test with no message history
    handler._handle_save_session()  # Should not crash

    # Test with message history
    mock_history = MagicMock()
    mock_history.get_messages.return_value = [{"role": "user", "content": "test"}]
    handler.message_history = mock_history

    with patch("aicoder.core.input_handler.write_file") as mock_write:
        handler._handle_save_session()
        mock_write.assert_called_once()


def test_close():
    """Test close method"""
    handler = InputHandler()

    # Should not crash
    handler.close()


def test_prompt():
    """Test prompt method"""
    handler = InputHandler()

    with patch("builtins.input", return_value="test input"):
        result = handler.prompt("Enter something: ")
        assert result == "test input"

    with patch("builtins.input", side_effect=EOFError):
        result = handler.prompt("Enter something: ")
        assert result == ""


def test_show_tmux_popup_menu_timeout():
    """Test tmux popup menu with timeout"""
    handler = InputHandler()

    # Mock tmux command to fail/not create temp file
    with patch("aicoder.core.input_handler.execute_command_sync") as mock_execute:
        mock_execute.return_value = MagicMock(success=True, stdout="", stderr="")

        handler.show_tmux_popup_menu()  # Should timeout gracefully


def test_show_tmux_popup_menu_with_selection():
    """Test tmux popup menu with selection"""
    handler = InputHandler()
    handler._handle_toggle_detail = MagicMock()

    # Create a real temp file for testing
    with tempfile.NamedTemporaryFile(mode="w", delete=False) as f:
        temp_file = f.name
        f.write("d")

    try:
        with patch("aicoder.core.input_handler.create_temp_file") as mock_create:
            with patch("aicoder.core.input_handler.delete_file") as mock_delete:
                mock_create.return_value = temp_file

                handler.show_tmux_popup_menu()

                # Should have called toggle detail
                handler._handle_toggle_detail.assert_called_once()
                mock_delete.assert_called()
    finally:
        # Clean up
        try:
            os.unlink(temp_file)
        except:
            pass


def test_get_user_input_interactive():
    """Test getting user input in interactive mode"""
    handler = InputHandler()

    with patch("sys.stdin.isatty", return_value=True):
        with patch("builtins.input", return_value="user input"):
            result = handler.get_user_input()
            assert result == "user input"


def test_get_user_input_non_interactive():
    """Test getting user input in non-interactive mode"""
    handler = InputHandler()

    with patch("sys.stdin.isatty", return_value=False):
        with patch("sys.stdin.read", return_value="piped input\n"):
            result = handler.get_user_input()
            assert result == "piped input"


def test_get_user_input_eof():
    """Test handling EOF in get_user_input"""
    handler = InputHandler()

    with patch("sys.stdin.isatty", return_value=True):
        with patch("builtins.input", side_effect=EOFError):
            result = handler.get_user_input()
            assert result == ""


def test_set_prompt():
    """Test setting readline prompt"""
    handler = InputHandler()

    # Should not crash
    handler.set_prompt("test> ")


def test_write():
    """Test writing to readline"""
    handler = InputHandler()

    # Should not crash
    handler.write("test output")


def test_tmux_integration():
    """Test tmux integration methods"""
    handler = InputHandler()

    # Test in tmux check
    with patch("aicoder.core.input_handler.Config.in_tmux", return_value=True):
        # Should not crash when in tmux
        assert True


def test_menu_integration():
    """Test menu system integration"""
    handler = InputHandler()

    # Test creating tmux menu
    with patch("aicoder.core.input_handler.Config.in_tmux", return_value=True):
        with patch("aicoder.core.input_handler.execute_command_sync") as mock_execute:
            mock_execute.return_value = MagicMock(success=True, stdout="", stderr="")

            # Should not crash when creating menu
            result = handler.show_tmux_popup_menu()
            assert result is None


def test_error_handling():
    """Test error handling in various methods"""
    handler = InputHandler()

    # Test prompt with keyboard interrupt
    with patch("builtins.input", side_effect=KeyboardInterrupt):
        result = handler.prompt("test")
        assert result == ""

    # Test save session with error
    handler.message_history = MagicMock()
    handler.message_history.get_messages.side_effect = Exception("Test error")

    # Should not crash
    handler._handle_save_session()


def test_context_bar_integration():
    """Test context bar integration"""
    handler = InputHandler()
    mock_context_bar = MagicMock()
    handler.context_bar = mock_context_bar

    # Test methods that use context bar
    handler._handle_show_stats()
    handler._handle_prune_context()

    # Should not crash even with context bar present
