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
        accumulated_tool_calls = {}

        try:
            for chunk in self.streaming_client.stream_request(messages, send_tools=True):
                # Check if user interrupted
                if not is_processing_callback():
                    LogUtils.print("\n[AI response interrupted]")
                    return {
                        "should_continue": False,
                        "full_response": full_response,
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

                # Content (ignore reasoning_content unless model is reasoning-only)
                if "delta" in choice:
                    content = choice["delta"].get("content")
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

        except Exception as e:
            LogUtils.error(f"\n[Streaming error: {e}]")
            return {
                "should_continue": False,
                "full_response": "",
                "accumulated_tool_calls": {},
                "error": str(e)
            }

        return {
            "should_continue": True,
            "full_response": full_response,
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
            if tool_call.get("function", {}).get("arguments"):
                existing["function"]["arguments"] += tool_call["function"]["arguments"]
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
                "arguments": tool_call.get("function", {}).get("arguments", ""),
            },
        }
