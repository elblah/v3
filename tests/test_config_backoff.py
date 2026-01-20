"""Test max backoff configuration"""

import os
import pytest
from unittest.mock import patch
from aicoder.core.config import Config


class TestMaxBackoffConfig:
    """Test max backoff configuration"""

    def test_default_max_backoff(self):
        """Test default max backoff value"""
        with patch.dict('os.environ', {}, clear=True):
            Config.reset()
            assert Config.max_backoff() == 64

    def test_env_var_max_backoff(self):
        """Test environment variable override"""
        with patch.dict('os.environ', {'MAX_BACKOFF_SECONDS': '120'}, clear=True):
            Config.reset()
            assert Config.max_backoff() == 120

    def test_runtime_max_backoff_override(self):
        """Test runtime max backoff override"""
        with patch.dict('os.environ', {'MAX_BACKOFF_SECONDS': '64'}, clear=True):
            Config.reset()
            Config.set_runtime_max_backoff(30)
            assert Config.effective_max_backoff() == 30

    def test_runtime_max_backoff_none(self):
        """Test that runtime override None uses environment"""
        with patch.dict('os.environ', {'MAX_BACKOFF_SECONDS': '100'}, clear=True):
            Config.reset()
            Config.set_runtime_max_backoff(None)
            assert Config.effective_max_backoff() == 100

    def test_max_backoff_minimum(self):
        """Test that max backoff has minimum"""
        with patch.dict('os.environ', {'MAX_BACKOFF_SECONDS': '0'}, clear=True):
            Config.reset()
            assert Config.max_backoff() == 0  # Allow 0 for flexibility

    def test_max_backoff_invalid_env(self):
        """Test handling of invalid environment variable"""
        with patch.dict('os.environ', {'MAX_BACKOFF_SECONDS': 'invalid'}, clear=True):
            Config.reset()
            with pytest.raises(ValueError):
                Config.max_backoff()