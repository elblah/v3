"""
Statistics tracking for AI Coder
Ported exactly from TypeScript version
Stateful: class needed for maintaining counters
"""

from typing import List, Dict, Any


class Stats:
    """
    Statistics tracking for AI Coder
    Ported exactly from TS version
    """

    def __init__(self):
        self.api_requests = 0
        self.api_success = 0
        self.api_errors = 0
        self.api_time_spent = 0
        self.messages_sent = 0
        self.tokens_processed = 0
        self.compactions = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.current_prompt_size = 0
        self.current_prompt_size_estimated = False
        self.last_user_prompt = ""
        self.usage_infos: List[Dict[str, Any]] = []

    def increment_api_requests(self) -> None:
        """
        Increment API request counter
        Ported exactly from TS version
        """
        self.api_requests += 1

    def increment_api_success(self) -> None:
        """
        Increment API success counter
        Ported exactly from TS version
        """
        self.api_success += 1

    def increment_api_errors(self) -> None:
        """
        Increment API error counter
        Ported exactly from TS version
        """
        self.api_errors += 1

    def add_api_time(self, time: float) -> None:
        """
        Add time to API time spent
        Ported exactly from TS version
        """
        self.api_time_spent += time

    def increment_messages_sent(self) -> None:
        """
        Increment messages sent counter
        Ported exactly from TS version
        """
        self.messages_sent += 1

    def add_tokens_processed(self, tokens: int) -> None:
        """
        Add tokens to processed counter
        Ported exactly from TS version
        """
        self.tokens_processed += tokens

    def increment_compactions(self) -> None:
        """
        Increment compactions counter
        Ported exactly from TS version
        """
        self.compactions += 1

    def add_prompt_tokens(self, tokens: int) -> None:
        """
        Add prompt tokens
        Ported exactly from TS version
        """
        self.prompt_tokens += tokens

    def add_completion_tokens(self, tokens: int) -> None:
        """
        Add completion tokens
        Ported exactly from TS version
        """
        self.completion_tokens += tokens

    def set_current_prompt_size(self, size: int, estimated: bool = False) -> None:
        """
        Set current prompt size
        Ported exactly from TS version
        """
        self.current_prompt_size = size
        self.current_prompt_size_estimated = estimated

    def set_last_user_prompt(self, prompt: str) -> None:
        """
        Store last user prompt
        Ported exactly from TS version
        """
        self.last_user_prompt = prompt

    def add_usage_info(self, usage: Dict[str, Any]) -> None:
        """
        Add usage info
        Ported exactly from TS version
        """
        import time

        self.usage_infos.append({"time": int(time.time() * 1000), "usage": usage})

    def increment_user_interactions(self) -> None:
        """
        Increment user interactions counter
        Ported exactly from TS version
        """
        self.messages_sent += 1

    def print_stats(self) -> None:
        """
        Print statistics on exit
        Ported exactly from TS version
        """
        print("\n=== Session Statistics ===")
        print(
            f"API Requests: {self.api_requests} (Success: {self.api_success}, Errors: {self.api_errors})"
        )
        print(f"API Time Spent: {self.api_time_spent:.2f}s")
        print(f"Messages Sent: {self.messages_sent}")
        print(f"Tokens Processed: {self.tokens_processed:,}")
        print(f"Prompt Tokens: {self.prompt_tokens:,}")
        print(f"Completion Tokens: {self.completion_tokens:,}")
        print(f"Compactions: {self.compactions}")

        if self.current_prompt_size > 0:
            estimated = " (estimated)" if self.current_prompt_size_estimated else ""
            print(f"Final Context Size: {self.current_prompt_size:,}{estimated}")

        print("========================")

    def reset(self) -> None:
        """
        Reset all statistics
        Ported exactly from TS version
        """
        self.api_requests = 0
        self.api_success = 0
        self.api_errors = 0
        self.api_time_spent = 0
        self.messages_sent = 0
        self.tokens_processed = 0
        self.compactions = 0
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.current_prompt_size = 0
        self.current_prompt_size_estimated = False
        self.last_user_prompt = ""
        self.usage_infos = []
