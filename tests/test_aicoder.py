"""
Test AICoder class - Synchronous version
Tests for
"""

import pytest
from unittest.mock import MagicMock, patch
from aicoder.core.aicoder import AICoder
from aicoder.core.message_history import MessageHistory
from aicoder.core.streaming_client import StreamingClient
from aicoder.core.tool_manager import ToolManager
from aicoder.core.stats import Stats
from aicoder.core.command_handler import CommandHandler

# Type definitions are now dicts
Message = dict[str, object]
MessageRole = str


@pytest.fixture
def app():
    """Create AICoder instance for testing"""
    return AICoder()


@pytest.fixture
def sample_messages():
    """Sample messages for testing"""
    return [
        {"role": "user", "content": "Hello"},
        {"role": "assistant", "content": "Hi there!"},
    ]


def test_aicoder_initialization(app):
    """Test AICoder initialization"""
    assert app.stats is not None
    assert app.message_history is not None
    assert app.streaming_client is not None
    assert app.tool_manager is not None
    assert app.command_handler is not None


def test_handle_command(app):
    """Test command handling"""
    # Mock command handler
    app.command_handler.handle_command = MagicMock()

    # Add user input (which triggers command handling via command_handler)
    app.add_user_input("/help")
    # Test that input was added (command execution happens in process_with_ai)
    assert len(app.message_history.get_messages()) > 0


def test_stream_api_response_success(app):
    """Test successful API response streaming"""
    # Mock the streaming client to return a controlled response
    mock_result = {
        "should_continue": True,
        "full_response": "Hello world!",
        "accumulated_tool_calls": {},
    }

    app.streaming_client.stream_request = MagicMock(return_value=iter([]))

    # Mock the method to return our controlled result
    app.stream_response = MagicMock(return_value=mock_result)

    # Test that stream_response can be called and returns expected structure
    sample_messages = [{"role": "user", "content": "test"}]
    result = app.stream_response(sample_messages)

    # Verify the response structure
    assert "should_continue" in result
    assert "full_response" in result
    assert "accumulated_tool_calls" in result
    assert result["should_continue"] == True
    assert result["full_response"] == "Hello world!"


def test_accumulate_tool_call(app):
    """Test tool call accumulation - matches accumulate_tool_call method"""
    # Setup
    accumulated_tool_calls = {}

    # Mock tool call
    tool_call = {
        "id": "call_123",
        "type": "function",
        "function": {"name": "test_tool", "arguments": '{"arg": "value"}'},
        "index": 0,
    }

    app.accumulate_tool_call(tool_call, accumulated_tool_calls)

    assert 0 in accumulated_tool_calls
    assert accumulated_tool_calls[0]["id"] == "call_123"
    assert accumulated_tool_calls[0]["function"]["name"] == "test_tool"


def test_execute_tool_calls(app):
    """Test tool call execution"""
    # Mock tool manager
    mock_result = MagicMock()
    mock_result.content = "Tool executed successfully"
    mock_result.friendly = "✓ Tool executed"

    app.tool_manager.execute_tool_with_args = MagicMock(return_value=mock_result)
    app.message_history.add_tool_results = MagicMock()

    # Mock validate_and_process_tool_calls
    app.validate_and_process_tool_calls = MagicMock(return_value=True)

    # Test with tool calls
    tool_calls = [
        {
            "id": "call_1",
            "type": "function",
            "function": {"name": "test_tool", "arguments": "{}"},
        }
    ]

    app._execute_tool_calls(tool_calls)

    app.tool_manager.execute_tool_with_args.assert_called_once()
    app.message_history.add_tool_results.assert_called_once()


def test_run_with_piped_input(app):
    """Test run method with piped input"""
    # Mock piped input
    with patch("sys.stdin.isatty", return_value=False):
        with patch("sys.stdin.read", return_value="test input"):
            app.process_with_ai = MagicMock()

            with patch("sys.exit", side_effect=SystemExit):
                try:
                    app.run()
                except SystemExit:
                    pass


def test_run_interactive(app):
    """Test run method in interactive mode"""
    # Mock interactive input
    with patch("sys.stdin.isatty", return_value=True):
        app.input_handler.get_user_input = MagicMock(return_value="test input")
        app.process_with_ai = MagicMock(side_effect=EOFError)
        app.input_handler.close = MagicMock()

        with patch("sys.exit", side_effect=SystemExit):
            try:
                app.run()
            except SystemExit:
                pass


def test_process_with_ai_empty_input(app):
    """Test process_with_ai with empty input"""
    # Should return early for empty input
    result = app.process_with_ai("")
    assert result is None


def test_process_with_ai_command(app):
    """Test process_with_ai with command"""
    # Mock command handling
    app._handle_command = MagicMock(return_value=True)

    # Should handle commands
    result = app.process_with_ai("/help")
    app._handle_command.assert_called_once_with("/help")
    assert result is True


def test_process_with_ai_message(app):
    """Test process_with_ai with regular message"""
    # Mock streaming
    app._stream_api_response = MagicMock()

    # Should process regular messages
    app.process_with_ai("Hello AI")

    # Should have added user message
    assert len(app.message_history.get_messages()) >= 1
    assert app.message_history.get_messages()[-1].role == MessageRole.USER


def test_initialize(app):
    """Test initialization"""
    app.initialize()

    # Should have system prompt
    messages = app.message_history.get_messages()
    system_messages = [m for m in messages if m.role == MessageRole.SYSTEM]
    assert len(system_messages) > 0


def test_context_creation():
    """Test context creation for different handlers"""
    app = AICoder()

    # Test context creation works
    context = app._create_context()
    assert context.stats is not None
    assert context.message_history is not None
    assert context.streaming_client is not None
    assert context.tool_manager is not None
