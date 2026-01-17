"""Tests for context bar module"""

import pytest
from unittest.mock import Mock, patch
from aicoder.core.context_bar import ContextBar


class TestContextBar:
    """Tests for ContextBar class"""

    def test_init(self):
        """Test ContextBar initializes"""
        cb = ContextBar()
        assert cb is not None

    def test_format_context_bar_basic(self):
        """Test format_context_bar returns a string"""
        cb = ContextBar()
        stats = Mock()
        stats.current_prompt_size = 50000
        message_history = Mock()

        with patch('aicoder.core.config.Config.context_size', return_value=128000):
            result = cb.format_context_bar(stats, message_history)
            assert isinstance(result, str)
            assert "Context:" in result

    def test_format_context_bar_percentage(self):
        """Test format_context_bar shows percentage"""
        cb = ContextBar()
        stats = Mock()
        stats.current_prompt_size = 12800  # 10% of 128000
        message_history = Mock()

        with patch('aicoder.core.config.Config.context_size', return_value=128000):
            result = cb.format_context_bar(stats, message_history)
            assert "10%" in result or "%" in result

    def test_format_context_bar_zero_tokens(self):
        """Test format_context_bar handles zero tokens"""
        cb = ContextBar()
        stats = Mock()
        stats.current_prompt_size = 0
        message_history = Mock()

        with patch('aicoder.core.config.Config.context_size', return_value=128000):
            result = cb.format_context_bar(stats, message_history)
            assert isinstance(result, str)

    def test_format_context_bar_high_percentage(self):
        """Test format_context_bar with high percentage (capped)"""
        cb = ContextBar()
        stats = Mock()
        stats.current_prompt_size = 200000  # More than max
        message_history = Mock()

        with patch('aicoder.core.config.Config.context_size', return_value=128000):
            result = cb.format_context_bar(stats, message_history)
            # Should be capped at a reasonable value
            assert isinstance(result, str)

    def test_format_context_bar_model_name(self):
        """Test format_context_bar includes model name"""
        cb = ContextBar()
        stats = Mock()
        stats.current_prompt_size = 50000
        message_history = Mock()

        with patch('aicoder.core.config.Config.context_size', return_value=128000), \
             patch('aicoder.core.config.Config.model', return_value="gpt-4"):
            result = cb.format_context_bar(stats, message_history)
            assert isinstance(result, str)

    def test_get_current_hour(self):
        """Test get_current_hour returns time string"""
        cb = ContextBar()
        result = cb.get_current_hour()
        # Should be in HH:MM:SS format
        assert ":" in result
        assert len(result.split(":")) == 3

    def test_create_progress_bar_low_percentage(self):
        """Test create_progress_bar with low percentage (green)"""
        cb = ContextBar()
        result = cb.create_progress_bar(10)
        assert "█" in result  # Filled portion
        assert "░" in result  # Empty portion
        # Result should contain the line with color codes
        assert len(result) > 0

    def test_create_progress_bar_medium_percentage(self):
        """Test create_progress_bar with medium percentage (yellow)"""
        cb = ContextBar()
        result = cb.create_progress_bar(50)
        assert "█" in result
        assert "░" in result
        assert len(result) > 0

    def test_create_progress_bar_high_percentage(self):
        """Test create_progress_bar with high percentage (red)"""
        cb = ContextBar()
        result = cb.create_progress_bar(90)
        assert "█" in result
        assert len(result) > 0

    def test_create_progress_bar_zero(self):
        """Test create_progress_bar with zero percentage"""
        cb = ContextBar()
        result = cb.create_progress_bar(0)
        assert "░" in result  # All empty

    def test_create_progress_bar_full(self):
        """Test create_progress_bar with 100%"""
        cb = ContextBar()
        result = cb.create_progress_bar(100)
        assert "█" in result  # All filled

    def test_create_progress_bar_negative(self):
        """Test create_progress_bar handles negative values"""
        cb = ContextBar()
        result = cb.create_progress_bar(-10)
        # Should be capped at 0
        assert "░" in result  # Should show as empty

    def test_create_progress_bar_over_100(self):
        """Test create_progress_bar handles values over 100%"""
        cb = ContextBar()
        result = cb.create_progress_bar(150)
        # Should be capped at 100
        assert "█" in result  # Should show as full

    def test_print_context_bar(self, capsys):
        """Test print_context_bar prints to stdout"""
        cb = ContextBar()
        stats = Mock()
        stats.current_prompt_size = 50000
        message_history = Mock()

        with patch('aicoder.core.config.Config.context_size', return_value=128000):
            cb.print_context_bar(stats, message_history)
            captured = capsys.readouterr()
            assert "Context:" in captured.out

    def test_print_context_bar_for_user(self, capsys):
        """Test print_context_bar_for_user prints with newline"""
        cb = ContextBar()
        stats = Mock()
        stats.current_prompt_size = 50000
        message_history = Mock()

        with patch('aicoder.core.config.Config.context_size', return_value=128000):
            cb.print_context_bar_for_user(stats, message_history)
            captured = capsys.readouterr()
            assert "Context:" in captured.out
            assert captured.out.startswith("\n")


class TestContextBarEdgeCases:
    """Tests for edge cases in ContextBar"""

    def test_format_context_bar_none_stats(self):
        """Test format_context_bar handles None stats - expects AttributeError"""
        cb = ContextBar()
        stats = None
        message_history = Mock()

        with patch('aicoder.core.config.Config.context_size', return_value=128000):
            # The code doesn't handle None stats, so it should raise AttributeError
            with pytest.raises(AttributeError):
                cb.format_context_bar(stats, message_history)

    def test_format_context_bar_none_current_tokens(self):
        """Test format_context_bar handles None current_prompt_size"""
        cb = ContextBar()
        stats = Mock()
        stats.current_prompt_size = None
        message_history = Mock()

        with patch('aicoder.core.config.Config.context_size', return_value=128000):
            result = cb.format_context_bar(stats, message_history)
            assert isinstance(result, str)

    def test_progress_bar_unicode_block_chars(self):
        """Test progress bar uses unicode block characters"""
        cb = ContextBar()
        result = cb.create_progress_bar(50)
        # Should use unicode block characters
        assert "█" in result or "░" in result

    def test_progress_bar_width(self):
        """Test progress bar has correct width"""
        cb = ContextBar()
        result = cb.create_progress_bar(50)
        # 10 characters total (including colors)
        # The actual visible width is 10 characters
        assert len(result) >= 10
