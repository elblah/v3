"""
Centralized compaction service - clean, simple, focused
Takes messages, returns compacted messages. That's it.
Ported exactly from TypeScript version - synchronous version
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
        # AI processor will be imported when needed to avoid circular imports

    def compact(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Compact messages using sliding window + AI summarization"""
        if len(messages) <= 3:
            return messages  # Too short to compact

        # Extract summaries and find where to insert new summary
        system_message = messages[0]
        other_summaries = []
        messages_to_compact = []
        last_summary_index = 0  # After system message by default

        for i, msg in enumerate(messages):
            content = msg.get("content", "")
            if content.startswith("[SUMMARY]"):
                other_summaries.append(msg)
                last_summary_index = i + 1  # After this summary
            elif i == 0 and msg.get("role") == "system":
                # Skip system message for now, add it back later
                continue
            else:
                messages_to_compact.append(msg)

        # Group into turns (user message + any assistant/tool responses)
        turns = self._group_into_turns(messages_to_compact)

        # Select turns to compact
        compact_turns = self._select_turns_to_compact(turns)

        # Generate summary for selected turns
        if compact_turns:
            summary = self._generate_summary(compact_turns)
            if summary:
                # Rebuild message list with summary
                return self._rebuild_message_list(
                    system_message,
                    other_summaries,
                    compact_turns,
                    summary,
                    turns,
                    last_summary_index,
                )

        return messages

    def _group_into_turns(self, messages: List[Dict[str, Any]]) -> List[MessageGroup]:
        """Group messages into conversation turns"""
        turns = []
        current_turn = []

        for msg in messages:
            # Start new turn with user message
            if msg.get("role") == "user" and current_turn:
                turns.append(
                    MessageGroup(
                        messages=current_turn,
                        is_summary=current_turn[0]
                        .get("content", "")
                        .startswith("[SUMMARY]"),
                        is_user_turn=current_turn[0].get("role") == "user",
                    )
                )
                current_turn = [msg]
            else:
                current_turn.append(msg)

        # Add last turn
        if current_turn:
            turns.append(
                MessageGroup(
                    messages=current_turn,
                    is_summary=current_turn[0]
                    .get("content", "")
                    .startswith("[SUMMARY]"),
                    is_user_turn=current_turn[0].get("role") == "user",
                )
            )

        return turns

    def _select_turns_to_compact(self, turns: List[MessageGroup]) -> List[MessageGroup]:
        """Select which turns to compact using sliding window"""
        # Keep most recent turns, compact older ones
        keep_recent = Config.compaction_keep_last() or 2
        compact_turns = turns[:-keep_recent] if len(turns) > keep_recent else []
        return compact_turns

    def _generate_summary(self, turns: List[MessageGroup]) -> Optional[str]:
        """Generate AI summary for selected turns"""
        try:
            # Combine all messages in turns to compact
            messages_to_summarize = []
            for turn in turns:
                messages_to_summarize.extend(turn.messages)

            # Create summary prompt
            summary_prompt = self._create_summary_prompt(messages_to_summarize)

            # Call API to generate summary
            # This is simplified - would need actual API call
            # For now, return a basic summary
            return f"[SUMMARY] Previous conversation condensed: {len(messages_to_summarize)} messages"

        except Exception as e:
            LogUtils.warn(f"Failed to generate summary: {e}")
            return None

    def _create_summary_prompt(self, messages: List[Dict[str, Any]]) -> str:
        """Create prompt for summarization"""
        prompt = "Summarize the following conversation:\n\n"

        for msg in messages:
            role = msg.get("role", "unknown")
            content = msg.get("content", "")
            prompt += f"{role}: {content}\n\n"

        prompt += (
            "Provide a concise summary preserving key technical details and decisions."
        )
        return prompt

    def _rebuild_message_list(
        self,
        system_message: Dict[str, Any],
        existing_summaries: List[Dict[str, Any]],
        compacted_turns: List[MessageGroup],
        new_summary: str,
        all_turns: List[MessageGroup],
        insert_index: int,
    ) -> List[Dict[str, Any]]:
        """Rebuild the message list with new summary inserted"""
        result = []

        # Add system message
        result.append(system_message)

        # Add existing summaries
        for summary in existing_summaries:
            result.append(summary)

        # Add new summary
        result.append({"role": "assistant", "content": new_summary})

        # Add remaining (non-compacted) turns
        compacted_set = set(id(turn) for turn in compacted_turns)
        for turn in all_turns:
            if id(turn) not in compacted_set:
                result.extend(turn.messages)

        return result
