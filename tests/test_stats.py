"""
Test Stats class
Tests for
"""

from aicoder.core.stats import Stats

# Type definitions are now dicts
ApiUsage = dict[str, int]


def test_stats_initialization():
    """Test Stats initialization with all default values"""
    stats = Stats()

    assert stats.api_requests == 0
    assert stats.api_success == 0
    assert stats.api_errors == 0
    assert stats.api_time_spent == 0
    assert stats.messages_sent == 0
    assert stats.tokens_processed == 0
    assert stats.compactions == 0
    assert stats.prompt_tokens == 0
    assert stats.completion_tokens == 0
    assert stats.current_prompt_size == 0
    assert stats.current_prompt_size_estimated == False
    assert stats.last_user_prompt == ""
    assert stats.usage_infos == []


def test_incrementers():
    """Test all increment methods"""
    stats = Stats()

    # Test API counters
    stats.increment_api_requests()
    stats.increment_api_requests()
    assert stats.api_requests == 2

    stats.increment_api_success()
    stats.increment_api_success()
    assert stats.api_success == 2

    stats.increment_api_errors()
    assert stats.api_errors == 1

    # Test other counters
    stats.increment_messages_sent()
    assert stats.messages_sent == 1

    stats.increment_compactions()
    assert stats.compactions == 1


def test_adders():
    """Test all add methods"""
    stats = Stats()

    # Test time and tokens
    stats.add_api_time(1.5)
    stats.add_api_time(0.75)
    assert stats.api_time_spent == 2.25

    stats.add_tokens_processed(100)
    stats.add_tokens_processed(50)
    assert stats.tokens_processed == 150

    stats.add_prompt_tokens(50)
    stats.add_prompt_tokens(30)
    assert stats.prompt_tokens == 80

    stats.add_completion_tokens(25)
    stats.add_completion_tokens(15)
    assert stats.completion_tokens == 40


def test_setters():
    """Test all setter methods"""
    stats = Stats()

    # Test prompt size
    stats.set_current_prompt_size(1000, True)
    assert stats.current_prompt_size == 1000
    assert stats.current_prompt_size_estimated == True

    stats.set_current_prompt_size(2000)
    assert stats.current_prompt_size == 2000
    assert stats.current_prompt_size_estimated == False

    # Test last user prompt
    stats.set_last_user_prompt("Hello world")
    assert stats.last_user_prompt == "Hello world"

    # Test usage info
    usage = {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
    stats.add_usage_info(usage)
    assert len(stats.usage_infos) == 1
    assert stats.usage_infos[0]["usage"] == usage
    assert "time" in stats.usage_infos[0]


def test_reset():
    """Test reset functionality"""
    stats = Stats()

    # Set some values
    stats.increment_api_requests()
    stats.add_api_time(1.0)
    stats.set_last_user_prompt("test")
    stats.add_usage_info(
        {"prompt_tokens": 10, "completion_tokens": 20, "total_tokens": 30}
    )

    # Reset
    stats.reset()

    # Check all are back to defaults
    assert stats.api_requests == 0
    assert stats.api_time_spent == 0
    assert stats.last_user_prompt == ""
    assert stats.usage_infos == []


def test_print_stats(capsys):
    """Test print_stats output format"""
    stats = Stats()

    # Add some data
    stats.increment_api_requests()
    stats.increment_api_success()
    stats.add_api_time(1.23)
    stats.increment_messages_sent()
    stats.add_tokens_processed(1000)
    stats.set_current_prompt_size(500, True)

    # Print stats
    stats.print_stats()

    # Capture output
    captured = capsys.readouterr()
    output = captured.out

    # Check key elements are present
    assert "=== Session Statistics ===" in output
    assert "API Requests: 1 (Success: 1, Errors: 0)" in output
    assert "API Time Spent: 1.23s" in output
    assert "Messages Sent: 1" in output
    assert "Tokens Processed: 1,000" in output
    assert "Final Context Size: 500 (estimated)" in output
    assert "========================" in output
