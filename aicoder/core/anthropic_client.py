"""Anthropic API client - uses Anthropic-compatible endpoint"""

import json
import os
import time
import itertools
from typing import List, Generator, Optional, Dict, Any

from aicoder.core.config import Config
from aicoder.core.markdown_colorizer import MarkdownColorizer
from aicoder.utils.log import warn as log_warn, debug as log_debug
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
                        from aicoder.utils.log import LogUtils
                        LogUtils.debug(f"*** Request payload saved to {debug_file}")
                    except Exception as e:
                        from aicoder.utils.log import LogUtils
                        LogUtils.debug(f"*** Failed to save request payload: {e}")

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
                import traceback
                print(f"[ERROR] Exception: {e}", flush=True)
                traceback.print_exc()
                if attempt_num >= max_retries if max_retries > 0 else False:
                    if throw_on_error:
                        raise
                    yield {"error": str(e), "done": True}
                    return

    def _build_headers(self) -> Dict[str, str]:
        api_key = Config.api_key()
        return {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
            "anthropic-version": "2023-06-01",
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

        return request_data

    def _handle_streaming_response(self, response: Response, start_time: float) -> Generator[Dict[str, Any], None, None]:
        accumulated_reasoning = ""
        accumulated_tool_calls = {}
        full_content = ""
        current_block_type = None
        current_tool_id = None
        current_tool_name = None
        current_tool_input = ""

        # Read all content first
        content_bytes = response.read()
        if not content_bytes:
            yield {"error": "Empty response", "done": True, "content": "", "accumulated_tool_calls": {}}
            return
        
        content_str = content_bytes.decode("utf-8")
        
        # Parse SSE format: "event: type\ndata: {...}"
        # Events are separated by blank lines
        event_blocks = content_str.strip().split("\n\n")
        
        for block in event_blocks:
            block = block.strip()
            if not block:
                continue
            
            # Parse event line and data line
            lines = block.split("\n")
            data_str = None
            
            for line in lines:
                line = line.strip()
                if line.startswith("data: "):
                    data_str = line[6:]
                    break
            
            if not data_str:
                continue
            
            try:
                data = json.loads(data_str)
                dtype = data.get("type", "")
                
                if dtype == "content_block_start":
                    content_block = data.get("content_block", {})
                    current_block_type = content_block.get("type")
                    # For tool_use, id and name are at data level, not inside content_block
                    current_tool_id = data.get("id") or content_block.get("id")
                    current_tool_name = data.get("name") or content_block.get("name")
                    current_tool_input = ""
                    if current_block_type == "tool_use":
                        # Initial input might be in content_block
                        init_input = content_block.get("input", {})
                        if init_input:
                            current_tool_input = json.dumps(init_input)
                    
                elif dtype == "content_block_delta":
                    delta = data.get("delta", {})
                    delta_type = delta.get("type")
                    
                    if delta_type == "thinking_delta":
                        thinking = delta.get("thinking", "")
                        accumulated_reasoning += thinking
                        yield {
                            "choices": [{"delta": {"reasoning_content": thinking}}],
                            "done": False
                        }
                        
                    elif delta_type == "text_delta":
                        text = delta.get("text", "")
                        full_content += text
                        yield {
                            "choices": [{"delta": {"content": text}}],
                            "done": False
                        }
                        
                    elif delta_type == "input_json_delta":
                        # Accumulate tool input JSON (partial_json in Anthropic format)
                        partial = delta.get("partial_json", "")
                        if partial:
                            current_tool_input += partial
                
                elif dtype == "message_delta":
                    # Final accumulation of tool call
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
                    pass
                    
            except json.JSONDecodeError:
                continue

        if self.stats:
            self.stats.increment_api_requests()

        yield {
            "content": full_content,
            "reasoning_content": accumulated_reasoning,
            "accumulated_tool_calls": accumulated_tool_calls,
            "done": True
        }

    def _handle_non_streaming_response(self, response: Response, start_time: float) -> Generator[Dict[str, Any], None, None]:
        data = response.json()
        
        full_content = ""
        accumulated_reasoning = ""
        accumulated_tool_calls = {}

        content = data.get('content', [])
        if isinstance(content, list):
            for block in content:
                btype = block.get('type')
                
                if btype == 'thinking':
                    accumulated_reasoning = block.get('thinking', '')
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

        if self.stats:
            self.stats.increment_api_requests()

        yield {
            "content": full_content,
            "reasoning_content": accumulated_reasoning,
            "accumulated_tool_calls": accumulated_tool_calls,
            "done": True
        }

    def process_with_colorization(self, content: str) -> str:
        return self.colorizer.process_with_colorization(content)

    def reset_colorizer(self) -> None:
        self.colorizer.reset_state()
