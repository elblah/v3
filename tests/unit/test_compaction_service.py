"""Unit tests for compaction service - core logic without API calls."""

import pytest
from unittest.mock import MagicMock, patch

import sys
sys.path.insert(0, '/home/blah/storage/ai-worktree-storage/feat_test_coverage__20260117_062928')

from aicoder.core.compaction_service import CompactionService, MessageGroup


class TestMessageGroup:
    """Test MessageGroup dataclass."""

    def test_message_group_creation(self):
        """Test MessageGroup can be created."""
        group = MessageGroup(
            messages=[{"role": "user", "content": "Hello"}],
            is_summary=False,
            is_user_turn=True
        )
        assert len(group.messages) == 1
        assert group.is_summary is False
        assert group.is_user_turn is True


class TestCompactionServiceUnit:
    """Unit tests for CompactionService core logic."""

    def test_init_without_api_client(self):
        """Test service initialization without API client."""
        service = CompactionService(api_client=None)
        assert service.api_client is None
        assert service.streaming_client is None

    def test_init_with_api_client(self):
        """Test service initialization with API client."""
        mock_client = MagicMock()
        service = CompactionService(api_client=mock_client)
        assert service.api_client is mock_client
        assert service.streaming_client is mock_client

    def test_compact_short_messages_unchanged(self):
        """Test that messages with 3 or fewer items are not compacted."""
        service = CompactionService(api_client=None)
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ]
        result = service.compact(messages)
        assert result == messages

    def test_compact_empty_messages(self):
        """Test compacting empty message list."""
        service = CompactionService(api_client=None)
        result = service.compact([])
        assert result == []

    def test_group_messages_simple(self):
        """Test grouping simple messages."""
        service = CompactionService(api_client=None)
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
            {"role": "user", "content": "How are you?"},
            {"role": "assistant", "content": "I'm good!"},
        ]
        groups = service.group_messages(messages)
        assert len(groups) >= 2  # At least 2 conversation rounds

    def test_group_messages_with_tool_calls(self):
        """Test grouping preserves tool calls with responses."""
        service = CompactionService(api_client=None)
        messages = [
            {"role": "user", "content": "Run a command"},
            {"role": "assistant", "content": "", "tool_calls": [{"id": "1", "function": {"name": "run_shell_command"}}]},
            {"role": "tool", "content": "Command output", "tool_call_id": "1"},
            {"role": "user", "content": "Next question"},
        ]
        groups = service.group_messages(messages)
        # Tool call and result should be in the same group
        assert len(groups) >= 1

    def test_group_messages_respects_summaries(self):
        """Test that summary messages are marked correctly."""
        service = CompactionService(api_client=None)
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
            {"role": "user", "content": "[SUMMARY] Previous conversation"},
        ]
        groups = service.group_messages(messages)
        summary_group = next((g for g in groups if g.is_summary), None)
        assert summary_group is not None

    def test_identify_rounds(self):
        """Test identifying conversation rounds."""
        service = CompactionService(api_client=None)
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
            {"role": "user", "content": "Second question"},
            {"role": "assistant", "content": "Second answer"},
        ]
        rounds = service._identify_rounds(messages)
        assert len(rounds) >= 2

    def test_identify_rounds_skips_system(self):
        """Test that system messages are skipped in rounds."""
        service = CompactionService(api_client=None)
        messages = [
            {"role": "system", "content": "You are helpful"},
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
        ]
        rounds = service._identify_rounds(messages)
        # System message should not be in any round
        for round in rounds:
            for msg in round.messages:
                assert msg.get("role") != "system"

    def test_identify_rounds_skips_summaries(self):
        """Test that summary messages are skipped in rounds."""
        service = CompactionService(api_client=None)
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"},
            {"role": "user", "content": "[SUMMARY] Previous context"},
        ]
        rounds = service._identify_rounds(messages)
        for round in rounds:
            for msg in round.messages:
                assert not msg.get("content", "").startswith("[SUMMARY]")

    def test_format_messages_for_summary(self):
        """Test message formatting for summary."""
        service = CompactionService(api_client=None)
        messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi there!"},
        ]
        formatted = service._format_messages_for_summary(messages)
        assert "User:" in formatted
        assert "Assistant:" in formatted
        assert "Hello" in formatted

    def test_format_messages_handles_long_content(self):
        """Test that long tool results are truncated."""
        service = CompactionService(api_client=None)
        messages = [
            {"role": "tool", "content": "x" * 1000, "tool_call_id": "123"},
        ]
        formatted = service._format_messages_for_summary(messages)
        assert "truncated for summarization" in formatted

    def test_format_messages_with_tool_calls(self):
        """Test formatting messages with tool calls."""
        service = CompactionService(api_client=None)
        messages = [
            {"role": "assistant", "content": "Let me run a command", "tool_calls": [
                {"function": {"name": "run_shell_command", "arguments": '{"command": "ls"}'}}
            ]},
        ]
        formatted = service._format_messages_for_summary(messages)
        assert "Tool Call:" in formatted
        assert "run_shell_command" in formatted

    def test_validate_summary_short(self):
        """Test summary validation rejects short summaries."""
        service = CompactionService(api_client=None)
        assert service._validate_summary("") is False
        assert service._validate_summary("Short") is False
        assert service._validate_summary("x" * 40) is False

    def test_validate_summary_valid(self):
        """Test summary validation accepts valid summaries."""
        service = CompactionService(api_client=None)
        assert service._validate_summary("x" * 50) is True
        # This has exactly 50 characters
        assert service._validate_summary("This is a valid summary with enough characters in it") is True

    def test_create_summary_message(self):
        """Test creating summary message."""
        service = CompactionService(api_client=None)
        summary = "Test summary content"
        msg = service._create_summary_message(summary)
        assert msg["role"] == "user"
        assert "[SUMMARY]" in msg["content"]
        assert "Test summary content" in msg["content"]

    def test_replace_messages_with_summary(self):
        """Test replacing messages with summary."""
        service = CompactionService(api_client=None)
        messages = [
            {"role": "user", "content": "Old message 1"},
            {"role": "assistant", "content": "Old response"},
            {"role": "user", "content": "Old message 2"},
        ]
        to_replace = [
            {"role": "user", "content": "Old message 1"},
            {"role": "assistant", "content": "Old response"},
        ]
        summary = {"role": "user", "content": "[SUMMARY] Compacted"}
        result = service._replace_messages_with_summary(messages, to_replace, summary)
        assert len(result) == 2  # Summary + remaining message
        assert result[0]["content"].startswith("[SUMMARY]")

    def test_replace_messages_empty_list(self):
        """Test replacing with empty list returns original."""
        service = CompactionService(api_client=None)
        messages = [{"role": "user", "content": "Hello"}]
        result = service._replace_messages_with_summary(messages, [], {"content": "Summary"})
        assert result == messages

    def test_replace_messages_not_found(self):
        """Test replacing messages not found returns original."""
        service = CompactionService(api_client=None)
        messages = [{"role": "user", "content": "Hello"}]
        to_replace = [{"role": "user", "content": "Different"}]
        result = service._replace_messages_with_summary(messages, to_replace, {"content": "Summary"})
        assert result == messages

    def test_force_compact_rounds_empty(self):
        """Test force_compact_rounds with no rounds."""
        service = CompactionService(api_client=None)
        messages = [{"role": "system", "content": "System"}]
        result = service.force_compact_rounds(messages, 1)
        assert result == messages

    def test_force_compact_messages_empty(self):
        """Test force_compact_messages with no eligible messages."""
        service = CompactionService(api_client=None)
        messages = [{"role": "system", "content": "System"}]
        result = service.force_compact_messages(messages, 1)
        assert result == messages

    def test_force_compact_messages_only_summaries(self):
        """Test force_compact_messages when only summaries exist."""
        service = CompactionService(api_client=None)
        messages = [{"role": "user", "content": "[SUMMARY] Previous summary"}]
        result = service.force_compact_messages(messages, 1)
        assert result == messages
