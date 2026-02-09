"""
Stream Processor - Handles streaming response processing and chunk accumulation
Extracted from AICoder class for better separation of concerns
"""

import builtins
import time
from typing import Dict, Any, List

from aicoder.core.config import Config
from aicoder.utils.log import LogUtils, LogOptions


class StreamProcessor:
    """Handles streaming response processing and chunk accumulation"""

    def __init__(self, streaming_client):
        self.streaming_client = streaming_client

    def process_stream(
        self,
        messages: List[Dict[str, Any]],
        is_processing_callback,
        process_chunk_callback
    ) -> Dict[str, Any]:
        """Process streaming response from API"""
        full_response = ""
        accumulated_reasoning = ""
        accumulated_tool_calls = {}
        reasoning_detected = False

        # Debug: show thinking configuration at start of stream
        if Config.debug():
            mode = Config.thinking()
            effort = Config.reasoning_effort()
            if mode != "default":
                mode_text = f"Thinking: {mode}"
                if mode == "on" and effort:
                    mode_text += f" (effort: {effort})"
                mode_text += f" (preserve: {not Config.clear_thinking()})"
                LogUtils.debug(f"*** {mode_text}")

        # Track which reasoning field name the provider uses
        reasoning_field_name = None

        try:
            for chunk in self.streaming_client.stream_request(messages, send_tools=True):
                # Check if user interrupted
                if not is_processing_callback():
                    LogUtils.print("\n[AI response interrupted]")
                    return {
                        "should_continue": False,
                        "full_response": full_response,
                        "reasoning_content": accumulated_reasoning,
                        "reasoning_field": reasoning_field_name,
                        "accumulated_tool_calls": accumulated_tool_calls,
                    }

                # Update token stats if present
                if "usage" in chunk and chunk["usage"]:
                    self.streaming_client.update_token_stats(chunk["usage"])

                # Process choice
                if "choices" not in chunk or not chunk["choices"]:
                    # Handle case where chunk doesn't have expected structure
                    LogUtils.debug(f"Chunk missing choices: {chunk}")
                    continue

                choice = chunk["choices"][0]

                # Content and reasoning processing
                if "delta" in choice:
                    delta = choice["delta"]

                    # Check for reasoning tokens across multiple field names
                    # Different providers use different field names for reasoning:
                    # - GLM, llama.cpp: "reasoning_content"
                    # - Some OpenAI-compatible endpoints: "reasoning"
                    # - Others: "reasoning_text"
                    # Use first non-empty field to avoid duplication (e.g., chutes.ai returns both)
                    reasoning_fields = ["reasoning_content", "reasoning", "reasoning_text"]

                    for field in reasoning_fields:
                        reasoning = delta.get(field)
                        if reasoning and reasoning.strip():
                            reasoning_detected = True
                            accumulated_reasoning += reasoning
                            # Remember the field name this provider uses (first one wins)
                            if reasoning_field_name is None:
                                reasoning_field_name = field
                            # Only use the first non-empty field (avoid duplication)
                            break

                    # Debug: log which reasoning field was detected
                    if Config.debug() and reasoning_field_name and accumulated_reasoning == reasoning:
                        LogUtils.debug(f"Reasoning detected via field: {reasoning_field_name}")

                    content = delta.get("content")
                    if content:
                        full_response += content
                        colored_content = self.streaming_client.process_with_colorization(content)
                        builtins.print(colored_content, end="", flush=True)

                # Tool calls
                if "delta" in choice and choice["delta"].get("tool_calls"):
                    for tool_call in choice["delta"]["tool_calls"]:
                        process_chunk_callback(tool_call, accumulated_tool_calls)

                # Finish reason
                if choice.get("finish_reason") == "tool_calls":
                    pass

            # Print reasoning detection status when DEBUG is on
            if Config.debug():
                effort = Config.reasoning_effort()
                effort_text = f" (effort: {effort})" if effort else ""
                field_text = f" (field: {reasoning_field_name})" if reasoning_field_name else ""
                LogUtils.print(f"Reasoning: {'ON' if reasoning_detected else 'OFF'}{effort_text}{field_text}")

        except Exception as e:
            LogUtils.error(f"\n[Streaming error: {e}]")
            return {
                "should_continue": False,
                "full_response": "",
                "reasoning_content": "",
                "reasoning_field": None,
                "accumulated_tool_calls": {},
                "error": str(e)
            }

        return {
            "should_continue": True,
            "full_response": full_response,
            "reasoning_content": accumulated_reasoning,
            "reasoning_field": reasoning_field_name,
            "accumulated_tool_calls": accumulated_tool_calls,
        }

    def accumulate_tool_call(
        self,
        tool_call: Dict[str, Any],
        accumulated_tool_calls: Dict[int, Dict[str, Any]]
    ) -> None:
        """Accumulate tool call from stream"""
        # Handle case where tool_call might not be a dict (unexpected API format)
        if not isinstance(tool_call, dict):
            LogUtils.error(f"Tool call is not a dict: {type(tool_call)} - {tool_call}")
            return

        index = tool_call.get("index")

        if index in accumulated_tool_calls:
            # Existing tool call - accumulate arguments
            existing = accumulated_tool_calls[index]
            new_args = tool_call.get("function", {}).get("arguments")
            if new_args:
                # Ensure existing arguments is a string, not None
                if existing["function"]["arguments"] is None:
                    existing["function"]["arguments"] = new_args
                else:
                    existing["function"]["arguments"] += new_args
            return

        # New tool call
        if not tool_call.get("function", {}).get("name"):
            LogUtils.error("Invalid tool call: missing function name")
            return

        accumulated_tool_calls[index] = {
            "id": tool_call.get("id", f"tool_call_{index}_{int(time.time())}"),
            "type": tool_call.get("type", "function"),
            "function": {
                "name": tool_call["function"]["name"],
                "arguments": tool_call.get("function", {}).get("arguments") or "",
            },
        }
