"""Tests for bg_jobs 'wait' action (blocking wait with required timeout).

Design (Sep 6 2026):
- wait blocks in-turn until the job exits, or until the required timeout
  expires. No default timeout: the AI always passes seconds explicitly.
- Timeout expiry = yield, not error and not kill: the job keeps running and
  the AI decides (wait again, keep working, kill it).
- Ctrl+C aborts only the wait (KeyboardInterrupt propagates); the job has
  its own process group and survives.
- The reaper may archive a dead job before/mid-wait, so results fall back
  to the completed_jobs history record.

Run: .venv/bin/python -m pytest tests/test_bg_jobs_wait.py
"""

import os
import re
import sys
import time
import unittest
from unittest import mock

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


def make_env(notify_env="1"):
    os.environ["BG_JOBS_NOTIFY"] = notify_env
    app = FakeApp()
    ctx = FakeCtx(app)
    bg_jobs.create_plugin(ctx)
    return app, ctx


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


def wait(ctx, pid, timeout):
    return ctx.tools["bg_jobs"]({"action": "wait", "pid": pid, "timeout": timeout})


def kill(ctx, pid):
    return ctx.tools["bg_jobs"]({"action": "kill", "pid": pid})


class WaitFinishedJobTests(unittest.TestCase):
    """Waiting on a job that already ended: read the history record."""

    def test_wait_on_archived_job_returns_record(self):
        _, ctx = make_env()
        pid = run_job(ctx, "quick", "exit 3")
        self.assertTrue(wait_all_dead(ctx))

        result = wait(ctx, pid, 5)
        self.assertIn("exited with code 3", result["friendly"])
        self.assertIn(f"pid {pid}", result["friendly"])
        self.assertIn("after ", result["friendly"])

    def test_wait_on_unknown_pid_errors(self):
        _, ctx = make_env()
        result = wait(ctx, 999999, 5)
        self.assertIn("Error", result["friendly"])
        self.assertIn("999999", result["friendly"])


class WaitRunningJobTests(unittest.TestCase):
    """Waiting on a live job: instant return on exit, yield on timeout."""

    def test_returns_when_job_exits(self):
        _, ctx = make_env()
        pid = run_job(ctx, "slowexit", "sleep 0.4; exit 3")

        started = time.time()
        result = wait(ctx, pid, 30)
        elapsed = time.time() - started

        self.assertIn("exited with code 3", result["friendly"])
        self.assertLess(elapsed, 10.0)

    def test_timeout_leaves_job_running(self):
        _, ctx = make_env()
        pid = run_job(ctx, "longjob", "sleep 30")

        started = time.time()
        result = wait(ctx, pid, 1)
        elapsed = time.time() - started

        self.assertIn("still running", result["friendly"])
        self.assertIn("job untouched", result["friendly"])
        self.assertGreaterEqual(elapsed, 0.9)

        # Job untouched: still listed as running
        listing = ctx.tools["bg_jobs"]({"action": "list"})
        self.assertIn("longjob", listing["friendly"] + listing["detailed"])

        kill(ctx, pid)

    def test_no_double_archive_after_wait(self):
        app, ctx = make_env()
        pid = run_job(ctx, "oncejob", "exit 0")
        result = wait(ctx, pid, 30)
        self.assertIn("finished", result["friendly"])

        history = ctx.tools["bg_jobs"]({"action": "history"})
        self.assertEqual(history["detailed"].count(f"pid: {pid}"), 1)

        # Exactly one completion nudge line for this pid
        ctx.hooks["on_context_bar"]()
        nudges = [
            m["content"] for m in app.message_history.messages
            if "<system-reminder>" in m.get("content", "")
        ]
        self.assertEqual(len(nudges), 1)
        self.assertEqual(nudges[0].count(f"oncejob (pid {pid})"), 1)

    def test_keyboard_interrupt_aborts_wait_only(self):
        _, ctx = make_env()
        pid = run_job(ctx, "survivor", "sleep 30")

        with mock.patch("time.sleep", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                wait(ctx, pid, 30)

        # Job survived the aborted wait
        listing = ctx.tools["bg_jobs"]({"action": "list"})
        self.assertIn("survivor", listing["friendly"] + listing["detailed"])
        history = ctx.tools["bg_jobs"]({"action": "history"})
        self.assertNotIn(f"pid: {pid}", history["detailed"])

        kill(ctx, pid)


class WaitTimeoutValidationTests(unittest.TestCase):
    """timeout is required and must be a positive integer."""

    def test_missing_timeout_errors(self):
        _, ctx = make_env()
        pid = run_job(ctx, "needsarg", "sleep 30")
        result = ctx.tools["bg_jobs"]({"action": "wait", "pid": pid})
        self.assertIn("Error", result["friendly"])
        self.assertIn("timeout", result["friendly"])
        kill(ctx, pid)

    def test_invalid_timeouts_error(self):
        _, ctx = make_env()
        for bad in (0, -5, "abc", 1.5):
            result = wait(ctx, 999999, bad)
            self.assertIn("Error", result["friendly"], f"bad timeout accepted: {bad}")

    def test_missing_pid_errors(self):
        _, ctx = make_env()
        result = ctx.tools["bg_jobs"]({"action": "wait", "timeout": 5})
        self.assertIn("Error", result["friendly"])
        self.assertIn("pid", result["friendly"])

    def test_wait_listed_in_schema(self):
        _, ctx = make_env()
        props = ctx.tool_defs["bg_jobs"]["parameters"]["properties"]
        self.assertIn("wait", props["action"]["enum"])
        self.assertIn("timeout", props)


if __name__ == "__main__":
    unittest.main()
