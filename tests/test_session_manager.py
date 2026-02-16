"""Unit tests for SessionManager."""

import pytest
from unittest.mock import MagicMock, patch
import sys
sys.path.insert(0, '/home/blah/storage/ai-worktree-storage/feat_test_coverage__20260117_062928')

from aicoder.core.session_manager import SessionManager


class TestSessionManagerBasics:
    """Test SessionManager basic initialization."""

    def test_session_manager_init(self):
        """Test SessionManager initializes correctly."""
        mock_app = MagicMock()
        mock_app.message_history = MagicMock()
        mock_app.streaming_client = MagicMock()
        mock_app.stream_processor = MagicMock()
        mock_app.tool_executor = MagicMock()
        mock_app.context_bar = MagicMock()
        mock_app.stats = MagicMock()
        mock_app.compaction_service = MagicMock()
        mock_app.plugin_system = MagicMock()

        manager = SessionManager(mock_app)

        assert manager.app == mock_app
        assert manager.message_history == mock_app.message_history
        assert manager.streaming_client == mock_app.streaming_client
        assert manager.stream_processor == mock_app.stream_processor
        assert manager.tool_executor == mock_app.tool_executor
        assert manager.context_bar == mock_app.context_bar
        assert manager.stats == mock_app.stats
        assert manager.compaction_service == mock_app.compaction_service
        assert manager.plugin_system == mock_app.plugin_system
        assert manager.is_processing is False

    def test_session_manager_is_processing_flag(self):
        """Test is_processing flag defaults to False."""
        mock_app = MagicMock()
        manager = SessionManager(mock_app)
        assert manager.is_processing is False


class TestSessionManagerValidateToolCalls:
    """Test SessionManager tool call validation."""

    def test_validate_tool_calls_empty(self):
        """Test validating empty tool calls."""
        mock_app = MagicMock()
        manager = SessionManager(mock_app)

        result = manager._validate_tool_calls({})
        assert result == []

    def test_validate_tool_calls_valid(self):
        """Test validating valid tool calls."""
        mock_app = MagicMock()
        manager = SessionManager(mock_app)

        tool_calls = {
            "1": {
                "id": "1",
                "function": {"name": "read_file", "arguments": "{}"}
            }
        }

        result = manager._validate_tool_calls(tool_calls)
        assert len(result) == 1
        assert result[0]["id"] == "1"

    def test_validate_tool_calls_missing_name(self):
        """Test tool calls without function name are rejected."""
        mock_app = MagicMock()
        manager = SessionManager(mock_app)

        tool_calls = {
            "1": {
                "id": "1",
                "function": {"arguments": "{}"}
            }
        }

        result = manager._validate_tool_calls(tool_calls)
        assert result == []

    def test_validate_tool_calls_missing_id(self):
        """Test tool calls without id are rejected."""
        mock_app = MagicMock()
        manager = SessionManager(mock_app)

        tool_calls = {
            "1": {
                "function": {"name": "read_file", "arguments": "{}"}
            }
        }

        result = manager._validate_tool_calls(tool_calls)
        assert result == []

    def test_validate_tool_calls_mixed(self):
        """Test validating mixed valid/invalid tool calls."""
        mock_app = MagicMock()
        manager = SessionManager(mock_app)

        tool_calls = {
            "1": {
                "id": "1",
                "function": {"name": "read_file", "arguments": "{}"}
            },
            "2": {
                "function": {"name": "write_file", "arguments": "{}"}
            },
            "3": {
                "id": "3",
                "function": {"arguments": "{}"}
            }
        }

        result = manager._validate_tool_calls(tool_calls)
        assert len(result) == 1
        assert result[0]["id"] == "1"

    def test_validate_tool_calls_valid_json_with_complex_args(self):
        """Test validating tool calls with valid complex JSON arguments."""
        mock_app = MagicMock()
        manager = SessionManager(mock_app)

        tool_calls = {
            "1": {
                "id": "1",
                "function": {
                    "name": "write_file",
                    "arguments": '{"path": "/tmp/test.txt", "content": "Hello World", "append": false}'
                }
            }
        }

        result = manager._validate_tool_calls(tool_calls)
        assert len(result) == 1
        assert result[0]["id"] == "1"

    def test_validate_tool_calls_malformed_json_rejected(self):
        """Test tool calls with malformed JSON are rejected."""
        mock_app = MagicMock()
        manager = SessionManager(mock_app)

        tool_calls = {
            "1": {
                "id": "1",
                "function": {
                    "name": "read_file",
                    "arguments": '{"path": "/tmp/test.txt"'  # Missing closing brace
                }
            }
        }

        result = manager._validate_tool_calls(tool_calls)
        assert result == []  # Should be completely rejected

    def test_validate_tool_calls_malformed_json_with_model_tags(self):
        """Test tool calls with model tags breaking JSON structure are rejected."""
        mock_app = MagicMock()
        manager = SessionManager(mock_app)

        tool_calls = {
            "1": {
                "id": "1",
                "function": {
                    "name": "save_progress",
                    "arguments": '{"summary": "</minimax-tool>" test}'  # Malformed JSON - broken by model tag
                }
            }
        }

        result = manager._validate_tool_calls(tool_calls)
        assert result == []  # Should be completely rejected

    def test_validate_tool_calls_mixed_json_validity(self):
        """Test mixed tool calls with some valid JSON and some invalid."""
        mock_app = MagicMock()
        manager = SessionManager(mock_app)

        tool_calls = {
            "1": {
                "id": "1",
                "function": {
                    "name": "read_file",
                    "arguments": '{"path": "valid.json"}'  # Valid JSON
                }
            },
            "2": {
                "id": "2",
                "function": {
                    "name": "write_file",
                    "arguments": '{"path": "invalid"'  # Invalid JSON
                }
            },
            "3": {
                "id": "3",
                "function": {
                    "name": "run_shell_command",
                    "arguments": '{"command": "ls -la"}'  # Valid JSON
                }
            }
        }

        result = manager._validate_tool_calls(tool_calls)
        assert len(result) == 2  # Only the valid ones
        assert result[0]["id"] == "1"
        assert result[1]["id"] == "3"

    def test_validate_tool_calls_empty_json_string(self):
        """Test tool calls with empty JSON string."""
        mock_app = MagicMock()
        manager = SessionManager(mock_app)

        tool_calls = {
            "1": {
                "id": "1",
                "function": {
                    "name": "test_tool",
                    "arguments": ''
                }
            }
        }

        result = manager._validate_tool_calls(tool_calls)
        assert result == []  # Empty string is not valid JSON

    def test_validate_tool_calls_non_object_json(self):
        """Test tool calls with JSON that is not an object."""
        mock_app = MagicMock()
        manager = SessionManager(mock_app)

        tool_calls = {
            "1": {
                "id": "1",
                "function": {
                    "name": "test_tool",
                    "arguments": '"just a string"'  # Valid JSON but not an object
                }
            }
        }

        # This should be accepted - json.loads() will succeed
        # We don't require object, just valid JSON
        result = manager._validate_tool_calls(tool_calls)
        assert len(result) == 1
        assert result[0]["id"] == "1"


class TestSessionManagerHandleEmptyResponse:
    """Test SessionManager empty response handling."""

    def test_handle_empty_response_with_content(self):
        """Test handling response with content but no tools."""
        mock_app = MagicMock()
        manager = SessionManager(mock_app)

        manager._handle_empty_response("Hello, how can I help?", "", "")

        mock_app.message_history.add_assistant_message.assert_called_once()
        call_args = mock_app.message_history.add_assistant_message.call_args[0][0]
        assert call_args["content"] == "Hello, how can I help?"

    def test_handle_empty_response_empty_string(self):
        """Test handling empty response."""
        mock_app = MagicMock()
        manager = SessionManager(mock_app)

        manager._handle_empty_response("", "", "")

        mock_app.message_history.add_assistant_message.assert_called_once()
        call_args = mock_app.message_history.add_assistant_message.call_args[0][0]
        assert call_args["content"] == ""

    def test_handle_empty_response_whitespace(self):
        """Test handling whitespace-only response."""
        mock_app = MagicMock()
        manager = SessionManager(mock_app)

        manager._handle_empty_response("   ", "", "")

        mock_app.message_history.add_assistant_message.assert_called_once()

    def test_handle_empty_response_with_reasoning(self):
        """Test handling response with reasoning content but no regular content."""
        mock_app = MagicMock()
        manager = SessionManager(mock_app)

        manager._handle_empty_response("", "Let me think about this...", "reasoning_content")

        mock_app.message_history.add_assistant_message.assert_called_once()
        call_args = mock_app.message_history.add_assistant_message.call_args[0][0]
        assert call_args["content"] == ""
        assert call_args.get("reasoning_content") == "Let me think about this..."

    def test_handle_empty_response_with_both_content_and_reasoning(self):
        """Test handling response with both content and reasoning."""
        mock_app = MagicMock()
        manager = SessionManager(mock_app)

        manager._handle_empty_response("Hello!", "Let me think...", "reasoning_content")

        mock_app.message_history.add_assistant_message.assert_called_once()
        call_args = mock_app.message_history.add_assistant_message.call_args[0][0]
        assert call_args["content"] == "Hello!"
        assert call_args.get("reasoning_content") == "Let me think..."


class TestSessionManagerForceCompaction:
    """Test SessionManager force compaction."""

    def test_force_compaction_success(self):
        """Test successful force compaction."""
        mock_app = MagicMock()
        mock_app.message_history.force_compact_rounds = MagicMock()
        manager = SessionManager(mock_app)

        manager._force_compaction()

        mock_app.message_history.force_compact_rounds.assert_called_once_with(1)

    def test_force_compaction_error(self):
        """Test force compaction with error."""
        mock_app = MagicMock()
        mock_app.message_history.force_compact_rounds = MagicMock(
            side_effect=Exception("Compaction failed")
        )
        manager = SessionManager(mock_app)

        # Should not raise exception
        manager._force_compaction()


class TestSessionManagerPerformAutoCompaction:
    """Test SessionManager auto compaction."""

    def test_perform_auto_compaction_success(self):
        """Test successful auto compaction."""
        mock_app = MagicMock()
        mock_app.message_history.compact_memory = MagicMock()
        manager = SessionManager(mock_app)

        manager._perform_auto_compaction()

        mock_app.message_history.compact_memory.assert_called_once()

    def test_perform_auto_compaction_with_debug(self):
        """Test auto compaction with debug mode enabled."""
        mock_app = MagicMock()
        mock_app.message_history.compact_memory = MagicMock(
            side_effect=Exception("Compaction failed")
        )
        manager = SessionManager(mock_app)

        with patch('aicoder.core.session_manager.Config') as mock_config:
            mock_config.debug.return_value = True
            # Should not raise even in debug mode
            manager._perform_auto_compaction()


class TestSessionManagerEnsureToolCallsHaveResponses:
    """Test SessionManager ensure tool calls have responses."""

    def test_ensure_tool_calls_no_messages(self):
        """Test with no messages."""
        mock_app = MagicMock()
        mock_app.message_history.messages = []
        manager = SessionManager(mock_app)

        manager._ensure_tool_calls_have_responses()
        # No assertions, just ensure no error

    def test_ensure_tool_calls_assistant_without_tools(self):
        """Test assistant message without tool calls."""
        mock_app = MagicMock()
        mock_app.message_history.messages = [
            {"role": "user", "content": "Hello"},
            {"role": "assistant", "content": "Hi!"}
        ]
        manager = SessionManager(mock_app)

        manager._ensure_tool_calls_have_responses()
        # No changes expected
        assert len(mock_app.message_history.messages) == 2

    def test_ensure_tool_calls_with_matching_responses(self):
        """Test tool calls with matching responses."""
        mock_app = MagicMock()
        mock_app.message_history.messages = [
            {"role": "user", "content": "Read a file"},
            {"role": "assistant", "content": "Reading file", "tool_calls": [{"id": "1"}]},
            {"role": "tool", "content": "File content", "tool_call_id": "1"}
        ]
        manager = SessionManager(mock_app)

        manager._ensure_tool_calls_have_responses()
        # No changes expected - already has response
        assert len(mock_app.message_history.messages) == 3

    def test_ensure_tool_calls_missing_response(self):
        """Test tool calls with missing response."""
        mock_app = MagicMock()
        mock_app.message_history.messages = [
            {"role": "user", "content": "Read a file"},
            {"role": "assistant", "content": "Reading file", "tool_calls": [{"id": "1"}]},
            {"role": "user", "content": "Next message"}  # No tool response
        ]
        manager = SessionManager(mock_app)

        manager._ensure_tool_calls_have_responses()
        # Should insert missing response
        assert len(mock_app.message_history.messages) == 4
        # Check that the inserted message is the cancelled tool response
        inserted_msg = mock_app.message_history.messages[2]
        assert inserted_msg["role"] == "tool"
        assert inserted_msg["tool_call_id"] == "1"
        assert inserted_msg["content"] == "TOOL CALL WAS CANCELLED BY THE USER"

    def test_ensure_tool_calls_multiple_missing_responses(self):
        """Test multiple tool calls with missing responses."""
        mock_app = MagicMock()
        mock_app.message_history.messages = [
            {"role": "user", "content": "Do multiple things"},
            {"role": "assistant", "content": "Doing things", "tool_calls": [{"id": "1"}, {"id": "2"}]},
            {"role": "user", "content": "Next message"}  # No tool responses
        ]
        manager = SessionManager(mock_app)

        manager._ensure_tool_calls_have_responses()
        # Should insert two missing responses
        assert len(mock_app.message_history.messages) == 5

    def test_ensure_tool_calls_partial_responses(self):
        """Test tool calls with partial responses."""
        mock_app = MagicMock()
        mock_app.message_history.messages = [
            {"role": "user", "content": "Do things"},
            {"role": "assistant", "content": "Doing things", "tool_calls": [{"id": "1"}, {"id": "2"}]},
            {"role": "tool", "content": "Result 1", "tool_call_id": "1"},
            {"role": "user", "content": "Next message"}  # Missing response for tool 2
        ]
        manager = SessionManager(mock_app)

        manager._ensure_tool_calls_have_responses()
        # Should insert missing response for tool 2
        assert len(mock_app.message_history.messages) == 5


class TestSessionManagerHandleProcessingError:
    """Test SessionManager error handling."""

    def test_handle_processing_error(self):
        """Test error handling logs correctly."""
        mock_app = MagicMock()
        manager = SessionManager(mock_app)

        with patch('aicoder.core.session_manager.LogUtils') as mock_log:
            manager._handle_processing_error(Exception("Test error"))
            mock_log.error.assert_called_once()


class TestSessionManagerProcessWithAi:
    """Test SessionManager main processing workflow."""

    def test_process_with_ai_empty_tool_calls(self):
        """Test process_with_ai when no tool calls."""
        mock_app = MagicMock()
        mock_app.message_history.get_messages.return_value = []
        mock_app.message_history.should_auto_compact.return_value = False
        mock_app.tool_executor.is_guidance_mode.return_value = False

        manager = SessionManager(mock_app)

        with patch.object(manager, '_prepare_for_processing') as mock_prep:
            mock_prep.return_value = {"should_continue": True, "messages": []}
            with patch.object(manager, '_stream_response') as mock_stream:
                mock_stream.return_value = {
                    "should_continue": True,
                    "full_response": "Hello!",
                    "accumulated_tool_calls": {}
                }
                manager.process_with_ai()

    def test_process_with_ai_with_tool_calls(self):
        """Test process_with_ai with tool calls."""
        mock_app = MagicMock()
        mock_app.message_history.get_messages.return_value = []
        mock_app.message_history.should_auto_compact.return_value = False
        mock_app.tool_executor.is_guidance_mode.return_value = False

        manager = SessionManager(mock_app)

        call_count = [0]
        original_process = manager.process_with_ai

        def mock_process_with_ai():
            call_count[0] += 1
            if call_count[0] > 1:
                return  # Prevent infinite recursion
            with patch.object(manager, '_prepare_for_processing') as mock_prep:
                mock_prep.return_value = {"should_continue": True, "messages": []}
                with patch.object(manager, '_stream_response') as mock_stream:
                    mock_stream.return_value = {
                        "should_continue": True,
                        "full_response": "Let me help with that",
                        "accumulated_tool_calls": {
                            "1": {"id": "1", "function": {"name": "read_file", "arguments": "{}"}}
                        }
                    }
                    original_process()

        with patch.object(manager, 'process_with_ai', mock_process_with_ai):
            manager.process_with_ai()

        mock_app.tool_executor.execute_tool_calls.assert_called_once()

    def test_process_with_ai_error_handling(self):
        """Test process_with_ai error handling."""
        mock_app = MagicMock()
        mock_app.message_history.get_messages.return_value = []
        mock_app.message_history.should_auto_compact.return_value = False
        mock_app.tool_executor.is_guidance_mode.return_value = False

        manager = SessionManager(mock_app)

        with patch.object(manager, '_prepare_for_processing') as mock_prep:
            mock_prep.side_effect = Exception("Processing error")
            # Should not raise, error handled internally
            manager.process_with_ai()
