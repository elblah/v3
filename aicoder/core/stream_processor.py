"""
Stream Processor - Handles streaming response processing and chunk accumulation
Extracted from AICoder class for better separation of concerns
"""

import builtins
import sys
import time
from typing import Dict, Any, List

from aicoder.core.config import Config
from aicoder.utils.log import LogUtils

# Liveness spinner: one ASCII char rotated per silent-phase chunk (hidden
# reasoning, tool-call args). 1-cell wide -> erase is exactly "\b \b".
_SPINNER = "\\|/-"


class StreamProcessor:
    """Handles streaming response processing and chunk accumulation"""

    def __init__(self, streaming_client):
        self.streaming_client = streaming_client
        # Maps tool_calls[] index -> call id for this stream. Some proxies
        # (opencode zen) send index=0 on every chunk; id is the reliable key.
        self._index_to_tool_id: Dict[Any, str] = {}
        self._spin_active = False
        self._spin_idx = 0
        self._spin_ts = 0.0  # last redraw time (200ms throttle)

    def _spin_tick(self) -> None:
        """Advance spinner one frame, throttled to 200ms. Chunk-driven (no
        timer): rotation proves data is flowing, and a frozen spinner means a
        frozen stream."""
        now = time.monotonic()
        if now - self._spin_ts < 0.2:
            return  # dropped frame — redraws only every ~200ms max
        self._spin_ts = now
        if self._spin_active:
            sys.stdout.write("\b" + _SPINNER[self._spin_idx % len(_SPINNER)])
        else:
            if not sys.stdout.isatty():
                return
            sys.stdout.write(_SPINNER[self._spin_idx % len(_SPINNER)])
            self._spin_active = True
        self._spin_idx += 1
        sys.stdout.flush()

    def _spin_stop(self) -> None:
        """Erase the spinner char, restoring cursor to where text ended."""
        if not self._spin_active:
            return
        sys.stdout.write("\b \b")
        sys.stdout.flush()
        self._spin_active = False

    def process_stream(
        self,
        messages: List[Dict[str, Any]],
        is_processing_callback,
        process_chunk_callback
    ) -> Dict[str, Any]:
        """Process streaming response from API"""
        self._index_to_tool_id.clear()
        full_response = ""
        accumulated_reasoning = ""
        accumulated_tool_calls = {}
        reasoning_detected = False
        reasoning_printed = False
        detected_model = None

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
        thinking_signature = ""

        try:
            for chunk in self.streaming_client.stream_request(messages, send_tools=True):
                # Detect model from first chunk that contains it
                if Config.debug() and not detected_model and chunk.get("model"):
                    detected_model = chunk["model"]
                    LogUtils.debug(f"*** Response model: {detected_model}")
                # Check if user interrupted
                if not is_processing_callback():
                    self._spin_stop()
                    LogUtils.print("\n[AI response interrupted]")
                    return {
                        "should_continue": False,
                        "full_response": full_response,
                        "reasoning_content": accumulated_reasoning,
                        "reasoning_field": reasoning_field_name,
                        "accumulated_tool_calls": accumulated_tool_calls,
                    }

                # Update token stats if present
                if chunk.get("usage"):
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

                    # Check for reasoning tokens
                    override = Config.get_reasoning_field()
                    if override:
                        reasoning_fields = [override]
                    else:
                        reasoning_fields = Config.get_possible_reasoning_fields()

                    # Anthropic re-sends full accumulated reasoning on the final
                    # done chunk (for storage) — already accumulated via deltas.
                    # Skip to avoid doubling.
                    if not (chunk.get("done") and accumulated_reasoning):
                        for field in reasoning_fields:
                            reasoning = delta.get(field)
                            if reasoning and reasoning.strip():
                                reasoning_detected = True
                                accumulated_reasoning += reasoning
                                if reasoning_field_name is None:
                                    reasoning_field_name = field
                                self._spin_tick()
                                break

                    # Capture thinking signature for Anthropic-style APIs
                    if delta.get("thinking_signature"):
                        thinking_signature = delta.get("thinking_signature")

                    # Debug: log which reasoning field was detected
                    if Config.debug() and reasoning_field_name and accumulated_reasoning == reasoning:
                        LogUtils.debug(f"Reasoning detected via field: {reasoning_field_name}")

                    content = delta.get("content")
                    if content:
                        # Handle content that may be a list (e.g., mistral-small returns list of content blocks)
                        if isinstance(content, list):
                            content = "".join(
                                block.get("text", "") if isinstance(block, dict) else str(block)
                                for block in content
                            )
                        if not content:
                            continue
                        # Spinner owns the cursor cell during silent phases —
                        # erase before real output takes over.
                        self._spin_stop()
                        # On first content chunk, print accumulated reasoning (if any)
                        # Use flag instead of checking full_response to handle
                        # whitespace-only chunks that get lstripped to nothing
                        if not reasoning_printed and Config.show_reasoning() and accumulated_reasoning:
                            builtins.print(f"\n{Config.colors['dim']}Reasoning: {accumulated_reasoning}{Config.colors['reset']}\n")
                            reasoning_printed = True
                        # Strip leading whitespace for cleaner output
                        if full_response == "":
                            content = content.lstrip()
                        full_response += content
                        colored_content = self.streaming_client.process_with_colorization(content)
                        builtins.print(colored_content, end="", flush=True)

                # Tool calls
                if "delta" in choice and choice["delta"].get("tool_calls"):
                    for tool_call in choice["delta"]["tool_calls"]:
                        self._spin_tick()
                        process_chunk_callback(tool_call, accumulated_tool_calls)

                # Finish reason
                if choice.get("finish_reason") == "tool_calls":
                    pass

            self._spin_stop()

            # Reasoning not yet printed (e.g. tool-call-only turn, reasoning after
            # last content chunk) — print it now before the stream ends.
            if not reasoning_printed and Config.show_reasoning() and accumulated_reasoning:
                builtins.print(f"\n{Config.colors['dim']}Reasoning: {accumulated_reasoning}{Config.colors['reset']}\n")
                reasoning_printed = True

            # Print reasoning detection status when DEBUG is on
            if Config.debug():
                effort = Config.reasoning_effort()
                effort_text = f" (effort: {effort})" if effort else ""
                field_text = f" (field: {reasoning_field_name})" if reasoning_field_name else ""
                LogUtils.print(f"Reasoning: {'ON' if reasoning_detected else 'OFF'}{effort_text}{field_text}")

        except Exception as e:
            self._spin_stop()
            LogUtils.error(f"[Streaming error: {e}]")
            return {
                "should_continue": False,
                "full_response": "",
                "reasoning_content": "",
                "reasoning_field": None,
                "thinking_signature": "",
                "accumulated_tool_calls": {},
                "error": str(e)
            }

        return {
            "should_continue": True,
            "full_response": full_response,
            "reasoning_content": accumulated_reasoning,
            "reasoning_field": reasoning_field_name,
            "thinking_signature": thinking_signature,
            "accumulated_tool_calls": accumulated_tool_calls,
        }

    def accumulate_tool_call(
        self,
        tool_call: Dict[str, Any],
        accumulated_tool_calls: Dict[str, Dict[str, Any]]
    ) -> None:
        """Accumulate tool call from stream.

        Keying: tool-call id when present; else a name-bearing chunk starts a
        new call; else (pure args delta) route via the index map, falling back
        to the most recently touched call. Some proxies (opencode zen) send
        index=0 on every chunk — index alone cannot distinguish parallel calls.
        """
        # Handle case where tool_call might not be a dict (unexpected API format)
        if not isinstance(tool_call, dict):
            LogUtils.error(f"Tool call is not a dict: {type(tool_call)} - {tool_call}")
            return

        index = tool_call.get("index")
        function = tool_call.get("function")
        if not isinstance(function, dict):
            function = {}
        name = function.get("name") or ""
        args = function.get("arguments") or ""
        tool_id = tool_call.get("id") or ""
        if Config.debug():
            LogUtils.debug(
                f"*** accumulate_tool_call: index={index}, name={name or 'unknown'}, "
                f"args={args[:50]!r}"
            )

        # Determine which accumulated call this chunk belongs to.
        if tool_id:
            key = tool_id
            if index is not None:
                self._index_to_tool_id[index] = tool_id
        elif name:
            # Name-bearing chunk without id: continuation if the index maps to
            # a call with the same name (some providers repeat the name on
            # every delta); otherwise start a new call.
            key = self._index_to_tool_id.get(index) if index is not None else None
            if key is not None and key in accumulated_tool_calls:
                existing_name = accumulated_tool_calls[key]["function"].get("name")
                if existing_name and existing_name != name:
                    key = None  # different call, same index
            if key is None:
                key = f"tool_call_{len(accumulated_tool_calls)}"
                if index is not None:
                    self._index_to_tool_id[index] = key
        else:
            # Pure args delta: route via index map, else most recent call.
            key = self._index_to_tool_id.get(index) if index is not None else None
            if key is None or key not in accumulated_tool_calls:
                if not accumulated_tool_calls:
                    LogUtils.warn(
                        f"[!] Tool call delta with no target: index={index}, name={name!r}"
                    )
                    return
                key = next(reversed(accumulated_tool_calls))
                # Re-insert to keep "most recent" ordering deterministic.
                accumulated_tool_calls[key] = accumulated_tool_calls.pop(key)

        if key not in accumulated_tool_calls:
            accumulated_tool_calls[key] = {
                "id": tool_id or key,
                "type": tool_call.get("type") or "function",
                "function": {
                    "name": name,
                    "arguments": args,
                },
            }
            return

        # Deltas may carry metadata and arguments separately. Preserve metadata
        # from earlier deltas while appending every argument fragment.
        existing = accumulated_tool_calls[key]
        existing_function = existing.setdefault("function", {})
        if name:
            existing_function["name"] = name
        if tool_id:
            existing["id"] = tool_id
        if tool_call.get("type"):
            existing["type"] = tool_call["type"]
        if args:
            existing_function["arguments"] = (
                existing_function.get("arguments") or ""
            ) + args
