"""
Test grep tool module
"""

import pytest
import subprocess
from unittest.mock import patch, Mock
from aicoder.tools.internal.grep import validateArguments, formatArguments, execute, check_sandbox
from aicoder.core.config import Config


@pytest.fixture(autouse=True)
def _reset_exec_latch(monkeypatch):
    """Each test starts with a clean exec-failure latch and no NO_EXEC marker."""
    from aicoder.tools.internal import grep as grep_mod

    monkeypatch.setattr(grep_mod, "_no_exec_reason", None, raising=False)
    monkeypatch.delenv("AICODER_NO_EXEC", raising=False)


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
            assert check_sandbox("/any/path") is True

    def test_allows_current_directory(self):
        with patch.object(Config, 'sandbox_disabled', return_value=False), \
             patch('os.getcwd', return_value="/home/test"):
            assert check_sandbox(".", print_message=False) is True

    def test_blocks_parent_directory(self):
        with patch.object(Config, 'sandbox_disabled', return_value=False), \
             patch('os.getcwd', return_value="/home/test"):
            assert check_sandbox("../outside", print_message=False) is False

    def test_allows_same_directory(self):
        with patch.object(Config, 'sandbox_disabled', return_value=False), \
             patch('os.getcwd', return_value="/home/test"):
            assert check_sandbox("/home/test", print_message=False) is True


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
             patch('aicoder.tools.internal.grep.subprocess.run', side_effect=subprocess.TimeoutExpired("rg", 30)):
            
            result = execute({"text": "timeout_test"})
            
            assert result["tool"] == "grep"
            assert "timed out" in result["friendly"].lower()

    def test_ripgrep_not_found(self):
        # A missing rg (or a sandbox blocking exec) must not kill the tool:
        # it falls back to the pure-Python search.
        with patch.object(Config, 'sandbox_disabled', return_value=True), \
             patch('aicoder.tools.internal.grep.subprocess.run', side_effect=FileNotFoundError("rg not found")), \
             patch('aicoder.tools.internal.grep.python_grep', return_value=(["f.py:1:hit"], None)):
            
            result = execute({"text": "test"})
            
            assert result["tool"] == "grep"
            assert "Found 1 matches" in result["friendly"]
            assert "python fallback" not in result["friendly"]
            assert "pure-Python fallback" in result["detailed"]

    def test_execvp_blocked_falls_back(self):
        # bash reports execvp failure for the sealed command
        mock_result = Mock()
        mock_result.stdout = ""
        mock_result.returncode = 127
        mock_result.stderr = "bash: execvp: Operation not permitted"

        with patch.object(Config, 'sandbox_disabled', return_value=True), \
             patch('aicoder.tools.internal.grep.subprocess.run', return_value=mock_result), \
             patch('aicoder.tools.internal.grep.python_grep', return_value=([], None)):
            
            result = execute({"text": "test"})
            
            assert result["tool"] == "grep"
            assert "No matches found" in result["friendly"]
            assert "pure-Python fallback" in result["detailed"]

    def test_bwrap_failure_falls_back_and_latches(self):
        # Nested bwrap cannot start (unshared PID namespace) -> the message is
        # an exec failure, so the tool must use the Python engine and remember it.
        mock_result = Mock()
        mock_result.stdout = ""
        mock_result.returncode = 1
        mock_result.stderr = "bwrap: Can't read /proc/sys/kernel/overflowuid"

        with patch.object(Config, 'sandbox_disabled', return_value=True), \
             patch('aicoder.tools.internal.grep.subprocess.run', return_value=mock_result) as run, \
             patch('aicoder.tools.internal.grep.python_grep', return_value=(["f.py:1:hit"], None)):
            first = execute({"text": "test"})

            assert "Found 1 matches" in first["friendly"]
            assert "bwrap:" in first["detailed"]
            assert run.call_count == 1

            # Second call: engine already latched, no subprocess at all
            with patch('aicoder.tools.internal.grep.resolve_command') as resolve:
                second = execute({"text": "test"})
            assert "Found 1 matches" in second["friendly"]
            assert run.call_count == 1
            resolve.assert_not_called()

    def test_no_exec_env_skips_subprocess(self):
        with patch.object(Config, 'sandbox_disabled', return_value=True), \
             patch.dict('os.environ', {"AICODER_NO_EXEC": "1"}), \
             patch('aicoder.tools.internal.grep.subprocess.run') as run, \
             patch('aicoder.tools.internal.grep.python_grep', return_value=(["a.py:2:hit"], None)):
            result = execute({"text": "needle", "path": "."})

            assert "Found 1 matches" in result["friendly"]
            assert "[python fallback]" not in result["friendly"]
            assert "AICODER_NO_EXEC is set" in result["detailed"]
            run.assert_not_called()

    def test_is_exec_failure_markers(self):
        from aicoder.tools.internal.grep import _is_exec_failure

        assert _is_exec_failure("bwrap: Can't read /proc/sys/kernel/overflowuid")
        assert _is_exec_failure("bwrap: No permissions to create new namespace")
        assert _is_exec_failure("bash: execvp: Operation not permitted")
        assert not _is_exec_failure("regex parse error: unclosed group")

    def test_fallback_bad_regex(self):
        with patch.object(Config, 'sandbox_disabled', return_value=True), \
             patch('aicoder.tools.internal.grep.subprocess.run', side_effect=PermissionError("denied")), \
             patch('aicoder.tools.internal.grep.python_grep', return_value=([], "error: unclosed group")):
            
            result = execute({"text": "predict("})
            
            assert result["tool"] == "grep"
            assert "Search failed" in result["friendly"]

    def test_python_grep_walks_files(self, tmp_path):
        from aicoder.tools.internal.grep import python_grep

        (tmp_path / "a.txt").write_text("alpha\nbeta\ngamma\n")
        (tmp_path / "sub").mkdir()
        (tmp_path / "sub" / "b.txt").write_text("needle here\n")
        (tmp_path / "skip_git").mkdir()
        (tmp_path / "skip_git" / "c.txt").write_text("needle ignored\n")
        # .git directories are pruned
        (tmp_path / ".git").mkdir()
        (tmp_path / ".git" / "d.txt").write_text("needle in git\n")

        matches, error = python_grep("needle", str(tmp_path), 10, 0)

        assert error is None
        assert any("b.txt:1:needle here" in m for m in matches)
        assert any("c.txt:1:needle ignored" in m for m in matches)
        assert not any("d.txt" in m for m in matches)

    def test_python_grep_context_and_limit(self, tmp_path):
        from aicoder.tools.internal.grep import python_grep

        (tmp_path / "a.txt").write_text("l1\nneedle\nl3\nneedle\nl5\n")

        matches, error = python_grep("needle", str(tmp_path), 10, 1)

        assert error is None
        # Matches use ':' separators, context lines use '-'
        assert any(f"a.txt:2:needle" in m for m in matches)
        assert any(f"a.txt-1-l1" in m for m in matches)
        assert any(f"a.txt-3-l3" in m for m in matches)

        limited, _ = python_grep("needle", str(tmp_path), 1, 0)
        assert len(limited) == 1

    def test_python_grep_skips_binary(self, tmp_path):
        from aicoder.tools.internal.grep import python_grep

        (tmp_path / "bin.dat").write_bytes(b"needle\0\0\0")
        (tmp_path / "text.txt").write_text("needle\n")

        matches, error = python_grep("needle", str(tmp_path), 10, 0)

        assert error is None
        assert all("bin.dat" not in m for m in matches)
        assert any("text.txt" in m for m in matches)

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
            # Command is routed through resolve_command (bash -c wrapper)
            cmd_str = " ".join(cmd) if isinstance(cmd[0], str) else " ".join(str(c) for c in cmd)
            
            assert "rg" in cmd_str
            assert "-n" in cmd_str
            assert "--max-count" in cmd_str
            assert "100" in cmd_str
            assert "-C" in cmd_str
            assert "pattern" in cmd_str
            assert "/abs/path" in cmd_str
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
