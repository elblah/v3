"""
Tests for input_handler module
"""

import pytest
from unittest.mock import MagicMock, patch, call
from aicoder.core.input_handler import InputHandler
from aicoder.core.stats import Stats


class TestInputHandlerInit:
    """Test InputHandler initialization"""

    def test_init_defaults(self):
        """Test default initialization"""
        handler = InputHandler()

        assert handler.history == []
        assert handler.history_index == -1
        assert handler.context_bar is None
        assert handler.stats is None
        assert handler.message_history is None
        assert len(handler.completers) == 0

    def test_init_with_context(self):
        """Test initialization with context"""
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


class TestGetUserInput:
    """Test get_user_input method"""

    def test_non_interactive_input(self):
        """Test getting input in non-interactive mode"""
        handler = InputHandler()
        handler.is_interactive = False

        with patch('aicoder.core.input_handler.sys.stdin.readline', return_value="piped input\n"):
            result = handler.get_user_input()
            assert result == "piped input\n"

    def test_interactive_input(self):
        """Test getting input in interactive mode"""
        handler = InputHandler()
        handler.is_interactive = True

        with patch("builtins.input", return_value="user input"):
            result = handler.get_user_input()
            assert result == "user input"

    def test_interactive_input_strips(self):
        """Test that input is stripped"""
        handler = InputHandler()
        handler.is_interactive = True

        with patch("builtins.input", return_value="  user input  "):
            result = handler.get_user_input()
            assert result == "user input"

    def test_keyboard_interrupt(self):
        """Test KeyboardInterrupt handling"""
        handler = InputHandler()
        handler.is_interactive = True

        with patch("builtins.input", side_effect=KeyboardInterrupt):
            with pytest.raises(KeyboardInterrupt):
                handler.get_user_input()

    def test_eof_error(self):
        """Test EOFError handling"""
        handler = InputHandler()
        handler.is_interactive = True

        with patch("builtins.input", side_effect=EOFError):
            with pytest.raises(EOFError):
                handler.get_user_input()

    def test_with_context_bar(self):
        """Test that context bar is printed"""
        mock_stats = MagicMock()
        mock_history = MagicMock()
        mock_context_bar = MagicMock()

        handler = InputHandler(
            context_bar=mock_context_bar,
            stats=mock_stats,
            message_history=mock_history,
        )
        handler.is_interactive = True

        with patch("builtins.input", return_value="test"):
            result = handler.get_user_input()

            mock_context_bar.print_context_bar_for_user.assert_called_once_with(
                mock_stats, mock_history
            )
            assert result == "test"


class TestRegisterCompleter:
    """Test completer registration"""

    def test_register_completer(self):
        """Test registering a completer"""
        handler = InputHandler()

        def my_completer(text, state):
            return None

        handler.register_completer(my_completer)

        assert len(handler.completers) == 1
        assert handler.completers[0] == my_completer

    def test_register_multiple_completers(self):
        """Test registering multiple completers"""
        handler = InputHandler()

        def completer1(text, state):
            return None

        def completer2(text, state):
            return None

        handler.register_completer(completer1)
        handler.register_completer(completer2)

        assert len(handler.completers) == 2


class TestCompleter:
    """Test tab completion"""

    def test_completer_empty_text(self):
        """Test completer with empty text returns None (no completion for empty)"""
        handler = InputHandler()

        # Empty text doesn't match commands (only text starting with / is completed)
        result = handler._completer("", 0)
        assert result is None

    def test_completer_slash_command(self):
        """Test completer with slash command"""
        handler = InputHandler()

        # Should complete /help
        result = handler._completer("/h", 0)
        assert result == "/help"

    def test_completer_unknown_command(self):
        """Test completer with unknown command"""
        handler = InputHandler()

        result = handler._completer("/xyz", 0)
        assert result is None

    def test_completer_quit_command(self):
        """Test completer with quit command"""
        handler = InputHandler()

        result = handler._completer("/qu", 0)
        assert result == "/quit"

    def test_completer_aliases(self):
        """Test completer with command aliases"""
        handler = InputHandler()

        # Test /h should return /help (it matches /help)
        result = handler._completer("/h", 0)
        assert result == "/help"

    def test_completer_all_commands(self):
        """Test that all commands are available"""
        handler = InputHandler()

        commands = [
            "/help", "/h", "/?",
            "/quit", "/stats", "/save", "/s", "/load", "/l",
            "/memory", "/new", "/n", "/yolo", "/y", "/detail", "/d",
            "/compact", "/c", "/sandbox-fs", "/sfs", "/edit", "/e",
            "/retry"
        ]

        for cmd in commands:
            result = handler._completer(cmd, 0)
            assert result is not None, f"Command {cmd} should complete to itself"

    def test_completer_state_iteration(self):
        """Test completer state iteration"""
        handler = InputHandler()

        # Get first match
        result0 = handler._completer("/h", 0)
        assert result0 == "/help"

        # Get second match (should be /h itself since it matches)
        result1 = handler._completer("/h", 1)
        assert result1 == "/h"

        # No more matches
        result2 = handler._completer("/h", 2)
        assert result2 is None

    def test_completer_with_registered_plugin_completer(self):
        """Test completer with registered plugin completer"""
        handler = InputHandler()

        def my_plugin_completer(text, state):
            if text == "@":
                if state == 0:
                    return "@snippet1"
                elif state == 1:
                    return "@snippet2"
            return None

        handler.register_completer(my_plugin_completer)

        # Should get plugin completions when text starts with @
        result0 = handler._completer("@", 0)
        assert result0 == "@snippet1"

        result1 = handler._completer("@", 1)
        assert result1 == "@snippet2"

        result2 = handler._completer("@", 2)
        assert result2 is None


class TestSetupSignalHandlers:
    """Test signal handler setup"""

    def test_setup_signal_handlers(self):
        """Test that signal handlers are set up"""
        handler = InputHandler()

        with patch("signal.signal") as mock_signal:
            handler.setup_signal_handlers()

            # Should have called signal.signal
            mock_signal.assert_called_once()

            # Get the handler that was registered
            sig, handler_fn = mock_signal.call_args[0]

            # Should be SIGINT
            import signal as sig_module
            assert sig == sig_module.SIGINT


class TestClose:
    """Test close method"""

    def test_close_does_not_raise(self):
        """Test that close doesn't raise"""
        handler = InputHandler()

        # Should not raise
        handler.close()


class TestHistory:
    """Test history handling"""

    def test_history_initially_empty(self):
        """Test history starts empty"""
        handler = InputHandler()
        assert handler.history == []
        assert handler.history_index == -1

    def test_history_index_initially_negative(self):
        """Test history index starts at -1"""
        handler = InputHandler()
        assert handler.history_index == -1


class TestCompletionsList:
    """Test completion matches list"""

    def test_completion_matches_initialized(self):
        """Test completion_matches is initialized"""
        handler = InputHandler()
        # Should have completion_matches attribute after first completer call
        handler._completer("/test", 0)
        assert hasattr(handler, 'completion_matches')


class TestIsInteractive:
    """Test is_interactive property"""

    def test_is_interactive_default(self):
        """Test is_interactive defaults to stdin.isatty()"""
        handler = InputHandler()
        # This will be True if running in a tty, False otherwise
        import sys
        assert handler.is_interactive == sys.stdin.isatty()
