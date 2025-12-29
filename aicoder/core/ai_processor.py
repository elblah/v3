"""
Generic AI Message Processor
Unified way to process messages with AI for different purposes

"""

from typing import List, Dict, Any, Optional


class AIProcessorConfig:
    """Configuration for AI processing"""

    def __init__(
        self,
        system_prompt: Optional[str] = None,
        max_retries: Optional[int] = None,
        timeout: Optional[int] = None,
    ):
        self.system_prompt = system_prompt
        self.max_retries = max_retries
        self.timeout = timeout


class AIProcessor:
    """
    Generic AI message processor
    Provides unified interface for different AI-powered features:
    - Compaction: Summarize conversations
    - Council: Generate expert opinions
    - Code Review: Analyze code for issues
    - Documentation: Generate docs from implementations
    """

    def __init__(self, streaming_client, config: Optional[Dict[str, Any]] = None):
        self.streaming_client = streaming_client
        self.config = config or {}

    def process_messages(
        self,
        messages: List[Dict[str, Any]],
        prompt: str,
        send_tools: bool = True,
    ) -> str:
        """
        Process messages with a custom prompt
        This is the core method that all features use
        """
        # Build message list
        all_messages = []

        # Add existing messages
        all_messages.extend(messages)

        # Add processing prompt
        all_messages.append({"role": "user", "content": prompt})

        # Process with retry logic - using streaming client's built-in retry
        full_response = ""

        try:
            response = self.streaming_client.stream_request(
                messages=all_messages,
                stream=False,
                throw_on_error=True,
                send_tools=send_tools,
            )

            for chunk in response:
                content = chunk.get("choices", [{}])[0].get("delta", {}).get("content")
                if content:
                    full_response += content

            return full_response.strip()
        except Exception as error:
            from aicoder.utils.log import LogUtils

            LogUtils.warn(f"AI Processor failed: {error}")
            raise Exception(f"AI Processor failed: {error}")

    def process(self, messages: List[Dict[str, Any]], prompt: str) -> str:
        """Convenience method for simple processing without system prompt"""
        return self.process_messages(messages, prompt)
