"""
Hook-contract tests for empty_retry.handle_empty.

User directive: plugins stay self-contained — empty_retry only cares about
empty replies, but it FIRES on_empty_assistant_message (with the reasoning
kwargs it received) so other plugins can listen and act. A truthy hook
result means another plugin took over the retry decision -> retry DIRECTLY
without adding the nudge message (mirrors the dedup path). Falsy or absent
results -> normal retry_msg returned.

Why it matters (live bug): a nudge user-message inserted between the tool
pairs and a retried [COMPACT_SUMMARY:TOOLS] tag reply breaks tools_compact's
backward scan (it stops at real user content) -> consume silently never
runs -> tool loop dies at the prompt.

Run: python3 tests/test_empty_retry_hooks.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["AICODER_EMPTY_RETRY_DELAY"] = "1"  # min clamp anyway; keep fast

from aicoder.plugins import empty_retry
from aicoder.plugins.empty_retry import EmptyRetryService


class FakeSessionManager:
    def __init__(self):
        self._retry_empty_content = False


class FakeMessageHistory:
    def __init__(self, msgs):
        self.messages = msgs


class FakePluginSystem:
    def __init__(self, results):
        self._results = results
        self.calls = []

    def call_hooks(self, name, **kwargs):
        self.calls.append((name, kwargs))
        return self._results


class FakeApp:
    def __init__(self, results, msgs):
        self.plugin_system = FakePluginSystem(results)
        self.message_history = FakeMessageHistory(msgs)
        self.session_manager = FakeSessionManager()

    def has_next_prompt(self):
        return False


class FakeCtx:
    def __init__(self, app):
        self.app = app
        self.hooks = {}
        self.commands = {}

    def register_hook(self, name, fn):
        self.hooks[name] = fn

    def register_command(self, name, fn, description=None):
        self.commands[name] = fn


def make_env(hook_results, msgs=None):
    app = FakeApp(hook_results, msgs if msgs is not None else [])
    ctx = FakeCtx(app)
    empty_retry.create_plugin(ctx)
    cmd = empty_retry.EmptyRetryCommand(ctx)
    return app, ctx, cmd


class EmptyRetryHookTests(unittest.TestCase):
    def setUp(self):
        EmptyRetryService.set_enabled(True)
        EmptyRetryService.set_delay(1)
        EmptyRetryService.reset_retry()
        EmptyRetryService.set_custom_message(None)
        EmptyRetryService.set_env_message(None)

    def test_truthy_hook_result_direct_retry_no_nudge(self):
        """Plugin took over -> handle_empty returns None (no history add),
        _retry_empty_content flag set -> session manager retries directly."""
        app, ctx, cmd = make_env([True], msgs=[{"role": "assistant", "content": "x"}])
        msgs = app.message_history.messages
        n_before = len(msgs)

        result = cmd.handle_empty(reasoning_content="thinking\n[COMPACT_SUMMARY:TOOLS]")

        self.assertIsNone(result)
        self.assertTrue(app.session_manager._retry_empty_content)
        self.assertEqual(len(msgs), n_before)  # no nudge message appended

    def test_falsy_hook_result_normal_retry_msg(self):
        """No plugin took over -> retry_msg returned (nudge added by caller)."""
        app, ctx, cmd = make_env([None])
        result = cmd.handle_empty(reasoning_content="plain thinking")
        self.assertEqual(result, EmptyRetryService.get_message())
        self.assertFalse(app.session_manager._retry_empty_content)

    def test_no_hooks_registered_normal_retry_msg(self):
        """Empty hook list (no listeners) -> normal retry, no flag."""
        app, ctx, cmd = make_env([])
        result = cmd.handle_empty(reasoning_content=None)
        self.assertEqual(result, EmptyRetryService.get_message())
        self.assertFalse(app.session_manager._retry_empty_content)

    def test_hook_receives_reasoning_kwargs(self):
        """The reasoning kwargs the session manager passed in are forwarded
        verbatim to on_empty_assistant_message."""
        app, ctx, cmd = make_env([None])
        cmd.handle_empty(
            reasoning_content="rc",
            reasoning_field="rf",
            thinking_signature="sig",
        )
        name, kwargs = app.plugin_system.calls[-1]
        self.assertEqual(name, "on_empty_assistant_message")
        self.assertEqual(kwargs["reasoning_content"], "rc")
        self.assertEqual(kwargs["reasoning_field"], "rf")
        self.assertEqual(kwargs["thinking_signature"], "sig")

    def test_any_truthy_result_takes_over(self):
        """Mixed results, one truthy -> takeover."""
        app, ctx, cmd = make_env([None, True, None])
        result = cmd.handle_empty(reasoning_content="")
        self.assertIsNone(result)
        self.assertTrue(app.session_manager._retry_empty_content)

    def test_direct_retry_still_honors_dedup_first(self):
        """Existing dedup path (last msg already nudged) unaffected by hooks:
        direct retry, no second nudge."""
        msg = EmptyRetryService.get_message()
        app, ctx, cmd = make_env([None],
                                 msgs=[{"role": "user", "content": msg}])
        result = cmd.handle_empty(reasoning_content="")
        self.assertIsNone(result)
        self.assertTrue(app.session_manager._retry_empty_content)
        self.assertEqual(len(app.message_history.messages), 1)


if __name__ == "__main__":
    unittest.main(verbosity=2)
