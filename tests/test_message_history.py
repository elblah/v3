"""
Test MessageHistory class
Updated tests for current API (dict-based messages)
"""

import pytest
from unittest.mock import MagicMock
from aicoder.core.message_history import MessageHistory


@pytest.fixture
def message_history():
    """Create MessageHistory instance for testing"""
    from aicoder.core.stats import Stats
    return MessageHistory(Stats())


def test_message_history_initialization(message_history):
    """Test MessageHistory initialization"""
    assert message_history.messages == []
    assert message_history.initial_system_prompt is None
    assert message_history.is_compacting is False


def test_add_system_message(message_history):
    """Test adding system message"""
    message_history.add_system_message("System prompt")

    assert len(message_history.messages) == 1
    assert message_history.messages[0]["role"] == "system"
    assert message_history.messages[0]["content"] == "System prompt"
    assert message_history.initial_system_prompt == message_history.messages[0]


def test_add_user_message(message_history):
    """Test adding user message"""
    message_history.add_user_message("User message")

    assert len(message_history.messages) == 1
    assert message_history.messages[0]["role"] == "user"
    assert message_history.messages[0]["content"] == "User message"


def test_add_assistant_message(message_history):
    """Test adding assistant message"""
    assistant_msg = {
        "role": "assistant",
        "content": "Assistant response",
        "tool_calls": [
            {
                "id": "call_1",
                "type": "function",
                "function": {"name": "test_tool", "arguments": '{"arg": "value"}'},
            },
        ]
    }

    message_history.add_assistant_message(assistant_msg)

    assert len(message_history.messages) == 1
    assert message_history.messages[0]["role"] == "assistant"
    assert message_history.messages[0]["content"] == "Assistant response"
    assert message_history.messages[0]["tool_calls"] == assistant_msg["tool_calls"]


def test_add_tool_results_list(message_history):
    """Test adding tool results as list"""
    tool_results = [
        {"tool_call_id": "call_1", "content": "Result 1"},
        {"tool_call_id": "call_2", "content": "Result 2"},
    ]

    message_history.add_tool_results(tool_results)

    assert len(message_history.messages) == 2
    assert message_history.messages[0]["role"] == "tool"
    assert message_history.messages[1]["role"] == "tool"


def test_add_single_tool_result(message_history):
    """Test adding single tool result"""
    tool_result = {"tool_call_id": "call_1", "content": "Single result"}
    message_history.add_tool_results([tool_result])

    assert len(message_history.messages) == 1
    assert message_history.messages[0]["role"] == "tool"
    assert message_history.messages[0]["tool_call_id"] == "call_1"
    assert message_history.messages[0]["content"] == "Single result"


def test_get_messages(message_history):
    """Test getting all messages"""
    message_history.add_system_message("System")
    message_history.add_user_message("User")
    message_history.add_assistant_message({"role": "assistant", "content": "Assistant"})

    messages = message_history.get_messages()

    assert len(messages) == 3
    assert messages[0]["role"] == "system"
    assert messages[1]["role"] == "user"
    assert messages[2]["role"] == "assistant"


def test_get_chat_messages(message_history):
    """Test getting chat messages (user + assistant only)"""
    message_history.add_system_message("System")
    message_history.add_user_message("User 1")
    message_history.add_assistant_message({"role": "assistant", "content": "Assistant 1"})
    message_history.add_user_message("User 2")
    message_history.add_assistant_message({"role": "assistant", "content": "Assistant 2"})

    chat_messages = message_history.get_chat_messages()

    # Should exclude system messages
    assert len(chat_messages) == 4
    assert chat_messages[0]["role"] == "user"
    assert chat_messages[1]["role"] == "assistant"
    assert chat_messages[2]["role"] == "user"
    assert chat_messages[3]["role"] == "assistant"


def test_clear(message_history):
    """Test clearing messages"""
    message_history.add_user_message("Message 1")
    message_history.add_user_message("Message 2")

    assert len(message_history.messages) == 2

    message_history.clear()

    assert len(message_history.messages) == 0


def test_get_message_count(message_history):
    """Test getting message count"""
    message_history.add_system_message("System")
    message_history.add_user_message("User 1")
    message_history.add_user_message("User 2")
    message_history.add_assistant_message({"role": "assistant", "content": "Assistant"})
    message_history.add_tool_results({"call_1": "Result"})

    assert message_history.get_message_count() == 5


def test_get_chat_message_count(message_history):
    """Test getting chat message count (excluding system)"""
    message_history.add_system_message("System")
    message_history.add_user_message("User 1")
    message_history.add_user_message("User 2")
    message_history.add_assistant_message({"role": "assistant", "content": "Assistant"})

    assert message_history.get_chat_message_count() == 3


def test_compaction_count_tracking(message_history):
    """Test compaction count tracking"""
    assert message_history.get_compaction_count() == 0

    message_history.increment_compaction_count()

    assert message_history.get_compaction_count() == 1


def test_compact_memory_no_client(message_history):
    """Test compact_memory with no API client"""
    # Should not crash, just return
    message_history.compact_memory()
    assert message_history.is_compacting is False


def test_compact_memory_with_client(message_history):
    """Test compact_memory with API client"""
    mock_client = MagicMock()
    message_history.set_api_client(mock_client)

    # Should call API client (even if compaction fails to run)
    message_history.compact_memory()
    assert message_history.is_compacting is False


def test_set_api_client(message_history):
    """Test setting API client"""
    client = MagicMock()
    message_history.set_api_client(client)

    assert message_history.api_client is client


def test_replace_messages(message_history):
    """Test replacing all messages"""
    message_history.add_user_message("Old message")

    new_messages = [
        {"role": "system", "content": "New system"},
        {"role": "user", "content": "New user"},
    ]

    message_history.replace_messages(new_messages)

    assert len(message_history.messages) == 2
    assert message_history.messages[0]["content"] == "New system"
    assert message_history.messages[1]["content"] == "New user"


def test_set_messages(message_history):
    """Test setting messages"""
    messages = [
        {"role": "system", "content": "System"},
        {"role": "user", "content": "User"},
    ]

    message_history.set_messages(messages)

    assert len(message_history.messages) == 2
    assert message_history.messages[0]["content"] == "System"


def test_get_initial_system_prompt(message_history):
    """Test getting initial system prompt"""
    message_history.add_system_message("First system")
    message_history.add_user_message("User")
    message_history.add_system_message("Second system")

    # Should return the FIRST system prompt
    assert message_history.get_initial_system_prompt()["content"] == "First system"


def test_force_compact_rounds(message_history):
    """Test force_compact_rounds method exists"""
    # Just ensure method exists and doesn't crash
    message_history.force_compact_rounds(0)
    # Compaction without client won't do anything
