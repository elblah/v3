"""
Extended tests for AICoder class - covering more code paths
"""

import pytest
from unittest.mock import MagicMock, patch, Mock
from aicoder.core.aicoder import AICoder
from aicoder.core.message_history import MessageHistory
from aicoder.core.stats import Stats


class TestAICoderExtended:
    """Extended tests for AICoder class"""

    def test_add_user_input_basic(self):
        """Test adding basic user input"""
        app = AICoder()
        app.add_user_input("Hello, AI!")
        messages = app.message_history.get_messages()
        # Should have system prompt + user message
        assert len(messages) >= 1
        # Last message should be from user
        assert messages[-1]["role"] == "user"
        assert messages[-1]["content"] == "Hello, AI!"

    def test_add_user_input_with_plugin_transformation(self):
        """Test user input with plugin hook transformation"""
        app = AICoder()

        # Mock plugin system to return transformed input
        mock_plugin_system = MagicMock()
        mock_plugin_system.call_hooks_with_return.return_value = "Transformed: Hello!"

        app.plugin_system = mock_plugin_system

        app.add_user_input("Hello!")

        # Verify plugin hook was called
        mock_plugin_system.call_hooks_with_return.assert_called_once()

        messages = app.message_history.get_messages()
        # Content should be transformed
        assert messages[-1]["content"] == "Transformed: Hello!"

    def test_add_user_input_plugin_returns_none(self):
        """Test user input when plugin hook returns None"""
        app = AICoder()

        mock_plugin_system = MagicMock()
        mock_plugin_system.call_hooks_with_return.return_value = None

        app.plugin_system = mock_plugin_system

        app.add_user_input("Hello!")

        messages = app.message_history.get_messages()
        # Content should be original
        assert messages[-1]["content"] == "Hello!"

    def test_add_plugin_message(self):
        """Test adding message from plugins"""
        app = AICoder()
        app.add_plugin_message("Plugin message")

        messages = app.message_history.get_messages()
        assert messages[-1]["content"] == "Plugin message"
        assert messages[-1]["role"] == "user"

    def test_call_notify_hook_when_defined(self):
        """Test calling notify hook when defined"""
        app = AICoder()

        # Create mock hook
        mock_hook = MagicMock()
        app.notify_hooks = {"on_test": mock_hook}

        app.call_notify_hook("on_test")

        mock_hook.assert_called_once()

    def test_call_notify_hook_when_not_defined(self):
        """Test calling notify hook when not defined"""
        app = AICoder()
        app.notify_hooks = None

        # Should not raise
        app.call_notify_hook("on_test")

    def test_call_notify_hook_with_exception(self):
        """Test calling notify hook when hook raises exception"""
        app = AICoder()

        mock_hook = MagicMock(side_effect=Exception("Hook error"))
        app.notify_hooks = {"on_test": mock_hook}

        with patch('aicoder.core.aicoder.Config') as mock_config:
            mock_config.debug.return_value = True
            with patch('aicoder.core.aicoder.LogUtils'):
                # Should not raise even when hook fails
                app.call_notify_hook("on_test")

    def test_perform_auto_compaction(self):
        """Test perform_auto_compaction delegates to session_manager"""
        app = AICoder()

        mock_session_manager = MagicMock()
        app.session_manager = mock_session_manager

        app.perform_auto_compaction()

        mock_session_manager._perform_auto_compaction.assert_called_once()

    def test_handle_test_message_basic(self):
        """Test handling basic test message"""
        app = AICoder()

        result = app.handle_test_message({"content": "Test response"})

        # Should return empty list (no tool calls)
        assert result == []

        messages = app.message_history.get_messages()
        # Should have assistant message
        assistant_msgs = [m for m in messages if m.get("role") == "assistant"]
        assert len(assistant_msgs) >= 1

    def test_handle_test_message_with_tool_calls(self):
        """Test handling test message with tool calls"""
        app = AICoder()

        tool_calls = [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "test_tool"}
            }
        ]

        result = app.handle_test_message({
            "content": "Using tool",
            "tool_calls": tool_calls
        })

        # Should return tool results
        assert len(result) == 1
        assert result[0]["tool_call_id"] == "call_1"
        assert result[0]["success"] is True

    def test_initialization_with_plugin_system(self):
        """Test initialize method sets up plugin system"""
        app = AICoder()

        with patch.object(app.plugin_system, 'set_app'):
            with patch.object(app.plugin_system, 'load_plugins'):
                with patch.object(app.message_history, 'set_api_client'):
                    app.initialize()

                    app.plugin_system.set_app.assert_called_once_with(app)

    def test_run_non_interactive_with_stdin_input(self):
        """Test run_non_interactive with piped input"""
        app = AICoder()

        with patch('aicoder.core.aicoder.read_stdin_as_string', return_value="Hello\nWorld"):
            with patch.object(app.message_history, 'get_messages', side_effect=[
                [],  # Before processing
                []   # After processing
            ]):
                with patch.object(app.command_handler, 'handle_command') as mock_handle:
                    # Return a result that doesn't run API call
                    from aicoder.core.commands.base import CommandResult
                    mock_handle.return_value = CommandResult(should_quit=False, run_api_call=False)

                    # Should not raise
                    app.run_non_interactive()

    def test_run_non_interactive_empty_input(self):
        """Test run_non_interactive with empty stdin"""
        app = AICoder()

        with patch('aicoder.core.aicoder.read_stdin_as_string', return_value=""):
            # Should not raise
            app.run_non_interactive()


class TestAICoderWithMockedComponents:
    """Tests with more complex mocking"""

    def test_shutdown_stops_socket_server(self):
        """Test shutdown stops socket server"""
        app = AICoder()

        mock_socket_server = MagicMock()
        app.socket_server = mock_socket_server

        mock_input_handler = MagicMock()
        app.input_handler = mock_input_handler

        app.shutdown()

        mock_socket_server.stop.assert_called_once()
        mock_input_handler.close.assert_called_once()

    def test_is_running_flag(self):
        """Test is_running flag controls main loop"""
        app = AICoder()

        # Initially running
        assert app.is_running is True

        # Can be set to False
        app.is_running = False
        assert app.is_running is False

    def test_message_history_integration(self):
        """Test message history is properly integrated"""
        app = AICoder()

        # Check that message_history has required methods
        assert hasattr(app.message_history, 'add_user_message')
        assert hasattr(app.message_history, 'add_system_message')
        assert hasattr(app.message_history, 'get_messages')

    def test_tool_manager_integration(self):
        """Test tool manager is properly integrated"""
        app = AICoder()

        # Check that tool_manager has required methods
        assert hasattr(app.tool_manager, 'tools')
        assert hasattr(app.tool_manager, 'get_tool_definitions')

    def test_streaming_client_integration(self):
        """Test streaming client is properly integrated"""
        app = AICoder()

        # Check that streaming_client has required methods
        assert hasattr(app.streaming_client, 'stream_request')
        assert hasattr(app.streaming_client, 'stats')
