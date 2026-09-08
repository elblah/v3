"""OpenAI Responses API client - uses /v1/responses endpoint

Duplicated from streaming_client.py intentionally - core must stay stable.
Only import when API_PROVIDER=responses is set.

Targets OpenCode Zen /v1/responses (e.g. free muse-spark model). Keyless
endpoints are supported: Authorization header is only sent when an API key
is configured.

Chunks yielded are chat-completions-shaped so stream_processor.py works
unchanged. Zen usage ({input_tokens,...}) is mapped to the chat shape
({prompt_tokens,...}) before stats updates and the after_usage_data hook,
so plugins need no per-provider logic.
"""

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
from aicoder.utils.file_utils import rotate_debug_log, debug_filename


class ResponsesClient:
    """Handles API requests via OpenAI Responses-compatible endpoint"""

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
            log_debug(f"*** Responses stream_request called with {len(messages)} messages, stream={stream}")

        start_time = time.time()
        if self.stats:
            self.stats.increment_api_requests()

        max_retries = Config.effective_max_retries()

        for attempt_num in range(1, max_retries + 1) if max_retries > 0 else itertools.count(1):
            try:
                if attempt_num > 1:
                    # _calculate_backoff takes a 0-based retry index
                    self._wait_for_retry(attempt_num - 2)

                request_data = self._prepare_request_data(messages, send_tools, stream)
                endpoint = self._endpoint()
                headers = self._build_headers()

                # Save request payload for debugging
                if Config.debug():
                    debug_dir = os.path.join(os.getcwd(), ".aicoder")
                    os.makedirs(debug_dir, exist_ok=True)
                    debug_file = os.path.join(debug_dir, debug_filename("last-request.json"))
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
                        status = int(error_msg.split()[1].rstrip(":"))
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

    def _endpoint(self) -> str:
        override = os.environ.get("API_ENDPOINT")
        if override:
            return override
        base = Config.base_url()
        return f"{base}/responses" if base else ""

    def _build_headers(self) -> Dict[str, str]:
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
        }
        api_key = Config.api_key()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"
        # Add custom headers from environment
        headers.update(Config.http_headers())
        return headers

    def _prepare_request_data(self, messages: List[Dict[str, Any]], send_tools: bool, stream: bool) -> Dict[str, Any]:
        system_parts = []
        input_items = []

        for msg in messages:
            role = msg.get("role")
            if role == "system":
                system_parts.append(msg.get("content", ""))
            elif role == "tool":
                # Tool result -> function_call_output item
                input_items.append({
                    "type": "function_call_output",
                    "call_id": msg.get("tool_call_id") or msg.get("tool_use_id", ""),
                    "output": msg.get("content", ""),
                })
            elif role == "assistant" and msg.get("tool_calls"):
                # Assistant turn with tool calls: text (if any) + function_call items
                if msg.get("content"):
                    input_items.append({"role": "assistant", "content": msg.get("content")})
                for tc in msg.get("tool_calls", []):
                    func = tc.get("function", {})
                    input_items.append({
                        "type": "function_call",
                        "call_id": tc.get("id", ""),
                        "name": func.get("name", ""),
                        "arguments": func.get("arguments", "{}") or "{}",
                    })
            else:
                content = msg.get("content", "")
                if isinstance(content, list):
                    content = "".join(
                        block.get("text", "") if isinstance(block, dict) else str(block)
                        for block in content
                    )
                input_items.append({"role": role or "user", "content": content})

        request_data: Dict[str, Any] = {
            "model": Config.model(),
            "input": input_items,
            "stream": stream,
        }

        if system_parts:
            request_data["instructions"] = "\n".join(system_parts)

        # Responses API uses max_output_tokens; only send when configured
        # (endpoint may reject unknown/empty limits on free models).
        max_tokens = Config.max_tokens()
        if max_tokens:
            request_data["max_output_tokens"] = max_tokens

        if send_tools and self.tool_manager:
            tools = self.tool_manager.get_tool_definitions()
            if tools:
                # Flatten from OpenAI chat nested format to Responses format
                flat_tools = []
                for tool in tools:
                    func = tool.get("function", {})
                    flat_tools.append({
                        "type": "function",
                        "name": func.get("name"),
                        "description": func.get("description", ""),
                        "parameters": func.get("parameters", {"type": "object", "properties": {}}),
                    })
                request_data["tools"] = flat_tools

        # Reasoning effort is nested in the Responses API. Valid values:
        # minimal/low/medium/high/xhigh. "none"/"max" are rejected -> omit.
        effort = Config.reasoning_effort()
        if effort and effort.lower() not in ("none", "max"):
            request_data["reasoning"] = {"effort": effort.lower()}

        # Escape hatch for provider-specific fields
        thinking_extra = Config.thinking_extra_body()
        if thinking_extra:
            request_data.update(thinking_extra)

        # Transform hook for provider-specific formats
        if self._plugin_system:
            request_data = self._plugin_system.call_hooks_with_return("transform_request", request_data) or request_data

        # NOTE: Config.thinking_params() emits top-level reasoning params
        # (chat-completions shape) which the Responses API rejects - not used
        # here. Use AICODER_THINKING_EXTRA_BODY or transform_request instead.

        return request_data

    def _map_usage(self, usage: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Map Responses usage to chat-completions shape for plugins/stats"""
        if not usage:
            return None
        input_details = usage.get("input_tokens_details") or {}
        output_details = usage.get("output_tokens_details") or {}
        mapped = {
            "prompt_tokens": usage.get("input_tokens") or 0,
            "completion_tokens": usage.get("output_tokens") or 0,
            "total_tokens": usage.get("total_tokens") or 0,
            "prompt_tokens_details": {"cached_tokens": input_details.get("cached_tokens") or 0},
            "completion_tokens_details": {"reasoning_tokens": output_details.get("reasoning_tokens") or 0},
        }
        if usage.get("cost_details"):
            mapped["cost_details"] = usage["cost_details"]
        if usage.get("cost") is not None:
            mapped["cost"] = usage["cost"]
        return mapped

    def _update_stats_on_success(self, start_time: float, usage: Optional[Dict[str, Any]]) -> None:
        if self.stats:
            log_debug("*** responses stats: increment_api_success, add_api_time")
            self.stats.increment_api_success()
            self.stats.add_api_time(time.time() - start_time)
            mapped = self._map_usage(usage)
            if mapped:
                self.stats.add_prompt_tokens(mapped["prompt_tokens"])
                self.stats.add_completion_tokens(mapped["completion_tokens"])

        # Fire usage hook AFTER stats are updated (elapsed is set)
        mapped = self._map_usage(usage)
        if mapped and self._plugin_system:
            self._plugin_system.call_hooks("after_usage_data", mapped)

    def _handle_streaming_response(self, response: Response, start_time: float) -> Generator[Dict[str, Any], None, None]:
        full_content = ""
        accumulated_tool_calls = {}
        tool_index = 0
        current_tool = None  # {"call_id","name","args"} while a function_call streams
        message_usage = None
        api_error = None

        # Read incrementally and process per event
        event_data = ""
        line_count = 0
        resp_log = None

        if Config.debug():
            log_debug("*** SSE streaming loop started")
            try:
                debug_dir = os.path.join(os.getcwd(), ".aicoder")
                os.makedirs(debug_dir, exist_ok=True)
                debug_file = os.path.join(debug_dir, debug_filename("last-response.log"))
                moved = rotate_debug_log(debug_file)
                if moved:
                    log_debug(f"*** Previous response log kept: {moved}")
                resp_log = open(debug_file, "w")
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

                            if Config.debug():
                                log_debug(f"*** SSE event: {json.dumps(data)}")

                            if dtype == "response.output_text.delta":
                                text = data.get("delta") or ""
                                if text:
                                    full_content += text
                                    yield {
                                        "choices": [{"delta": {"content": text}}],
                                        "done": False
                                    }

                            elif dtype == "response.output_item.added":
                                item = data.get("item") or {}
                                if item.get("type") == "function_call":
                                    current_tool = {
                                        "call_id": item.get("call_id") or item.get("id") or "",
                                        "name": item.get("name") or "",
                                        "args": item.get("arguments") or "",
                                    }

                            elif dtype == "response.function_call_arguments.delta":
                                if current_tool is not None:
                                    current_tool["args"] += data.get("delta") or ""

                            elif dtype == "response.output_item.done":
                                item = data.get("item") or {}
                                if item.get("type") == "function_call":
                                    call_id = item.get("call_id") or (current_tool or {}).get("call_id") or ""
                                    name = item.get("name") or (current_tool or {}).get("name") or ""
                                    args = item.get("arguments")
                                    if args is None:
                                        args = (current_tool or {}).get("args", "")
                                    call = {
                                        "id": call_id,
                                        "type": "function",
                                        "function": {"name": name, "arguments": args}
                                    }
                                    accumulated_tool_calls[call_id] = call
                                    yield {
                                        "choices": [{
                                            "delta": {
                                                "tool_calls": [{
                                                    "index": tool_index,
                                                    **call
                                                }]
                                            }
                                        }],
                                        "done": False
                                    }
                                    tool_index += 1
                                    current_tool = None

                            elif dtype == "response.completed":
                                resp = data.get("response") or {}
                                message_usage = resp.get("usage")

                            elif dtype == "response.failed":
                                resp = data.get("response") or {}
                                api_error = resp.get("error") or "response.failed"

                        except json.JSONDecodeError:
                            pass

                    event_data = ""
                continue

            event_data += line
        finally:
            if resp_log:
                resp_log.close()

        if api_error:
            yield {"error": json.dumps(api_error), "done": True}
            return

        self._update_stats_on_success(start_time, message_usage)

        # Final yield - content already streamed via deltas, so don't include
        # it to avoid double-printing.
        yield {
            "choices": [{
                "delta": {
                    "finish_reason": "stop",
                    "index": 0
                }
            }],
            "accumulated_tool_calls": accumulated_tool_calls,
            "done": True
        }

    def _handle_non_streaming_response(self, response: Response, start_time: float) -> Generator[Dict[str, Any], None, None]:
        data = response.json()

        full_content = ""
        accumulated_tool_calls = {}

        if data.get("error"):
            yield {"error": json.dumps(data["error"]), "done": True}
            return

        output = data.get("output") or []
        if isinstance(output, dict):
            output = [output]
        for item in output:
            item_type = item.get("type")
            if item_type == "message":
                for part in item.get("content") or []:
                    if part.get("type") == "output_text":
                        full_content += part.get("text", "")
            elif item_type == "function_call":
                call_id = item.get("call_id") or item.get("id") or ""
                accumulated_tool_calls[call_id] = {
                    "id": call_id,
                    "type": "function",
                    "function": {
                        "name": item.get("name", ""),
                        "arguments": item.get("arguments", "{}") or "{}"
                    }
                }

        self._update_stats_on_success(start_time, data.get("usage"))

        # Yield same format as streaming content chunks (with choices wrapper)
        tool_calls_list = [
            {**tc, "index": i} for i, tc in enumerate(accumulated_tool_calls.values())
        ]
        yield {
            "choices": [{
                "delta": {
                    "content": full_content,
                    "tool_calls": tool_calls_list
                },
                "finish_reason": "stop",
                "index": 0
            }],
            "done": True
        }

    def process_with_colorization(self, content: str) -> str:
        return self.colorizer.process_with_colorization(content)

    def reset_colorizer(self) -> None:
        self.colorizer.reset_state()
