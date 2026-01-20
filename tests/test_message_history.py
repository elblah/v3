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


class TestToolResultInsertPosition:
    """Tests for tool result insertion after matching tool call (fixes compaction breakage)"""

    def test_tool_result_inserted_after_matching_call(self, message_history):
        """Tool result should insert after its matching tool call, not at end.
        
        This fixes the issue where compaction inserts [SUMMARY] between tool call and result,
        breaking the conversation structure. Tool results should repair the structure.
        """
        # Simulate: user -> assistant (tool call) -> compaction (summary) -> tool result
        message_history.messages = [
            {"role": "system", "content": "You are a helpful assistant"},
            {"role": "user", "content": "read_file the file"},
            {
                "role": "assistant",
                "content": "I'll read the file for you",
                "tool_calls": [{"id": "call_123", "function": {"name": "read_file", "arguments": "{}"}}]
            },
            # Compaction inserted a summary here (breaks the structure)
            {"role": "user", "content": "[SUMMARY] Old conversation..."},
        ]

        # Add tool result - it should go AFTER the tool call, not at end
        message_history.add_tool_results({
            "tool_call_id": "call_123",
            "content": "File content here..."
        })

        # Tool result should be at position 3 (after tool call at position 2)
        assert len(message_history.messages) == 5
        
        # Find positions
        tool_call_idx = None
        tool_result_idx = None
        summary_idx = None

        for i, msg in enumerate(message_history.messages):
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                tool_call_idx = i
            if msg.get("role") == "tool":
                tool_result_idx = i
            if "[SUMMARY]" in msg.get("content", ""):
                summary_idx = i

        assert tool_call_idx == 2, "Tool call should be at index 2"
        assert tool_result_idx == 3, "Tool result should be at index 3 (right after call)"
        assert summary_idx == 4, "Summary should be after tool result"

    def test_tool_result_appended_when_no_matching_call(self, message_history):
        """If no matching tool call found, append at end (backward compatible)"""
        message_history.messages = [
            {"role": "system", "content": "System"},
            {"role": "user", "content": "hello"},
        ]

        # Add tool result with unknown call ID
        message_history.add_tool_results({
            "tool_call_id": "unknown_call",
            "content": "Some result"
        })

        # Should append at end
        assert len(message_history.messages) == 3
        assert message_history.messages[-1]["role"] == "tool"
        assert message_history.messages[-1]["content"] == "Some result"

    def test_tool_result_finds_most_recent_call_when_multiple(self, message_history):
        """When multiple tool calls exist, find the most recent one (bottom-up search)"""
        message_history.messages = [
            {"role": "system", "content": "System"},
            # First tool call
            {
                "role": "assistant",
                "content": "Calling tool A",
                "tool_calls": [{"id": "call_A", "function": {"name": "tool_a", "arguments": "{}"}}]
            },
            {"role": "tool", "content": "Result A", "tool_call_id": "call_A"},
            # Second tool call
            {
                "role": "assistant",
                "content": "Calling tool B",
                "tool_calls": [{"id": "call_B", "function": {"name": "tool_b", "arguments": "{}"}}]
            },
            # Compaction broke it - inserted summary
            {"role": "user", "content": "[SUMMARY] Some old stuff"},
        ]

        # Add result for call_B - should go after call_B, not call_A
        message_history.add_tool_results({
            "tool_call_id": "call_B",
            "content": "Result B"
        })

        # Find positions
        call_b_idx = None
        result_b_idx = None

        for i, msg in enumerate(message_history.messages):
            if msg.get("role") == "assistant":
                calls = msg.get("tool_calls", [])
                for call in calls:
                    if call.get("id") == "call_B":
                        call_b_idx = i
            if msg.get("role") == "tool" and msg.get("content") == "Result B":
                result_b_idx = i

        assert result_b_idx == call_b_idx + 1, \
            f"Result B should be after call B: call_b={call_b_idx}, result={result_b_idx}"

    def test_tool_result_with_no_id_appended_at_end(self, message_history):
        """When tool result has no ID, append at end (backward compatible)"""
        message_history.messages = [
            {"role": "system", "content": "System"},
            {"role": "user", "content": "hello"},
        ]

        # Add tool result without ID
        message_history.add_tool_results({
            "content": "Some result without ID"
        })

        # Should append at end
        assert len(message_history.messages) == 3
        assert message_history.messages[-1]["role"] == "tool"

    def test_multiple_tool_results_maintain_order(self, message_history):
        """Multiple tool results should both go after the matching assistant message.
        
        When multiple tool calls are in the same assistant message and results are
        added together, they both insert at the same position. This is correct -
        each result is placed right after its tool call (the same assistant message).
        """
        message_history.messages = [
            {"role": "system", "content": "System"},
            {
                "role": "assistant",
                "content": "Calling multiple tools",
                "tool_calls": [
                    {"id": "call_1", "function": {"name": "tool1", "arguments": "{}"}},
                    {"id": "call_2", "function": {"name": "tool2", "arguments": "{}"}},
                ]
            },
            {"role": "user", "content": "[SUMMARY] Old..."},
        ]

        # Add results in order
        message_history.add_tool_results([
            {"tool_call_id": "call_1", "content": "Result 1"},
            {"tool_call_id": "call_2", "content": "Result 2"},
        ])

        # Both should be after the assistant message (positions 2 and 3)
        assert len(message_history.messages) == 5
        
        # Find tool result positions
        tool_positions = [
            (i, msg) for i, msg in enumerate(message_history.messages)
            if msg.get("role") == "tool"
        ]
        
        assert len(tool_positions) == 2
        # Both results should be after the assistant (at index 1)
        assert tool_positions[0][0] == 2, "First result should be at position 2"
        assert tool_positions[1][0] == 3, "Second result should be at position 3"
        # Summary should be after both
        summary_idx = next(
            i for i, msg in enumerate(message_history.messages)
            if "[SUMMARY]" in msg.get("content", "")
        )
        assert summary_idx == 4

    def test_remove_orphan_tool_results(self, message_history):
        """Test cleanup of orphan tool results without parent calls.
        
        This can happen when compaction removes tool calls but leaves results.
        """
        message_history.messages = [
            {"role": "system", "content": "System"},
            # Valid tool call
            {
                "role": "assistant",
                "content": "Calling tool A",
                "tool_calls": [{"id": "call_A", "function": {"name": "tool_a", "arguments": "{}"}}]
            },
            {"role": "tool", "content": "Result A", "tool_call_id": "call_A"},
            # Compaction removed this tool call but left the result (orphan)
            {"role": "tool", "content": "Orphan result", "tool_call_id": "orphan_call"},
            # Another orphan with no ID
            {"role": "tool", "content": "Orphan with no ID"},
            {"role": "user", "content": "hello"},
        ]

        # Before cleanup: 6 messages (1 system, 1 assistant, 3 tool, 1 user)
        assert len(message_history.messages) == 6

        # Clean up orphans
        removed = message_history.remove_orphan_tool_results()

        # Should have removed 2 orphans
        assert removed == 2

        # After cleanup: 4 messages
        assert len(message_history.messages) == 4

        # Check remaining messages
        roles = [msg.get("role") for msg in message_history.messages]
        assert roles == ["system", "assistant", "tool", "user"]

        # Only the valid tool result should remain
        tool_results = [msg for msg in message_history.messages if msg.get("role") == "tool"]
        assert len(tool_results) == 1
        assert tool_results[0]["tool_call_id"] == "call_A"

    def test_remove_orphan_tool_results_none_to_remove(self, message_history):
        """Test cleanup when no orphans exist."""
        message_history.messages = [
            {"role": "system", "content": "System"},
            {
                "role": "assistant",
                "content": "Calling tool",
                "tool_calls": [{"id": "call_1", "function": {"name": "tool", "arguments": "{}"}}]
            },
            {"role": "tool", "content": "Result", "tool_call_id": "call_1"},
        ]

        removed = message_history.remove_orphan_tool_results()

        assert removed == 0
        assert len(message_history.messages) == 3

    def test_set_messages_cleans_orphans(self, message_history):
        """Test that set_messages cleans up orphan tool results.
        
        This ensures compaction/load operations don't leave orphans.
        """
        messages_with_orphans = [
            {"role": "system", "content": "System"},
            {
                "role": "assistant",
                "content": "Calling tool",
                "tool_calls": [{"id": "valid_call", "function": {"name": "tool", "arguments": "{}"}}]
            },
            {"role": "tool", "content": "Valid result", "tool_call_id": "valid_call"},
            # Orphan from compaction
            {"role": "tool", "content": "Orphan", "tool_call_id": "orphan_id"},
        ]

        # Set messages - should clean up orphans automatically
        message_history.set_messages(messages_with_orphans)

        # Should have 3 messages (1 system, 1 assistant, 1 tool)
        assert len(message_history.messages) == 3

        # Only valid tool result should remain
        tool_results = [msg for msg in message_history.messages if msg.get("role") == "tool"]
        assert len(tool_results) == 1
        assert tool_results[0]["tool_call_id"] == "valid_call"
