"""
Centralized compaction service - clean, simple, focused
Takes messages, returns compacted messages. That's it.
 - synchronous version
"""

from typing import List, Dict, Any, Optional
from dataclasses import dataclass

from aicoder.utils.log import LogUtils
from aicoder.core.config import Config


@dataclass
class MessageGroup:
    """Group of messages that should stay together"""
    messages: List[Dict[str, Any]]
    is_summary: bool
    is_user_turn: bool  # true if this starts with user message


class CompactionService:
    """Simple compaction service with clean interfaces"""

    def __init__(self, api_client):
        self.api_client = api_client
        # Streaming client for API calls
        self.streaming_client = None
        if api_client:
            self.streaming_client = api_client

    @staticmethod
    def _get_content_as_string(content: Any) -> Optional[str]:
        """Safely get message content as string (handles both string and list types).
        Returns None if content contains images (should be filtered out)."""
        if isinstance(content, list):
            # For multi-modal messages, check for images
            for item in content:
                if isinstance(item, dict) and item.get("type") == "image_url":
                    return None  # Discard messages with images
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

    def compact(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Compact messages using sliding window + AI summarization"""
        if len(messages) <= 3:
            return messages  # Too short to compact

        # Extract summaries and find where to insert new summary
        system_message = messages[0]
        other_summaries = []
        messages_to_compact = []

        for i, msg in enumerate(messages):
            # Skip messages with images
            if self._has_image_content(msg):
                continue
            content = self._get_content_as_string(msg.get("content", ""))
            if content and content.startswith("[SUMMARY]"):
                other_summaries.append(msg)
            elif i == 0 and msg.get("role") == "system":
                # Skip system message for now, add it back later
                continue
            else:
                messages_to_compact.append(msg)

        # Group only non-summary messages for compaction
        groups = self.group_messages(messages_to_compact)
        recent_groups = groups[-Config.compact_protect_rounds():] if len(groups) > Config.compact_protect_rounds() else []
        old_groups = groups[:len(groups) - len(recent_groups)] if len(recent_groups) < len(groups) else []

        if len(old_groups) == 0:
            return messages  # Nothing old enough to compact

        try:
            summary = self._get_ai_summary(old_groups)
            if summary is None:
                return messages  # Summary failed validation, skip compaction
            summary_message = self._create_summary_message(summary)

            # Rebuild: system + existing summaries + new summary + recent messages
            recent_messages = []
            for g in recent_groups:
                recent_messages.extend(g.messages)
            new_messages: List[Dict[str, Any]] = [
                system_message,
                *other_summaries,
                summary_message,
                *recent_messages,
            ]

            return new_messages
        except Exception as e:
            LogUtils.error(f"[X] Compaction failed: {e}")
            raise e  # Re-throw to let caller handle it

    def force_compact_rounds(self, messages: List[Dict[str, Any]], n: int) -> List[Dict[str, Any]]:
        """Force compact conversation rounds.

        Args:
            messages: List of message dicts
            n: Number of rounds to compact.
               Positive: compact N oldest rounds
               Negative: keep only |N| newest rounds, compact everything else
        """
        rounds = self._identify_rounds(messages)
        if len(rounds) == 0:
            return messages

        if n < 0:
            # Negative: keep only |n| newest rounds, compact the rest
            keep_count = abs(n)
            rounds_to_compact = rounds[:max(0, len(rounds) - keep_count)]
        else:
            # Positive: compact N oldest rounds
            rounds_to_compact = rounds[:min(n, len(rounds))]

        if len(rounds_to_compact) == 0:
            return messages

        messages_to_compact = []
        for round in rounds_to_compact:
            messages_to_compact.extend(round.messages)
        # Filter out any summary messages and image messages from compaction
        filtered_messages = []
        for msg in messages_to_compact:
            if self._has_image_content(msg):
                continue
            content = self._get_content_as_string(msg.get("content", ""))
            if content and not content.startswith("[SUMMARY]"):
                filtered_messages.append(msg)

        if len(filtered_messages) == 0:
            return messages

        summary = self._get_ai_summary(
            [
                MessageGroup(
                    messages=[msg],
                    is_summary=False,
                    is_user_turn=False,
                )
                for msg in filtered_messages
            ]
        )
        if summary is None:
            return messages  # Summary failed validation, skip compaction
        summary_message = self._create_summary_message(summary)

        return self._replace_messages_with_summary(messages, filtered_messages, summary_message)

    def force_compact_messages(self, messages: List[Dict[str, Any]], n: int) -> List[Dict[str, Any]]:
        """Force compact individual messages.

        Args:
            messages: List of message dicts
            n: Number of messages to compact.
               Positive: compact N oldest messages
               Negative: keep only |N| newest messages, compact rest
        """
        eligible_messages = []
        for msg in messages:
            if msg.get("role") == "system":
                continue
            if self._has_image_content(msg):
                continue
            content = self._get_content_as_string(msg.get("content", ""))
            if content and not content.startswith("[SUMMARY]"):
                eligible_messages.append(msg)

        if len(eligible_messages) == 0:
            return messages

        if n < 0:
            # Negative: keep only |n| newest messages, compact the rest
            keep_count = abs(n)
            messages_to_compact = eligible_messages[:max(0, len(eligible_messages) - keep_count)]
        else:
            # Positive: compact N oldest messages
            messages_to_compact = eligible_messages[:min(n, len(eligible_messages))]

        if len(messages_to_compact) == 0:
            return messages

        summary = self._get_ai_summary(
            [
                MessageGroup(
                    messages=[msg],
                    is_summary=False,
                    is_user_turn=False,
                )
                for msg in messages_to_compact
            ]
        )
        if summary is None:
            return messages  # Summary failed validation, skip compaction
        summary_message = self._create_summary_message(summary)

        return self._replace_messages_with_summary(messages, messages_to_compact, summary_message)

    def group_messages(self, messages: List[Dict[str, Any]]) -> List[MessageGroup]:
        """Group messages into atomic units (tool calls stay with responses)"""
        groups: List[MessageGroup] = []
        current: List[Dict[str, Any]] = []

        for msg in messages:
            # Skip messages with images
            if self._has_image_content(msg):
                continue

            current.append(msg)

            # Complete group at tool result OR new user message (not first)
            if msg.get("role") == "tool" or (msg.get("role") == "user" and len(current) > 1):
                content = self._get_content_as_string(current[0].get("content", "")) if current[0] else ""
                groups.append(
                    MessageGroup(
                        messages=list(current),
                        is_summary=bool(content and content.startswith("[SUMMARY]")),
                        is_user_turn=current[0].get("role") == "user",
                    )
                )
                current = [msg] if msg.get("role") == "user" else []

        if len(current) > 0:
            content = self._get_content_as_string(current[0].get("content", "")) if current[0] else ""
            groups.append(
                MessageGroup(
                    messages=current,
                    is_summary=bool(content and content.startswith("[SUMMARY]")),
                    is_user_turn=current[0].get("role") == "user",
                )
            )

        return groups

    def _identify_rounds(self, messages: List[Dict[str, Any]]) -> List[MessageGroup]:
        """Identify conversation rounds"""
        rounds: List[MessageGroup] = []
        current_round: List[Dict[str, Any]] = []

        for msg in messages:
            # Skip messages with images
            if self._has_image_content(msg):
                continue

            content = self._get_content_as_string(msg.get("content", ""))
            if msg.get("role") == "system" or (content and content.startswith("[SUMMARY]")):
                continue  # Skip system and summary messages

            current_round.append(msg)

            # Round ends at next user message
            if msg.get("role") == "user" and len(current_round) > 1:
                content_first = self._get_content_as_string(current_round[0].get("content", "")) if current_round[0] else ""
                if len(current_round) > 1:
                    rounds.append(
                        MessageGroup(
                            messages=list(current_round[:-1]),
                            is_summary=bool(content_first and content_first.startswith("[SUMMARY]")),
                            is_user_turn=current_round[0].get("role") == "user",
                        )
                    )
                current_round = [msg]  # Start new round

        if len(current_round) > 0:
            content_first = self._get_content_as_string(current_round[0].get("content", "")) if current_round[0] else ""
            rounds.append(
                MessageGroup(
                    messages=current_round,
                    is_summary=bool(content_first and content_first.startswith("[SUMMARY]")),
                    is_user_turn=current_round[0].get("role") == "user",
                )
            )

        return rounds

    def _get_ai_summary(self, groups: List[MessageGroup]) -> Optional[str]:
        """Get AI summary using existing streaming client"""
        messages = []
        for g in groups:
            messages.extend(g.messages)
        messages_to_summarize = []
        for msg in messages:
            if self._has_image_content(msg):
                continue
            content = self._get_content_as_string(msg.get("content", ""))
            if content and not content.startswith("[SUMMARY]"):
                messages_to_summarize.append(msg)

        if len(messages_to_summarize) == 0:
            return "No previous content"

        prompt = f"""Based on the conversation below:

Numbered conversation to analyze:
{self._format_messages_for_summary(messages_to_summarize)}

---
Provide a detailed but concise summary of our conversation above. Focus on information that would be helpful for continuing the conversation, including what we did, what we're doing, which files we're working on, and what we're going to do next. Generate at least 1000 if you have enough information available to do so."""

        try:
            system_prompt = """You are a helpful AI assistant tasked with summarizing conversations.

When asked to summarize, provide a detailed but concise summary of the conversation.
Focus on information that would be helpful for continuing the conversation, including:

- What was done
- What is currently being worked on
- Which files are being modified
- What needs to be done next

Your summary should be comprehensive enough to provide context but concise enough to be quickly understood."""

            if not self.streaming_client:
                LogUtils.warn("[!] No streaming client available for summarization")
                return f"Previous conversation condensed: {len(messages_to_summarize)} messages"

            # Build messages for summarization
            summary_messages: List[Dict[str, Any]] = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ]

            # Non-streaming request to get complete summary
            full_response = ""
            for chunk in self.streaming_client.stream_request(
                summary_messages,
                stream=False,
                throw_on_error=True,
                send_tools=False
            ):
                content = chunk.get("choices", [{}])[0].get("delta", {}).get("content", "")
                if content:
                    full_response += content

            if not self._validate_summary(full_response):
                LogUtils.warn("[!] Generated summary too short - skipping compaction")
                return None  # Signal to skip compaction

            return full_response or "Conversation summarized"

        except Exception as e:
            raise Exception(f"AI summarization failed: {e}")

    def _format_messages_for_summary(self, messages: List[Dict[str, Any]]) -> str:
        """Format messages for AI summarization with temporal tagging (Python strategy)"""
        total_messages = len(messages)
        result = []

        for i, msg in enumerate(messages):
            role = msg.get("role")
            content = self._get_content_as_string(msg.get("content", ""))

            # Skip messages with no text content
            if not content:
                continue

            # Calculate temporal position (Python's exact strategy)
            current_index = i + 1
            position_ratio = current_index / total_messages
            position_percent = position_ratio * 100

            # Add temporal priority indicator
            if position_percent >= 80:
                priority = "🔴 VERY RECENT (Last 20%)"
            elif position_percent >= 60:
                priority = "🟡 RECENT (Last 40%)"
            elif position_percent >= 30:
                priority = "🟢 MIDDLE"
            else:
                priority = "🔵 OLD (First 30%)"

            prefix = f"[{current_index:03d}/{total_messages}] {priority} "

            # Format based on role with enhanced details
            if role == "assistant":
                tool_calls = msg.get("tool_calls", [])
                if tool_calls and len(tool_calls) > 0:
                    tool_info = "\n".join(
                        f"Tool Call: {call.get('function', {}).get('name', 'unknown')}({call.get('function', {}).get('arguments', '{}')})"
                        for call in tool_calls
                    )
                    result.append(f"{prefix} Assistant: {content}\n{tool_info}")
                else:
                    result.append(f"{prefix} Assistant: {content}")
            elif role == "tool":
                tool_call_id = msg.get("tool_call_id", "unknown")
                tool_content = content

                # Truncate very long tool results for summarization
                if len(tool_content) > 500:
                    tool_content = tool_content[:500] + "... (truncated for summarization)"

                result.append(f"{prefix} Tool Result (ID: {tool_call_id}): {tool_content}")
            elif role == "user":
                result.append(f"{prefix} User: {content}")
            else:
                result.append(f"{prefix} {role.capitalize() if role else 'Unknown'}: {content}")

            result.append("---")

        return "\n".join(result)

    def _validate_summary(self, summary: str) -> bool:
        """Validate summary quality"""
        return bool(summary and len(summary) >= 50)

    def _create_summary_message(self, summary: str) -> Dict[str, Any]:
        """Create summary message (user role to avoid model issues)"""
        return {
            "role": "user",
            "content": f"[SUMMARY] {summary}",
        }

    def _replace_messages_with_summary(
        self,
        messages: List[Dict[str, Any]],
        to_replace: List[Dict[str, Any]],
        summary: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Replace a range of messages with summary"""
        if len(to_replace) == 0:
            return messages

        # Find indices by matching content and role (more reliable than object reference)
        first_index = -1
        for i, msg in enumerate(messages):
            if msg.get("role") == to_replace[0].get("role") and msg.get("content") == to_replace[0].get("content"):
                first_index = i
                break

        if first_index == -1:
            return messages

        # Find last index by matching last message in to_replace
        last_message_to_replace = to_replace[-1]
        last_index = -1
        for i, msg in enumerate(messages):
            if (i >= first_index and
                    msg.get("role") == last_message_to_replace.get("role") and
                    msg.get("content") == last_message_to_replace.get("content")):
                last_index = i
                break

        actual_last_index = last_index if last_index != -1 else first_index + len(to_replace) - 1

        return messages[:first_index] + [summary] + messages[actual_last_index + 1:]
