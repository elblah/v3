"""Test retry command max backoff functionality"""

from unittest.mock import Mock, patch
from aicoder.core.commands.retry import RetryCommand


class TestRetryCommandBackoff:
    """Test retry command max backoff functionality"""

    def test_handle_max_backoff_valid(self):
        """Test setting valid max backoff"""
        context = Mock()
        context.message_history = Mock()
        command = RetryCommand(context)
        
        with patch('aicoder.core.commands.retry.Config') as mock_config:
            command.handle_max_backoff("120")
            mock_config.set_runtime_max_backoff.assert_called_once_with(120)

    def test_handle_max_backoff_invalid(self):
        """Test setting invalid max backoff"""
        context = Mock()
        context.message_history = Mock()
        command = RetryCommand(context)
        
        with patch('aicoder.core.commands.retry.LogUtils') as mock_log:
            command.handle_max_backoff("invalid")
            mock_log.error.assert_called_once()

    def test_handle_max_backoff_zero(self):
        """Test setting max backoff to zero (should be rejected)"""
        context = Mock()
        context.message_history = Mock()
        command = RetryCommand(context)
        
        with patch('aicoder.core.commands.retry.LogUtils') as mock_log:
            command.handle_max_backoff("0")
            mock_log.error.assert_called_once()

    def test_show_current_max_backoff(self):
        """Test showing current max backoff"""
        context = Mock()
        context.message_history = Mock()
        command = RetryCommand(context)
        
        with patch('aicoder.core.commands.retry.Config') as mock_config, \
             patch('aicoder.core.commands.retry.LogUtils') as mock_log:
            mock_config.effective_max_backoff.return_value = 90
            command.show_current_max_backoff()
            mock_log.print.assert_called_once_with("[*] Current max backoff: 90s")

    def test_help_includes_current_values(self):
        """Test that help includes current configuration values"""
        context = Mock()
        context.message_history = Mock()
        command = RetryCommand(context)
        
        with patch('aicoder.core.commands.retry.Config') as mock_config, \
             patch('aicoder.core.commands.retry.LogUtils') as mock_log:
            mock_config.effective_max_retries.return_value = 5
            mock_config.effective_max_backoff.return_value = 120
            
            command.show_help()
            
            # Check that help was printed
            mock_log.print.assert_called_once()
            args = mock_log.print.call_args[0][0]
            assert "Max retries: 5" in args
            assert "Max backoff: 120s" in args
            assert "MAX_BACKOFF_SECONDS" in args