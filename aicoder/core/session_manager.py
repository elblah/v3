"""
Session Manager - Handles AI session processing workflow
Extracted from AICoder class for better separation of concerns
"""

from typing import Dict, Any, List

from aicoder.core.config import Config
from aicoder.utils.log import LogUtils, LogOptions


class SessionManager:
    """Handles the main AI session processing workflow"""

    def __init__(self, message_history, streaming_client, stream_processor, tool_executor, 
                 context_bar, stats, compaction_service):
        self.message_history = message_history
        self.streaming_client = streaming_client
        self.stream_processor = stream_processor
        self.tool_executor = tool_executor
        self.context_bar = context_bar
        self.stats = stats
        self.compaction_service = compaction_service
        self.is_processing = False

    def process_with_ai(self) -> None:
        """Process conversation with AI"""
        if Config.debug():
            LogUtils.debug("*** process_with_ai called")

        self.is_processing = True

        try:
            preparation = self._prepare_for_processing()
            if Config.debug():
                LogUtils.debug(
                    f"*** prepare_for_processing returned should_continue={preparation.get('should_continue')}"
                )
            if not preparation["should_continue"]:
                return

            self.streaming_client.reset_colorizer()

            streaming_result = self._stream_response(preparation["messages"])
            if not streaming_result["should_continue"]:
                return

            has_tool_calls = self._validate_and_process_tool_calls(
                streaming_result["full_response"],
                streaming_result["accumulated_tool_calls"],
            )

            self._handle_post_processing(has_tool_calls)

        except Exception as e:
            self._handle_processing_error(e)
        finally:
            self.is_processing = False

    def _prepare_for_processing(self) -> Dict[str, Any]:
        """Prepare for AI processing"""
        # Handle compaction
        if Config.auto_compact_enabled():
            current_size = self.stats.current_prompt_size or 0
            if current_size > Config.context_size():
                self._force_compaction()

        # Show context bar before AI response
        print()
        self.context_bar.print_context_bar(self.stats, self.message_history)
        LogUtils.print("AI: ", LogOptions(color=Config.colors["cyan"], bold=True))

        # Check if interrupted
        if not self.is_processing:
            print("\n[AI response interrupted before starting]")
            return {"should_continue": False, "messages": []}

        messages = self.message_history.get_messages()
        return {"should_continue": True, "messages": messages}

    def _stream_response(self, messages: List[Dict[str, Any]]) -> Dict[str, Any]:
        """Stream response from API"""
        if Config.debug():
            LogUtils.debug(f"*** stream_response called with {len(messages)} messages")

        # Use StreamProcessor to handle the streaming
        result = self.stream_processor.process_stream(
            messages,
            lambda: self.is_processing,  # is_processing_callback
            self.stream_processor.accumulate_tool_call  # process_chunk_callback
        )

        # Handle error case by adding to message history
        if result.get("error"):
            self.message_history.add_assistant_message(
                {"content": f"[API Error: {result['error']}]"}
            )

        return result

    def _validate_and_process_tool_calls(
        self, full_response: str, accumulated_tool_calls: dict
    ) -> bool:
        """Validate and process accumulated tool calls"""
        if not accumulated_tool_calls:
            self._handle_empty_response(full_response)
            return False

        valid_tool_calls = self._validate_tool_calls(accumulated_tool_calls)
        if not valid_tool_calls:
            LogUtils.error("No valid tool calls to execute")
            return False

        # Add assistant message with tool calls
        tool_calls_for_message = []
        for i, call in enumerate(valid_tool_calls):
            tool_calls_for_message.append(
                {
                    "id": call.get("id"),
                    "type": call.get("type", "function"),
                    "function": {
                        "name": call.get("function", {}).get("name"),
                        "arguments": call.get("function", {}).get("arguments"),
                    },
                    "index": i,
                }
            )

        self.message_history.add_assistant_message(
            {
                "content": full_response or "I'll help you with that.",
                "tool_calls": tool_calls_for_message,
            }
        )

        self.tool_executor.execute_tool_calls(valid_tool_calls)
        return True

    def _handle_post_processing(self, has_tool_calls: bool) -> None:
        """Handle post-processing after AI response"""
        # Check if user requested guidance mode (stop after current tool)
        if self.tool_executor.is_guidance_mode():
            LogUtils.success("[*] Guidance mode: Your turn - tell the AI how to proceed")
            self.tool_executor.clear_guidance_mode()
            return

        if has_tool_calls and self.is_processing and self.message_history.should_auto_compact():
            self._perform_auto_compaction()

        if has_tool_calls and self.is_processing:
            # Continue processing for recursive tool calls
            self.process_with_ai()

    def _handle_processing_error(self, error: Exception) -> None:
        """Handle processing errors"""
        LogUtils.error(f"Processing error: {error}")

    def _handle_empty_response(self, full_response: str) -> None:
        """Handle empty response from AI"""
        if full_response and full_response.strip() != "":
            # AI provided text response but no tools

            self.message_history.add_assistant_message(
                {"content": full_response}
            )
            print("")
        else:
            # AI provided no text response (this is normal when AI has nothing to say)
            # Add a minimal message to show AI responded, then continue

            self.message_history.add_assistant_message({"content": ""})
            print("")

    def _validate_tool_calls(self, tool_calls: dict) -> list:
        """Validate tool calls"""
        return [
            tool_call
            for tool_call in tool_calls.values()
            if tool_call.get("function", {}).get("name") and tool_call.get("id")
        ]

    def _force_compaction(self) -> None:
        """Force compaction of messages (compacts 1 oldest round)"""
        try:
            self.message_history.force_compact_rounds(1)
        except Exception as e:
            LogUtils.error(f"Force compaction failed: {e}")

    def _perform_auto_compaction(self) -> None:
        """Perform automatic compaction"""
        try:
            self.message_history.compact_memory()
        except Exception as e:
            if Config.debug():
                LogUtils.warn(f"[!] Auto-compaction failed: {e}")