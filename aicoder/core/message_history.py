"""Message history management for AI Coder

"""

import json
from typing import List, Optional, TYPE_CHECKING, Dict, Any




# Import ToolResult from types package


from aicoder.core.stats import Stats
from aicoder.utils.log import LogUtils

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
        self.messages: List[Dict[str, Any]] = []
        self.initial_system_prompt: Optional[Dict[str, Any]] = None
        self.is_compacting = False
        self._plugin_system = None

    def set_plugin_system(self, plugin_system) -> None:
        """Set plugin system for hooks"""
        self._plugin_system = plugin_system

    def set_api_client(self, api_client: "StreamingClient") -> None:
        """Set API client for compaction"""
        self.api_client = api_client

    @staticmethod
    def _get_content_as_string(content: Any) -> Optional[str]:
        """Safely get message content as string (handles both string and list types).
        Returns None if content contains images."""
        if isinstance(content, list):
            # For multi-modal messages, check for images
            for item in content:
                if isinstance(item, dict) and item.get("type") == "image_url":
                    return None
            # Extract text content
            for item in content:
                if isinstance(item, dict) and item.get("type") == "text":
                    return item.get("text", "")
            return ""
        return str(content) if content else ""

    @staticmethod
    def _has_image_content(msg: Dict[str, Any]) -> bool:
        """Check if message contains image content"""
        content = msg.get("content", "")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict) and item.get("type") == "image_url":
                    return True
        return False

    def add_system_message(self, content: str) -> None:
        """Add a system message"""
        message = {"role": "system", "content": content}
        
        # Cache tokens immediately on creation (performance optimization)
        from .token_estimator import cache_message
        cache_message(message)
        
        self.messages.append(message)
        self.estimate_context()

        if not self.initial_system_prompt:
            self.initial_system_prompt = message
        
        # Call plugin hook after session initialized (system prompt created)
        if self._plugin_system:
            self._plugin_system.call_hooks("after_session_initialized", self.messages)

    def add_user_message(self, content: str) -> None:
        """Add a user message (string text or pre-formatted multimodal dict)"""
        # Support multimodal messages from plugins (e.g., vision plugin)
        if isinstance(content, dict):
            message = content
        else:
            message = {"role": "user", "content": content}
        
        # Cache tokens immediately on creation (performance optimization)
        from .token_estimator import cache_message
        cache_message(message)
        
        self.messages.append(message)
        self.stats.increment_messages_sent()
        # Update context size estimate
        self.estimate_context()

        # Call plugin hooks
        if self._plugin_system:
            self._plugin_system.call_hooks("after_user_message_added", message)

    def insert_user_message_at_appropriate_position(self, content: str) -> None:
        """
        Insert a user message at the correct position in message history.
        
        Scans backwards from the end and finds the appropriate injection position:
        Priority: 1) after last tool response, 2) after last assistant message with no tool calls, 3) after last user message
        
        This prevents breaking tool call/response chains during injection.
        """
        last_tool_index = -1
        last_assistant_index = -1
        last_user_index = -1
        
        # Scan backwards from the end to find the LAST occurrence of each type
        for i in range(len(self.messages) - 1, -1, -1):
            msg = self.messages[i]
            role = msg.get("role")
            
            if role == "tool" and last_tool_index == -1:
                last_tool_index = i
            elif role == "assistant":
                tool_calls = msg.get("tool_calls")
                # Only consider assistant messages without tool calls
                if (not tool_calls or len(tool_calls) == 0) and last_assistant_index == -1:
                    last_assistant_index = i
            elif role == "user" and last_user_index == -1:
                last_user_index = i
        
        # Priority: tool > assistant > user
        insertion_index = len(self.messages)  # Default: append to end
        
        if last_tool_index != -1:
            insertion_index = last_tool_index + 1
        elif last_assistant_index != -1:
            insertion_index = last_assistant_index + 1
        elif last_user_index != -1:
            insertion_index = last_user_index + 1
        
        # Create and insert the user message
        user_message = {"role": "user", "content": content}
        
        # Cache tokens immediately on creation (performance optimization)
        from .token_estimator import cache_message
        cache_message(user_message)
        
        self.messages.insert(insertion_index, user_message)
        self.stats.increment_messages_sent()
        # Update context size estimate
        self.estimate_context()

    def add_assistant_message(self, message: Dict[str, Any]) -> None:
        """Add an assistant message"""
        assistant_message = {"role": "assistant", "content": message.get("content"), "tool_calls": message.get("tool_calls")}

        # Preserve reasoning field with whatever name the provider uses
        for field in ["reasoning_content", "reasoning", "reasoning_text"]:
            if message.get(field):
                assistant_message[field] = message.get(field)
                break  # Only preserve first found

        # Cache tokens immediately on creation (performance optimization)
        from .token_estimator import cache_message
        cache_message(assistant_message)

        self.messages.append(assistant_message)
        # Update context size estimate
        self.estimate_context()

        # Call plugin hooks
        if self._plugin_system:
            self._plugin_system.call_hooks("after_assistant_message_added", assistant_message)

    def add_tool_results(self, tool_results) -> None:
        """Add tool results - accepts both dicts and objects"""
        # Ensure tool_results is iterable
        if isinstance(tool_results, dict) or not hasattr(
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

            tool_message = {
                "role": "tool", "content": content, "tool_call_id": tool_call_id
            }
            
            # Cache tokens immediately on creation (performance optimization)
            from .token_estimator import cache_message
            cache_message(tool_message)
            
            # Try to insert after matching tool call, fallback to append
            if tool_call_id:
                insert_index = self._find_tool_insert_position(tool_call_id)
                if insert_index != -1:
                    self.messages.insert(insert_index, tool_message)
                else:
                    # No matching call found - append at end (backward compatible)
                    self.messages.append(tool_message)
            else:
                # No ID provided - append at end
                self.messages.append(tool_message)
            
            # Call plugin hooks for each tool message
            if self._plugin_system:
                self._plugin_system.call_hooks("after_tool_results_added", tool_message)
        
        # Update context size estimate
        self.estimate_context()

    def _find_tool_insert_position(self, tool_call_id: str) -> int:
        """Find the correct insertion position for a tool result.
        
        Inserts immediately after the matching tool call to ensure
        tool calls and results stay paired, even if compaction broke them apart.
        Searches from end (bottom-up) to find the most recent matching call.
        
        Returns:
            int: Position to insert at (0 to len(messages))
            -1: No matching call found (caller should append)
        """
        # Search from END to find the MOST RECENT matching tool call
        for i in range(len(self.messages) - 1, -1, -1):
            msg = self.messages[i]
            if msg.get("role") == "assistant":
                tool_calls = msg.get("tool_calls") or []
                for call in tool_calls:
                    if call.get("id") == tool_call_id:
                        # Found the matching call - insert after this message
                        return i + 1
        
        # No matching call found
        return -1

    def remove_orphan_tool_results(self) -> int:
        """Remove tool results that have no matching parent tool call.
        
        This can happen when compaction removes tool calls but leaves results.
        Returns the number of orphan tool results removed.
        """
        # Collect all valid tool_call_ids from assistant messages
        valid_call_ids = set()
        for msg in self.messages:
            if msg.get("role") == "assistant":
                tool_calls = msg.get("tool_calls") or []
                for call in tool_calls:
                    call_id = call.get("id")
                    if call_id:
                        valid_call_ids.add(call_id)
        
        # Find and remove orphan tool results
        orphan_count = 0
        new_messages = []
        for msg in self.messages:
            if msg.get("role") == "tool":
                call_id = msg.get("tool_call_id")
                if call_id and call_id in valid_call_ids:
                    # Valid tool result - keep it
                    new_messages.append(msg)
                else:
                    # Orphan - discard it
                    orphan_count += 1
            else:
                # Non-tool message - keep it
                new_messages.append(msg)
        
        if orphan_count > 0:
            self.messages = new_messages
            self.estimate_context()
        
        return orphan_count

    def get_messages(self) -> List[Dict[str, Any]]:
        """Get all messages"""
        return self.messages.copy()

    def get_chat_messages(self) -> List[Dict[str, Any]]:
        """Get chat messages (excluding system messages)"""
        return [msg for msg in self.messages if msg.get("role") != "system"]

    def replace_messages(self, new_messages: List[Dict[str, Any]]) -> None:
        """Replace all messages with new list"""
        self.messages = new_messages
        self.estimate_context()

    def estimate_context(self) -> None:
        """Estimate context size using optimized weighted estimation"""
        from .token_estimator import estimate_messages
        
        # Use cached estimation - super fast, no fallback
        estimated_tokens = estimate_messages(self.messages)
        self.stats.set_current_prompt_size(estimated_tokens, True)

    def clear(self) -> None:
        """Clear all messages except the initial system prompt"""
        # Save the initial system prompt if it exists
        system_prompt = self.initial_system_prompt

        # Clear all messages
        self.messages = []
        self.stats.set_current_prompt_size(0)

        # Restore the initial system prompt if it exists
        if system_prompt:
            from .token_estimator import cache_message
            cache_message(system_prompt)
            self.messages.append(system_prompt)
            self.estimate_context()
        else:
            # Clear cache if no system prompt to restore
            from .token_estimator import clear_cache
            clear_cache()

    def set_messages(self, messages: List[Dict[str, Any]]) -> None:
        """Set messages (for loading)"""
        self.messages = messages.copy()
        
        # Clear cache and re-cache all messages when replaced
        from .token_estimator import clear_cache, cache_message
        clear_cache()
        for msg in self.messages:
            cache_message(msg)
        
        # Clean up any orphan tool results (e.g., from compaction)
        self.remove_orphan_tool_results()
        
        self.estimate_context()
        
        # Call plugin hooks for serious operations like compaction, load, /m edits
        if self._plugin_system:
            self._plugin_system.call_hooks("after_messages_set", messages)

    def get_message_count(self) -> int:
        """Get total message count"""
        return len(self.messages)

    def get_chat_message_count(self) -> int:
        """Get chat message count (excluding system)"""
        return len(self.get_chat_messages())

    def get_initial_system_prompt(self) -> Optional[Dict[str, Any]]:
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
            LogUtils.warn("Compaction already in progress, skipping...")
            return

        if not self.api_client:
            LogUtils.error("API client not available for compaction")
            return

        self.is_compacting = True
        try:
            # Import here to avoid circular imports
            from .compaction_service import CompactionService

            LogUtils.warn(f"[*] Compacting conversation ({self.stats.current_prompt_size or 0:,} tokens)...")

            compaction = CompactionService(self.api_client)
            original_count = len(self.messages)

            new_messages = compaction.compact(self.messages)
            self.set_messages(new_messages)

            if len(self.messages) < original_count:
                self.increment_compaction_count()
                LogUtils.success("Conversation compacted successfully")

                # Call after_compaction hook (after compaction is complete)
                if self._plugin_system:
                    self._plugin_system.call_hooks("after_compaction")

        finally:
            self.is_compacting = False

    def force_compact_rounds(self, n: int) -> None:
        """Force compact N oldest rounds"""
        # Import here to avoid circular imports
        from .compaction_service import CompactionService

        compaction = CompactionService(self.api_client)
        new_messages = compaction.force_compact_rounds(self.messages, n)
        self.set_messages(new_messages)

    def force_compact_messages(self, n: int) -> None:
        """Force compact N oldest messages"""
        # Import here to avoid circular imports
        from .compaction_service import CompactionService

        compaction = CompactionService(self.api_client)
        new_messages = compaction.force_compact_messages(self.messages, n)
        self.set_messages(new_messages)

    def should_auto_compact(self) -> bool:
        """Check if auto-compaction should be triggered"""
        from aicoder.core.config import Config

        percentage = Config.context_compact_percentage()
        if percentage <= 0:
            return False  # Auto-compaction disabled

        # Use the estimated prompt size from stats (not string length)
        current_size = self.stats.current_prompt_size or 0
        max_size = Config.context_size()
        threshold = max_size * (percentage / 100)

        return current_size > threshold

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

    def get_tool_result_messages(self) -> List[Dict[str, Any]]:
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
                        # Update the token cache for this modified message
                        from .token_estimator import cache_message
                        cache_message(self.messages[message_index])
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

    def prune_keep_newest_tool_results(self, keep_count: int) -> int:
        """Keep only the newest N tool results, prune all others"""
        tool_messages = self.get_tool_result_messages()
        
        if keep_count >= len(tool_messages):
            return 0  # Nothing to prune
        
        # Prune all except the last keep_count messages
        prune_count = len(tool_messages) - keep_count
        indices = list(range(prune_count))
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

    def prune_old_summaries(self) -> int:
        """Keep only the last [SUMMARY] message, remove all older ones.

        This is the 'highlander' mode - there can be only one [SUMMARY].
        Useful when context is cluttered with many compaction summaries.
        """
        summary_indices = []
        for i, msg in enumerate(self.messages):
            content = self._get_content_as_string(msg.get("content", ""))
            if content and content.startswith("[SUMMARY]"):
                summary_indices.append(i)

        if len(summary_indices) <= 1:
            return 0  # Nothing to prune

        # Keep only the last summary
        keep_index = summary_indices[-1]
        prune_indices = summary_indices[:-1]

        pruned_count = 0
        for idx in sorted(prune_indices, reverse=True):
            self.messages.pop(idx)
            pruned_count += 1

        self.estimate_context()
        return pruned_count

    def keep_last_message(self) -> int:
        """Keep only the last message, remove all others.

        This is the 'highlight-message' (hm) mode - keep only the most recent
        message regardless of its type (could be a summary, assistant response, etc.).
        Useful when you want to ask AI to create a detailed summary and keep only that.

        If the last message is not a user message (or is a summary), a placeholder
        user message is inserted before it to ensure the first chat message is always
        a user message.
        """
        if len(self.messages) <= 1:
            return 0  # Nothing to remove

        # Keep only the last message
        last_message = self.messages[-1]
        original_count = len(self.messages)

        # Check if last message needs a placeholder before it
        # Needs placeholder if: not a user message, OR is a summary (even if role is user)
        content = self._get_content_as_string(last_message.get("content", ""))
        needs_placeholder = (
            last_message.get("role") != "user" or
            (content and content.startswith("[SUMMARY]"))
        )

        if needs_placeholder:
            placeholder = {"role": "user", "content": "..."}
            self.messages = [placeholder, last_message]
        else:
            self.messages = [last_message]

        pruned_count = original_count - len(self.messages)

        self.estimate_context()
        return pruned_count
