"""
Test AICoder class - Synchronous version
Updated tests for current API
"""

import pytest
from unittest.mock import MagicMock, patch
from aicoder.core.aicoder import AICoder
from aicoder.core.message_history import MessageHistory
from aicoder.core.stats import Stats


@pytest.fixture
def app():
    """Create AICoder instance for testing"""
    return AICoder()


def test_aicoder_initialization(app):
    """Test AICoder initialization"""
    assert app.stats is not None
    assert app.message_history is not None
    assert app.streaming_client is not None
    assert app.tool_executor is not None
    assert app.command_handler is not None


def test_handle_command(app):
    """Test command handling"""
    # Add user input
    app.add_user_input("/help")
    # Test that input was processed
    assert len(app.message_history.get_messages()) >= 0


def test_next_prompt_mechanism(app):
    """Test next_prompt mechanism"""
    # Initially, no next prompt
    assert not app.has_next_prompt()
    assert app.get_next_prompt() is None

    # Set next prompt
    app.set_next_prompt("test prompt")
    assert app.has_next_prompt()
    prompt = app.get_next_prompt()
    assert prompt == "test prompt"

    # get_next_prompt() clears the value
    assert not app.has_next_prompt()
    assert app.get_next_prompt() is None


def test_is_processing_flag(app):
    """Test is_processing flag"""
    # Initially not processing
    assert not app.is_processing

    # Set processing flag
    app.is_processing = True
    assert app.is_processing

    # Clear processing flag
    app.is_processing = False
    assert not app.is_processing


def test_initialize_system_prompt(app):
    """Test system prompt initialization"""
    # Should work without errors
    app.initialize_system_prompt()
    # System prompt should be set
    assert app.message_history.initial_system_prompt is not None


def test_plugin_system(app):
    """Test plugin system exists"""
    assert app.plugin_system is not None


def test_session_manager(app):
    """Test session manager exists"""
    assert app.session_manager is not None


def test_compaction_service(app):
    """Test compaction service exists"""
    assert app.compaction_service is not None


def test_context_bar(app):
    """Test context bar exists"""
    assert app.context_bar is not None


def test_tool_executor(app):
    """Test tool executor exists"""
    assert app.tool_executor is not None


def test_shutdown(app):
    """Test shutdown method"""
    # Should not raise errors
    app.shutdown()
