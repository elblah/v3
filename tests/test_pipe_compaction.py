"""Auto-compaction in non-interactive (piped) mode.

The interactive loop ran a turn-boundary compaction check and the
before_user_prompt hook chain every turn. Piped mode did neither, so a long
piped session only hit the emergency force-compaction above 100% of the
context window and could otherwise grow until every API request failed.
"""

from unittest.mock import MagicMock, patch

import pytest

from aicoder.core.aicoder import AICoder


@pytest.fixture
def app():
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


def test_compaction_runs_before_first_piped_turn(app):
    """Over-threshold context must be compacted before the single pipe call"""
    order = []
    app.message_history.should_auto_compact = MagicMock(return_value=True)
    app.perform_auto_compaction = MagicMock(
        side_effect=lambda: order.append("compact")
    )
    app.session_manager.process_with_ai = lambda: order.append("api")

    _run_pipe(app)

    assert order == ["compact", "api"]


def test_no_compaction_under_threshold(app):
    """Below the threshold nothing is compacted"""
    app.message_history.should_auto_compact = MagicMock(return_value=False)
    app.perform_auto_compaction = MagicMock()
    app.session_manager.process_with_ai = lambda: None

    _run_pipe(app)

    app.perform_auto_compaction.assert_not_called()


def test_skip_once_flag_is_honoured(app):
    """The post-Ctrl+C skip flag suppresses exactly one check"""
    app.message_history.should_auto_compact = MagicMock(return_value=True)
    app.perform_auto_compaction = MagicMock()
    app._skip_auto_compact_once = True

    app._maybe_auto_compact()
    app.perform_auto_compaction.assert_not_called()
    assert app._skip_auto_compact_once is False

    app._maybe_auto_compact()
    app.perform_auto_compaction.assert_called_once()


def test_compaction_runs_between_continuation_turns(app):
    """Each drained turn gets the same pre-turn check as interactive mode"""
    order = []

    def process():
        order.append("api")
        if order.count("api") == 1:
            app.set_next_prompt("continue")

    app.message_history.should_auto_compact = MagicMock(return_value=True)
    app.perform_auto_compaction = MagicMock(
        side_effect=lambda: order.append("compact")
    )
    app.session_manager.process_with_ai = process

    _run_pipe(app)

    # Checked before the piped call and again before the drained turn.
    assert order == ["compact", "api", "compact", "api"]
    assert order.count("api") == 2


def test_pre_prompt_hooks_run_between_piped_turns(app):
    """Feeders registered on before_user_prompt must fire in pipe mode"""
    calls = []
    app.message_history.should_auto_compact = MagicMock(return_value=False)
    app.session_manager.process_with_ai = lambda: calls.append("api")
    app.set_next_prompt("first")

    def hooks(name, *args):
        if name == "before_user_prompt":
            calls.append("hook")

    app.plugin_system.call_hooks = MagicMock(side_effect=hooks)

    _run_pipe(app)

    assert calls.count("hook") >= 1
    assert calls.count("api") == 1


def test_hook_queued_prompt_is_processed_in_pipe_mode(app):
    """A feeder can turn the end of a piped turn into another turn"""
    calls = []
    state = {"turn_done": False, "fired": False}
    app.message_history.should_auto_compact = MagicMock(return_value=False)

    def process():
        calls.append("api")
        state["turn_done"] = True

    app.session_manager.process_with_ai = process

    def hooks(name, *args):
        # Ignore the startup feeder pass: only a real completed turn counts.
        if name == "before_user_prompt" and state["turn_done"] and not state["fired"]:
            state["fired"] = True
            app.set_next_prompt("cache_compact demand")

    app.plugin_system.call_hooks = MagicMock(side_effect=hooks)

    _run_pipe(app)

    assert calls == ["api", "api"]


def test_drain_bound_still_applies_with_hooks(app):
    """A feeder that always re-queues stays bounded"""
    calls = []
    app.message_history.should_auto_compact = MagicMock(return_value=False)
    app.session_manager.process_with_ai = lambda: calls.append("api")

    def hooks(name, *args):
        if name == "before_user_prompt":
            app.set_next_prompt("forever")

    app.plugin_system.call_hooks = MagicMock(side_effect=hooks)

    turns = app._drain_pending_prompts(max_turns=3)

    assert turns == 3
    assert len(calls) == 3
