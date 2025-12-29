"""
Test InputHandler class - Synchronous version
Tests match actual API implementation
"""

import pytest
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


def test_input_handler_with_context():
    """Test InputHandler initialization with context"""
    mock_stats = MagicMock()
    mock_history = MagicMock()
    mock_context_bar = MagicMock()

    handler = InputHandler(
        context_bar=mock_context_bar,
        stats=mock_stats,
        message_history=mock_history,
    )

    assert handler.stats == mock_stats
    assert handler.message_history == mock_history
    assert handler.context_bar == mock_context_bar


def test_get_user_input_interactive():
    """Test getting user input in interactive mode"""
    handler = InputHandler()

    # Simulate TTY mode
    original_isatty = handler.is_interactive
    handler.is_interactive = True

    with patch("builtins.input", return_value="user input"):
        result = handler.get_user_input()
        assert result == "user input"

    handler.is_interactive = original_isatty


def test_get_user_input_non_interactive():
    """Test getting user input in non-interactive mode"""
    handler = InputHandler()

    # Simulate non-TTY mode
    original_isatty = handler.is_interactive
    handler.is_interactive = False

    with patch("aicoder.core.input_handler.sys.stdin.readline", return_value="piped input\n"):
        result = handler.get_user_input()
        # The method returns raw readline output
        assert result == "piped input\n"

    handler.is_interactive = original_isatty


def test_get_user_input_eof():
    """Test handling EOF in get_user input"""
    handler = InputHandler()

    # Simulate TTY mode
    original_isatty = handler.is_interactive
    handler.is_interactive = True

    with patch("builtins.input", side_effect=EOFError):
        # Should re-raise EOFError
        with pytest.raises(EOFError):
            handler.get_user_input()

    handler.is_interactive = original_isatty


def test_get_user_input_keyboard_interrupt():
    """Test handling KeyboardInterrupt in get_user_input"""
    handler = InputHandler()

    # Simulate TTY mode
    original_isatty = handler.is_interactive
    handler.is_interactive = True

    with patch("builtins.input", side_effect=KeyboardInterrupt):
        # Should re-raise KeyboardInterrupt
        with pytest.raises(KeyboardInterrupt):
            handler.get_user_input()

    handler.is_interactive = original_isatty


def test_get_user_input_with_context_bar():
    """Test get_user_input shows context bar"""
    mock_stats = MagicMock()
    mock_history = MagicMock()
    mock_context_bar = MagicMock()

    handler = InputHandler(
        context_bar=mock_context_bar,
        stats=mock_stats,
        message_history=mock_history,
    )

    # Simulate TTY mode
    original_isatty = handler.is_interactive
    handler.is_interactive = True

    with patch("builtins.input", return_value="test"):
        result = handler.get_user_input()

        # Context bar should have been printed
        mock_context_bar.print_context_bar_for_user.assert_called_once_with(
            mock_stats, mock_history
        )
        assert result == "test"

    handler.is_interactive = original_isatty


def test_close():
    """Test close method"""
    handler = InputHandler()

    # Should not crash
    handler.close()


def test_setup_signal_handlers():
    """Test setup_signal_handlers method"""
    handler = InputHandler()

    with patch("signal.signal") as mock_signal:
        handler.setup_signal_handlers()

        # Should have set up signal handler
        mock_signal.assert_called()


def test_completer():
    """Test tab completer"""
    handler = InputHandler()

    # Test completion for command starting with /
    result1 = handler._completer("/h", 0)
    assert result1 == "/help"

    result2 = handler._completer("/h", 1)
    # Second match is the original text
    assert result2 == "/h"

    result3 = handler._completer("/h", 2)
    # No more matches
    assert result3 is None

    # Test completion for partial command
    result = handler._completer("/qu", 0)
    assert result == "/quit"

    # Test no matches
    result = handler._completer("/xyz", 0)
    assert result is None
