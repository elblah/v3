"""Anthropic API client - uses Anthropic-compatible endpoint"""

# Duplicated from streaming_client.py intentionally - core must stay stable.
# Only import when PROVIDER=anthropic is set.

import json
import os
import sys
import time
import itertools
from typing import List, Generator, Optional, Dict, Any

from aicoder.core.config import Config
from aicoder.core.markdown_colorizer import MarkdownColorizer
from aicoder.utils.log import LogUtils, warn as log_warn, debug as log_debug
from aicoder.utils.http_utils import fetch, Response


class AnthropicClient:
    """Handles API requests via Anthropic-compatible endpoint"""

    def __init__(self, stats: Optional[Any] = None, tool_manager: Optional[Any] = None, message_history: Optional[Any] = None):
        self.stats = stats
        self.colorizer = MarkdownColorizer()
        self.tool_manager = tool_manager
        self.message_history = message_history
        self._plugin_system = None

    def set_plugin_system(self, plugin_system) -> None:
        self._plugin_system = plugin_system

    def _calculate_backoff(self, attempt_num: int) -> float:
        max_backoff = Config.effective_max_backoff()
        return min(2 ** (attempt_num + 1), max_backoff)

    def _wait_for_retry(self, attempt_num: int) -> None:
        delay = self._calculate_backoff(attempt_num)
        log_warn(f"Retrying in {delay}s...")
        time.sleep(delay)

    def stream_request(
        self,
        messages: List[Dict[str, Any]],
        stream: Optional[bool] = None,
        throw_on_error: bool = False,
        send_tools: bool = True,
    ) -> Generator[Dict[str, Any], None, None]:
        if stream is None:
            stream = Config.streaming_enabled()

        if Config.debug():
            log_debug(f"*** Anthropic stream_request called with {len(messages)} messages, stream={stream}")

        start_time = time.time()
        if self.stats:
            self.stats.increment_api_requests()

        max_retries = Config.effective_max_retries()
        max_tokens = Config.max_tokens() if Config.max_tokens() else 8192

        for attempt_num in range(1, max_retries + 1) if max_retries > 0 else itertools.count(1):
            try:
                if attempt_num > 1:
                    self._wait_for_retry(attempt_num)

                request_data = self._prepare_request_data(messages, max_tokens, send_tools, stream)
                endpoint = Config.api_endpoint()
                headers = self._build_headers()

                # Save request payload for debugging
                if Config.debug():
                    debug_dir = os.path.join(os.getcwd(), ".aicoder")
                    os.makedirs(debug_dir, exist_ok=True)
                    debug_file = os.path.join(debug_dir, "last-request.json")
                    try:
                        with open(debug_file, "w") as f:
                            json.dump({
                                "endpoint": endpoint,
                                "headers": {k: v if k.lower() != "authorization" else "***" for k, v in headers.items()},
                                "body": request_data
                            }, f, indent=2)
                        log_debug(f"*** Request payload saved to {debug_file}")
                    except Exception as e:
                        log_debug(f"*** Failed to save request payload: {e}")

                response = fetch(
                    endpoint,
                    {
                        "method": "POST",
                        "headers": headers,
                        "body": json.dumps(request_data),
                        "timeout": Config.total_timeout(),
                    },
                )

                if not response.ok():
                    error_msg = f"HTTP {response.status}: {response.reason}"
                    try:
                        error_data = response.json()
                        if error_data:
                            error_msg += f" - {json.dumps(error_data)}"
                    except Exception:
                        pass
                    print(f"[ERROR] {error_msg}", flush=True)
                    raise Exception(error_msg)

                if stream:
                    yield from self._handle_streaming_response(response, start_time)
                else:
                    yield from self._handle_non_streaming_response(response, start_time)
                return

            except Exception as e:
                LogUtils.error(f"Exception: {e}")
                # Don't retry if HTTP status is known and not in retryable set
                error_msg = str(e) if e else ""
                status = 0
                if error_msg.startswith("HTTP "):
                    try:
                        status = int(error_msg.split()[1])
                    except (IndexError, ValueError):
                        pass
                retryable = Config.retry_status_codes()
                if status != 0 and status not in retryable:
                    LogUtils.warn(f"Not retrying HTTP {status} (not in retryable codes: {sorted(retryable)})")
                    if throw_on_error:
                        raise
                    yield {"error": str(e), "done": True}
                    return
                if max_retries > 0 and attempt_num >= max_retries:
                    if throw_on_error:
                        raise
                    yield {"error": str(e), "done": True}
                    return

    def _build_headers(self) -> Dict[str, str]:
        api_key = Config.api_key()
        return {
            "Content-Type": "application/json",
            "x-api-key": api_key,
            "anthropic-version": "2023-06-01",
            "User-Agent": "Mozilla/5.0",
        }

    def _prepare_request_data(self, messages: List[Dict[str, Any]], max_tokens: int, send_tools: bool, stream: bool = False) -> Dict[str, Any]:
        # Separate system message from conversation messages
        system_parts = []
        conversation = []
        
        for msg in messages:
            if msg.get("role") == "system":
                system_parts.append(msg.get("content", ""))
            elif msg.get("role") == "tool":
                # Convert OpenAI tool result format to Anthropic format
                tool_use_id = msg.get("tool_call_id") or msg.get("tool_use_id", "")
                conversation.append({
                    "role": "user",
                    "content": [{
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "content": msg.get("content", "")
                    }]
                })
            elif msg.get("role") == "assistant" and msg.get("tool_calls"):
                # Convert OpenAI assistant+tool_calls format to Anthropic format
                content_blocks = []
                # Add thinking block if present (with signature for Anthropic)
                if msg.get("thinking") and msg.get("thinking_signature"):
                    content_blocks.append({
                        "type": "thinking",
                        "thinking": msg.get("thinking"),
                        "signature": msg.get("thinking_signature")
                    })
                elif msg.get("thinking"):
                    # Fallback without signature (may fail for Anthropic)
                    content_blocks.append({
                        "type": "thinking",
                        "thinking": msg.get("thinking")
                    })
                for tc in msg.get("tool_calls", []):
                    content_blocks.append({
                        "type": "tool_use",
                        "id": tc.get("id", ""),
                        "name": tc.get("function", {}).get("name", ""),
                        "input": json.loads(tc.get("function", {}).get("arguments", "{}") or "{}")
                    })
                if msg.get("content"):
                    content_blocks.append({
                        "type": "text",
                        "text": msg.get("content")
                    })
                conversation.append({
                    "role": "assistant",
                    "content": content_blocks
                })
            elif msg.get("role") == "assistant" and msg.get("thinking"):
                # Assistant with thinking but no tool_calls - format properly for Anthropic
                content_blocks = []
                # Add thinking block if present (with signature for Anthropic)
                if msg.get("thinking_signature"):
                    content_blocks.append({
                        "type": "thinking",
                        "thinking": msg.get("thinking"),
                        "signature": msg.get("thinking_signature")
                    })
                else:
                    content_blocks.append({
                        "type": "thinking",
                        "thinking": msg.get("thinking")
                    })
                if msg.get("content"):
                    content_blocks.append({
                        "type": "text",
                        "text": msg.get("content")
                    })
                conversation.append({
                    "role": "assistant",
                    "content": content_blocks
                })
            else:
                conversation.append(msg)

        request_data = {
            "model": Config.model(),
            "messages": conversation,
            "max_tokens": max_tokens,
            "stream": stream,
        }
        
        if system_parts:
            request_data["system"] = "\n".join(system_parts)
        
        # Add tools using Anthropic format (name + input_schema)
        if send_tools and self.tool_manager:
            tools = self.tool_manager.get_tool_definitions()
            if tools:
                # Convert from OpenAI format to Anthropic format
                anthropic_tools = []
                for tool in tools:
                    func = tool.get("function", {})
                    anthropic_tools.append({
                        "name": func.get("name"),
                        "description": func.get("description", ""),
                        "input_schema": func.get("parameters", {"type": "object", "properties": {}})
                    })
                request_data["tools"] = anthropic_tools

        # Transform hook for provider-specific formats
        if self._plugin_system:
            request_data = self._plugin_system.call_hooks_with_return("transform_request", request_data) or request_data

        return request_data

    def _handle_streaming_response(self, response: Response, start_time: float) -> Generator[Dict[str, Any], None, None]:
        accumulated_reasoning = ""
        accumulated_tool_calls = {}
        full_content = ""
        current_block_type = None
        current_tool_id = None
        current_tool_name = None
        current_tool_input = ""
        thinking_printed = False
        message_usage = None
        self._thinking_signature = ""

        def _show_thinking():
            nonlocal thinking_printed
            if not thinking_printed:
                sys.stdout.write(f"{Config.colors['dim']}thinking...{Config.colors['reset']}")
                sys.stdout.flush()
                thinking_printed = True

        def _clear_thinking():
            nonlocal thinking_printed
            if thinking_printed:
                sys.stdout.write("\r\x1b[K")
                sys.stdout.flush()
                thinking_printed = False
        
        # Read incrementally and process per event
        event_data = ""
        line_count = 0
        resp_log = None

        if Config.debug():
            log_debug("*** SSE streaming loop started")
            try:
                debug_dir = os.path.join(os.getcwd(), ".aicoder")
                os.makedirs(debug_dir, exist_ok=True)
                resp_log = open(os.path.join(debug_dir, "last-response.log"), "w")
            except Exception as e:
                log_debug(f"*** Failed to open response log: {e}")

        try:
          while True:
            line_bytes = response.readline()
            if not line_bytes:
                if Config.debug():
                    log_debug(f"*** SSE stream ended after {line_count} lines")
                break
            
            line_count += 1
            line = line_bytes.decode("utf-8")

            if resp_log:
                resp_log.write(line_bytes.decode("utf-8", errors="replace"))
                resp_log.flush()

            if Config.debug():
                log_debug(f"*** SSE raw line {line_count}: {repr(line_bytes)}")

            # Blank line = end of event block
            if line.strip() == "":
                if event_data.strip():
                    # Parse event data - handle both "data:" and "data: " (SSE spec allows optional space)
                    data_str = None
                    for ln in event_data.split("\n"):
                        ln = ln.strip()
                        if ln.startswith("data:"):
                            data_str = ln[5:].lstrip()
                            break
                    
                    if data_str:
                        try:
                            data = json.loads(data_str)
                            dtype = data.get("type", "")

                            # Log every raw SSE event in debug mode
                            if Config.debug():
                                log_debug(f"*** SSE event: {json.dumps(data)}")

                            # Capture usage from message_start event
                            if dtype == "message_start":
                                msg = data.get("message", {})
                                if "usage" in msg:
                                    message_usage = msg["usage"]
                            
                            elif dtype == "content_block_start":
                                content_block = data.get("content_block", {})
                                current_block_type = content_block.get("type")
                                current_tool_id = data.get("id") or content_block.get("id")
                                current_tool_name = data.get("name") or content_block.get("name")
                                current_tool_input = ""
                                if current_block_type == "tool_use":
                                    init_input = content_block.get("input", {})
                                    if init_input:
                                        current_tool_input = json.dumps(init_input)
                            
                            elif dtype == "content_block_delta":
                                delta = data.get("delta", {})
                                delta_type = delta.get("type")
                                
                                if delta_type == "thinking_delta":
                                    thinking = delta.get("thinking", "")
                                    accumulated_reasoning += thinking
                                    if not thinking_printed:
                                        _show_thinking()
                                    yield {
                                        "choices": [{"delta": {"thinking": thinking}}],
                                        "done": False
                                    }
                                    
                                elif delta_type == "signature_delta":
                                    # Capture signature for thinking block (required for multi-turn)
                                    self._thinking_signature = delta.get("signature", "")
                                    if Config.debug():
                                        log_debug(f"*** Captured thinking signature: {self._thinking_signature[:20]}...")
                                    
                                elif delta_type == "text_delta":
                                    _clear_thinking()
                                    text = delta.get("text", "")
                                    full_content += text
                                    yield {
                                        "choices": [{"delta": {"content": text}}],
                                        "done": False
                                    }
                                    
                                elif delta_type == "input_json_delta":
                                    partial = delta.get("partial_json", "")
                                    if partial:
                                        current_tool_input += partial
                            
                            elif dtype == "message_delta":
                                # Capture usage when available (at top level of data, not inside delta)
                                if "usage" in data:
                                    message_usage = data["usage"]
                                
                                if current_block_type == "tool_use" and current_tool_id:
                                    accumulated_tool_calls[current_tool_id] = {
                                        'id': current_tool_id,
                                        'type': 'function',
                                        'function': {
                                            'name': current_tool_name,
                                            'arguments': current_tool_input
                                        }
                                    }
                                    idx = len(accumulated_tool_calls) - 1
                                    yield {
                                        "choices": [{
                                            "delta": {
                                                "tool_calls": [{
                                                    "index": idx,
                                                    "id": current_tool_id,
                                                    "type": "function",
                                                    "function": {
                                                        "name": current_tool_name,
                                                        "arguments": current_tool_input
                                                    }
                                                }]
                                            }
                                        }],
                                        "done": False
                                    }
                                    
                            elif dtype == "message_stop":
                                # Clear thinking indicator at end of message
                                _clear_thinking()
                                    
                        except json.JSONDecodeError:
                            pass
                    
                    event_data = ""
                continue
            
            event_data += line
        finally:
            if resp_log:
                resp_log.close()

        # Update stats on success
        if self.stats:
            log_debug(f"*** streaming stats: increment_api_success, add_api_time")
            self.stats.increment_api_success()
            self.stats.add_api_time(time.time() - start_time)
            # Update token stats from accumulated usage
            if message_usage:
                input_tokens = message_usage.get("input_tokens") or 0
                output_tokens = message_usage.get("output_tokens") or 0
                cache_read = message_usage.get("cache_read_input_tokens") or 0
                total_prompt = input_tokens + cache_read
                if total_prompt or output_tokens:
                    self.stats.add_prompt_tokens(total_prompt)
                    self.stats.add_completion_tokens(output_tokens)

        # Fire usage hook AFTER stats are updated (elapsed is set)
        if message_usage and self._plugin_system:
            self._plugin_system.call_hooks("after_usage_data", message_usage)

        # Final yield - content already streamed via deltas, so don't include it
        # to avoid double-printing. Include reasoning and signature for storage.
        yield {
            "choices": [{
                "delta": {
                    "reasoning_content": accumulated_reasoning,
                    "thinking_signature": self._thinking_signature,
                },
                "finish_reason": "stop",
                "index": 0
            }],
            "accumulated_tool_calls": accumulated_tool_calls,
            "done": True
        }

    def _handle_non_streaming_response(self, response: Response, start_time: float) -> Generator[Dict[str, Any], None, None]:
        data = response.json()
        
        full_content = ""
        accumulated_reasoning = ""
        accumulated_tool_calls = {}

        content = data.get('content', [])
        thinking_signature = ""
        if isinstance(content, list):
            for block in content:
                btype = block.get('type')
                
                if btype == 'thinking':
                    accumulated_reasoning = block.get('thinking', '')
                    thinking_signature = block.get('signature', '')
                elif btype == 'text':
                    full_content = block.get('text', '')
                elif btype == 'tool_use':
                    tool_id = block.get('id', '')
                    tool_name = block.get('name', '')
                    tool_input = block.get('input', {})
                    accumulated_tool_calls[tool_id] = {
                        'id': tool_id,
                        'type': 'function',
                        'function': {
                            'name': tool_name,
                            'arguments': json.dumps(tool_input)
                        }
                    }

        # Update stats on success
        if self.stats:
            log_debug(f"*** non-stream stats block 1: increment_api_success, add_api_time")
            self.stats.increment_api_success()
            self.stats.add_api_time(time.time() - start_time)
            # Update token stats from usage
            usage = data.get("usage")
            if usage:
                input_tokens = usage.get("input_tokens") or 0
                output_tokens = usage.get("output_tokens") or 0
                cache_read = usage.get("cache_read_input_tokens") or 0
                total_prompt = input_tokens + cache_read
                if total_prompt or output_tokens:
                    self.stats.add_prompt_tokens(total_prompt)
                    self.stats.add_completion_tokens(output_tokens)

        # Fire usage hook AFTER stats are updated (elapsed is set)
        usage = data.get("usage")
        if usage and self._plugin_system:
            self._plugin_system.call_hooks("after_usage_data", usage)

        # Yield same format as streaming content chunks (with choices wrapper)
        # Convert tool_calls to list with numeric index for stream_processor compatibility
        tool_calls_list = [
            {**tc, "index": i} for i, tc in enumerate(accumulated_tool_calls.values())
        ]
        yield {
            "choices": [{
                "delta": {
                    "content": full_content,
                    "reasoning_content": accumulated_reasoning,
                    "thinking_signature": thinking_signature,
                    "tool_calls": tool_calls_list
                }
            }],
            "done": True
        }

    def process_with_colorization(self, content: str) -> str:
        return self.colorizer.process_with_colorization(content)

    def reset_colorizer(self) -> None:
        self.colorizer.reset_state()
