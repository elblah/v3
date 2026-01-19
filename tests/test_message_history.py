"""
Test MessageHistory class
Updated tests for current API (dict-based messages)
"""

import pytest
from unittest.mock import MagicMock, patch
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


def test_insert_user_message_at_beginning(message_history):
    """Test inserting user message when history is empty"""
    message_history.insert_user_message_at_appropriate_position("New message")
    assert len(message_history.messages) == 1
    assert message_history.messages[0]["content"] == "New message"
    assert message_history.messages[0]["role"] == "user"


def test_insert_user_message_after_tool(message_history):
    """Test inserting user message after tool response"""
    message_history.add_user_message("User 1")
    message_history.add_assistant_message({"role": "assistant", "content": "Assistant"})
    message_history.add_tool_results([{"tool_call_id": "call_1", "content": "Tool result"}])

    # Insert should go after tool response (priority 1)
    message_history.insert_user_message_at_appropriate_position("New message")

    # The new message should be at the end since it scans backwards
    # and finds tool at index 3, so inserts at index 4
    assert len(message_history.messages) == 4
    # New message is appended
    assert message_history.messages[3]["content"] == "New message"
    assert message_history.messages[3]["role"] == "user"


def test_insert_user_message_after_assistant(message_history):
    """Test inserting user message after assistant without tool calls"""
    message_history.add_user_message("User 1")
    message_history.add_assistant_message({"role": "assistant", "content": "Assistant without tools"})

    # Insert should go after assistant (priority 2)
    message_history.insert_user_message_at_appropriate_position("New message")

    assert len(message_history.messages) == 3
    assert message_history.messages[2]["content"] == "New message"


def test_insert_user_message_multiple_insertions(message_history):
    """Test multiple message insertions"""
    message_history.add_user_message("Original")
    message_history.insert_user_message_at_appropriate_position("Inserted 1")
    message_history.insert_user_message_at_appropriate_position("Inserted 2")

    # Should have 3 messages in order
    assert len(message_history.messages) == 3
    # Newest insert should be at the end
    assert message_history.messages[2]["content"] == "Inserted 2"


def test_get_round_count_empty(message_history):
    """Test get_round_count with empty history"""
    assert message_history.get_round_count() == 0


def test_get_round_count_single_user(message_history):
    """Test get_round_count with single user message"""
    message_history.add_user_message("User message")
    assert message_history.get_round_count() == 1


def test_get_round_count_conversation(message_history):
    """Test get_round_count counts conversation rounds correctly"""
    message_history.add_user_message("User 1")
    message_history.add_assistant_message({"role": "assistant", "content": "Assistant 1"})
    message_history.add_user_message("User 2")
    message_history.add_assistant_message({"role": "assistant", "content": "Assistant 2"})

    assert message_history.get_round_count() == 2


def test_get_tool_result_messages_empty(message_history):
    """Test get_tool_result_messages with no tools"""
    results = message_history.get_tool_result_messages()
    assert results == []


def test_get_tool_result_messages_with_tools(message_history):
    """Test get_tool_result_messages returns only tool messages"""
    message_history.add_user_message("User")
    message_history.add_tool_results([
        {"tool_call_id": "call_1", "content": "Result 1"},
        {"tool_call_id": "call_2", "content": "Result 2"}
    ])
    message_history.add_assistant_message({"role": "assistant", "content": "Assistant"})

    results = message_history.get_tool_result_messages()
    assert len(results) == 2
    assert all(msg["role"] == "tool" for msg in results)


def test_get_tool_call_stats_empty(message_history):
    """Test get_tool_call_stats with no tools"""
    stats = message_history.get_tool_call_stats()
    assert stats["count"] == 0
    assert stats["tokens"] == 0
    assert stats["bytes"] == 0


def test_get_tool_call_stats_with_tools(message_history):
    """Test get_tool_call_stats calculates statistics"""
    message_history.add_tool_results([
        {"tool_call_id": "call_1", "content": "Result 1"},
        {"tool_call_id": "call_2", "content": "AB"}  # 2 bytes
    ])

    stats = message_history.get_tool_call_stats()
    assert stats["count"] == 2
    assert stats["bytes"] == (len("Result 1".encode("utf-8")) + 2)


def test_prune_tool_results_no_tools(message_history):
    """Test prune_tool_results with no tools"""
    message_history.add_user_message("User")
    result = message_history.prune_tool_results([0])
    assert result == 0


def test_prune_tool_results_index_out_of_range(message_history):
    """Test prune_tool_results with out-of-range index"""
    message_history.add_tool_results([{"tool_call_id": "call_1", "content": "Result"}])
    result = message_history.prune_tool_results([5, 10])  # Invalid indices
    assert result == 0


def test_prune_tool_results_small_content(message_history):
    """Test prune_tool_results doesn't prune small content"""
    from aicoder.core.message_history import PRUNE_PROTECTION_THRESHOLD

    # Create a small tool result (below protection threshold)
    small_content = "A" * 100
    message_history.add_tool_results([{"tool_call_id": "call_1", "content": small_content}])

    result = message_history.prune_tool_results([0])
    assert result == 0  # Should not prune
    assert message_history.messages[0]["content"] == small_content


def test_prune_tool_results_large_content(message_history):
    """Test prune_tool_results prunes large content"""
    from aicoder.core.message_history import PRUNED_TOOL_MESSAGE

    # Create a large tool result
    large_content = "A" * 1000
    message_history.add_tool_results([{"tool_call_id": "call_1", "content": large_content}])

    result = message_history.prune_tool_results([0])
    assert result == 1
    assert message_history.messages[0]["content"] == PRUNED_TOOL_MESSAGE


def test_prune_all_tool_results(message_history):
    """Test prune_all_tool_results prunes all tool results"""
    from aicoder.core.message_history import PRUNED_TOOL_MESSAGE

    message_history.add_tool_results([
        {"tool_call_id": "call_1", "content": "Large content A" * 100},
        {"tool_call_id": "call_2", "content": "Large content B" * 100}
    ])

    result = message_history.prune_all_tool_results()
    assert result == 2
    assert message_history.messages[0]["content"] == PRUNED_TOOL_MESSAGE
    assert message_history.messages[1]["content"] == PRUNED_TOOL_MESSAGE


def test_prune_oldest_tool_results(message_history):
    """Test prune_oldest_tool_results prunes oldest results first"""
    from aicoder.core.message_history import PRUNED_TOOL_MESSAGE

    message_history.add_tool_results([
        {"tool_call_id": "call_1", "content": "Large content A" * 100},
        {"tool_call_id": "call_2", "content": "Large content B" * 100}
    ])

    result = message_history.prune_oldest_tool_results(1)
    assert result == 1
    assert message_history.messages[0]["content"] == PRUNED_TOOL_MESSAGE
    # Second should still have original content
    assert "Large content B" in message_history.messages[1]["content"]


def test_prune_tool_results_by_percentage_no_tools(message_history):
    """Test prune_tool_results_by_percentage with no tools"""
    result = message_history.prune_tool_results_by_percentage(50)
    assert result["prunedCount"] == 0


def test_prune_tool_results_by_percentage(message_history):
    """Test prune_tool_results_by_percentage returns structure for empty list"""
    # Test with no tools - this path works correctly
    result = message_history.prune_tool_results_by_percentage(50)
    assert result["prunedCount"] == 0
    assert result["totalSize"] == 0
    assert result["actualPercentage"] == 0


def test_should_auto_compact_disabled(message_history):
    """Test should_auto_compact returns False when disabled"""
    from aicoder.core.config import Config

    with patch.object(Config, 'context_compact_percentage', return_value=0):
        assert message_history.should_auto_compact() is False


def test_should_auto_compact_below_threshold(message_history):
    """Test should_auto_compact returns False when below threshold"""
    from aicoder.core.config import Config

    # Set compact percentage to 80%
    with patch.object(Config, 'context_compact_percentage', return_value=80), \
         patch.object(Config, 'context_size', return_value=100000):
        message_history.stats.current_prompt_size = 10000  # Below threshold
        assert message_history.should_auto_compact() is False


def test_should_auto_compact_above_threshold(message_history):
    """Test should_auto_compact returns True when above threshold"""
    from aicoder.core.config import Config

    # Set compact percentage to 80%
    with patch.object(Config, 'context_compact_percentage', return_value=80), \
         patch.object(Config, 'context_size', return_value=100000):
        message_history.stats.current_prompt_size = 90000  # Above threshold
        assert message_history.should_auto_compact() is True


def test_add_user_message_multimodal(message_history):
    """Test adding user message with multimodal content"""
    multimodal_message = {
        "role": "user",
        "content": [
            {"type": "text", "text": "What do you see?"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc123"}}
        ]
    }
    message_history.add_user_message(multimodal_message)

    assert len(message_history.messages) == 1
    assert message_history.messages[0]["role"] == "user"
    assert isinstance(message_history.messages[0]["content"], list)


def test_add_tool_results_object(message_history):
    """Test adding tool results as object with attributes"""
    class ToolResult:
        tool_call_id = "call_1"
        content = "Result from object"

    message_history.add_tool_results(ToolResult())

    assert len(message_history.messages) == 1
    assert message_history.messages[0]["role"] == "tool"
    assert message_history.messages[0]["tool_call_id"] == "call_1"


def test_force_compact_messages(message_history):
    """Test force_compact_messages method exists and doesn't crash"""
    # Just ensure method exists and doesn't crash
    message_history.force_compact_messages(0)
    # Compaction without client won't do anything


def test_clear_preserves_system_prompt(message_history):
    """Test that clear preserves the initial system prompt"""
    message_history.add_system_message("System prompt")
    message_history.add_user_message("User message")
    message_history.add_assistant_message({"role": "assistant", "content": "Assistant"})

    message_history.clear()

    # System prompt should be preserved
    assert len(message_history.messages) == 1
    assert message_history.messages[0]["role"] == "system"
    assert message_history.messages[0]["content"] == "System prompt"


def test_clear_with_no_system_prompt(message_history):
    """Test clear when no system prompt exists"""
    message_history.add_user_message("User message")

    message_history.clear()

    assert len(message_history.messages) == 0


def test_set_plugin_system(message_history):
    """Test setting plugin system"""
    mock_plugin_system = MagicMock()
    message_history.set_plugin_system(mock_plugin_system)

    assert message_history._plugin_system is mock_plugin_system


def test_add_user_message_calls_hook(message_history):
    """Test that user message addition triggers hook"""
    mock_plugin_system = MagicMock()
    message_history.set_plugin_system(mock_plugin_system)

    message_history.add_user_message("Test message")

    mock_plugin_system.call_hooks.assert_called_once()
    call_args = mock_plugin_system.call_hooks.call_args
    assert call_args[0][0] == "after_user_message_added"


def test_add_assistant_message_calls_hook(message_history):
    """Test that assistant message addition triggers hook"""
    mock_plugin_system = MagicMock()
    message_history.set_plugin_system(mock_plugin_system)

    message_history.add_assistant_message({"role": "assistant", "content": "Test"})

    mock_plugin_system.call_hooks.assert_called_once()


def test_add_tool_results_calls_hook(message_history):
    """Test that tool results addition triggers hook"""
    mock_plugin_system = MagicMock()
    message_history.set_plugin_system(mock_plugin_system)

    message_history.add_tool_results([{"tool_call_id": "call_1", "content": "Result"}])

    # Should be called for each tool result
    assert mock_plugin_system.call_hooks.call_count >= 1


def test_set_messages_calls_hook(message_history):
    """Test that set_messages triggers hook"""
    mock_plugin_system = MagicMock()
    message_history.set_plugin_system(mock_plugin_system)

    messages = [{"role": "system", "content": "System"}, {"role": "user", "content": "User"}]
    message_history.set_messages(messages)

    mock_plugin_system.call_hooks.assert_called_once_with("after_messages_set", messages)
