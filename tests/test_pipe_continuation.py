"""Tests for continuation prompts in non-interactive (piped) mode.

Prompts queued while the AI is working (compaction continuation, empty
response retry, auto next prompt, ...) used to be dropped in pipe mode,
so the session ended silently right after e.g. a compaction.
"""

from unittest.mock import MagicMock, patch

import pytest

from aicoder.core.aicoder import AICoder


@pytest.fixture
def app():
    """AICoder instance with plugin hook calls neutralized"""
    instance = AICoder()
    instance.plugin_system.call_hooks = MagicMock()
    instance.plugin_system.call_hooks_with_return = MagicMock(return_value=None)
    instance.is_running = True
    return instance


def _run_pipe(app, stdin_text="hello"):
    with patch(
        "aicoder.core.aicoder.read_stdin_as_string", return_value=stdin_text
    ):
        with patch.object(app, "shutdown"):
            app.run_non_interactive()


def test_pending_prompt_after_turn_triggers_second_call(app):
    """A prompt set during the AI turn must be consumed, not dropped"""
    calls = []

    def fake_process():
        calls.append(1)
        if len(calls) == 1:
            app.set_next_prompt("SYSTEM: continue after compaction")

    app.session_manager.process_with_ai = fake_process

    _run_pipe(app)

    assert len(calls) == 2
    # Consumed, so nothing is left pending at exit
    assert app.has_next_prompt() is False


def test_no_pending_prompt_is_single_call(app):
    """Normal end of a piped turn stays a single call"""
    calls = []
    app.session_manager.process_with_ai = lambda: calls.append(1)

    _run_pipe(app)

    assert len(calls) == 1


def test_drain_is_bounded(app):
    """A plugin that always re-queues cannot loop forever"""
    calls = []

    def process():
        calls.append(1)
        app.set_next_prompt("forever")

    app.session_manager.process_with_ai = process
    app.set_next_prompt("forever")

    turns = app._drain_pending_prompts(max_turns=3)

    assert turns == 3
    assert len(calls) == 3
    # The leftover prompt is reported, not silently dropped
    assert app.has_next_prompt() is True


def test_empty_prompt_is_discarded(app):
    """An empty prompt must not trigger an API call"""
    calls = []
    app.session_manager.process_with_ai = lambda: calls.append(1)
    app.set_next_prompt("   ")

    turns = app._drain_pending_prompts()

    assert turns == 0
    assert calls == []
    assert app.has_next_prompt() is False


def test_drain_stops_when_not_running(app):
    """No continuation turns after the session is stopped"""
    calls = []
    app.session_manager.process_with_ai = lambda: calls.append(1)
    app.is_running = False
    app.set_next_prompt("continue")

    turns = app._drain_pending_prompts()

    assert turns == 0
    assert calls == []


def test_recursion_error_is_reported_distinctly():
    """RecursionError must not hide behind the generic error path"""
    instance = AICoder()
    instance.plugin_system.call_hooks = MagicMock()

    with patch(
        "aicoder.core.aicoder.read_stdin_as_string", return_value="hello"
    ):
        with patch.object(instance.session_manager, "process_with_ai",
                          side_effect=RecursionError("too deep")):
            with patch.object(instance, "shutdown"):
                with patch("aicoder.core.aicoder.LogUtils") as mock_log:
                    instance.run_non_interactive()

    messages = " ".join(str(c.args[0]) for c in mock_log.error.call_args_list)
    assert "recursion limit" in messages
