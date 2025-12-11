"""Message history management for AI Coder
Following TypeScript patterns exactly
"""

import json
from typing import List, Optional, TYPE_CHECKING
from dataclasses import dataclass

from aicoder.type_defs.message_types import (
    Message,
    MessageRole,
    AssistantMessage,
    ToolResultData,
)


# Import ToolResult from types package
from aicoder.type_defs.tool_types import ToolResult


from aicoder.core.stats import Stats

if TYPE_CHECKING:
    from ..core.streaming_client import StreamingClient


PRUNED_TOOL_MESSAGE = "[Old tool result content cleared due to memory compaction]"

# Minimum size for tool result to be considered for pruning
# Tool results smaller than this are protected from pruning
PRUNE_PROTECTION_THRESHOLD = 256  # bytes


class MessageHistory:
    """Simple message storage with delegated compaction logic"""

    def __init__(self, stats: Stats, api_client: Optional["StreamingClient"] = None):
        self.stats = stats
        self.api_client = api_client
        self.messages: List[Message] = []
        self.initial_system_prompt: Optional[Message] = None
        self.is_compacting = False

    def set_api_client(self, api_client: "StreamingClient") -> None:
        """Set API client for compaction"""
        self.api_client = api_client

    def add_system_message(self, content: str) -> None:
        """Add a system message"""
        message = Message(role="system", content=content)
        self.messages.append(message)
        self.estimate_context()

        if not self.initial_system_prompt:
            self.initial_system_prompt = message

    def add_user_message(self, content: str) -> None:
        """Add a user message"""
        message = Message(role="user", content=content)
        self.messages.append(message)
        self.stats.increment_messages_sent()
        # Update context size estimate
        self.estimate_context()

    def add_assistant_message(self, message: AssistantMessage) -> None:
        """Add an assistant message"""
        assistant_message = Message(
            role="assistant",
            content=message.get("content"),
            tool_calls=message.get("tool_calls"),
        )
        self.messages.append(assistant_message)
        # Update context size estimate
        self.estimate_context()

    def add_tool_results(self, tool_results) -> None:
        """Add tool results - accepts both dicts and objects"""
        # Ensure tool_results is iterable
        if isinstance(tool_results, (dict, ToolResult)) or not hasattr(
            tool_results, "__iter__"
        ):
            tool_results = [tool_results]

        for result in tool_results:
            # Handle both dict and object
            if isinstance(result, dict):
                tool_call_id = result.get("tool_call_id")
                content = result.get("content")
            else:
                tool_call_id = getattr(result, "tool_call_id", None)
                content = getattr(result, "content", None)

            tool_message = Message(
                role="tool", content=content, tool_call_id=tool_call_id
            )
            self.messages.append(tool_message)
        # Update context size estimate
        self.estimate_context()

    def get_messages(self) -> List[Message]:
        """Get all messages"""
        return self.messages.copy()

    def get_chat_messages(self) -> List[Message]:
        """Get chat messages (excluding system messages)"""
        return [msg for msg in self.messages if msg.get("role") != "system"]

    def estimate_context(self) -> None:
        """Estimate context size"""
        # For simplicity, just count characters
        total_chars = 0
        for msg in self.messages:
            content = msg.get("content")
            if content:
                total_chars += len(content)

        # Rough estimate: 1 token = 4 characters
        self.stats.set_current_prompt_size(total_chars // 4)

    def clear(self) -> None:
        """Clear all messages"""
        self.messages = []
        self.stats.set_current_prompt_size(0)

    def set_messages(self, messages: List[Message]) -> None:
        """Set messages (for loading)"""
        self.messages = messages.copy()
        self.estimate_context()

    def get_message_count(self) -> int:
        """Get total message count"""
        return len(self.messages)

    def get_chat_message_count(self) -> int:
        """Get chat message count (excluding system)"""
        return len(self.get_chat_messages())

    def get_initial_system_prompt(self) -> Optional[Message]:
        """Get the initial system prompt"""
        return self.initial_system_prompt

    def increment_compaction_count(self) -> None:
        """Increment compaction counter"""
        self.stats.increment_compactions()

    def get_compaction_count(self) -> int:
        """Get compaction count"""
        return self.stats.compactions

    def compact_memory(self) -> None:
        """Compact memory using CompactionService"""
        # Prevent concurrent compactions
        if self.is_compacting:
            print("[!] Compaction already in progress, skipping...")
            return

        if not self.api_client:
            print("[!] API client not available for compaction")
            return

        # For now, just prune tool results - full compaction service will be added later
        self.is_compacting = True
        try:
            result = self.prune_tool_results_by_percentage(50)
            if result["prunedCount"] > 0:
                self.increment_compaction_count()
                print("[✓] Conversation compacted successfully")
        finally:
            self.is_compacting = False

    def force_compact_rounds(self, n: int) -> None:
        """Force compact N oldest rounds"""
        # Simplified implementation for now
        self.compact_memory()

    def force_compact_messages(self, n: int) -> None:
        """Force compact N oldest messages"""
        # Simplified implementation for now
        self.compact_memory()

    def should_auto_compact(self) -> bool:
        """Check if auto-compaction should be triggered"""
        # Simplified: always false for now
        return False

    def get_round_count(self) -> int:
        """Get number of conversation rounds"""
        chat_messages = self.get_chat_messages()
        rounds = 0
        in_user_message = False

        for message in chat_messages:
            if message.get("role") == "user":
                if not in_user_message:
                    rounds += 1
                    in_user_message = True
            else:
                in_user_message = False

        return rounds

    def get_tool_result_messages(self) -> List[Message]:
        """Get all tool result messages"""
        return [msg for msg in self.messages if msg.get("role") == "tool"]

    def get_tool_call_stats(self) -> dict:
        """Get tool call statistics"""
        tool_messages = self.get_tool_result_messages()
        count = len(tool_messages)

        total_content = ""
        for msg in tool_messages:
            content = msg.get("content")
            if content:
                total_content += content

        bytes_count = len(total_content.encode("utf-8"))
        tokens = len(total_content) // 4  # Rough estimate

        return {"count": count, "tokens": tokens, "bytes": bytes_count}

    def prune_tool_results(self, indices: List[int]) -> int:
        """Replace tool result content with pruning message"""
        tool_messages = self.get_tool_result_messages()
        pruned_count = 0

        for index in indices:
            if 0 <= index < len(tool_messages):
                tool_message = tool_messages[index]
                message_index = next(
                    (i for i, msg in enumerate(self.messages) if msg == tool_message),
                    -1,
                )
                if message_index != -1:
                    current_content = self.messages[message_index].get("content") or ""
                    current_size = len(current_content.encode("utf-8"))
                    # Only prune if content is larger than both the pruning message AND protection threshold
                    if current_size > max(
                        len(PRUNED_TOOL_MESSAGE.encode("utf-8")),
                        PRUNE_PROTECTION_THRESHOLD,
                    ):
                        self.messages[message_index]["content"] = PRUNED_TOOL_MESSAGE
                        pruned_count += 1

        self.estimate_context()
        return pruned_count

    def prune_all_tool_results(self) -> int:
        """Prune all tool results"""
        tool_messages = self.get_tool_result_messages()
        indices = list(range(len(tool_messages)))
        return self.prune_tool_results(indices)

    def prune_oldest_tool_results(self, n: int) -> int:
        """Prune N oldest tool results"""
        tool_messages = self.get_tool_result_messages()
        indices = list(range(min(n, len(tool_messages))))
        return self.prune_tool_results(indices)

    def prune_tool_results_by_percentage(self, target_percentage: int = 50) -> dict:
        """Prune tool results by percentage"""
        tool_messages = self.get_tool_result_messages()

        if len(tool_messages) == 0:
            return {"prunedCount": 0, "totalSize": 0, "actualPercentage": 0}

        # Sort by size (largest first)
        sorted_messages = sorted(
            enumerate(tool_messages),
            key=lambda x: len((x[1].content or "").encode("utf-8")),
            reverse=True,
        )

        total_size = sum(
            len((msg.get("content") or "").encode("utf-8"))
            for _, msg in sorted_messages
        )

        # Calculate target size
        target_size = (total_size * (100 - target_percentage)) // 100
        current_size = total_size
        pruned_indices = []

        for index, msg in sorted_messages:
            if current_size <= target_size:
                break

            msg_size = len((msg.get("content") or "").encode("utf-8"))
            # Only prune if content is larger than both the pruning message AND protection threshold
            if msg_size > max(
                len(PRUNED_TOOL_MESSAGE.encode("utf-8")), PRUNE_PROTECTION_THRESHOLD
            ):
                pruned_indices.append(index)
                current_size -= msg_size

        # Prune identified messages
        pruned_count = self.prune_tool_results(pruned_indices)

        return {
            "prunedCount": pruned_count,
            "totalSize": total_size,
            "actualPercentage": ((total_size - current_size) * 100) // total_size
            if total_size > 0
            else 0,
        }
