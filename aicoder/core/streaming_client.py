"""Streaming API client for AI requests"""

import json
import sys
import time
import itertools
import os
from typing import List, Generator, Optional, Dict, Any

from aicoder.core.config import Config
from aicoder.core.markdown_colorizer import MarkdownColorizer
from aicoder.utils.log import error as log_error, warn as log_warn, info as log_info, debug as log_debug
from aicoder.utils.http_utils import fetch, Response





class StreamingClient:
    """Handles streaming API requests"""

    def __init__(self, stats: Optional[Any] = None, tool_manager: Optional[Any] = None, message_history: Optional[Any] = None):
        self.stats = stats
        self.colorizer = MarkdownColorizer()
        self.tool_manager = tool_manager
        self.message_history = message_history
        self._recovery_attempted = False
        self._plugin_system = None
        self._last_raw_usage = None
        # Pending state for Alibaba SDK streaming tool calls
        self._pending_tool_name = None
        self._pending_tool_id = None
        self._pending_tool_index = None
        self._pending_tool_args = None

    def set_plugin_system(self, plugin_system) -> None:
        """Set plugin system for hooks"""
        self._plugin_system = plugin_system

    def _calculate_backoff(self, attempt_num: int) -> float:
        """Calculate exponential backoff: 2s, 4s, 8s, 16s, 32s, max_backoff (capped)"""
        max_backoff = Config.effective_max_backoff()
        return min(2 ** (attempt_num + 1), max_backoff)

    def _wait_for_retry(self, attempt_num: int) -> None:
        """Wait before retry with backoff and show message"""
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
        """Stream API request - streamRequest"""
        # Use config default if stream parameter is not explicitly set
        if stream is None:
            stream = Config.streaming_enabled()

        if Config.debug():
            log_debug(
                f"*** stream_request called with {len(messages)} messages, stream={stream}, send_tools={send_tools}"
            )

        start_time = time.time()
        if self.stats:
            self.stats.increment_api_requests()

        # Reset recovery flag for each new request
        self._recovery_attempted = False

        max_retries = Config.effective_max_retries()

        for attempt_num in range(1, max_retries + 1) if max_retries > 0 else itertools.count(1):
            config = {"base_url": Config.base_url(), "model": Config.model()}

            try:
                self._log_retry_attempt(config, attempt_num)
                request_data = self._prepare_request_data(
                    messages, config["model"], stream, send_tools
                )
                endpoint = Config.api_endpoint()

                self._log_request_details(endpoint, config, request_data, attempt_num)
                headers = self._build_headers(stream)

                self._log_api_config_debug(config)

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

                # Call plugin hook before API request (for throttling, etc.)
                if self._plugin_system:
                    self._plugin_system.call_hooks("before_api_request", endpoint, request_data)

                response = None
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
                    self._log_error_response(response)
                    error_msg = f"HTTP {response.status}: {response.reason}"
                    if not Config.suppress_error_body():
                        try:
                            error_data = response.json()
                            if error_data and isinstance(error_data, dict):
                                error_msg += f" - {json.dumps(error_data)}"
                        except Exception:
                            pass
                    raise Exception(error_msg)

                # Handle case-insensitive header access
                content_type = ""
                for header_name, header_value in response.headers.items():
                    if header_name.lower() == "content-type":
                        content_type = header_value
                        break

                if Config.debug():
                    log_debug(
                        f"Response: {content_type}, streaming={content_type.startswith('text/event-stream')}"
                    )

                if self._is_streaming_response(content_type):
                    yield from self._handle_streaming_response(response)
                else:
                    if Config.debug():
                        log_debug(
                            f"API returned non-streaming response, Content-Type: {content_type}"
                        )
                    yield from self._handle_non_streaming_response(response)

                self._update_stats_on_success(start_time)

                # Fire usage hook AFTER stats are updated (elapsed is set)
                if self._last_raw_usage and self._plugin_system:
                    self._plugin_system.call_hooks("after_usage_data", self._last_raw_usage)
                    self._last_raw_usage = None

                return  # Success - exit retry loop

            except Exception as error:
                if not self._handle_attempt_error(
                    error, attempt_num, max_retries, throw_on_error, start_time
                ):
                    return

                # Fire error hook with real HTTP status from response (no text parsing)
                if self._plugin_system:
                    try:
                        http_status = response.status
                    except (NameError, AttributeError):
                        http_status = 0
                    if http_status:
                        self._plugin_system.call_hooks("on_api_error", str(error), http_status)
                    else:
                        self._plugin_system.call_hooks("on_api_error", str(error), 0)

                # Wait before next retry (except for last attempt)
                # In unlimited mode (max_retries=0), always wait and continue
                if max_retries == 0 or attempt_num < max_retries:
                    self._wait_for_retry(attempt_num - 1)

    def _log_retry_attempt(self, config: Dict[str, str], attempt_num: int) -> None:
        """Log retry attempt -"""
        if Config.debug() and attempt_num > 1:

            log_debug(
                f"*** Retrying: {config['base_url']} with model {config['model']}",
                "yellow",
            )

    def _log_request_details(
        self,
        endpoint: str,
        config: Dict[str, str],
        request_data: Dict[str, Any],
        attempt_num: int,
    ) -> None:
        """Log request details -"""
        if Config.debug():

            tools_count = len(request_data.get("tools", []))
            tool_choice = request_data.get("tool_choice", "none")
            log_debug(
                f"API Request: {tools_count} tools, tool_choice={tool_choice}"
            )

    def _log_api_config_debug(self, config: Dict[str, str]) -> None:
        """Log API config for debugging -"""
        if Config.debug():

            log_debug(f"Base URL: {config['base_url']}")
            log_debug(f"Model: {config['model']}")

    def _make_api_request(
        self, endpoint: str, headers: Dict[str, str], request_data: str
    ) -> Response:
        """Make API request - makeApiRequest"""
        # This is handled by fetch() in Python version
        pass

    def _log_error_response(self, response: Response) -> None:
        """Log error response -"""
        if Config.debug():

            log_debug(f"Error response status: {response.status}")
            log_debug(f"Error response headers: {response.headers}")

            try:
                error_data = response.json()
                log_debug(
                    f"Error response body: {json.dumps(error_data, indent=2)}"
                )
            except Exception:
                log_debug("Error response body: <could not parse as JSON>")

    def _log_attempt_error(self, error: Exception, attempt_num: int) -> None:
        """Log attempt error -"""
        if Config.debug():

            log_error(f"Attempt {attempt_num} failed: {error}")
            log_error(f"Error type: {type(error)}")
            log_error(
                f"Error stack: {getattr(error, '__traceback__', 'No stack')}"
            )

    def _handle_final_attempt_failure(
        self, error: Exception, throw_on_error: bool, start_time: float
    ) -> bool:
        """Handle final attempt failure -"""
        if self.stats:
            self.stats.increment_api_errors()
            self.stats.add_api_time((time.time() - start_time))

        error_message = f"All API attempts failed. Last error: {str(error)}"

        log_error(error_message)

        if throw_on_error:
            raise Exception(error_message)

        return False  # Exit retry loop

    def _update_stats_on_success(self, start_time: float) -> None:
        """Update stats on success -"""
        if self.stats:
            log_debug("*** _update_stats_on_success: increment_api_success, add_api_time")
            self.stats.increment_api_success()
            self.stats.add_api_time((time.time() - start_time))

    def _prepare_request_data(
        self,
        messages: List[Dict[str, Any]],
        model: Optional[str],
        stream: bool,
        send_tools: bool = True,
    ) -> Dict[str, Any]:
        """Prepare request data -"""
        data = {
            "model": model or Config.model(),
            "messages": self._format_messages(messages),
            "stream": stream,
        }

        if stream:
            data["stream_options"] = {"include_usage": True}

        self._add_optional_parameters(data)

        # Add tool definitions only if send_tools is True
        if send_tools:
            self._add_tool_definitions(data)

        # Add extra_body for thinking mode if configured
        extra_body = Config.thinking_extra_body()
        if extra_body:
            data.update(extra_body)
            if Config.debug():
                log_debug(f"*** Adding extra_body: {extra_body}")

        # Add top-level thinking params (e.g., reasoning_effort for DeepSeek, reasoningEffort for GLM)
        thinking_params = Config.thinking_params()
        if thinking_params:
            data.update(thinking_params)
            if Config.debug():
                log_debug(f"*** Adding thinking_params: {thinking_params}")

        # Transform hook for provider-specific formats (e.g., alibaba cache control)
        if self._plugin_system:
            data = self._plugin_system.call_hooks_with_return("transform_request", data) or data

        return data

    def _add_optional_parameters(self, data: Dict[str, Any]) -> None:
        """Add optional model parameters if configured"""
        optional_params = [
            ("temperature", Config.temperature()),
            ("top_p", Config.top_p()),
            ("frequency_penalty", Config.frequency_penalty()),
            ("presence_penalty", Config.presence_penalty()),
            ("top_k", Config.top_k()),
            ("repetition_penalty", Config.repetition_penalty()),
            ("max_tokens", Config.max_tokens()),
        ]

        for param_name, value in optional_params:
            if value is not None:
                data[param_name] = value

    def _add_tool_definitions(self, data: Dict[str, Any]) -> None:
        """Add tool definitions to request data -"""
        if not self.tool_manager:
            return

        tool_definitions = self.tool_manager.get_tool_definitions()

        if tool_definitions and len(tool_definitions) > 0:
            data["tools"] = tool_definitions
            data["tool_choice"] = "auto"

            if Config.debug():
                log_debug(f"*** Tool definitions count: {len(tool_definitions)}")
                log_debug(f"*** Message count: {len(data.get('messages', []))}")

    def _format_messages(self, messages: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """Format messages for API -"""
        formatted = []
        for msg in messages:
            msg_dict = {"role": msg.get("role"), "content": msg.get("content")}

            if msg.get("tool_calls"):
                msg_dict["tool_calls"] = msg["tool_calls"]

            if msg.get("tool_call_id"):
                msg_dict["tool_call_id"] = msg["tool_call_id"]

            # Preserve reasoning with the field name the current provider expects
            # clear_thinking=True strips reasoning from non-tool-call messages (save bandwidth)
            if Config.clear_thinking() is True and not msg.get("tool_calls"):
                pass  # strip reasoning from non-tool-call assistant messages
            else:
                override = Config.get_reasoning_field()
                if override:
                    # Remap: find reasoning from any stored field, send with override name
                    for field in Config.get_possible_reasoning_fields():
                        if msg.get(field):
                            msg_dict[override] = msg[field]
                            break
                else:
                    # No override: preserve whatever field name was stored
                    for field in Config.get_possible_reasoning_fields():
                        if msg.get(field):
                            msg_dict[field] = msg[field]
                            break

            formatted.append(msg_dict)

        return formatted

    def _build_headers(self, stream: bool = True) -> Dict[str, str]:
        """Build request headers -"""
        headers = {
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0",
        }
        if Config.gzip_enabled():
            headers["Accept-Encoding"] = "gzip, deflate"
        if stream:
            headers["Accept"] = "text/event-stream"

        # Add API key if available
        api_key = Config.api_key()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        # Add custom headers from environment
        custom_headers = Config.http_headers()
        headers.update(custom_headers)

        return headers

    def _is_streaming_response(self, content_type: str) -> bool:
        """Check if response is streaming -"""
        return "text/event-stream" in content_type.lower()

    def _handle_streaming_response(
        self, response: Response
    ) -> Generator[Dict[str, Any], None, None]:
        """Handle streaming response - handleStreamingResponse"""
        try:
            if not response:
                raise Exception("No response body for streaming")

            thinking_printed = False

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

            raw_response = ""

            # Read response incrementally
            while True:
                line_bytes = (
                    response.readline()
                )  # Read one SSE line at a time
                if not line_bytes:
                    break

                line = line_bytes.decode("utf-8").rstrip("\n")
                raw_response += line + "\n"

                # Debug: print first few lines
                if Config.debug() and len(raw_response) < 200:
                    log_debug(f"SSE line: {repr(line)}")

                # Skip empty lines
                if line.strip() == "":
                    continue

                if Config.debug() and "tool_calls" in line:
                    log_debug(f"Tool call detected in stream: {line[:100]}")

                if line.startswith("data:"):
                    data_str = line[
                        5:
                    ]  # Remove 'data:' prefix (handle both 'data:' and 'data: ')
                    # Remove leading space if present
                    if data_str.startswith(" "):
                        data_str = data_str[1:]
                    if data_str == "[DONE]":
                        if Config.debug():
                            log_debug("Received [DONE] signal")
                        return

                    try:
                        if Config.debug() and "tool_calls" in data_str:
                            log_debug(f"Tool call JSON: {data_str[:100]}...")
                        chunk_data = json.loads(data_str)

                        # Use choice dicts directly
                        choices = []
                        if chunk_data.get("choices"):
                            for choice_dict in chunk_data["choices"]:
                                choice = choice_dict
                                choices.append(choice)

                            # Show thinking indicator if any reasoning field present
                            for c in choices:
                                delta = c.get("delta", {})
                                override = Config.get_reasoning_field()
                                fields = [override] if override else Config.get_possible_reasoning_fields()
                                if any(delta.get(f) and delta.get(f).strip() for f in fields):
                                    _show_thinking()
                                    break
                        else:
                            # Alibaba SDK format: check content_block.type
                            content_block = chunk_data.get("content_block", {})
                            block_type = content_block.get("type", "")
                            # Only yield for content_block with tool_use if NOT a content_block_start event
                            # content_block_start is handled separately below
                            if block_type == "tool_use" and chunk_data.get("type") != "content_block_start":
                                choice = {
                                    "delta": {
                                        "tool_calls": [{
                                            "index": chunk_data.get("index", 0),
                                            "id": content_block.get("id", ""),
                                            "type": "function",
                                            "function": {
                                                "name": content_block.get("name", ""),
                                                "arguments": json.dumps(content_block.get("input", {})),
                                            }
                                        }]
                                    },
                                }
                                choices = [choice]
                                chunk_data["model"] = chunk_data.get("message", {}).get("model") or chunk_data.get("model")

                        # Handle input_json_delta for streaming tool arguments (Alibaba SDK)
                        delta = chunk_data.get("delta", {})
                        delta_type = delta.get("type", "")

                        if delta_type == "input_json_delta":
                            partial = delta.get("partial_json", "")
                            if partial:
                                # Track pending tool args - DON'T yield here, wait for message_delta
                                if not hasattr(self, '_pending_tool_args') or self._pending_tool_args is None:
                                    self._pending_tool_args = ""
                                self._pending_tool_args += partial
                                if Config.debug():
                                    log_debug(f"*** input_json_delta: accumulated={repr(self._pending_tool_args[:100])}")

                        elif delta_type == "text_delta" and not choices:
                            # Only yield text if no choices already set (tool_use takes priority)
                            text = delta.get("text", "")
                            if text:
                                choice = {"delta": {"content": text}}
                                choices = [choice]

                        elif delta_type == "thinking_delta" and not choices:
                            thinking = delta.get("thinking", "")
                            if thinking:
                                choice = {"delta": {"thinking": thinking}}
                                choices = [choice]

                        # Handle content_block_start for tool_use (Alibaba SDK)
                        if chunk_data.get("type") == "content_block_start":
                            content_block = chunk_data.get("content_block", {})
                            if content_block.get("type") == "tool_use":
                                # Store tool info - DON'T yield, wait for message_delta
                                self._pending_tool_name = content_block.get("name", "")
                                self._pending_tool_id = content_block.get("id", "")
                                self._pending_tool_index = chunk_data.get("index", 0)
                                self._pending_tool_args = ""
                                # Skip to chunk creation with empty choices
                                if Config.debug():
                                    log_debug(f"*** content_block_start tool_use: name={self._pending_tool_name}, id={self._pending_tool_id}")

                        # Handle message_delta for tool_use completion (Alibaba SDK)
                        elif chunk_data.get("type") == "message_delta":
                            stop_reason = delta.get("stop_reason", "")
                            if stop_reason == "tool_use":
                                # Yield final tool call with accumulated args
                                tool_name = getattr(self, '_pending_tool_name', '') or ""
                                tool_id = getattr(self, '_pending_tool_id', '') or ""
                                tool_index = getattr(self, '_pending_tool_index', 0) or 0
                                tool_args = getattr(self, '_pending_tool_args', '') or ""
                                if tool_name and tool_args:
                                    choice = {
                                        "delta": {
                                            "tool_calls": [{
                                                "index": tool_index,
                                                "id": tool_id,
                                                "type": "function",
                                                "function": {
                                                    "name": tool_name,
                                                    "arguments": tool_args
                                                }
                                            }]
                                        },
                                    }
                                    choices = [choice]
                                    if Config.debug():
                                        log_debug(f"*** message_delta yielding tool: name={tool_name}, args={tool_args}")
                                # Clear pending
                                self._pending_tool_name = None
                                self._pending_tool_id = None
                                self._pending_tool_index = None
                                self._pending_tool_args = None

                        # Store raw usage (hook fires after streaming completes)
                        raw_usage = chunk_data.get("usage")

                        # Clear thinking indicator once real content or tool call arrives
                        if thinking_printed and any(
                            c.get("delta", {}).get("content") or c.get("delta", {}).get("tool_calls")
                            for c in choices
                        ):
                            _clear_thinking()

                        chunk = {
                            "id": chunk_data.get("id"),
                            "object": chunk_data.get("object"),
                            "created": chunk_data.get("created"),
                            "model": chunk_data.get("model"),
                            "choices": choices,
                            "usage": self._create_usage(raw_usage),
                        }

                        if raw_usage:
                            self._last_raw_usage = raw_usage

                        # Handle message_stop (end of Alibaba stream)
                        if chunk_data.get("type") == "message_stop":
                            if Config.debug():
                                log_debug("Received message_stop")
                            return

                        if Config.debug():
                            if chunk_data.get("model"):
                                log_debug(f"*** Model: {chunk_data.get('model')}")
                            if chunk_data.get("provider"):
                                log_debug(f"*** Provider: {chunk_data.get('provider')}")
                        yield chunk
                    except Exception as error:
                        log_error(f"SSE Parse Error: {error}")
                        log_error(f"Raw data: {data_str[:200]}")
                        continue

        finally:
            # Save raw SSE response for debugging
            if Config.debug():
                debug_dir = os.path.join(os.getcwd(), ".aicoder")
                os.makedirs(debug_dir, exist_ok=True)
                debug_file = os.path.join(debug_dir, "last-response.log")
                try:
                    with open(debug_file, "w") as f:
                        f.write(raw_response)
                    log_debug(f"*** Streaming response saved to {debug_file}")
                except Exception as e:
                    log_debug(f"*** Failed to save streaming response: {e}")

    def _handle_non_streaming_response(
        self, response: Response
    ) -> Generator[Dict[str, Any], None, None]:
        """Handle non-streaming response - handleNonStreamingResponse"""
        data = response.json()

        # Save response for debugging
        if Config.debug():
            debug_dir = os.path.join(os.getcwd(), ".aicoder")
            os.makedirs(debug_dir, exist_ok=True)
            debug_file = os.path.join(debug_dir, "last-response.json")
            try:
                with open(debug_file, "w") as f:
                    json.dump(data, f, indent=2)
                log_debug(f"*** Non-streaming response saved to {debug_file}")
            except Exception as e:
                log_debug(f"*** Failed to save response: {e}")

            # Log discovered model/provider info
            model = data.get("model")
            provider = data.get("provider")
            if model:
                log_debug(f"*** Model: {model}")
            if provider:
                log_debug(f"*** Provider: {provider}")

        # Convert non-streaming response to streaming format
        if data.get("choices") and len(data["choices"]) > 0:
            choice = data["choices"][0]

            if choice.get("message"):
                message = choice["message"]
                # Create synthetic streaming chunk from complete message
                # Include reasoning fields for multi-provider support
                chunk: Dict[str, Any] = {
                    "choices": [
                        {
                            "delta": {
                                "content": message.get("content"),
                                "tool_calls": message.get("tool_calls"),
                                # Include reasoning fields (same list as streaming handler)
                                "reasoning_content": message.get("reasoning_content"),
                                "reasoning": message.get("reasoning"),
                                "thinking": message.get("thinking"),
                                "reasoning_text": message.get("reasoning_text"),
                            },
                            "finish_reason": choice.get("finish_reason"),
                            "index": choice.get("index", 0),
                        }
                    ]
                }

                # Update stats from usage if available
                usage = data.get("usage")
                if usage:
                    self._update_stats_from_usage(usage)
                    self._last_raw_usage = usage

                yield chunk
                return

    @staticmethod
    def _parse_http_status(error_msg: str) -> int:
        """Parse HTTP status code from error message like 'HTTP 429: Too Many Requests'"""
        if error_msg.startswith("HTTP "):
            try:
                return int(error_msg.split()[1])
            except (IndexError, ValueError):
                pass
        return 0

    def _handle_attempt_error(
        self,
        error: Exception,
        attempt_num: int,
        max_retries: int,
        throw_on_error: bool,
        start_time: float,
    ) -> bool:
        """Handle attempt error"""
        error_msg = str(error) if error else "Unknown error"
        status = self._parse_http_status(error_msg)

        # Defense-in-depth: remove orphan tool results that cause "tool result's
        # tool id not found" (2013) errors. Idempotent — no harm if none exist.
        if self.message_history:
            orphan_count = self.message_history.remove_orphan_tool_results()
            if orphan_count:
                log_info(f"[*] Removed {orphan_count} orphaned tool result(s), retrying...")
                return True  # Retry — the data is now consistent

        # Check if context is too large and attempt auto-recovery (once per request)
        if self.message_history and self.stats and not throw_on_error:
            current_size = self.stats.current_prompt_size or 0
            threshold = Config.auto_compact_threshold()
            if current_size > threshold and not self._recovery_attempted:
                log_warn("[*] API failed with large context - attempting auto-recovery")
                log_warn(f"[*] Context size: {current_size:,} (threshold: {threshold:,})")
                self._recovery_attempted = True
                self.message_history.force_compact_rounds(1)
                log_info("[*] Retrying request after compaction...")
                return True  # Retry with compacted context

        # Don't retry if HTTP status is known and not in retryable set
        retryable = Config.retry_status_codes()
        if status != 0 and status not in retryable:
            log_warn(f"Not retrying HTTP {status} (not in retryable codes: {sorted(retryable)})")
            if self.stats:
                self.stats.increment_api_errors()
                self.stats.add_api_time((time.time() - start_time))
            if throw_on_error:
                raise Exception(error_msg)
            return False


        # Display attempt count (unlimited mode doesn't show max)
        if max_retries == 0:
            log_warn(f"Attempt {attempt_num} failed: {error_msg}")
            return True  # Always retry in unlimited mode
        else:
            log_warn(f"Attempt {attempt_num}/{max_retries} failed: {error_msg}")

            if attempt_num < max_retries:
                return True
            else:
                # Final attempt failed
                if self.stats:
                    self.stats.increment_api_errors()
                    self.stats.add_api_time((time.time() - start_time))

                log_error(f"All {max_retries} attempts failed. Last error: {error_msg}")
                log_warn("Use /retry to try again or /retry limit <n> to increase retries.")

                if throw_on_error:
                    raise Exception(f"All attempts failed: {error_msg}")

                return False

    def _update_stats_from_usage(self, usage: Dict[str, Any]) -> None:
        """Update basic stats from usage"""
        if self.stats and usage:
            # Handle both dict and object types
            if isinstance(usage, dict):
                prompt_tokens = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
                completion_tokens = usage.get("completion_tokens") or usage.get("output_tokens") or 0
            else:
                prompt_tokens = getattr(usage, "prompt_tokens", 0) or getattr(usage, "input_tokens", 0) or 0
                completion_tokens = getattr(usage, "completion_tokens", 0) or getattr(usage, "output_tokens", 0) or 0

            self.stats.add_prompt_tokens(prompt_tokens)
            self.stats.add_completion_tokens(completion_tokens)

    # Methods for colorization (from original Python version)
    def process_with_colorization(self, content: str) -> str:
        """Process content with colorization"""
        return self.colorizer.process_with_colorization(content)

    def reset_colorizer(self) -> None:
        """Reset colorizer state"""
        self.colorizer.reset_state()

    def _create_usage(self, usage_data: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
        """Create ApiUsage object from dict data"""
        if not usage_data:
            return None
        # Cost: prefer upstream_inference_cost, fall back to cost field
        cost = (usage_data.get("cost_details", {}).get("upstream_inference_cost")
               or usage_data.get("cost") or 0)
        prompt_details = usage_data.get("prompt_tokens_details") or {}
        return {
            "prompt_tokens": usage_data.get("prompt_tokens") or usage_data.get("input_tokens") or 0,
            "completion_tokens": usage_data.get("completion_tokens") or usage_data.get("output_tokens") or 0,
            "total_tokens": usage_data.get("total_tokens") or 0,
            "cache_read": (prompt_details.get("cached_tokens")
                         or usage_data.get("cache_read_input_tokens")
                         or usage_data.get("prompt_cache_hit_tokens") or 0),
            "cache_creation": usage_data.get("cache_creation_input_tokens") or usage_data.get("prompt_cache_miss_tokens") or 0,
            "cost": cost,
        }
    def update_token_stats(self, usage: Dict[str, Any]) -> None:
        """Update token statistics"""
        if self.stats and usage:
            prompt_tokens = usage.get("prompt_tokens") or usage.get("input_tokens") or 0
            completion_tokens = usage.get("completion_tokens") or usage.get("output_tokens") or 0

            self.stats.add_prompt_tokens(prompt_tokens)
            self.stats.add_completion_tokens(completion_tokens)
