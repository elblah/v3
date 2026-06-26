"""
SUMMARON Plugin - Context Digestion via Summary Tags

Automatically manages conversation context by digesting messages that have <summary> tags:
- Each user prompt creates a round with its own [SUMMARON] message
- Extracts <summary> tags from AI responses into [SUMMARON] bullet lists
- Keeps working space at threshold% by digesting oldest summary blocks
- Digestion finds oldest <summary>, adds it to [SUMMARON], deletes everything up to it
- Preserves: user messages, system messages, ALL tagged messages (anything starting with [)
- Prevents infinite loops with progress tracking
- Only digests rounds that have summaries (no information loss)

Commands:
/summaron status  - Show current status
/summaron set N   - Set working threshold (default: 50)
/summaron limit N - Set total [SUMMARON] limit (default: 100k)
/summaron rounds  - Show all rounds and their sizes
/summaron digest N - Manually digest N oldest summary blocks
/summaron enable/disable - Toggle auto-digestion
"""

import os
import re

from aicoder.core.config import Config
from aicoder.utils.log import LogUtils


def create_plugin(ctx):
    """Create SUMMARON plugin"""

    class SummaronPlugin:
        def __init__(self, ctx):
            self.app = ctx.app
            self.enabled = os.getenv("SUMMARON_ENABLED", "1") == "1"
            self.threshold = int(os.getenv("SUMMARON_THRESHOLD", "50"))
            self.limit = int(os.getenv("SUMMARON_LIMIT", "100000"))

        def cleanup(self):
            pass

        def _estimate_tokens(self, text: str) -> int:
            """Rough token estimation: 1 token ≈ 4 characters"""
            return len(text) // 4

        def _get_active_context_size(self) -> int:
            """Calculate active context size (excluding all [SUMMARON] messages)"""
            total = 0
            for msg in self.app.message_history.messages:
                content = msg.get("content", "")
                if isinstance(content, list):
                    # Handle multimodal content
                    for item in content:
                        if isinstance(item, dict) and "text" in item:
                            total += self._estimate_tokens(item["text"])
                else:
                    if not content.startswith("[SUMMARON]"):
                        total += self._estimate_tokens(content)

            return max(total, 0)

        def _find_rounds(self):
            """Find all rounds in conversation"""
            rounds = []
            messages = self.app.message_history.messages

            current_round = None

            for idx, msg in enumerate(messages):
                role = msg.get("role")
                content = msg.get("content", "")

                if role == "user":
                    # Start of new round
                    if current_round:
                        rounds.append(current_round)

                    current_round = {
                        "start": idx,
                        "end": idx + 1,
                        "user_msg": content,
                        "has_summaron": False,
                        "summaron_idx": None
                    }
                elif current_round and isinstance(content, str) and content.startswith("[SUMMARON]"):
                    # Found [SUMMARON] for this round
                    current_round["has_summaron"] = True
                    current_round["summaron_idx"] = idx
                    current_round["end"] = idx + 1
                elif current_round:
                    # Part of current round
                    current_round["end"] = idx + 1

            # Add last round
            if current_round:
                rounds.append(current_round)

            return rounds

        def _create_round_summaron(self, user_msg_idx):
            """Create [SUMMARON] right after user message"""
            summaron_msg = {
                "role": "user",
                "content": """[SUMMARON]

IMPORTANT: Always include <summary> tags in your responses!

Your summary should be INCREMENTAL - only add NEW information from THIS message, don't repeat system prompt or context.

CRITICAL: Do NOT include:
- System prompt information (your capabilities, skills, etc.)
- Context from earlier in the conversation
- General knowledge about yourself

ONLY include:
- What we learned/did in THIS specific response
- New findings from tools (if any)
- New files examined (if any)
- Changes made (file paths, line numbers)
- Current state update
- Next steps or pending issues

<summary>
- (Only new information from THIS response)
</summary>

The [SUMMARON] list below accumulates your summary points across the conversation.
"""
            }
            self.app.message_history.messages.insert(user_msg_idx + 1, summaron_msg)

            # Reestimate context size
            self.app.message_history.estimate_context()

            return user_msg_idx + 1

        def _get_current_round_summaron_idx(self):
            """Find [SUMMARON] index for current (last) round"""
            messages = self.app.message_history.messages

            # Find last user message, then [SUMMARON] after it
            for idx in range(len(messages) - 1, -1, -1):
                if messages[idx].get("role") == "user":
                    # Check if [SUMMARON] exists after this
                    if idx + 1 < len(messages):
                        next_msg = messages[idx + 1]
                        content = next_msg.get("content", "")
                        if isinstance(content, str) and content.startswith("[SUMMARON]"):
                            return idx + 1
                    break

            return None

        def _add_to_current_summaron(self, summary_text):
            """Add summary to current round's [SUMMARON]"""
            summaron_idx = self._get_current_round_summaron_idx()

            if summaron_idx is not None:
                msg = self.app.message_history.messages[summaron_idx]
                content = msg.get("content", "")
                if isinstance(content, str):
                    # Add summary with proper formatting (may already have bullets)
                    if not summary_text.startswith('-'):
                        msg["content"] += f"- {summary_text}\n"
                    else:
                        msg["content"] += f"{summary_text}\n"

        def _extract_summary(self, message):
            """Extract <summary> tag content from message"""
            content = message.get("content", "")
            if isinstance(content, str):
                # Find <summary> tag
                match = re.search(r'<summary>(.*?)</summary>', content, re.DOTALL)
                if match:
                    return match.group(1).strip()
            return None

        def _find_oldest_summary_message(self):
            """Find the oldest assistant message with <summary> tag"""
            messages = self.app.message_history.messages

            for idx, msg in enumerate(messages):
                if msg.get("role") == "assistant":
                    content = msg.get("content", "")
                    if isinstance(content, str) and "<summary>" in content:
                        return idx

            return None

        def _digest_oldest_summary(self):
            """
            Find oldest message with <summary>, add to [SUMMARON], delete everything up to it
            Keeps: user messages, system messages, all tagged messages (anything starting with [)
            Returns True if digestion happened, False otherwise
            """
            summary_idx = self._find_oldest_summary_message()
            if summary_idx is None:
                return False

            # Find the [SUMMARON] for this round (after user message)
            # Work backwards to find user message, then [SUMMARON]
            summaron_idx = None
            user_msg_idx = None

            for idx in range(summary_idx, -1, -1):
                msg = self.app.message_history.messages[idx]
                if msg.get("role") == "user":
                    # Skip [SUMMARON] messages
                    content = msg.get("content", "")
                    if isinstance(content, str) and content.startswith("[SUMMARON]"):
                        continue
                    user_msg_idx = idx
                    # Check if [SUMMARON] exists after this
                    if idx + 1 < len(self.app.message_history.messages):
                        next_msg = self.app.message_history.messages[idx + 1]
                        content = next_msg.get("content", "")
                        if isinstance(content, str) and content.startswith("[SUMMARON]"):
                            summaron_idx = idx + 1
                    break

            if summaron_idx is None:
                # No [SUMMARON] found, create one after user message
                summaron_idx = self._create_round_summaron(user_msg_idx)

            # Extract summary content and add to [SUMMARON]
            summary_msg = self.app.message_history.messages[summaron_idx]
            assistant_msg = self.app.message_history.messages[summary_idx]
            summary_content = self._extract_summary(assistant_msg)

            if summary_content:
                # Add summary content (may already have bullet points)
                if not summary_content.startswith('-'):
                    summary_msg["content"] += f"- {summary_content}\n"
                else:
                    summary_msg["content"] += f"{summary_content}\n"

            # Now delete everything from start of messages up to and including the summary message
            # But keep: user messages, system messages, ALL tagged messages (anything starting with [)
            messages = self.app.message_history.messages

            # Delete backwards to preserve indices
            # Delete everything before user_msg_idx (previous rounds, non-essential)
            # Delete everything after user_msg_idx up to summary_idx (tool calls, results, assistant message)
            # Keep: user_msg_idx and summaron_idx

            # First, find what to keep
            keep_indices = set()
            for idx in range(len(messages)):
                msg = messages[idx]
                role = msg.get("role")
                content = msg.get("content", "")

                # Keep user and system messages
                if role in ("user", "system"):
                    keep_indices.add(idx)

                # Keep ALL tagged messages (anything starting with [)
                if isinstance(content, str) and content.startswith("["):
                    keep_indices.add(idx)

            # Delete everything from start to summary_idx that's not in keep_indices
            for idx in range(summary_idx, -1, -1):
                if idx not in keep_indices:
                    del messages[idx]

            return True

        def _maybe_digest(self):
            """Check threshold and digest oldest rounds if needed"""
            if not self.enabled:
                return

            active_context = self._get_active_context_size()
            max_tokens = Config.context_size()
            percentage = (active_context / max_tokens) * 100 if max_tokens else 0

            if percentage > self.threshold:
                # Find oldest message with <summary> and digest everything up to it
                # Repeat until below threshold
                digested_count = 0
                prev_percentage = percentage
                stuck_count = 0

                while percentage > self.threshold:
                    if not self._digest_oldest_summary():
                        # No more summaries to digest
                        break

                    digested_count += 1

                    # Reestimate context
                    self.app.message_history.estimate_context()
                    active_context = self._get_active_context_size()
                    percentage = (active_context / max_tokens) * 100 if max_tokens else 0

                    # Safety: break if percentage isn't decreasing (infinite loop prevention)
                    if percentage >= prev_percentage:
                        stuck_count += 1
                        if stuck_count >= 3:
                            LogUtils.print("[SUMMARON] Warning: Can't reduce context further. Stopping digestion.")
                            break
                    else:
                        stuck_count = 0
                    prev_percentage = percentage

                if digested_count > 0:
                    LogUtils.print(f"[SUMMARON] Digested {digested_count} summary block(s) ({percentage:.0f}% active)")

        def _check_summary_tag(self):
            """Check if last assistant message included <summary> tag"""
            messages = self.app.message_history.messages

            # Find last assistant message
            for msg in reversed(messages):
                if msg.get("role") == "assistant":
                    content = msg.get("content", "")

                    if isinstance(content, str) and "<summary>" not in content:
                        # Add reminder with helpful format
                        reminder = """[REMINDER] Please include a <summary> tag in your response!

CRITICAL: Do NOT include system prompt, context, or general knowledge about yourself.

ONLY include NEW information from THIS response:
- What we learned/did in THIS response
- New findings from tools (if any)
- New files examined (if any)
- Changes made (file paths, line numbers)
- Current state update
- Next steps or pending issues

Format:
<summary>
- (Only new information from THIS response)
</summary>
"""
                        self.app.message_history.add_user_message(reminder)
                    else:
                        # Extract summary and add to current [SUMMARON]
                        summary = self._extract_summary(msg)
                        if summary:
                            # Add the entire summary content (already has bullet points)
                            self._add_to_current_summaron(summary)

                    break

        def _get_status(self):
            """Get current status"""
            active_context = self._get_active_context_size()
            max_tokens = Config.context_size()
            percentage = (active_context / max_tokens) * 100 if max_tokens else 0

            # Calculate total [SUMMARON] size
            summaron_total = 0
            for msg in self.app.message_history.messages:
                content = msg.get("content", "")
                if isinstance(content, str) and content.startswith("[SUMMARON]"):
                    summaron_total += self._estimate_tokens(content)

            # Get round count
            rounds = self._find_rounds()

            return f"""SUMMARON Status:
- Enabled: {self.enabled}
- Working threshold: {self.threshold}%
- Active context: {percentage:.0f}% ({active_context:,} / {max_tokens:,} tokens)
- Total [SUMMARON]: {summaron_total:,} / {self.limit:,} tokens
- Rounds: {len(rounds)}

Commands:
/summaron set <N>     - Set working threshold (default: 50)
/summaron limit <N>    - Set total [SUMMARON] limit (default: 100k)
/summaron rounds       - Show all rounds
/summaron digest <N>   - Manually digest N oldest rounds
/summaron enable/disable - Toggle auto-digestion
"""

        def _cmd_handler(self, args_str):
            """Handle /summaron commands"""
            args = args_str.strip().split() if args_str.strip() else []

            if not args:
                return self._get_status()

            command = args[0]
            args_value = args[1] if len(args) > 1 else None

            if command == "status":
                return self._get_status()
            elif command == "set":
                if args_value:
                    try:
                        self.threshold = int(args_value)
                        return f"Working threshold set to {self.threshold}%"
                    except ValueError:
                        return "Usage: /summaron set <percentage>"
            elif command == "limit":
                if args_value:
                    try:
                        self.limit = int(args_value)
                        return f"Total [SUMMARON] limit set to {self.limit:,} tokens"
                    except ValueError:
                        return "Usage: /summaron limit <tokens>"
            elif command == "rounds":
                rounds = self._find_rounds()
                if not rounds:
                    return "No rounds found"

                output = []
                for i, round_info in enumerate(rounds, 1):
                    user_msg = round_info["user_msg"][:50] + "..." if len(round_info["user_msg"]) > 50 else round_info["user_msg"]
                    has_summaron = round_info["has_summaron"]
                    output.append(f"Round {i}: {user_msg} [SUMMARON: {'Yes' if has_summaron else 'No'}]")

                return "\n".join(output)
            elif command == "digest":
                if args_value:
                    try:
                        n = int(args_value)
                        digested = 0
                        for _ in range(n):
                            if self._digest_oldest_summary():
                                digested += 1
                            else:
                                break

                        self.app.message_history.estimate_context()
                        return f"Digested {digested} summary block(s)"
                    except ValueError:
                        return "Usage: /summaron digest <number>"
                else:
                    # Digest one oldest summary
                    if self._digest_oldest_summary():
                        self.app.message_history.estimate_context()
                        return "Digested 1 summary block"
                    return "No summaries to digest"
            elif command in ("enable", "on"):
                self.enabled = True
                return "SUMMARON enabled"
            elif command in ("disable", "off"):
                self.enabled = False
                return "SUMMARON disabled"

            return f"Unknown command: {command}. Use: status, set, limit, rounds, digest, enable, disable"

        def _after_user_message_added(self, message):
            """Hook called after user message added - create round structure"""
            if not self.enabled:
                return

            # Find user message index
            idx = None
            for i, msg in enumerate(self.app.message_history.messages):
                if msg is message:
                    idx = i
                    break

            if idx is not None:
                # Create [SUMMARON] right after this user message
                self._create_round_summaron(idx)

        def _after_assistant_message_added(self, message):
            """Hook called after assistant message added"""
            if not self.enabled:
                return

            # Check for <summary> tag
            self._check_summary_tag()

            # Digest if needed
            self._maybe_digest()

        def _after_tool_results_added(self, message):
            """Hook called after tool results added"""
            if not self.enabled:
                return

            # Digest if needed (tool results add to context)
            self._maybe_digest()

        def _after_compaction(self):
            """Hook called after auto-compaction"""
            # Reset round structure if needed (auto-compaction handles cleanup)
            pass

        def _on_session_change(self):
            """Hook called when session changes"""
            # Cleanup on session change
            pass

    plugin = SummaronPlugin(ctx)

    # Register command
    ctx.register_command("summaron", plugin._cmd_handler,
                       description="SUMMARON round-based context digestion")

    # Register hooks
    ctx.register_hook("after_user_message_added", plugin._after_user_message_added)
    ctx.register_hook("after_assistant_message_added", plugin._after_assistant_message_added)
    ctx.register_hook("after_tool_results_added", plugin._after_tool_results_added)
    ctx.register_hook("after_compaction", plugin._after_compaction)
    ctx.register_hook("on_session_change", plugin._on_session_change)

    if Config.debug():
        LogUtils.print(f"[+] SUMMARON plugin loaded")
        LogUtils.print(f"  - Working threshold: {plugin.threshold}%")
        LogUtils.print(f"  - Total [SUMMARON] limit: {plugin.limit:,} tokens")
        LogUtils.print(f"  - /summaron commands available (status, set, limit, rounds, digest, enable, disable)")

    return {"cleanup": plugin.cleanup}
