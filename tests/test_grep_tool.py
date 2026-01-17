"""
Test grep tool module
"""

import pytest
import subprocess
from unittest.mock import patch, Mock
from aicoder.tools.internal.grep import validateArguments, formatArguments, execute, _has_ripgrep, _check_sandbox
from aicoder.core.config import Config


class TestValidateArguments:
    """Test argument validation"""

    def test_valid_text(self):
        validateArguments({"text": "search term"})

    def test_missing_text(self):
        with pytest.raises(Exception) as exc_info:
            validateArguments({})
        assert "text" in str(exc_info.value)

    def test_empty_text(self):
        with pytest.raises(Exception) as exc_info:
            validateArguments({"text": ""})
        assert "text" in str(exc_info.value)

    def test_whitespace_only_text(self):
        # Empty string passes validation but execution will handle it
        validateArguments({"text": "   \n\t  "})

    def test_non_string_text(self):
        with pytest.raises(Exception) as exc_info:
            validateArguments({"text": 123})
        assert "text" in str(exc_info.value)


class TestFormatArguments:
    """Test argument formatting"""

    def test_basic_format(self):
        result = formatArguments({"text": "hello"})
        assert 'Text: "hello"' in result
        assert "Path" not in result

    def test_with_path(self):
        result = formatArguments({"text": "hello", "path": "/custom"})
        assert "/custom" in result

    def test_with_custom_max_results(self):
        result = formatArguments({"text": "test", "max_results": 100})
        assert "Max results: 100" in result

    def test_with_custom_context(self):
        result = formatArguments({"text": "test", "context": 5})
        assert "Context: 5 lines" in result

    def test_all_parameters(self):
        result = formatArguments({
            "text": "search",
            "path": "/path",
            "max_results": 50,
            "context": 3
        })
        assert 'Text: "search"' in result
        assert "Path: /path" in result
        assert "Max results: 50" in result
        assert "Context: 3 lines" in result


class TestCheckSandbox:
    """Test sandbox checking"""

    def test_allows_when_disabled(self):
        with patch.object(Config, 'sandbox_disabled', return_value=True):
            assert _check_sandbox("/any/path") is True

    def test_allows_current_directory(self):
        with patch.object(Config, 'sandbox_disabled', return_value=False), \
             patch('os.getcwd', return_value="/home/test"), \
             patch('os.path.abspath', side_effect=lambda x: "/home/test" if x == "." else f"/abs/{x}"):
            
            assert _check_sandbox(".", print_message=False) is True

    def test_blocks_parent_directory(self):
        with patch.object(Config, 'sandbox_disabled', return_value=False), \
             patch('os.getcwd', return_value="/home/test"), \
             patch('os.path.abspath', side_effect=lambda x: f"/abs/{x}"):
            
            assert _check_sandbox("../outside") is False

    def test_allows_same_directory(self):
        with patch.object(Config, 'sandbox_disabled', return_value=False), \
             patch('os.getcwd', return_value="/home/test"), \
             patch('os.path.abspath', return_value="/home/test"):
            
            assert _check_sandbox("/home/test") is True


class TestHasRipgrep:
    """Test ripgrep availability"""

    def test_ripgrep_available(self):
        with patch('subprocess.run') as mock_run:
            mock_run.return_value = Mock()
            result = _has_ripgrep()
            assert result is True
            mock_run.assert_called_once_with(["rg", "--version"], capture_output=True, check=True)

    def test_ripgrep_not_available(self):
        with patch('subprocess.run', side_effect=FileNotFoundError()):
            result = _has_ripgrep()
            assert result is False


class TestExecute:
    """Test execute function"""

    def test_empty_search_text(self):
        # Test that execute raises exception for empty text
        with pytest.raises(Exception) as exc_info:
            execute({"text": ""})
        assert "Text is required" in str(exc_info.value)

    def test_sandbox_violation(self):
        with patch.object(Config, 'sandbox_disabled', return_value=False), \
             patch('os.getcwd', return_value="/home/test"), \
             patch('os.path.abspath', side_effect=lambda x: f"/abs/{x}"):
            
            result = execute({"text": "test", "path": "../outside"})
            
            assert result["tool"] == "grep"
            assert "Sandbox" in result["friendly"]
            assert "outside" in result["friendly"]

    def test_successful_search(self):
        mock_result = Mock()
        mock_result.stdout = "file1.py:10:found here\nfile2.py:20:also found"
        mock_result.returncode = 0
        
        with patch.object(Config, 'sandbox_disabled', return_value=True), \
             patch('subprocess.run', return_value=mock_result), \
             patch('os.path.abspath', return_value="/abs/path"):
            
            result = execute({"text": "pattern", "path": "/test"})
            
            assert result["tool"] == "grep"
            assert "Found 2 matches" in result["friendly"]
            assert "file1.py:10:found here" in result["detailed"]

    def test_no_matches(self):
        mock_result = Mock()
        mock_result.stdout = ""
        mock_result.returncode = 0
        
        with patch.object(Config, 'sandbox_disabled', return_value=True), \
             patch('subprocess.run', return_value=mock_result), \
             patch('os.path.abspath', return_value="/abs/path"):
            
            result = execute({"text": "nomatch", "path": "/test"})
            
            assert result["tool"] == "grep"
            assert "No matches found" in result["friendly"]

    def test_timeout(self):
        with patch.object(Config, 'sandbox_disabled', return_value=True), \
             patch('subprocess.run', side_effect=subprocess.TimeoutExpired("rg", 30)):
            
            result = execute({"text": "timeout_test"})
            
            assert result["tool"] == "grep"
            assert "timed out" in result["friendly"].lower()

    def test_ripgrep_not_found(self):
        with patch.object(Config, 'sandbox_disabled', return_value=True), \
             patch('subprocess.run', side_effect=FileNotFoundError("rg not found")):
            
            result = execute({"text": "test"})
            
            assert result["tool"] == "grep"
            assert "error" in result["friendly"].lower()

    def test_command_parameters(self):
        mock_result = Mock()
        mock_result.stdout = "result"
        mock_result.returncode = 0
        
        with patch.object(Config, 'sandbox_disabled', return_value=True), \
             patch('subprocess.run') as mock_run, \
             patch('os.path.abspath', return_value="/abs/path"):
            
            mock_run.return_value = mock_result
            
            execute({
                "text": "pattern",
                "path": "/test",
                "max_results": 100,
                "context": 5
            })
            
            # Verify command was built correctly
            mock_run.assert_called_once()
            args, kwargs = mock_run.call_args
            cmd = args[0]
            
            assert "rg" in cmd
            assert "-n" in cmd
            assert "--max-count" in cmd
            assert "100" in cmd
            assert "-C" in cmd
            assert "5" in cmd
            assert "pattern" in cmd
            assert "/abs/path" in cmd
            assert kwargs["timeout"] == 30


class TestToolDefinition:
    """Test TOOL_DEFINITION structure"""

    def test_has_required_fields(self):
        from aicoder.tools.internal.grep import TOOL_DEFINITION
        assert TOOL_DEFINITION["type"] == "internal"
        assert "description" in TOOL_DEFINITION
        assert "parameters" in TOOL_DEFINITION
        assert callable(TOOL_DEFINITION["validateArguments"])
        assert callable(TOOL_DEFINITION["formatArguments"])
        assert callable(TOOL_DEFINITION["execute"])

    def test_parameters_has_required_fields(self):
        from aicoder.tools.internal.grep import TOOL_DEFINITION
        params = TOOL_DEFINITION["parameters"]
        assert params["type"] == "object"
        assert "text" in params["required"]
        assert "properties" in params
        assert "text" in params["properties"]
        assert "path" in params["properties"]
