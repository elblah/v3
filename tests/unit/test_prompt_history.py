"""Unit tests for prompt_history module."""

import json
import os
import pytest
import tempfile
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, '/home/blah/storage/ai-worktree-storage/feat_test_coverage__20260117_062928')


class TestSavePrompt:
    """Test save_prompt function."""

    def test_save_empty_prompt(self):
        """Test that empty prompts are not saved."""
        from aicoder.core.prompt_history import save_prompt

        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write("")
            temp_path = f.name

        try:
            with patch('aicoder.core.prompt_history._HISTORY_PATH', temp_path):
                save_prompt("")
                with open(temp_path, 'r') as f:
                    content = f.read()
                assert content == ""
        finally:
            os.unlink(temp_path)

    def test_save_whitespace_only_prompt(self):
        """Test that whitespace-only prompts are not saved."""
        from aicoder.core.prompt_history import save_prompt

        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write("")
            temp_path = f.name

        try:
            with patch('aicoder.core.prompt_history._HISTORY_PATH', temp_path):
                save_prompt("   \n\t  ")
                with open(temp_path, 'r') as f:
                    content = f.read()
                assert content == ""
        finally:
            os.unlink(temp_path)

    def test_save_approval_responses(self):
        """Test that 'Y' and 'n' responses are not saved."""
        from aicoder.core.prompt_history import save_prompt

        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write("")
            temp_path = f.name

        try:
            with patch('aicoder.core.prompt_history._HISTORY_PATH', temp_path):
                save_prompt("Y")
                save_prompt("n")
                with open(temp_path, 'r') as f:
                    content = f.read()
                assert content == ""
        finally:
            os.unlink(temp_path)

    def test_save_normal_prompt(self):
        """Test that normal prompts are saved."""
        from aicoder.core.prompt_history import save_prompt

        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write("")
            temp_path = f.name

        try:
            with patch('aicoder.core.prompt_history._HISTORY_PATH', temp_path):
                save_prompt("Test prompt")
                with open(temp_path, 'r') as f:
                    content = f.read()
                assert content.strip() != ""

                # Verify JSON format
                line = content.strip()
                entry = json.loads(line)
                assert entry["prompt"] == "Test prompt"
        finally:
            os.unlink(temp_path)

    def test_save_multiple_prompts(self):
        """Test that multiple prompts are saved."""
        from aicoder.core.prompt_history import save_prompt

        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write("")
            temp_path = f.name

        try:
            with patch('aicoder.core.prompt_history._HISTORY_PATH', temp_path):
                save_prompt("Prompt 1")
                save_prompt("Prompt 2")
                save_prompt("Prompt 3")

                with open(temp_path, 'r') as f:
                    lines = [json.loads(line.strip()) for line in f if line.strip()]

                assert len(lines) == 3
                assert lines[0]["prompt"] == "Prompt 1"
                assert lines[1]["prompt"] == "Prompt 2"
                assert lines[2]["prompt"] == "Prompt 3"
        finally:
            os.unlink(temp_path)

    def test_save_with_disabled_history(self):
        """Test that nothing is saved when history is disabled."""
        from aicoder.core.prompt_history import save_prompt

        with patch('aicoder.core.prompt_history._HISTORY_PATH', None):
            # Should not raise
            save_prompt("Test prompt")

    def test_save_handles_write_error(self):
        """Test that write errors are handled silently."""
        from aicoder.core.prompt_history import save_prompt

        # Mock open to raise an error
        with patch('builtins.open', side_effect=OSError("Permission denied")):
            # Should not raise
            save_prompt("Test prompt")


class TestReadHistory:
    """Test read_history function."""

    def test_read_empty_file(self):
        """Test reading empty history file."""
        from aicoder.core.prompt_history import read_history

        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write("")
            temp_path = f.name

        try:
            with patch('aicoder.core.prompt_history._HISTORY_PATH', temp_path):
                result = read_history()
                assert result == []
        finally:
            os.unlink(temp_path)

    def test_read_with_entries(self):
        """Test reading history with entries."""
        from aicoder.core.prompt_history import read_history

        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write('{"prompt": "Prompt 1"}\n')
            f.write('{"prompt": "Prompt 2"}\n')
            temp_path = f.name

        try:
            with patch('aicoder.core.prompt_history._HISTORY_PATH', temp_path):
                result = read_history()
                assert len(result) == 2
                assert result[0]["prompt"] == "Prompt 1"
                assert result[1]["prompt"] == "Prompt 2"
        finally:
            os.unlink(temp_path)

    def test_read_skips_empty_prompts(self):
        """Test that entries with empty prompts are filtered."""
        from aicoder.core.prompt_history import read_history

        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write('{"prompt": "Valid prompt"}\n')
            f.write('{"prompt": ""}\n')
            f.write('{"prompt": "Another valid"}\n')
            temp_path = f.name

        try:
            with patch('aicoder.core.prompt_history._HISTORY_PATH', temp_path):
                result = read_history()
                assert len(result) == 2
        finally:
            os.unlink(temp_path)

    def test_read_handles_invalid_json(self):
        """Test that invalid JSON lines are handled gracefully."""
        from aicoder.core.prompt_history import read_history

        with tempfile.NamedTemporaryFile(mode='w', suffix='.jsonl', delete=False) as f:
            f.write('{"prompt": "Valid"}\n')
            f.write('not valid json\n')
            f.write('{"prompt": "Also valid"}\n')
            temp_path = f.name

        try:
            with patch('aicoder.core.prompt_history._HISTORY_PATH', temp_path):
                result = read_history()
                # Should return valid entries only
                assert len(result) == 2
        finally:
            os.unlink(temp_path)

    def test_read_with_disabled_history(self):
        """Test that disabled history returns empty list."""
        from aicoder.core.prompt_history import read_history

        with patch('aicoder.core.prompt_history._HISTORY_PATH', None):
            result = read_history()
            assert result == []

    def test_read_nonexistent_file(self):
        """Test reading non-existent file returns empty list."""
        from aicoder.core.prompt_history import read_history

        with patch('aicoder.core.prompt_history._HISTORY_PATH', "/nonexistent/path.jsonl"):
            result = read_history()
            assert result == []

    def test_read_handles_read_error(self):
        """Test that read errors are handled silently."""
        from aicoder.core.prompt_history import read_history

        with patch('aicoder.core.prompt_history._HISTORY_PATH', "/nonexistent/file"):
            result = read_history()
            assert result == []


class TestHistoryPathInitialization:
    """Test history path initialization."""

    def test_history_path_created(self):
        """Test that .aicoder directory is created on import."""
        # Test the _init_history_path function directly
        import tempfile
        import shutil

        test_dir = tempfile.mkdtemp()

        try:
            # Mock the path checks and cwd
            with patch('os.path.exists', return_value=False):
                with patch('os.makedirs') as makedirs_mock:
                    with patch('os.getcwd', return_value=test_dir):
                        from aicoder.core.prompt_history import _init_history_path

                        result = _init_history_path()

                        # Import should attempt to create directory
                        makedirs_mock.assert_called()
                        # Result should be relative path (based on aicoder_dir = ".aicoder")
                        assert ".aicoder" in result
                        assert result.endswith("history")
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)

    def test_history_path_handles_mkdir_error(self):
        """Test that mkdir errors are handled silently."""
        import tempfile
        import shutil

        test_dir = tempfile.mkdtemp()
        test_aicoder_dir = os.path.join(test_dir, ".aicoder")

        try:
            with patch('os.path.exists', return_value=False):
                with patch('os.makedirs', side_effect=OSError("Permission denied")):
                    from aicoder.core.prompt_history import _init_history_path

                    result = _init_history_path()
                    # History path should be None when mkdir fails
                    assert result is None
        finally:
            shutil.rmtree(test_dir, ignore_errors=True)
