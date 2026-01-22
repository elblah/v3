"""
Session Manager - Handles AI session processing workflow
Extracted from AICoder class for better separation of concerns
"""

import json
from typing import Dict, Any, List, Union

from aicoder.core.config import Config
from aicoder.utils.log import LogUtils, LogOptions


class SessionManager:
    """Handles the main AI session processing workflow"""

    def __init__(self, app):
        self.app = app
        self.message_history = app.message_history
        self.streaming_client = app.streaming_client
        self.stream_processor = app.stream_processor
        self.tool_executor = app.tool_executor
        self.context_bar = app.context_bar
        self.stats = app.stats
        self.compaction_service = app.compaction_service
        self.plugin_system = app.plugin_system
        self.is_processing = False

    def process_with_ai(self) -> None:
        """Process conversation with AI"""
        if Config.debug():
            LogUtils.debug("*** process_with_ai called")

        # Ensure all tool calls have corresponding responses before making API call
        self._ensure_tool_calls_have_responses()

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

            has_tool_calls, status = self._validate_and_process_tool_calls(
                streaming_result["full_response"],
                streaming_result["accumulated_tool_calls"],
            )

            self._handle_post_processing(has_tool_calls, status)

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
        LogUtils.print()
        self.context_bar.print_context_bar(self.stats, self.message_history)
        LogUtils.printc("AI: ", color="cyan", bold=True)

        # Check if interrupted
        if not self.is_processing:
            LogUtils.print("\n[AI response interrupted before starting]")
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
    ) -> tuple[bool, str]:
        """Validate and process accumulated tool calls
        
        Returns:
            tuple: (has_tool_calls, status) where status is one of:
                - "success": Tool calls executed successfully
                - "empty_response": No tool calls (normal conversation)
                - "validation_error": Tool calls had invalid JSON (error condition)
        """
        if not accumulated_tool_calls:
            self._handle_empty_response(full_response)
            return False, "empty_response"

        valid_tool_calls = self._validate_tool_calls(accumulated_tool_calls)
        if not valid_tool_calls:
            LogUtils.error("No valid tool calls to execute")
            # Add user message to inform AI about the JSON validation failure
            self.message_history.add_user_message(
                "ERROR: The tool calls you sent had invalid JSON format and could not be processed. Please try again with properly formatted JSON."
            )
            return False, "validation_error"

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
        return True, "success"

    def _handle_post_processing(self, has_tool_calls: bool, status: str) -> None:
        """Handle post-processing after AI response"""
        # Check if user requested guidance mode (stop after current tool)
        if self.tool_executor.is_guidance_mode():
            LogUtils.success("[*] Guidance mode: Your turn - tell the AI how to proceed")
            self.tool_executor.clear_guidance_mode()
            return

        # Call plugin hooks after AI processing
        if self.plugin_system:
            hook_results = self.plugin_system.call_hooks("after_ai_processing", has_tool_calls)
            if hook_results:
                for result in hook_results:
                    if result and isinstance(result, str):
                        self.app.set_next_prompt(result)

        if has_tool_calls and self.is_processing and self.message_history.should_auto_compact():
            self._perform_auto_compaction()

        # Continue processing only when appropriate
        if self.is_processing:
            if has_tool_calls:
                # Continue processing for recursive tool calls
                self.process_with_ai()
            elif status == "validation_error":
                # Continue processing to allow AI to respond to validation error
                self.process_with_ai()
            # status == "empty_response": Normal conversation, don't continue

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
            LogUtils.print("")
        else:
            # AI provided no text response (this is normal when AI has nothing to say)
            # Add a minimal message to show AI responded, then continue

            self.message_history.add_assistant_message({"content": ""})
            LogUtils.print("")

    def _validate_tool_calls(self, tool_calls: dict) -> list:
        """Validate tool calls - rejects malformed JSON completely"""
        valid_tool_calls = []
        
        for tool_call in tool_calls.values():
            # Basic structure validation
            if not (tool_call.get("function", {}).get("name") and tool_call.get("id")):
                continue
                
            function = tool_call.get("function", {})
            arguments_raw = function.get("arguments", "")
            
            # Validate JSON format - reject if malformed
            if isinstance(arguments_raw, str):
                try:
                    # Try to parse the JSON - if it fails, reject this tool call entirely
                    json.loads(arguments_raw)
                except json.JSONDecodeError:
                    if Config.debug():
                        LogUtils.warn(f"[!] Malformed JSON in tool call '{function.get('name', 'unknown')}': {arguments_raw}")
                    continue  # Skip this tool call entirely
            
            valid_tool_calls.append(tool_call)
        
        return valid_tool_calls

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

    def _ensure_tool_calls_have_responses(self) -> None:
        """Ensure all tool calls have corresponding tool responses.
        
        This fixes corrupted message history when tool execution is interrupted
        (e.g., user presses Ctrl+C or sends 'stop' via socket). Without this check,
        incomplete tool call/response pairs can cause models to stop responding.
        """
        messages = self.message_history.messages
        i = 0
        
        while i < len(messages):
            msg = messages[i]
            
            # Look for assistant messages with tool_calls
            if msg.get("role") == "assistant" and msg.get("tool_calls"):
                tool_call_ids = {tc.get("id") for tc in msg["tool_calls"]}
                
                # Collect tool_call_ids that have responses
                response_ids = set()
                j = i + 1
                while j < len(messages):
                    msg_j = messages[j]
                    
                    # Stop when we hit another assistant or user message
                    if msg_j.get("role") in ("user", "assistant"):
                        break
                    
                    # Check for tool response
                    tool_id = msg_j.get("tool_call_id")
                    if tool_id:
                        response_ids.add(tool_id)
                    
                    j += 1
                
                # Add missing responses
                missing_ids = tool_call_ids - response_ids
                for tool_id in missing_ids:
                    # Insert right after the assistant message
                    self.message_history.messages.insert(i + 1, {
                        "role": "tool",
                        "tool_call_id": tool_id,
                        "content": "TOOL CALL WAS CANCELLED BY THE USER",
                    })
                    i += 1  # Account for inserted message
            
            i += 1