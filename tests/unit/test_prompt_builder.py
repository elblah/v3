"""Unit tests for PromptBuilder - system prompt construction."""

import pytest
from unittest.mock import MagicMock, patch
import sys

from aicoder.core.prompt_builder import PromptBuilder, PromptContext, PromptOptions


class TestPromptContext:
    """Test PromptContext dataclass."""

    def test_context_init(self):
        """Test context initializes with all fields."""
        context = PromptContext()

        assert context.current_directory is not None
        assert context.current_datetime is not None
        assert context.system_info is not None
        assert context.agents_content is None

    def test_context_current_datetime_format(self):
        """Test datetime format matches PromptContext._get_current_datetime()."""
        context = PromptContext()

        # Format should be: YYYY-MM-DD
        assert len(context.current_datetime) == 10
        # Should follow pattern: 2026-01-22
        import re
        assert re.match(r'\d{4}-\d{2}-\d{2}', context.current_datetime)

    def test_context_system_info_contains_platform(self):
        """Test system info contains platform info."""
        context = PromptContext()

        assert "Platform:" in context.system_info
        assert "Python:" in context.system_info

    def test_context_agents_content_can_be_set(self):
        """Test agents_content can be set."""
        context = PromptContext()
        context.agents_content = "Custom agents content"

        assert context.agents_content == "Custom agents content"


class TestPromptOptions:
    """Test PromptOptions dataclass."""

    def test_options_init(self):
        """Test options initializes with defaults."""
        options = PromptOptions()

        assert options.override_prompt is None


class TestPromptBuilderBuildPrompt:
    """Test PromptBuilder build_prompt method."""

    def test_build_prompt_with_template(self):
        """Test building prompt with template override."""
        context = PromptContext()
        options = PromptOptions()
        options.override_prompt = "Hello {current_directory}"

        prompt = PromptBuilder.build_prompt(context, options)

        assert context.current_directory in prompt

    def test_build_prompt_replaces_datetime(self):
        """Test datetime variable is replaced."""
        context = PromptContext()
        options = PromptOptions()
        options.override_prompt = "Time: {current_datetime}"

        prompt = PromptBuilder.build_prompt(context, options)

        assert context.current_datetime in prompt

    def test_build_prompt_replaces_system_info(self):
        """Test system_info variable is replaced."""
        context = PromptContext()
        options = PromptOptions()
        options.override_prompt = "System: {system_info}"

        prompt = PromptBuilder.build_prompt(context, options)

        assert context.system_info in prompt

    def test_build_prompt_replaces_agents_content(self):
        """Test agents_content variable is replaced."""
        context = PromptContext()
        context.agents_content = "Custom agents"
        options = PromptOptions()
        options.override_prompt = "Agents: {agents_content}"

        prompt = PromptBuilder.build_prompt(context, options)

        assert "Custom agents" in prompt

    def test_build_prompt_replaces_available_tools(self):
        """Test available_tools variable is replaced."""
        context = PromptContext()
        options = PromptOptions()
        options.override_prompt = "Tools: {available_tools}"

        prompt = PromptBuilder.build_prompt(context, options)

        assert "Tools:" in prompt or "tools" in prompt.lower()

    def test_build_prompt_with_dollar_bracket_format(self):
        """Test ${variable} format is converted."""
        context = PromptContext()
        options = PromptOptions()
        options.override_prompt = "Dir: ${current_directory}"

        prompt = PromptBuilder.build_prompt(context, options)

        assert context.current_directory in prompt

    def test_build_prompt_with_override(self):
        """Test override_prompt takes precedence over default template."""
        context = PromptContext()
        options = PromptOptions()
        options.override_prompt = "Override content"

        prompt = PromptBuilder.build_prompt(context, options)

        assert "Override content" in prompt
        assert "{current_directory}" not in prompt

    def test_build_prompt_with_none_options(self):
        """Test build_prompt works with None options (loads default template)."""
        context = PromptContext()

        prompt = PromptBuilder.build_prompt(context)

        assert context.current_directory in prompt
        assert len(prompt) > 50


class TestPromptBuilderLoadTemplate:
    """Test _load_template method."""

    def test_load_template_returns_fallback_on_missing_file(self):
        """Test _load_template returns fallback when no file exists."""
        with patch('builtins.open', side_effect=FileNotFoundError):
            result = PromptBuilder._load_template()
        assert "You are a helpful AI assistant" in result


class TestPromptBuilderBuildSystemPrompt:
    """Test PromptBuilder.build_system_prompt."""

    def test_build_system_prompt_returns_string(self):
        """Test build_system_prompt returns valid string."""
        prompt = PromptBuilder.build_system_prompt()
        assert isinstance(prompt, str)
        assert len(prompt) > 100

    def test_build_system_prompt_contains_context(self):
        """Test system prompt contains context variables."""
        prompt = PromptBuilder.build_system_prompt()
        assert "Platform:" in prompt
        assert "Python:" in prompt
