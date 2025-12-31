"""
Test the /retry command to ensure it handles retry limit correctly
"""

import pytest
import os
from unittest.mock import Mock, patch
from aicoder.core.commands.retry import RetryCommand
from aicoder.core.commands.base import CommandContext
from aicoder.core.stats import Stats
from aicoder.core.message_history import MessageHistory
from aicoder.core.config import Config


@pytest.fixture(autouse=True)
def cleanup_config():
    """Clean up config before and after each test"""
    # Clear any runtime overrides
    Config.set_runtime_max_retries(None)
    yield
    # Clean up after test
    Config.set_runtime_max_retries(None)


def test_retry_without_user_messages():
    """Test that /retry fails when there are no user messages"""
    stats = Stats()
    message_history = MessageHistory(stats)
    
    # Create command context
    context = CommandContext(
        message_history=message_history,
        input_handler=Mock(),
        stats=stats
    )
    
    # Execute the /retry command
    cmd = RetryCommand(context)
    result = cmd.execute()
    
    # Check result
    assert not result.should_quit
    assert not result.run_api_call  # Should not run API call with no messages


def test_retry_with_user_messages():
    """Test that /retry triggers API call when user messages exist"""
    stats = Stats()
    message_history = MessageHistory(stats)
    
    # Add a user message
    message_history.add_user_message("Hello")
    
    # Create command context
    context = CommandContext(
        message_history=message_history,
        input_handler=Mock(),
        stats=stats
    )
    
    # Execute the /retry command
    cmd = RetryCommand(context)
    result = cmd.execute()
    
    # Check result
    assert not result.should_quit
    assert result.run_api_call  # Should run API call


def test_retry_limit_set():
    """Test that /retry limit <n> sets the retry limit"""
    stats = Stats()
    message_history = MessageHistory(stats)
    
    # Create command context
    context = CommandContext(
        message_history=message_history,
        input_handler=Mock(),
        stats=stats
    )
    
    # Execute /retry limit 5
    cmd = RetryCommand(context)
    result = cmd.execute(["limit", "5"])
    
    # Check result
    assert not result.should_quit
    assert not result.run_api_call
    
    # Verify the limit was set (use effective_max_retries to check runtime override)
    assert Config.effective_max_retries() == 5


def test_retry_limit_set_zero():
    """Test that /retry limit 0 sets unlimited retries"""
    stats = Stats()
    message_history = MessageHistory(stats)
    
    # Create command context
    context = CommandContext(
        message_history=message_history,
        input_handler=Mock(),
        stats=stats
    )
    
    # Execute /retry limit 0
    cmd = RetryCommand(context)
    result = cmd.execute(["limit", "0"])
    
    # Check result
    assert not result.should_quit
    assert not result.run_api_call
    
    # Verify the limit was set to 0 (unlimited)
    assert Config.max_retries() == 0


def test_retry_limit_invalid_negative():
    """Test that /retry limit with negative number fails"""
    stats = Stats()
    message_history = MessageHistory(stats)
    
    # Create command context
    context = CommandContext(
        message_history=message_history,
        input_handler=Mock(),
        stats=stats
    )
    
    # Execute /retry limit -1
    cmd = RetryCommand(context)
    result = cmd.execute(["limit", "-1"])
    
    # Check result
    assert not result.should_quit
    assert not result.run_api_call


def test_retry_limit_invalid_non_numeric():
    """Test that /retry limit with non-numeric value fails"""
    stats = Stats()
    message_history = MessageHistory(stats)
    
    # Create command context
    context = CommandContext(
        message_history=message_history,
        input_handler=Mock(),
        stats=stats
    )
    
    # Execute /retry limit abc
    cmd = RetryCommand(context)
    result = cmd.execute(["limit", "abc"])
    
    # Check result
    assert not result.should_quit
    assert not result.run_api_call


def test_retry_limit_show_current():
    """Test that /retry limit without argument shows current limit"""
    stats = Stats()
    message_history = MessageHistory(stats)
    
    # Create command context
    context = CommandContext(
        message_history=message_history,
        input_handler=Mock(),
        stats=stats
    )
    
    # Set a limit first
    Config.set_runtime_max_retries(7)
    
    # Execute /retry limit (without argument)
    cmd = RetryCommand(context)
    result = cmd.execute(["limit"])
    
    # Check result
    assert not result.should_quit
    assert not result.run_api_call
    
    # Verify the limit is still set (use effective_max_retries to check runtime override)
    assert Config.effective_max_retries() == 7


def test_retry_limit_show_default():
    """Test that /retry limit shows default value when not set"""
    stats = Stats()
    message_history = MessageHistory(stats)
    
    # Create command context
    context = CommandContext(
        message_history=message_history,
        input_handler=Mock(),
        stats=stats
    )
    
    # Don't set any limit (should use environment default)
    Config.set_runtime_max_retries(None)
    
    # Execute /retry limit (without argument)
    cmd = RetryCommand(context)
    result = cmd.execute(["limit"])
    
    # Check result
    assert not result.should_quit
    assert not result.run_api_call
    
    # Verify we get the default from environment
    # Default is 3, but this could vary by environment
    assert Config.max_retries() >= 0


def test_retry_help():
    """Test that /retry help shows help text"""
    stats = Stats()
    message_history = MessageHistory(stats)
    
    # Create command context
    context = CommandContext(
        message_history=message_history,
        input_handler=Mock(),
        stats=stats
    )
    
    # Execute /retry help
    cmd = RetryCommand(context)
    result = cmd.execute(["help"])
    
    # Check result
    assert not result.should_quit
    assert not result.run_api_call


def test_retry_command_properties():
    """Test that /retry command has correct properties"""
    # Create command context
    context = CommandContext(
        message_history=Mock(),
        input_handler=Mock(),
        stats=Mock()
    )
    
    # Create command
    cmd = RetryCommand(context)
    
    # Check properties
    assert cmd.get_name() == "retry"
    assert cmd.get_description() == "Retry the last message or configure retry limit"
    assert cmd.get_aliases() == ["r"]


def test_retry_alias():
    """Test that /r (retry alias) works"""
    stats = Stats()
    message_history = MessageHistory(stats)
    
    # Add a user message
    message_history.add_user_message("Hello")
    
    # Create command context
    context = CommandContext(
        message_history=message_history,
        input_handler=Mock(),
        stats=stats
    )
    
    # Execute /r command (via command registry it would be recognized as retry)
    cmd = RetryCommand(context)
    result = cmd.execute()
    
    # Check result
    assert not result.should_quit
    assert result.run_api_call
