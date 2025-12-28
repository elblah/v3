"""
Test MessageHistory class
Tests for
"""

import pytest
from aicoder.core.message_history import (
    MessageHistory,
    PRUNED_TOOL_MESSAGE,
    PRUNE_PROTECTION_THRESHOLD,
)
from aicoder.core.stats import Stats

# Type definitions are now dicts
Message = dict[str, object]
MessageRole = str
AssistantMessage = dict[str, object]
MessageToolCall = dict[str, object]


@pytest.fixture
def mock_tool_result():
    class ToolResult:
        def __init__(self, tool_call_id, content, success=True, friendly=None):
            self.tool_call_id = tool_call_id
            self.content = content
            self.success = success
            self.friendly = friendly

    return ToolResult


@pytest.fixture
def message_history():
    """Create MessageHistory instance for testing"""
    stats = Stats()
    return MessageHistory(stats)


@pytest.fixture
def sample_tool_calls():
    """Sample tool calls for testing"""
    return [
        MessageToolCall(
            id="call_1",
            type="function",
            function={"name": "test_tool", "arguments": '{"param": "value"}'},
        )
    ]


def test_message_history_initialization(message_history):
    """Test MessageHistory initialization"""
    assert message_history.messages == []
    assert message_history.initial_system_prompt is None
    assert message_history.is_compacting is False


def test_add_system_message(message_history):
    """Test adding system message"""
    message_history.add_system_message("System prompt")

    assert len(message_history.messages) == 1
    assert message_history.messages[0].role == MessageRole.SYSTEM
    assert message_history.messages[0].content == "System prompt"
    assert message_history.initial_system_prompt == message_history.messages[0]


def test_add_user_message(message_history):
    """Test adding user message"""
    message_history.add_user_message("User message")

    assert len(message_history.messages) == 1
    assert message_history.messages[0].role == MessageRole.USER
    assert message_history.messages[0].content == "User message"
    assert message_history.stats.messages_sent == 1


def test_add_assistant_message(message_history, sample_tool_calls):
    """Test adding assistant message"""
    assistant_msg = AssistantMessage(
        content="Assistant response", tool_calls=sample_tool_calls
    )
    message_history.add_assistant_message(assistant_msg)

    assert len(message_history.messages) == 1
    assert message_history.messages[0].role == MessageRole.ASSISTANT
    assert message_history.messages[0].content == "Assistant response"
    assert message_history.messages[0].tool_calls == sample_tool_calls


def test_add_tool_results_dict(message_history):
    """Test adding tool results from dict"""
    tool_results = [
        {"tool_call_id": "call_1", "content": "Tool result 1"},
        {"tool_call_id": "call_2", "content": "Tool result 2"},
    ]

    message_history.add_tool_results(tool_results)

    assert len(message_history.messages) == 2
    assert message_history.messages[0].role == MessageRole.TOOL
    assert message_history.messages[0].tool_call_id == "call_1"
    assert message_history.messages[0].content == "Tool result 1"
    assert message_history.messages[1].tool_call_id == "call_2"


def test_add_tool_results_object(message_history, mock_tool_result):
    """Test adding tool results from object"""
    ToolResult = mock_tool_result
    tool_results = [
        ToolResult("call_1", "Tool result 1"),
        ToolResult("call_2", "Tool result 2"),
    ]

    message_history.add_tool_results(tool_results)

    assert len(message_history.messages) == 2
    assert message_history.messages[0].role == MessageRole.TOOL
    assert message_history.messages[0].tool_call_id == "call_1"
    assert message_history.messages[0].content == "Tool result 1"


def test_add_single_tool_result(message_history, mock_tool_result):
    """Test adding single tool result"""
    ToolResult = mock_tool_result
    result = ToolResult("call_1", "Tool result 1")
    message_history.add_tool_results(result)

    assert len(message_history.messages) == 1
    assert message_history.messages[0].role == MessageRole.TOOL
    assert message_history.messages[0].tool_call_id == "call_1"


def test_get_messages(message_history):
    """Test getting messages"""
    message_history.add_system_message("System")
    message_history.add_user_message("User")

    messages = message_history.get_messages()

    assert len(messages) == 2
    # Should be a copy
    messages.append(Message(role=MessageRole.USER, content="New"))
    assert len(message_history.messages) == 2


def test_get_chat_messages(message_history):
    """Test getting chat messages (excluding system)"""
    message_history.add_system_message("System")
    message_history.add_user_message("User")
    message_history.add_assistant_message(AssistantMessage(content="Assistant"))

    chat_messages = message_history.get_chat_messages()

    assert len(chat_messages) == 2
    assert all(msg.role != MessageRole.SYSTEM for msg in chat_messages)


def test_clear(message_history):
    """Test clearing messages - should preserve system prompt"""
    message_history.add_system_message("System")
    message_history.add_user_message("User")

    assert len(message_history.messages) == 2

    message_history.clear()

    # Should preserve the system prompt
    assert len(message_history.messages) == 1
    assert message_history.messages[0]["role"] == "system"
    assert message_history.messages[0]["content"] == "System"
    # Prompt size should account for the preserved system prompt
    assert message_history.stats.current_prompt_size > 0


def test_set_messages(message_history):
    """Test setting messages"""
    messages = [
        Message(role=MessageRole.USER, content="User"),
        Message(role=MessageRole.ASSISTANT, content="Assistant"),
    ]

    message_history.set_messages(messages)

    assert len(message_history.messages) == 2
    assert message_history.messages[0].content == "User"
    # Should be a copy
    messages.append(Message(role=MessageRole.USER, content="New"))
    assert len(message_history.messages) == 2


def test_get_message_counts(message_history):
    """Test getting message counts"""
    assert message_history.get_message_count() == 0
    assert message_history.get_chat_message_count() == 0

    message_history.add_system_message("System")
    message_history.add_user_message("User")
    message_history.add_assistant_message(AssistantMessage(content="Assistant"))

    assert message_history.get_message_count() == 3
    assert message_history.get_chat_message_count() == 2


def test_get_round_count(message_history):
    """Test getting round count"""
    assert message_history.get_round_count() == 0

    # Add a round
    message_history.add_user_message("User 1")
    message_history.add_assistant_message(AssistantMessage(content="Assistant 1"))

    assert message_history.get_round_count() == 1

    # Add another round
    message_history.add_user_message("User 2")
    message_history.add_assistant_message(AssistantMessage(content="Assistant 2"))

    assert message_history.get_round_count() == 2

    # Multiple user messages in a row should still count as one round
    message_history.add_user_message("User 3")
    message_history.add_user_message("User 3b")
    message_history.add_assistant_message(AssistantMessage(content="Assistant 3"))

    assert message_history.get_round_count() == 3


def test_get_tool_result_messages(message_history):
    """Test getting tool result messages"""
    tool_results = [
        {"tool_call_id": "call_1", "content": "Result 1"},
        {"tool_call_id": "call_2", "content": "Result 2"},
    ]

    message_history.add_user_message("User")
    message_history.add_tool_results(tool_results)
    message_history.add_assistant_message(AssistantMessage(content="Assistant"))

    tool_messages = message_history.get_tool_result_messages()

    assert len(tool_messages) == 2
    assert all(msg.role == MessageRole.TOOL for msg in tool_messages)


def test_prune_tool_results_by_percentage_empty(message_history):
    """Test pruning when no tool results exist"""
    result = message_history.prune_tool_results_by_percentage(50)

    assert result["prunedCount"] == 0
    assert result["totalSize"] == 0
    assert result["actualPercentage"] == 0


def test_prune_tool_results_by_percentage_protected(message_history):
    """Test pruning small tool results (protected)"""
    # Add small tool results (under protection threshold)
    small_content = "x" * (PRUNE_PROTECTION_THRESHOLD - 10)
    tool_results = [
        {"tool_call_id": "call_1", "content": small_content},
        {"tool_call_id": "call_2", "content": small_content},
    ]

    message_history.add_user_message("User")
    message_history.add_tool_results(tool_results)

    result = message_history.prune_tool_results_by_percentage(50)

    # Nothing should be pruned (under protection threshold)
    assert result["prunedCount"] == 0


def test_prune_tool_results_by_percentage_large(message_history):
    """Test pruning large tool results"""
    # Add large tool results
    large_content = "x" * 1000  # Much larger than protection threshold
    tool_results = [
        {"tool_call_id": "call_1", "content": large_content},
        {"tool_call_id": "call_2", "content": large_content},
    ]

    message_history.add_user_message("User")
    message_history.add_tool_results(tool_results)

    # Prune 50%
    result = message_history.prune_tool_results_by_percentage(50)

    # Should prune at least one message
    assert result["prunedCount"] >= 1
    assert result["totalSize"] > 0
    assert result["actualPercentage"] > 0

    # Check that pruned messages were replaced
    tool_messages = message_history.get_tool_result_messages()
    pruned_count = sum(1 for msg in tool_messages if msg.content == PRUNED_TOOL_MESSAGE)
    assert pruned_count == result["prunedCount"]


def test_compaction_count_tracking(message_history):
    """Test compaction count tracking"""
    assert message_history.get_compaction_count() == 0

    message_history.increment_compaction_count()
    assert message_history.get_compaction_count() == 1

    # Stats should track it too
    assert message_history.stats.compactions == 1


def test_should_auto_compact(message_history):
    """Test auto-compact check"""
    # Currently always returns False (simplified)
    assert not message_history.should_auto_compact()


def test_set_api_client(message_history):
    """Test setting API client"""
    mock_client = object()
    message_history.set_api_client(mock_client)
    assert message_history.api_client is mock_client
