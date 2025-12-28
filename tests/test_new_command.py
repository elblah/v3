"""
Test the /new command to ensure it preserves the system prompt
"""

import pytest
from unittest.mock import Mock
from aicoder.core.commands.new import NewCommand
from aicoder.core.commands.base import CommandContext
from aicoder.core.stats import Stats
from aicoder.core.message_history import MessageHistory


def test_new_preserves_system_prompt():
    """Test that /new command preserves the system prompt"""
    # Create the necessary objects
    stats = Stats()
    message_history = MessageHistory(stats)
    
    # Add a system prompt
    system_prompt = "You are a helpful assistant."
    message_history.add_system_message(system_prompt)
    
    # Add some user messages
    message_history.add_user_message("Hello")
    message_history.add_assistant_message({"content": "Hi there!"})
    message_history.add_user_message("How are you?")
    message_history.add_assistant_message({"content": "I'm doing well!"})
    
    # Verify we have messages
    assert len(message_history.get_messages()) == 5  # system + 4 messages
    
    # Create command context
    context = CommandContext(
        message_history=message_history,
        input_handler=Mock(),
        stats=stats
    )
    
    # Execute the /new command
    cmd = NewCommand(context)
    result = cmd.execute()
    
    # Check result
    assert not result.should_quit
    assert not result.run_api_call
    
    # Verify only the system prompt remains
    messages = message_history.get_messages()
    assert len(messages) == 1  # Only system prompt
    assert messages[0]["role"] == "system"
    assert messages[0]["content"] == system_prompt


def test_new_with_no_system_prompt():
    """Test that /new command works when there's no system prompt"""
    # Create the necessary objects
    stats = Stats()
    message_history = MessageHistory(stats)
    
    # Add some user messages (no system prompt)
    message_history.add_user_message("Hello")
    message_history.add_assistant_message({"content": "Hi there!"})
    
    # Verify we have messages
    assert len(message_history.get_messages()) == 2
    
    # Create command context
    context = CommandContext(
        message_history=message_history,
        input_handler=Mock(),
        stats=stats
    )
    
    # Execute the /new command
    cmd = NewCommand(context)
    result = cmd.execute()
    
    # Check result
    assert not result.should_quit
    assert not result.run_api_call
    
    # Verify all messages are cleared
    messages = message_history.get_messages()
    assert len(messages) == 0


def test_new_command_properties():
    """Test that /new command has correct properties"""
    # Create command context
    context = CommandContext(
        message_history=Mock(),
        input_handler=Mock(),
        stats=Mock()
    )
    
    # Create command
    cmd = NewCommand(context)
    
    # Check properties
    assert cmd.get_name() == "new"
    assert cmd.get_description() == "Reset the entire session"
    assert cmd.get_aliases() == ["n"]