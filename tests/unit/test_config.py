"""
Unit tests for Config AI prefix behavior.
"""

from unittest.mock import patch

from aicoder.core.config import Config


class TestAiPrefix:
    """Test Config.ai_prefix()."""

    def test_default_shows_current_model(self):
        """Unset env: prefix shows the model current at print time."""
        with patch.object(Config, '_ai_prefix_override', None), \
             patch.object(Config, 'model', return_value="deepseek/deepseek-v4.1-flash"):
            assert Config.ai_prefix() == "AI (deepseek-v4.1-flash): "

    def test_default_missing_model_falls_back_to_unknown(self):
        """Unset env and no model configured: prefix says unknown."""
        with patch.object(Config, '_ai_prefix_override', None), \
             patch.object(Config, 'model', return_value=""):
            assert Config.ai_prefix() == "AI (unknown): "

    def test_env_override_replaces_whole_marker(self):
        """Set env: the value replaces the whole marker verbatim."""
        with patch.object(Config, '_ai_prefix_override', 'Sage: '):
            assert Config.ai_prefix() == "Sage: "
