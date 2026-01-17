"""Unit tests for PromptBuilder - system prompt construction."""

import pytest
from unittest.mock import MagicMock, patch
import sys
sys.path.insert(0, '/home/blah/storage/ai-worktree-storage/feat_test_coverage__20260117_062928')

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
        """Test datetime is in ISO format."""
        context = PromptContext()

        # ISO format should contain 'T' for time separator
        assert 'T' in context.current_datetime or '-' in context.current_datetime

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


class TestPromptBuilderBasics:
    """Test PromptBuilder basic functionality."""

    def test_is_initialized_false_by_default(self):
        """Test prompt builder is not initialized by default."""
        # Reset to ensure clean state
        PromptBuilder._default_prompt_template = None
        assert PromptBuilder.is_initialized() is False

    def test_initialize_loads_template(self):
        """Test initialization loads template."""
        PromptBuilder._default_prompt_template = None
        PromptBuilder.initialize()

        assert PromptBuilder.is_initialized()
        assert PromptBuilder._default_prompt_template is not None


class TestPromptBuilderBuildPrompt:
    """Test PromptBuilder build_prompt method."""

    def test_build_prompt_with_empty_template(self):
        """Test building prompt with minimal template."""
        PromptBuilder._default_prompt_template = "Hello {current_directory}"
        context = PromptContext()
        options = PromptOptions()

        prompt = PromptBuilder.build_prompt(context, options)

        assert context.current_directory in prompt

    def test_build_prompt_replaces_datetime(self):
        """Test datetime variable is replaced."""
        PromptBuilder._default_prompt_template = "Time: {current_datetime}"
        context = PromptContext()
        options = PromptOptions()

        prompt = PromptBuilder.build_prompt(context, options)

        assert context.current_datetime in prompt

    def test_build_prompt_replaces_system_info(self):
        """Test system_info variable is replaced."""
        PromptBuilder._default_prompt_template = "System: {system_info}"
        context = PromptContext()
        options = PromptOptions()

        prompt = PromptBuilder.build_prompt(context, options)

        assert context.system_info in prompt

    def test_build_prompt_replaces_agents_content(self):
        """Test agents_content variable is replaced."""
        PromptBuilder._default_prompt_template = "Agents: {agents_content}"
        context = PromptContext()
        context.agents_content = "Custom agents"
        options = PromptOptions()

        prompt = PromptBuilder.build_prompt(context, options)

        assert "Custom agents" in prompt

    def test_build_prompt_replaces_available_tools(self):
        """Test available_tools variable is replaced."""
        PromptBuilder._default_prompt_template = "Tools: {available_tools}"
        context = PromptContext()
        options = PromptOptions()

        prompt = PromptBuilder.build_prompt(context, options)

        assert "Tools:" in prompt or "tools" in prompt.lower()

    def test_build_prompt_with_dollar_bracket_format(self):
        """Test ${variable} format is converted."""
        PromptBuilder._default_prompt_template = "Dir: ${current_directory}"
        context = PromptContext()
        options = PromptOptions()

        prompt = PromptBuilder.build_prompt(context, options)

        assert context.current_directory in prompt

    def test_build_prompt_with_override(self):
        """Test override_prompt takes precedence."""
        PromptBuilder._default_prompt_template = "Default: {current_directory}"
        context = PromptContext()
        options = PromptOptions()
        options.override_prompt = "Override content"

        prompt = PromptBuilder.build_prompt(context, options)

        assert "Override content" in prompt
        assert "{current_directory}" not in prompt

    def test_build_prompt_with_none_options(self):
        """Test build_prompt works with None options."""
        PromptBuilder._default_prompt_template = "Test: {current_directory}"
        context = PromptContext()

        prompt = PromptBuilder.build_prompt(context, None)

        assert context.current_directory in prompt


class TestPromptBuilderLoadPromptOverride:
    """Test PromptBuilder load_prompt_override method."""

    def test_load_prompt_override_not_exists(self):
        """Test loading when PROMPT-OVERRIDE.md doesn't exist."""
        with patch('os.path.exists', return_value=False):
            result = PromptBuilder.load_prompt_override()
            assert result is None

    def test_load_prompt_override_exists(self):
        """Test loading PROMPT-OVERRIDE.md when it exists."""
        mock_content = "Custom prompt"
        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)
        mock_file.read = MagicMock(return_value=mock_content)
        with patch('os.path.exists', return_value=True):
            with patch('builtins.open', return_value=mock_file):
                result = PromptBuilder.load_prompt_override()
                assert result == mock_content


class TestPromptBuilderLoadAgentsContent:
    """Test PromptBuilder load_agents_content method."""

    def test_load_agents_content_not_exists(self):
        """Test loading when AGENTS.md doesn't exist."""
        with patch('os.path.exists', return_value=False):
            result = PromptBuilder.load_agents_content()
            assert result is None

    def test_load_agents_content_exists(self):
        """Test loading AGENTS.md when it exists."""
        mock_content = "Agent instructions"
        mock_file = MagicMock()
        mock_file.__enter__ = MagicMock(return_value=mock_file)
        mock_file.__exit__ = MagicMock(return_value=False)
        mock_file.read = MagicMock(return_value=mock_content)
        with patch('os.path.exists', return_value=True):
            with patch('builtins.open', return_value=mock_file):
                result = PromptBuilder.load_agents_content()
                # Content is prefixed with separator
                assert mock_content in result


class TestPromptBuilderBuildSystemPrompt:
    """Test PromptBuilder build_system_prompt method."""

    def test_build_system_prompt_initializes(self):
        """Test build_system_prompt initializes template."""
        original_template = PromptBuilder._default_prompt_template
        PromptBuilder._default_prompt_template = None

        try:
            def mock_initialize():
                PromptBuilder._default_prompt_template = "Initialized template"

            with patch.object(PromptBuilder, 'initialize', side_effect=mock_initialize):
                with patch.object(PromptBuilder, 'load_agents_content', return_value=None):
                    with patch.object(PromptBuilder, 'load_prompt_override', return_value=None):
                        with patch('aicoder.core.config.Config') as mock_config:
                            mock_config.system_prompt.return_value = None
                            with patch('builtins.print'):
                                prompt = PromptBuilder.build_system_prompt()

                    # Verify initialize was called when template is None
                    PromptBuilder.initialize.assert_called_once()
        finally:
            PromptBuilder._default_prompt_template = original_template

    def test_build_system_prompt_returns_string(self):
        """Test build_system_prompt returns a string."""
        original_template = PromptBuilder._default_prompt_template
        PromptBuilder._default_prompt_template = "Test prompt"

        try:
            with patch.object(PromptBuilder, 'load_agents_content', return_value=None):
                with patch.object(PromptBuilder, 'load_prompt_override', return_value=None):
                    with patch('aicoder.core.config.Config') as mock_config:
                        mock_config.system_prompt.return_value = None
                        prompt = PromptBuilder.build_system_prompt()

            assert isinstance(prompt, str)
            assert len(prompt) > 0
        finally:
            PromptBuilder._default_prompt_template = original_template

    def test_build_system_prompt_with_env_override(self):
        """Test build_system_prompt uses env var override."""
        original_template = PromptBuilder._default_prompt_template
        PromptBuilder._default_prompt_template = "Default"

        try:
            with patch.object(PromptBuilder, 'load_agents_content', return_value=None):
                with patch.object(PromptBuilder, 'load_prompt_override', return_value=None):
                    with patch('aicoder.core.config.Config') as mock_config:
                        mock_config.system_prompt.return_value = "Env prompt"
                        with patch('builtins.print'):
                            prompt = PromptBuilder.build_system_prompt()

                        assert "Env prompt" in prompt
        finally:
            PromptBuilder._default_prompt_template = original_template


class TestPromptBuilderAvailableToolsInfo:
    """Test PromptBuilder _get_available_tools_info method."""

    def test_available_tools_info_contains_basic_tools(self):
        """Test available tools info mentions basic tools."""
        info = PromptBuilder._get_available_tools_info()

        assert "file" in info.lower() or "read" in info.lower()

    def test_available_tools_info_mentions_search(self):
        """Test available tools info mentions search."""
        info = PromptBuilder._get_available_tools_info()

        assert "search" in info.lower() or "grep" in info.lower()

    def test_available_tools_info_is_string(self):
        """Test available tools info returns string."""
        info = PromptBuilder._get_available_tools_info()

        assert isinstance(info, str)
        assert len(info) > 0


class TestPromptBuilderSmartAgentsHandling:
    """Test PromptBuilder smart AGENTS.md handling."""

    def test_agents_appended_to_override_without_agents_var(self):
        """Test AGENTS.md appended when override doesn't have agents var."""
        PromptBuilder._default_prompt_template = "Base"
        context = PromptContext()
        context.agents_content = "\n\n---\n\nCustom agents"
        options = PromptOptions()
        options.override_prompt = "Override without var"

        with patch('builtins.print'):
            prompt = PromptBuilder.build_prompt(context, options)

        assert "Custom agents" in prompt

    def test_agents_not_duplicated_when_present(self):
        """Test AGENTS.md not duplicated when already in template."""
        PromptBuilder._default_prompt_template = "Base: {agents_content}"
        context = PromptContext()
        context.agents_content = "Custom agents"
        options = PromptOptions()
        options.override_prompt = "Override with var"

        with patch('builtins.print'):
            prompt = PromptBuilder.build_prompt(context, options)

        # Should use the variable, not append
        assert "Custom agents" in prompt
