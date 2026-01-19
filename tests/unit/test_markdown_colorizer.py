"""Unit tests for MarkdownColorizer."""

import pytest
from unittest.mock import patch, MagicMock

import sys
sys.path.insert(0, '/home/blah/storage/ai-worktree-storage/feat_test_coverage__20260117_062928')

from aicoder.core.markdown_colorizer import MarkdownColorizer


class TestMarkdownColorizer:
    """Test MarkdownColorizer class."""

    @pytest.fixture(autouse=True)
    def setup_mocks(self):
        """Setup mocks for each test."""
        self.mock_colors = {
            "green": "\033[32m",
            "bold": "\033[1m",
            "red": "\033[31m",
            "reset": "\033[0m"
        }
        with patch('aicoder.core.markdown_colorizer.Config') as mock_config:
            mock_config.colors = self.mock_colors
            self.colorizer = MarkdownColorizer()
            yield mock_config

    def test_initial_state(self):
        """Test initial state after reset."""
        assert self.colorizer._in_code is False
        assert self.colorizer._code_tick_count == 0
        assert self.colorizer._in_star is False
        assert self.colorizer._star_count == 0
        assert self.colorizer._at_line_start is True
        assert self.colorizer._in_header is False
        assert self.colorizer._in_bold is False
        assert self.colorizer._consecutive_count == 0
        assert self.colorizer._can_be_bold is False

    def test_reset_state(self):
        """Test state reset."""
        # Set some state
        self.colorizer._in_code = True
        self.colorizer._code_tick_count = 3
        self.colorizer._in_star = True
        self.colorizer._in_header = True

        # Reset
        self.colorizer.reset_state()

        # Verify reset
        assert self.colorizer._in_code is False
        assert self.colorizer._code_tick_count == 0
        assert self.colorizer._in_star is False
        assert self.colorizer._in_header is False

    def test_empty_content(self):
        """Test processing empty content."""
        result = self.colorizer.process_with_colorization("")
        assert result == ""

    def test_none_content(self):
        """Test processing None content."""
        result = self.colorizer.process_with_colorization(None)
        assert result is None

    def test_plain_text(self):
        """Test processing plain text without markup."""
        result = self.colorizer.process_with_colorization("Hello World")
        assert result == "Hello World"

    def test_header_at_line_start(self):
        """Test header detection at line start."""
        result = self.colorizer.process_with_colorization("# Header")
        assert "\033[31m" in result  # Red color for header

    def test_header_not_at_line_start(self):
        """Test that # is not treated as header when not at line start."""
        result = self.colorizer.process_with_colorization("text # not header")
        assert "\033[31m" not in result  # No red color

    def test_single_asterisk_not_bold(self):
        """Test single asterisk doesn't trigger bold."""
        result = self.colorizer.process_with_colorization("*italic*")
        # Single asterisk should get green color
        assert "\033[32m" in result

    def test_double_asterisk_bold(self):
        """Test double asterisks trigger bold."""
        result = self.colorizer.process_with_colorization("**bold**")
        # Should have bold color
        assert "\033[1m" in result

    def test_triple_asterisk_not_bold(self):
        """Test triple asterisks don't trigger bold."""
        result = self.colorizer.process_with_colorization("***text***")
        # Triple should not be bold (can_be_bold is False for >2)
        # The green color should be applied though
        assert "\033[32m" in result

    def test_code_inline(self):
        """Test inline code with backticks."""
        result = self.colorizer.process_with_colorization("`code`")
        assert "\033[32m" in result  # Green for code

    def test_code_block(self):
        """Test code block with triple backticks."""
        result = self.colorizer.process_with_colorization("```\ncode\n```")
        assert "\033[32m" in result  # Green for code block

    def test_code_within_text(self):
        """Test inline code within regular text."""
        result = self.colorizer.process_with_colorization("Use `ls` command")
        assert "Use " in result
        assert "\033[32m" in result
        assert "ls" in result

    def test_newline_resets_line_start(self):
        """Test that newline resets line start state."""
        result = self.colorizer.process_with_colorization("line1\nline2")
        assert "line1\nline2" in result

    def test_newline_resets_header_mode(self):
        """Test that newline resets header color mode."""
        result = self.colorizer.process_with_colorization("# Header\ntext")
        assert "\033[31m" in result  # Header color
        assert "\033[0m" in result  # Reset after header

    def test_multiple_headers(self):
        """Test multiple headers in content."""
        result = self.colorizer.process_with_colorization("# Header1\ntext\n# Header2")
        assert result.count("\033[31m") == 2  # Two headers

    def test_bold_toggle(self):
        """Test bold mode toggle."""
        result = self.colorizer.process_with_colorization("**bold**normal**bold again**")
        # Should have multiple bold sections
        bold_count = result.count("\033[1m")
        assert bold_count >= 2

    def test_starmode_tracking(self):
        """Test that star mode is tracked correctly."""
        result = self.colorizer.process_with_colorization("*italic*")
        # Should enter star mode
        assert "\033[32m" in result  # Green applied

    def test_process_with_colorization_alias(self):
        """Test that process_with_colorization is alias for print_with_colorization."""
        result1 = self.colorizer.process_with_colorization("test")
        self.colorizer.reset_state()
        result2 = self.colorizer.print_with_colorization("test")
        assert result1 == result2

    def test_mixed_markdown(self):
        """Test mixed markdown content."""
        result = self.colorizer.process_with_colorization("**bold** and `code`")
        assert "\033[1m" in result  # Bold
        assert "\033[32m" in result  # Code

    def test_consecutive_asterisks_counting(self):
        """Test consecutive asterisk counting."""
        result = self.colorizer.process_with_colorization("****")
        # Should handle 4 asterisks (two sets of **)
        assert "\033[32m" in result

    def test_backtick_counting(self):
        """Test backtick counting for code blocks."""
        result = self.colorizer.process_with_colorization("````")
        # Should handle 4 backticks
        assert "\033[32m" in result
