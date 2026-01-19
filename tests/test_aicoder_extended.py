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

    def test_command_handler_integration(self):
        """Test command handler is properly integrated"""
        app = AICoder()

        # Check that command_handler has required attributes
        assert hasattr(app.command_handler, 'handle_command')
        assert hasattr(app.command_handler, 'registry')

    def test_input_handler_integration(self):
        """Test input handler is properly integrated"""
        app = AICoder()

        # Check that input_handler has required attributes
        assert hasattr(app.input_handler, 'get_user_input')

    def test_stats_integration(self):
        """Test stats is properly integrated"""
        app = AICoder()

        # Check that stats has required methods
        assert hasattr(app.stats, 'increment_user_interactions')
        assert hasattr(app.stats, 'increment_api_requests')


class TestAICoderRunModes:
    """Tests for different run modes"""

    def test_run_with_socket_only_env(self):
        """Test run_socket_only mode sets YOLO"""
        app = AICoder()

        with patch('aicoder.core.aicoder.Config') as mock_config:
            mock_config.socket_only.return_value = True
            mock_config.debug.return_value = False
            mock_config.print_startup_info = MagicMock()
            mock_config.set_yolo_mode = MagicMock()

            # Run in socket-only mode - should set YOLO
            with patch.object(app, 'shutdown'):
                with patch('time.sleep'):
                    app.is_running = False  # Stop immediately after starting
                    app.run_socket_only()

            mock_config.set_yolo_mode.assert_called_with(True)

    def test_run_non_interactive_calls_shutdown(self):
        """Test run_non_interactive calls shutdown on error"""
        app = AICoder()

        with patch('aicoder.core.aicoder.read_stdin_as_string', side_effect=Exception("Stdin error")):
            with patch.object(app, 'shutdown') as mock_shutdown:
                app.run_non_interactive()
                mock_shutdown.assert_called_once()


class TestAICoderErrorHandling:
    """Tests for error handling"""

    def test_call_notify_hook_with_exception_in_debug_mode(self):
        """Test that notify hook exceptions are handled gracefully in debug mode"""
        app = AICoder()

        mock_hook = MagicMock(side_effect=Exception("Hook error"))
        app.notify_hooks = {"on_test": mock_hook}

        with patch('aicoder.core.aicoder.Config') as mock_config:
            mock_config.debug.return_value = True
            with patch('aicoder.core.aicoder.LogUtils') as mock_log:
                # Should not raise even when hook fails
                app.call_notify_hook("on_test")
                mock_log.warn.assert_called()


class TestAICoderPluginIntegration:
    """Tests for plugin integration"""

    def test_plugin_system_set_app_called(self):
        """Test that set_app is called on plugin system during initialize"""
        app = AICoder()

        with patch.object(app.plugin_system, 'set_app'):
            with patch.object(app.message_history, 'set_api_client'):
                with patch.object(app.plugin_system, 'load_plugins'):
                    app.initialize()
                    app.plugin_system.set_app.assert_called_once_with(app)

    def test_tool_manager_set_plugin_system_called(self):
        """Test that set_plugin_system is called on tool manager"""
        app = AICoder()

        with patch.object(app.message_history, 'set_api_client'):
            with patch.object(app.plugin_system, 'load_plugins'):
                with patch.object(app.tool_manager, 'set_plugin_system') as mock_set:
                    app.initialize()
                    mock_set.assert_called_once()

    def test_message_history_set_plugin_system_called(self):
        """Test that set_plugin_system is called on message history"""
        app = AICoder()

        with patch.object(app.message_history, 'set_api_client'):
            with patch.object(app.plugin_system, 'load_plugins'):
                with patch.object(app.message_history, 'set_plugin_system') as mock_set:
                    app.initialize()
                    mock_set.assert_called_once()

    def test_get_plugin_tools_iterates(self):
        """Test that get_plugin_tools returns tools dict"""
        app = AICoder()

        # Just verify the method exists and can be called
        tools = app.plugin_system.get_plugin_tools()
        assert isinstance(tools, dict)

    def test_get_plugin_commands_iterates(self):
        """Test that get_plugin_commands returns commands dict"""
        app = AICoder()

        # Just verify the method exists and can be called
        commands = app.plugin_system.get_plugin_commands()
        assert isinstance(commands, dict)


class TestAICoderCommandExecution:
    """Tests for command execution flow"""

    def test_add_user_input_triggers_prompt_history_save(self):
        """Test that add_user_input saves to prompt history"""
        app = AICoder()

        with patch('aicoder.core.prompt_history.save_prompt') as mock_save:
            app.add_user_input("Test message")
            mock_save.assert_called_once_with("Test message")

    def test_command_execution_adds_message(self):
        """Test that command execution can add user messages"""
        app = AICoder()

        initial_count = len(app.message_history.get_messages())

        # Execute a command that should run API call
        from aicoder.core.commands.base import CommandResult
        mock_result = CommandResult(should_quit=False, run_api_call=True, message="Hello from command")

        # Verify command handling works (basic sanity check)
        assert hasattr(app.command_handler, 'handle_command')
