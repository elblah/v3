"""Tests for bg_jobs completion notification.

Design (Sep 6 2026):
- Jobs archived at exit get ONE batched <system-reminder> nudge at the next
  on_context_bar (safe turn-boundary injection point).
- ALWAYS-ON model: every non-killed job end notifies (crash or clean, short
  or long). bg_jobs is FOR background work, so any AI-chosen job end is
  significant; small tasks belong in run_shell_command. Kills are silent
  (the AI sees the 'killed' status in the kill tool result).
- Per-job `notify` param (default true) = AI opt-out. Global gate:
  BG_JOBS_NOTIFY (captured at create_plugin time, so env must be set BEFORE
  create_plugin). Default ON; BG_JOBS_NOTIFY=0 disables.

Run: .venv/bin/python -m pytest tests/test_bg_jobs_notify.py
"""

import os
import re
import sys
import time
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aicoder.plugins import bg_jobs


_PID_RE = re.compile(r"pid: (\d+)")


class FakeHistory:
    def __init__(self):
        self.messages = []

    def get_messages(self):
        return self.messages

    def add_user_message(self, content):
        self.messages.append({"role": "user", "content": content})

    def set_messages(self, msgs):
        self.messages = list(msgs)


class FakeApp:
    def __init__(self):
        self.message_history = FakeHistory()


class FakeCtx:
    def __init__(self, app):
        self.app = app
        self.hooks = {}
        self.commands = {}
        self.tools = {}
        self.tool_defs = {}

    def register_hook(self, name, fn):
        self.hooks[name] = fn

    def register_command(self, name, fn, description=None):
        self.commands[name] = fn

    def register_tool(self, name, fn, **kwargs):
        self.tools[name] = fn
        self.tool_defs[name] = kwargs


def make_env(notify_env):
    os.environ["BG_JOBS_NOTIFY"] = notify_env
    app = FakeApp()
    ctx = FakeCtx(app)
    bg_jobs.create_plugin(ctx)
    return app, ctx


def make_env_unset():
    """Create plugin with BG_JOBS_NOTIFY unset (tests default-on gate)."""
    old = os.environ.pop("BG_JOBS_NOTIFY", None)
    try:
        app = FakeApp()
        ctx = FakeCtx(app)
        bg_jobs.create_plugin(ctx)
    finally:
        if old is not None:
            os.environ["BG_JOBS_NOTIFY"] = old
    return app, ctx


def nudge_count(app):
    return sum(
        1 for m in app.message_history.messages
        if "<system-reminder>" in m.get("content", "")
    )


def run_job(ctx, name, command, notify=None):
    args = {"action": "run", "name": name, "command": command}
    if notify is not None:
        args["notify"] = notify
    result = ctx.tools["bg_jobs"](args)
    m = _PID_RE.search(result["friendly"])
    if m is None:
        raise AssertionError(f"no pid in tool result: {result}")
    return int(m.group(1))


def wait_all_dead(ctx, timeout=10.0):
    """Poll bg_jobs list until cleanup_dead_jobs has archived everything."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        result = ctx.tools["bg_jobs"]({"action": "list"})
        if "No background jobs running" in result["friendly"]:
            return True
        time.sleep(0.1)
    return False


class ShouldNotifyTests(unittest.TestCase):
    """Pure predicate logic (no subprocesses)."""

    def test_default_notifies(self):
        self.assertTrue(bg_jobs._should_notify())

    def test_killed_always_silent(self):
        self.assertFalse(bg_jobs._should_notify(killed=True))

    def test_notify_flag_off_silent(self):
        self.assertFalse(bg_jobs._should_notify(notify=False))


class NudgeInjectionTests(unittest.TestCase):
    """End-to-end: real subprocess jobs, one batched nudge at context bar."""

    def test_crash_nudge_delivered(self):
        app, ctx = make_env("1")
        run_job(ctx, "webserver", "exit 4")
        self.assertTrue(wait_all_dead(ctx))
        ctx.hooks["on_context_bar"]()
        content = app.message_history.messages[-1]["content"]
        self.assertTrue(content.startswith("<system-reminder>"))
        self.assertIn("[NUDGE:BG_JOBS]", content)
        self.assertIn("webserver (pid", content)
        self.assertIn("exited with code 4", content)
        self.assertIn("after ", content)
        self.assertEqual(nudge_count(app), 1)
        # dedup: nothing new archived since last bar -> no second nudge
        ctx.hooks["on_context_bar"]()
        self.assertEqual(nudge_count(app), 1)

    def test_clean_short_nudge_delivered(self):
        """No duration/exit-code filter: quick clean job still notifies."""
        app, ctx = make_env("1")
        run_job(ctx, "quick", "echo hi && true")
        self.assertTrue(wait_all_dead(ctx))
        ctx.hooks["on_context_bar"]()
        self.assertEqual(nudge_count(app), 1)
        content = app.message_history.messages[-1]["content"]
        self.assertIn("[NUDGE:BG_JOBS]", content)
        self.assertIn("quick (pid", content)
        self.assertIn("finished", content)

    def test_batch_single_reminder(self):
        app, ctx = make_env("1")
        run_job(ctx, "batch-a", "exit 3")
        run_job(ctx, "batch-b", "exit 5")
        self.assertTrue(wait_all_dead(ctx))
        ctx.hooks["on_context_bar"]()
        self.assertEqual(nudge_count(app), 1)
        content = app.message_history.messages[-1]["content"]
        self.assertIn("batch-a (pid", content)
        self.assertIn("batch-b (pid", content)
        self.assertIn("exited with code 3", content)
        self.assertIn("exited with code 5", content)

    def test_env_off_no_nudge(self):
        app, ctx = make_env("0")
        run_job(ctx, "server", "exit 3")
        self.assertTrue(wait_all_dead(ctx))
        ctx.hooks["on_context_bar"]()
        self.assertEqual(nudge_count(app), 0)
        ctx.hooks["on_context_bar"]()  # pending drained, still nothing
        self.assertEqual(nudge_count(app), 0)

    def test_env_unset_defaults_on(self):
        app, ctx = make_env_unset()
        run_job(ctx, "server", "exit 3")
        self.assertTrue(wait_all_dead(ctx))
        ctx.hooks["on_context_bar"]()
        self.assertEqual(nudge_count(app), 1)

    def test_notify_false_job_silent(self):
        app, ctx = make_env("1")
        run_job(ctx, "quiet", "exit 2", notify=False)
        self.assertTrue(wait_all_dead(ctx))
        ctx.hooks["on_context_bar"]()
        self.assertEqual(nudge_count(app), 0)

    def test_kill_silent(self):
        app, ctx = make_env("1")
        pid = run_job(ctx, "longjob", "sleep 30")
        result = ctx.tools["bg_jobs"]({"action": "kill", "pid": pid})
        # kill status returned IN the tool result (no nudge needed)
        self.assertIn("Killed background job", result["friendly"])
        result = ctx.tools["bg_jobs"]({"action": "list"})
        self.assertIn("No background jobs", result["friendly"])
        ctx.hooks["on_context_bar"]()
        self.assertEqual(nudge_count(app), 0)


class ToolSchemaTests(unittest.TestCase):
    """Tool schema adapts to the gate: notify param only when enabled."""

    def test_notify_param_present_when_enabled(self):
        app, ctx = make_env("1")
        props = ctx.tool_defs["bg_jobs"]["parameters"]["properties"]
        self.assertIn("notify", props)
        self.assertNotIn(
            "Completion notifications are disabled",
            ctx.tool_defs["bg_jobs"]["description"],
        )

    def test_notify_param_absent_when_disabled(self):
        app, ctx = make_env("0")
        props = ctx.tool_defs["bg_jobs"]["parameters"]["properties"]
        self.assertNotIn("notify", props)
        self.assertIn(
            "Completion notifications are disabled",
            ctx.tool_defs["bg_jobs"]["description"],
        )


if __name__ == "__main__":
    unittest.main()