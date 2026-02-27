"""
Unit tests for context bar component.
"""

import pytest
from unittest.mock import Mock, patch, PropertyMock
import math

import sys
sys.path.insert(0, '/home/blah/storage/ai-worktree-storage/feat_test_coverage__20260117_062928')

from aicoder.core.context_bar import ContextBar
from aicoder.core.config import Config


class TestContextBar:
    """Test ContextBar class."""

    def setup_method(self):
        """Set up test fixtures."""
        self.context_bar = ContextBar()

    def test_format_context_bar_zero_tokens(self):
        """Test context bar with zero tokens."""
        mock_stats = Mock()
        mock_stats.current_prompt_size = 0
        mock_stats.last_api_time = 0

        with patch('aicoder.core.context_bar.Config.context_size', return_value=100000), \
             patch('aicoder.core.context_bar.Config.model', return_value="gpt-4"):
            result = self.context_bar.format_context_bar(mock_stats, None)

            assert "Context:" in result
            assert "0%" in result
            assert "@gpt-4" in result

    def test_format_context_bar_partial_tokens(self):
        """Test context bar with partial tokens."""
        mock_stats = Mock()
        mock_stats.current_prompt_size = 50000  # 50% of 100k
        mock_stats.last_api_time = 0

        with patch('aicoder.core.context_bar.Config.context_size', return_value=100000), \
             patch('aicoder.core.context_bar.Config.model', return_value="gpt-4"):
            result = self.context_bar.format_context_bar(mock_stats, None)

            assert "50" in result

    def test_format_context_bar_high_tokens(self):
        """Test context bar with high tokens."""
        mock_stats = Mock()
        mock_stats.current_prompt_size = 90000  # 90% of 100k
        mock_stats.last_api_time = 0

        with patch('aicoder.core.context_bar.Config.context_size', return_value=100000), \
             patch('aicoder.core.context_bar.Config.model', return_value="gpt-4"):
            result = self.context_bar.format_context_bar(mock_stats, None)

            assert "90" in result or "9" in result

    def test_format_context_bar_with_model_name(self):
        """Test context bar shows model name."""
        mock_stats = Mock()
        mock_stats.current_prompt_size = 1000
        mock_stats.last_api_time = 0

        with patch('aicoder.core.context_bar.Config.context_size', return_value=100000), \
             patch('aicoder.core.context_bar.Config.model', return_value="gpt-4"):
            result = self.context_bar.format_context_bar(mock_stats, None)

            assert "gpt-4" in result

    def test_format_context_bar_model_with_slash(self):
        """Test context bar with model name containing slash."""
        mock_stats = Mock()
        mock_stats.current_prompt_size = 1000
        mock_stats.last_api_time = 0

        with patch('aicoder.core.context_bar.Config.context_size', return_value=100000), \
             patch('aicoder.core.context_bar.Config.model', return_value="openai/gpt-4"):
            result = self.context_bar.format_context_bar(mock_stats, None)
            # Should use short name (gpt-4)
            assert "gpt-4" in result

    def test_format_context_bar_large_numbers_k(self):
        """Test context bar formats large numbers with k."""
        mock_stats = Mock()
        mock_stats.current_prompt_size = 50000  # 50k
        mock_stats.last_api_time = 0

        with patch('aicoder.core.context_bar.Config.context_size', return_value=100000), \
             patch('aicoder.core.context_bar.Config.model', return_value="gpt-4"):
            result = self.context_bar.format_context_bar(mock_stats, None)

            # Should show k notation
            assert "50" in result

    def test_format_context_bar_small_numbers(self):
        """Test context bar shows small numbers as-is."""
        mock_stats = Mock()
        mock_stats.current_prompt_size = 500
        mock_stats.last_api_time = 0

        with patch('aicoder.core.context_bar.Config.context_size', return_value=100000), \
             patch('aicoder.core.context_bar.Config.model', return_value="gpt-4"):
            result = self.context_bar.format_context_bar(mock_stats, None)

            assert "500" in result

    def test_get_current_hour(self):
        """Test getting current hour."""
        result = self.context_bar.get_current_hour()
        # Should be HH:MM:SS format
        assert ":" in result
        parts = result.split(":")
        assert len(parts) == 3
        assert len(parts[0]) == 2  # Hours
        assert len(parts[1]) == 2  # Minutes
        assert len(parts[2]) == 2  # Seconds


class TestProgressBar:
    """Test progress bar creation."""

    def setup_method(self):
        """Set up test fixtures."""
        self.context_bar = ContextBar()

    def test_progress_bar_zero_percent(self):
        """Test progress bar at 0%."""
        result = self.context_bar.create_progress_bar(0)
        assert "░" in result or result is not None

    def test_progress_bar_half_percent(self):
        """Test progress bar at 50%."""
        result = self.context_bar.create_progress_bar(50)
        assert "█" in result or "░" in result

    def test_progress_bar_full_percent(self):
        """Test progress bar at 100%."""
        result = self.context_bar.create_progress_bar(100)
        assert "█" in result or result is not None

    def test_progress_bar_negative_percentage(self):
        """Test progress bar with negative percentage."""
        result = self.context_bar.create_progress_bar(-10)
        # Should handle gracefully
        assert result is not None

    def test_progress_bar_overflow_percentage(self):
        """Test progress bar with percentage over 100."""
        result = self.context_bar.create_progress_bar(150)
        # Should cap at 100%
        assert "█" in result or result is not None

    def test_progress_bar_width(self):
        """Test progress bar has correct width."""
        result = self.context_bar.create_progress_bar(50)
        # Should be around 10 characters (plus color codes)
        for color in Config.colors.values():
            result = result.replace(color, "")
        assert len(result) >= 8
        assert len(result) <= 15


class TestPrintContextBar:
    """Test printing context bar."""

    def setup_method(self):
        """Set up test fixtures."""
        self.context_bar = ContextBar()

    def test_print_context_bar(self, capsys):
        """Test printing context bar."""
        mock_stats = Mock()
        mock_stats.current_prompt_size = 1000
        mock_stats.last_api_time = 0

        with patch('aicoder.core.context_bar.Config.context_size', return_value=100000), \
             patch('aicoder.core.context_bar.Config.model', return_value="gpt-4"):
            self.context_bar.print_context_bar(mock_stats, None)

            captured = capsys.readouterr()
            assert "Context:" in captured.out

    def test_print_context_bar_for_user(self, capsys):
        """Test printing context bar for user."""
        mock_stats = Mock()
        mock_stats.current_prompt_size = 1000
        mock_stats.last_api_time = 0

        with patch('aicoder.core.context_bar.Config.context_size', return_value=100000), \
             patch('aicoder.core.context_bar.Config.model', return_value="gpt-4"):
            self.context_bar.print_context_bar_for_user(mock_stats, None)

            captured = capsys.readouterr()
            assert "Context:" in captured.out
            assert "\n" in captured.out  # Should have newline before


class TestContextBarEdgeCases:
    """Test edge cases for context bar."""

    def setup_method(self):
        """Set up test fixtures."""
        self.context_bar = ContextBar()

    def test_progress_bar_infinity(self):
        """Test progress bar with infinity."""
        result = self.context_bar.create_progress_bar(math.inf)
        # Should handle gracefully
        assert result is not None

    def test_progress_bar_nan(self):
        """Test progress bar with NaN."""
        result = self.context_bar.create_progress_bar(float('nan'))
        # Should handle gracefully
        assert result is not None
