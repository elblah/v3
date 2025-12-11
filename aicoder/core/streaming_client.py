"""Streaming client for API requests - Python version ported exactly from TypeScript"""

import json
import time
from typing import List, Generator, Optional, Dict, Any

from aicoder.core.config import Config
from aicoder.core.markdown_colorizer import MarkdownColorizer
from aicoder.utils.log import LogUtils
from aicoder.type_defs.api_types import StreamChunk, ApiUsage
from aicoder.type_defs.message_types import Message, MessageRole
from aicoder.type_defs.tool_types import ToolDefinition
from aicoder.utils.http_utils import fetch, Response
from dataclasses import dataclass


@dataclass
class ChoiceDelta:
    content: Optional[str] = None
    reasoning_content: Optional[str] = None
    tool_calls: Optional[List[Dict[str, Any]]] = None
    role: Optional[str] = None


@dataclass
class Choice:
    index: int
    delta: Optional[ChoiceDelta] = None
    finish_reason: Optional[str] = None


class StreamingClient:
    """Handles streaming API requests - exact port from TypeScript"""

    def __init__(self, stats: Optional[Any] = None, tool_manager: Optional[Any] = None):
        self.stats = stats
        self.colorizer = MarkdownColorizer()
        self.tool_manager = tool_manager

    def stream_request(
        self,
        messages: List[Message],
        stream: bool = True,
        throw_on_error: bool = False,
        send_tools: bool = True,
    ) -> Generator[StreamChunk, None, None]:
        """Stream API request - exact port from TypeScript streamRequest"""
        if Config.debug():
            LogUtils.debug(
                f"*** stream_request called with {len(messages)} messages, send_tools={send_tools}"
            )

        start_time = time.time()
        if self.stats:
            self.stats.increment_api_requests()

        # Retry up to 3 times like TS
        max_retries = 3

        for attempt_num in range(1, max_retries + 1):
            config = {"base_url": Config.base_url(), "model": Config.model()}

            try:
                self._log_retry_attempt(config, attempt_num)
                request_data = self._prepare_request_data(
                    messages, config["model"], stream
                )
                endpoint = f"{config['base_url']}/chat/completions"

                self._log_request_details(endpoint, config, request_data, attempt_num)
                headers = self._build_headers()

                self._log_api_config_debug(config)

                response = fetch(
                    endpoint,
                    {
                        "method": "POST",
                        "headers": headers,
                        "body": json.dumps(request_data),
                        "timeout": Config.total_timeout() / 1000,
                    },
                )

                if not response.ok():
                    self._log_error_response(response)
                    raise Exception(f"HTTP {response.status}: {response.reason}")

                # Handle case-insensitive header access
                content_type = ""
                for header_name, header_value in response.headers.items():
                    if header_name.lower() == "content-type":
                        content_type = header_value
                        break

                if Config.debug():
                    LogUtils.debug(
                        f"Response: {content_type}, streaming={content_type.startswith('text/event-stream')}"
                    )

                if self._is_streaming_response(content_type):
                    yield from self._handle_streaming_response(response)
                else:
                    if Config.debug():
                        LogUtils.debug(
                            f"API returned non-streaming response, Content-Type: {content_type}"
                        )
                    yield from self._handle_non_streaming_response(response)

                self._update_stats_on_success(start_time)
                return  # Success - exit retry loop

            except Exception as error:
                if not self._handle_attempt_error(
                    error, attempt_num, max_retries, throw_on_error, start_time
                ):
                    return

    def _log_retry_attempt(self, config: Dict[str, str], attempt_num: int) -> None:
        """Log retry attempt - exact port from TS"""
        if Config.debug() and attempt_num > 1:
            from aicoder.utils.log import LogUtils

            LogUtils.debug(
                f"*** Retrying: {config['base_url']} with model {config['model']}",
                Config.colors["yellow"],
            )

    def _log_request_details(
        self,
        endpoint: str,
        config: Dict[str, str],
        request_data: Dict[str, Any],
        attempt_num: int,
    ) -> None:
        """Log request details - exact port from TS"""
        if Config.debug():
            from aicoder.utils.log import LogUtils

            tools_count = len(request_data.get("tools", []))
            tool_choice = request_data.get("tool_choice", "none")
            LogUtils.debug(
                f"API Request: {tools_count} tools, tool_choice={tool_choice}"
            )

    def _log_api_config_debug(self, config: Dict[str, str]) -> None:
        """Log API config for debugging - exact port from TS"""
        if Config.debug():
            from aicoder.utils.log import LogUtils

            LogUtils.debug(f"Base URL: {config['base_url']}")
            LogUtils.debug(f"Model: {config['model']}")

    def _make_api_request(
        self, endpoint: str, headers: Dict[str, str], request_data: str
    ) -> Response:
        """Make API request - exact port from TS makeApiRequest"""
        # This is handled by fetch() in Python version
        pass

    def _log_error_response(self, response: Response) -> None:
        """Log error response - exact port from TS"""
        if Config.debug():
            from aicoder.utils.log import LogUtils

            LogUtils.debug(f"Error response status: {response.status}")
            LogUtils.debug(f"Error response headers: {response.headers}")

            try:
                error_data = response.json()
                LogUtils.debug(
                    f"Error response body: {json.dumps(error_data, indent=2)}"
                )
            except:
                LogUtils.debug("Error response body: <could not parse as JSON>")

    def _log_attempt_error(self, error: Exception, attempt_num: int) -> None:
        """Log attempt error - exact port from TS"""
        if Config.debug():
            from aicoder.utils.log import LogUtils

            LogUtils.error(f"Attempt {attempt_num} failed: {error}")
            LogUtils.error(f"Error type: {type(error)}")
            LogUtils.error(
                f"Error stack: {getattr(error, '__traceback__', 'No stack')}"
            )

    def _handle_final_attempt_failure(
        self, error: Exception, throw_on_error: bool, start_time: float
    ) -> bool:
        """Handle final attempt failure - exact port from TS"""
        if self.stats:
            self.stats.increment_api_errors()
            self.stats.add_api_time((time.time() - start_time))

        error_message = f"All API attempts failed. Last error: {str(error)}"
        from aicoder.utils.log import LogUtils

        LogUtils.error(error_message)

        if throw_on_error:
            raise Exception(error_message)

        return False  # Exit retry loop

    def _update_stats_on_success(self, start_time: float) -> None:
        """Update stats on success - exact port from TS"""
        if self.stats:
            self.stats.increment_api_success()
            self.stats.add_api_time((time.time() - start_time))

    def _prepare_request_data(
        self,
        messages: List[Message],
        model: Optional[str],
        stream: bool,
        send_tools: bool = True,
    ) -> Dict[str, Any]:
        """Prepare request data - exact port from TS"""
        data = {
            "model": model or Config.model(),
            "messages": self._format_messages(messages),
            "stream": stream,
        }

        # Only include temperature if explicitly set by user
        temperature = Config.temperature()
        if temperature is not None:
            data["temperature"] = temperature

        # Add max tokens if configured
        if Config.max_tokens():
            data["max_tokens"] = Config.max_tokens()

        # Add tool definitions only if send_tools is True
        if send_tools:
            self._add_tool_definitions(data)

        return data

    def _add_tool_definitions(self, data: Dict[str, Any]) -> None:
        """Add tool definitions to request data - exact port from TS"""
        if not self.tool_manager:
            return

        tool_definitions = self.tool_manager.get_tool_definitions()

        if tool_definitions and len(tool_definitions) > 0:
            data["tools"] = tool_definitions
            data["tool_choice"] = "auto"

            if Config.debug():
                LogUtils.debug(f"*** Tool definitions count: {len(tool_definitions)}")
                LogUtils.debug(f"*** Message count: {len(data.get('messages', []))}")

    def _format_messages(self, messages: List[Message]) -> List[Dict[str, Any]]:
        """Format messages for API - exact port from TS"""
        formatted = []
        for msg in messages:
            msg_dict = {"role": msg.get("role"), "content": msg.get("content")}

            if msg.get("tool_calls"):
                msg_dict["tool_calls"] = msg["tool_calls"]

            if msg.get("tool_call_id"):
                msg_dict["tool_call_id"] = msg["tool_call_id"]

            formatted.append(msg_dict)

        return formatted

    def _build_headers(self) -> Dict[str, str]:
        """Build request headers - exact port from TS"""
        headers = {
            "Content-Type": "application/json",
            "Accept": "text/event-stream",
            "User-Agent": "Mozilla/5.0",
            "Referer": "http://localhost",
        }

        # Add API key if available
        api_key = Config.api_key()
        if api_key:
            headers["Authorization"] = f"Bearer {api_key}"

        return headers

    def _is_streaming_response(self, content_type: str) -> bool:
        """Check if response is streaming - exact port from TS"""
        return "text/event-stream" in content_type.lower()

    def _handle_streaming_response(
        self, response: Response
    ) -> Generator[StreamChunk, None, None]:
        """Handle streaming response - exact port from TS handleStreamingResponse"""
        try:
            if not response:
                raise Exception("No response body for streaming")

            from aicoder.utils.log import LogUtils

            buffer = ""
            raw_response = ""

            # Read response incrementally like TypeScript
            while True:
                line_bytes = (
                    response.readline()
                )  # Read one SSE line at a time like dt-aicoder
                if not line_bytes:
                    break

                line = line_bytes.decode("utf-8").rstrip("\n")
                raw_response += line + "\n"

                # Debug: print first few lines
                if Config.debug() and len(raw_response) < 200:
                    LogUtils.debug(f"SSE line: {repr(line)}")

                # Skip empty lines
                if line.strip() == "":
                    continue

                if Config.debug() and "tool_calls" in line:
                    LogUtils.debug(f"Tool call detected in stream")

                if line.startswith("data:"):
                    data_str = line[
                        5:
                    ]  # Remove 'data:' prefix (handle both 'data:' and 'data: ')
                    # Remove leading space if present
                    if data_str.startswith(" "):
                        data_str = data_str[1:]
                    if data_str == "[DONE]":
                        if Config.debug():
                            LogUtils.debug("Received [DONE] signal")
                        return

                    try:
                        if Config.debug() and "tool_calls" in data_str:
                            LogUtils.debug(f"Tool call JSON: {data_str[:100]}...")
                        chunk_data = json.loads(data_str)

                        # Convert dict choices to Choice objects
                        choices = []
                        if chunk_data.get("choices"):
                            for choice_dict in chunk_data["choices"]:
                                # Convert delta dict to ChoiceDelta object
                                delta_dict = choice_dict.get("delta", {})
                                delta = ChoiceDelta(
                                    content=delta_dict.get("content"),
                                    reasoning_content=delta_dict.get(
                                        "reasoning_content"
                                    ),
                                    tool_calls=delta_dict.get("tool_calls"),
                                    role=delta_dict.get("role"),
                                )

                                choice = Choice(
                                    index=choice_dict.get("index", 0),
                                    delta=delta,
                                    finish_reason=choice_dict.get("finish_reason"),
                                )
                                choices.append(choice)

                        # Create StreamChunk object
                        chunk = StreamChunk(
                            id=chunk_data.get("id"),
                            object=chunk_data.get("object"),
                            created=chunk_data.get("created"),
                            model=chunk_data.get("model"),
                            choices=choices,
                            usage=self._create_usage(chunk_data.get("usage")),
                        )

                        if (
                            Config.debug()
                            and chunk.choices
                            and chunk.choices[0].delta.tool_calls
                        ):
                            LogUtils.debug(
                                f"Tool call chunk: {len(chunk.choices[0].delta.tool_calls)} calls"
                            )
                        yield chunk
                    except Exception as error:
                        LogUtils.error(f"SSE Parse Error: {error}")
                        LogUtils.error(f"Raw data: {data_str[:200]}")
                        continue

        finally:
            # Python doesn't have reader.releaseLock() like TS
            pass

    def _handle_non_streaming_response(
        self, response: Response
    ) -> Generator[StreamChunk, None, None]:
        """Handle non-streaming response - exact port from TS handleNonStreamingResponse"""
        data = response.json()

        # Convert non-streaming response to streaming format like TS
        if data.get("choices") and len(data["choices"]) > 0:
            choice = data["choices"][0]

            if choice.get("message"):
                # Create synthetic streaming chunk from complete message
                chunk: StreamChunk = {
                    "choices": [
                        {
                            "delta": {
                                "content": choice["message"].get("content"),
                                "tool_calls": choice["message"].get("tool_calls"),
                            },
                            "finish_reason": choice.get("finish_reason"),
                            "index": choice.get("index", 0),
                        }
                    ]
                }

                # Update stats from usage if available
                usage = data.get("usage")
                if usage:
                    self._update_stats_from_usage(ApiUsage(**usage))

                yield chunk
                return

    def _handle_attempt_error(
        self,
        error: Exception,
        attempt_num: int,
        max_retries: int,
        throw_on_error: bool,
        start_time: float,
    ) -> bool:
        """Handle attempt error - exact port from TS handleAttemptError"""
        self._log_attempt_error(error, attempt_num)

        if attempt_num < max_retries:
            # Continue retrying
            return True
        else:
            # Final attempt failed
            return self._handle_final_attempt_failure(error, throw_on_error, start_time)

    def _update_stats_from_usage(self, usage: ApiUsage) -> None:
        """Update stats from usage - exact port from TS"""
        if self.stats:
            if hasattr(usage, "prompt_tokens"):
                self.stats.add_prompt_tokens(usage.prompt_tokens)
            if hasattr(usage, "completion_tokens"):
                self.stats.add_completion_tokens(usage.completion_tokens)

    # Methods for colorization (from original Python version)
    def process_with_colorization(self, content: str) -> str:
        """Process content with colorization"""
        return self.colorizer.process_with_colorization(content)

    def reset_colorizer(self) -> None:
        """Reset colorizer state"""
        self.colorizer.reset_state()

    def _create_usage(self, usage_data: Optional[Dict[str, Any]]) -> Optional[ApiUsage]:
        """Create ApiUsage object from dict data"""
        if not usage_data:
            return None
        return ApiUsage(
            prompt_tokens=usage_data.get("prompt_tokens"),
            completion_tokens=usage_data.get("completion_tokens"),
            total_tokens=usage_data.get("total_tokens"),
        )

    def update_token_stats(self, usage: Any) -> None:
        """Update token statistics"""
        if self.stats and usage:
            prompt_tokens = getattr(usage, "prompt_tokens", 0)
            completion_tokens = getattr(usage, "completion_tokens", 0)
            self.stats.add_prompt_tokens(prompt_tokens)
            self.stats.add_completion_tokens(completion_tokens)
