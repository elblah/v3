"""Unit tests for ToolExecutor - core tool execution logic."""

import pytest
from unittest.mock import MagicMock, patch
import sys
sys.path.insert(0, '/home/blah/storage/ai-worktree-storage/feat_test_coverage__20260117_062928')

from aicoder.core.tool_executor import ToolExecutor


class TestToolExecutorBasics:
    """Test ToolExecutor basic initialization."""

    def test_tool_executor_init(self):
        """Test ToolExecutor initializes correctly."""
        mock_tool_manager = MagicMock()
        mock_message_history = MagicMock()

        executor = ToolExecutor(mock_tool_manager, mock_message_history)

        assert executor.tool_manager == mock_tool_manager
        assert executor.message_history == mock_message_history
        assert executor.plugin_system is None
        assert executor._guidance_mode is False

    def test_tool_executor_init_with_plugin_system(self):
        """Test ToolExecutor with plugin system."""
        mock_tool_manager = MagicMock()
        mock_message_history = MagicMock()
        mock_plugin_system = MagicMock()

        executor = ToolExecutor(mock_tool_manager, mock_message_history, mock_plugin_system)

        assert executor.plugin_system == mock_plugin_system


class TestToolExecutorGuidanceMode:
    """Test ToolExecutor guidance mode functionality."""

    def test_is_guidance_mode_false_by_default(self):
        """Test guidance mode is False by default."""
        mock_tool_manager = MagicMock()
        mock_message_history = MagicMock()

        executor = ToolExecutor(mock_tool_manager, mock_message_history)
        assert executor.is_guidance_mode() is False

    def test_guidance_mode_can_be_set(self):
        """Test guidance mode can be set."""
        mock_tool_manager = MagicMock()
        mock_message_history = MagicMock()

        executor = ToolExecutor(mock_tool_manager, mock_message_history)
        executor._guidance_mode = True
        assert executor.is_guidance_mode() is True

    def test_clear_guidance_mode(self):
        """Test clearing guidance mode."""
        mock_tool_manager = MagicMock()
        mock_message_history = MagicMock()

        executor = ToolExecutor(mock_tool_manager, mock_message_history)
        executor._guidance_mode = True
        executor.clear_guidance_mode()
        assert executor.is_guidance_mode() is False


class TestToolExecutorParseArguments:
    """Test ToolExecutor argument parsing."""

    def test_parse_valid_json_arguments(self):
        """Test parsing valid JSON arguments."""
        mock_tool_manager = MagicMock()
        mock_message_history = MagicMock()

        executor = ToolExecutor(mock_tool_manager, mock_message_history)

        result = executor._parse_tool_arguments('{"path": "/test", "limit": 10}')
        assert result == {"path": "/test", "limit": 10}

    def test_parse_dict_arguments(self):
        """Test parsing dict arguments (already parsed)."""
        mock_tool_manager = MagicMock()
        mock_message_history = MagicMock()

        executor = ToolExecutor(mock_tool_manager, mock_message_history)

        args_dict = {"path": "/test"}
        result = executor._parse_tool_arguments(args_dict)
        assert result == args_dict

    def test_parse_empty_arguments(self):
        """Test parsing empty arguments."""
        mock_tool_manager = MagicMock()
        mock_message_history = MagicMock()

        executor = ToolExecutor(mock_tool_manager, mock_message_history)

        result = executor._parse_tool_arguments("{}")
        assert result == {}

    def test_parse_invalid_json(self):
        """Test parsing invalid JSON returns empty dict."""
        mock_tool_manager = MagicMock()
        mock_message_history = MagicMock()

        executor = ToolExecutor(mock_tool_manager, mock_message_history)

        result = executor._parse_tool_arguments("invalid json")
        assert result == {}

    def test_parse_none_arguments(self):
        """Test parsing None arguments returns empty dict."""
        mock_tool_manager = MagicMock()
        mock_message_history = MagicMock()

        executor = ToolExecutor(mock_tool_manager, mock_message_history)

        result = executor._parse_tool_arguments(None)
        assert result == {}


class TestToolExecutorHandleToolNotFound:
    """Test ToolExecutor tool not found handling."""

    def test_handle_tool_not_found(self):
        """Test handling when tool is not found."""
        mock_tool_manager = MagicMock()
        mock_message_history = MagicMock()

        executor = ToolExecutor(mock_tool_manager, mock_message_history)

        result = executor._handle_tool_not_found("unknown_tool", "call_123")

        assert result["tool_call_id"] == "call_123"
        assert "unknown_tool" in result["content"]
        mock_message_history.add_system_message.assert_called_once()


class TestToolExecutorShouldShowPreview:
    """Test ToolExecutor preview display logic."""

    def test_should_show_preview_true(self):
        """Test preview should be shown when tool has generatePreview."""
        mock_tool_manager = MagicMock()
        mock_message_history = MagicMock()

        executor = ToolExecutor(mock_tool_manager, mock_message_history)

        tool_def = {"generatePreview": MagicMock()}
        # Method returns truthy value when tool_def has generatePreview
        assert executor._should_show_preview(tool_def, {}) is not None

    def test_should_show_preview_false_no_def(self):
        """Test preview not shown when no tool def."""
        mock_tool_manager = MagicMock()
        mock_message_history = MagicMock()

        executor = ToolExecutor(mock_tool_manager, mock_message_history)

        # None returns None/falsy
        result = executor._should_show_preview(None, {})
        assert not result

    def test_should_show_preview_false_no_preview(self):
        """Test preview not shown when tool has no preview."""
        mock_tool_manager = MagicMock()
        mock_message_history = MagicMock()

        executor = ToolExecutor(mock_tool_manager, mock_message_history)

        tool_def = {"name": "read_file"}
        # Method returns None/falsy when no generatePreview key
        result = executor._should_show_preview(tool_def, {})
        assert not result


class TestToolExecutorPreviewDisplay:
    """Test ToolExecutor preview display handling."""

    def test_handle_preview_display_generation_error(self):
        """Test preview display when generation fails."""
        mock_tool_manager = MagicMock()
        mock_message_history = MagicMock()

        executor = ToolExecutor(mock_tool_manager, mock_message_history)

        tool_def = {"generatePreview": MagicMock(side_effect=Exception("Preview failed"))}

        with patch('aicoder.core.tool_executor.LogUtils'):
            result = executor._handle_preview_display(tool_def, {}, "call_123")
            assert result is True  # Continue without preview

    def test_handle_preview_display_no_preview(self):
        """Test preview display when preview is None/empty."""
        mock_tool_manager = MagicMock()
        mock_message_history = MagicMock()

        executor = ToolExecutor(mock_tool_manager, mock_message_history)

        tool_def = {"generatePreview": MagicMock(return_value=None)}

        result = executor._handle_preview_display(tool_def, {}, "call_123")
        assert result is True

    def test_handle_preview_display_cannot_approve(self):
        """Test preview display when can't approve (safety violation)."""
        mock_tool_manager = MagicMock()
        mock_message_history = MagicMock()

        executor = ToolExecutor(mock_tool_manager, mock_message_history)

        preview_result = {
            "can_approve": False,
            "content": "Sensitive content"
        }
        tool_def = {"generatePreview": MagicMock(return_value=preview_result)}

        with patch('aicoder.core.tool_executor.LogUtils'):
            result = executor._handle_preview_display(tool_def, {}, "call_123")
            assert isinstance(result, dict)
            assert result["tool_call_id"] == "call_123"
            assert result["content"] == "Sensitive content"


class TestToolExecutorApproval:
    """Test ToolExecutor approval logic."""

    def test_approval_not_needed_when_yolo_mode(self):
        """Test approval skipped in YOLO mode."""
        mock_tool_manager = MagicMock()
        mock_tool_manager.needs_approval.return_value = True
        mock_message_history = MagicMock()

        executor = ToolExecutor(mock_tool_manager, mock_message_history)

        with patch('aicoder.core.tool_executor.Config') as mock_config:
            mock_config.yolo_mode.return_value = True
            result = executor._get_tool_approval("read_file", {"path": "/test"})
            assert result is True

    def test_approval_not_needed_when_tool_no_approval(self):
        """Test approval skipped when tool doesn't need approval."""
        mock_tool_manager = MagicMock()
        mock_tool_manager.needs_approval.return_value = False
        mock_message_history = MagicMock()

        executor = ToolExecutor(mock_tool_manager, mock_message_history)

        with patch('aicoder.core.tool_executor.Config') as mock_config:
            mock_config.yolo_mode.return_value = False
            result = executor._get_tool_approval("read_file", {"path": "/test"})
            assert result is True

    def test_approval_denied(self):
        """Test approval denied by user."""
        mock_tool_manager = MagicMock()
        mock_tool_manager.needs_approval.return_value = True
        mock_message_history = MagicMock()

        executor = ToolExecutor(mock_tool_manager, mock_message_history)

        with patch('aicoder.core.tool_executor.Config') as mock_config:
            mock_config.yolo_mode.return_value = False
            with patch('builtins.input', return_value='n'):
                with patch('aicoder.core.tool_executor.LogUtils'):
                    result = executor._get_tool_approval("read_file", {"path": "/test"})
                    assert result is False

    def test_approval_default_yes(self):
        """Test default approval is yes."""
        mock_tool_manager = MagicMock()
        mock_tool_manager.needs_approval.return_value = True
        mock_message_history = MagicMock()

        executor = ToolExecutor(mock_tool_manager, mock_message_history)

        with patch('aicoder.core.tool_executor.Config') as mock_config:
            mock_config.yolo_mode.return_value = False
            with patch('builtins.input', return_value=''):
                with patch('aicoder.core.tool_executor.LogUtils'):
                    result = executor._get_tool_approval("read_file", {"path": "/test"})
                    assert result is True

    def test_approval_yolo_command(self):
        """Test yolo command enables YOLO mode."""
        mock_tool_manager = MagicMock()
        mock_tool_manager.needs_approval.return_value = True
        mock_message_history = MagicMock()

        executor = ToolExecutor(mock_tool_manager, mock_message_history)

        with patch('aicoder.core.tool_executor.Config') as mock_config:
            mock_config.yolo_mode.return_value = False
            with patch('builtins.input', return_value='yolo'):
                with patch('aicoder.core.tool_executor.LogUtils') as mock_log:
                    with patch.object(mock_config, 'set_yolo_mode') as mock_set:
                        result = executor._get_tool_approval("read_file", {"path": "/test"})
                        mock_set.assert_called_once_with(True)
                        assert result is True


class TestToolExecutorExecuteToolCalls:
    """Test ToolExecutor execute_tool_calls."""

    def test_execute_empty_tool_calls(self):
        """Test executing empty tool calls list."""
        mock_tool_manager = MagicMock()
        mock_message_history = MagicMock()

        executor = ToolExecutor(mock_tool_manager, mock_message_history)

        executor.execute_tool_calls([])

        mock_message_history.add_tool_results.assert_not_called()

    def test_execute_tool_calls_with_guidance_mode(self):
        """Test tool execution stops when guidance mode activated."""
        mock_tool_manager = MagicMock()
        mock_message_history = MagicMock()
        mock_plugin_system = MagicMock()

        executor = ToolExecutor(mock_tool_manager, mock_message_history, mock_plugin_system)

        tool_calls = [
            {"id": "1", "function": {"name": "read_file", "arguments": "{}"}}
        ]

        mock_tool_manager.tools.get.return_value = {
            "name": "read_file",
            "execute": MagicMock(return_value={"friendly": "OK", "detailed": "Done"})
        }

        # First call returns approved, second triggers guidance mode
        call_count = [0]
        original_get_approval = executor._get_tool_approval

        def mock_approval(tool_name, args):
            call_count[0] += 1
            if call_count[0] == 1:
                return True  # First tool approved
            executor._guidance_mode = True
            return False  # Would set guidance mode

        with patch.object(executor, '_get_tool_approval', mock_approval):
            with patch.object(executor, '_execute_tool') as mock_exec:
                mock_exec.return_value = {"tool_call_id": "1", "content": "Done"}
                executor.execute_tool_calls(tool_calls)

        # Only first tool should execute
        assert mock_exec.call_count == 1


class TestToolExecutorExecuteTool:
    """Test ToolExecutor _execute_tool method."""

    def test_execute_tool_success(self):
        """Test successful tool execution."""
        mock_tool_manager = MagicMock()
        mock_message_history = MagicMock()

        executor = ToolExecutor(mock_tool_manager, mock_message_history)

        mock_tool_result = {"friendly": "File content", "detailed": "Full details"}
        mock_tool_manager.execute_tool_with_args.return_value = mock_tool_result
        mock_tool_manager.tools.get.return_value = {"name": "read_file"}

        with patch.object(executor, 'display_tool_result'):
            result = executor._execute_tool("read_file", {"path": "/test"}, "call_123")

        assert result["tool_call_id"] == "call_123"
        assert result["content"] == "Full details"

    def test_execute_tool_error(self):
        """Test tool execution error."""
        mock_tool_manager = MagicMock()
        mock_message_history = MagicMock()

        executor = ToolExecutor(mock_tool_manager, mock_message_history)

        mock_tool_manager.execute_tool_with_args.side_effect = Exception("Tool failed")
        mock_tool_manager.tools.get.return_value = {"name": "read_file"}

        with patch('aicoder.core.tool_executor.LogUtils'):
            result = executor._execute_tool("read_file", {"path": "/test"}, "call_123")

        assert result["tool_call_id"] == "call_123"
        assert "Tool failed" in result["content"]


class TestToolExecutorDisplayResult:
    """Test ToolExecutor display_tool_result."""

    def test_display_result_hidden(self):
        """Test hiding tool results when configured."""
        mock_tool_manager = MagicMock()
        mock_message_history = MagicMock()

        executor = ToolExecutor(mock_tool_manager, mock_message_history)

        result = {"friendly": "OK", "detailed": "Done"}
        tool_def = {"hide_results": True}

        with patch('aicoder.core.tool_executor.LogUtils') as mock_log:
            executor.display_tool_result(result, tool_def)
            mock_log.success.assert_called_once()

    def test_display_result_detail_mode(self):
        """Test displaying result in detail mode."""
        mock_tool_manager = MagicMock()
        mock_message_history = MagicMock()

        executor = ToolExecutor(mock_tool_manager, mock_message_history)

        result = {"friendly": "Friendly output", "detailed": "Detailed output"}
        tool_def = {}

        with patch('aicoder.core.tool_executor.Config') as mock_config:
            mock_config.detail_mode.return_value = True
            with patch('aicoder.core.tool_executor.LogUtils') as mock_log:
                executor.display_tool_result(result, tool_def)
                # Should print both detailed and friendly
                assert mock_log.print.call_count == 2

    def test_display_result_normal_mode(self):
        """Test displaying result in normal mode (friendly only)."""
        mock_tool_manager = MagicMock()
        mock_message_history = MagicMock()

        executor = ToolExecutor(mock_tool_manager, mock_message_history)

        result = {"friendly": "Friendly output", "detailed": "Detailed output"}
        tool_def = {}

        with patch('aicoder.core.tool_executor.Config') as mock_config:
            mock_config.detail_mode.return_value = False
            with patch('aicoder.core.tool_executor.LogUtils') as mock_log:
                executor.display_tool_result(result, tool_def)
                # Should print only friendly
                mock_log.print.assert_called_once()


class TestToolExecutorPluginHooks:
    """Test ToolExecutor plugin hook integration."""

    def test_plugin_hook_after_tool_results(self):
        """Test plugin hook called after tool results."""
        mock_tool_manager = MagicMock()
        mock_message_history = MagicMock()
        mock_plugin_system = MagicMock()

        executor = ToolExecutor(mock_tool_manager, mock_message_history, mock_plugin_system)

        tool_results = [{"tool_call_id": "1", "content": "Result"}]

        with patch.object(executor, '_execute_single_tool_call', return_value={"tool_call_id": "1", "content": "Result"}):
            executor.execute_tool_calls([{"id": "1", "function": {"name": "read_file"}}])

        mock_plugin_system.call_hooks.assert_called_once_with("after_tool_results", tool_results)


class TestToolExecutorSingleToolCall:
    """Test ToolExecutor _execute_single_tool_call."""

    def test_execute_single_tool_no_name(self):
        """Test execution fails when tool has no name."""
        mock_tool_manager = MagicMock()
        mock_message_history = MagicMock()

        executor = ToolExecutor(mock_tool_manager, mock_message_history)

        result = executor._execute_single_tool_call({"function": {}})
        assert result is None

    def test_execute_single_tool_with_preview_rejected(self):
        """Test tool with rejected preview."""
        mock_tool_manager = MagicMock()
        mock_message_history = MagicMock()

        executor = ToolExecutor(mock_tool_manager, mock_message_history)

        tool_def = {
            "name": "edit_file",
            "generatePreview": MagicMock(return_value={"can_approve": False, "content": "Preview"})
        }
        mock_tool_manager.tools.get.return_value = tool_def

        with patch('aicoder.core.tool_executor.LogUtils'):
            with patch.object(executor, '_get_tool_approval', return_value=True):
                result = executor._execute_single_tool_call({
                    "id": "1",
                    "function": {"name": "edit_file", "arguments": "{}"}
                })

                # Should return preview content for AI
                assert result["tool_call_id"] == "1"
