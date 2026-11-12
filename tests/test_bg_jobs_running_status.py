"""Tests for the running-jobs snapshot bundled in every bg_jobs tool result.

Rationale: after a context compaction (or plain forgetfulness) the AI can
launch a duplicate build. Every bg_jobs action therefore reports the jobs
still running, so one call gives the whole picture.

Run: .venv/bin/python -m pytest tests/test_bg_jobs_running_status.py
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


SLEEPER = "import time; time.sleep(60)"


def make_env():
    old = os.environ.pop("BG_JOBS_NOTIFY", None)
    try:
        app = FakeApp()
        ctx = FakeCtx(app)
        bg_jobs.create_plugin(ctx)
    finally:
        if old is not None:
            os.environ["BG_JOBS_NOTIFY"] = old
    return app, ctx


def run_job(ctx, name):
    result = ctx.tools["bg_jobs"]({
        "action": "run",
        "name": name,
        "command": f"{sys.executable} -c '{SLEEPER}'",
        "notify": False,
    })
    m = _PID_RE.search(result["friendly"])
    if m is None:
        raise AssertionError(f"no pid in tool result: {result}")
    return int(m.group(1)), result


class RunningStatusTests(unittest.TestCase):
    def setUp(self):
        self.app, self.ctx = make_env()
        self.pids = []

    def tearDown(self):
        for pid in self.pids:
            self.ctx.tools["bg_jobs"]({"action": "kill", "pid": pid})

    def tool(self, **args):
        return self.ctx.tools["bg_jobs"](args)

    def test_run_reports_single_job(self):
        pid, result = run_job(self.ctx, "build")
        self.pids.append(pid)
        self.assertIn("— 1 running", result["friendly"])
        self.assertIn("Running now (1):", result["detailed"])
        self.assertIn("build", result["detailed"])
        self.assertIn(f"pid: {pid}", result["detailed"])

    def test_run_reports_preexisting_jobs(self):
        first, _ = run_job(self.ctx, "old-build")
        self.pids.append(first)
        second, result = run_job(self.ctx, "new-build")
        self.pids.append(second)
        self.assertIn("— 2 running", result["friendly"])
        self.assertIn("Running now (2):", result["detailed"])
        self.assertIn("old-build", result["detailed"])
        self.assertIn("new-build", result["detailed"])

    def test_detail_line_format(self):
        pid, result = run_job(self.ctx, "fmt")
        self.pids.append(pid)
        self.assertRegex(
            result["detailed"],
            r"\n1\) fmt\s+\(pid: \d+\) — running \d+s",
        )

    def test_kill_reports_remaining_jobs(self):
        keep, _ = run_job(self.ctx, "keep")
        doomed, _ = run_job(self.ctx, "doomed")
        self.pids.extend([keep, doomed])
        result = self.tool(action="kill", pid=doomed)
        self.assertIn("— 1 running", result["friendly"])
        block = result["detailed"].split("Running now", 1)[1]
        self.assertIn("keep", block)
        self.assertNotIn("doomed", block)

    def test_kill_last_job_reports_none(self):
        pid, _ = run_job(self.ctx, "solo")
        result = self.tool(action="kill", pid=pid)
        self.assertIn("— none running", result["friendly"])
        self.assertNotIn("Running now", result["detailed"])

    def test_wait_timeout_reports_all_running(self):
        waiter, _ = run_job(self.ctx, "waiter")
        other, _ = run_job(self.ctx, "other")
        self.pids.extend([waiter, other])
        result = self.tool(action="wait", pid=waiter, timeout=1)
        self.assertIn("still running", result["friendly"])
        self.assertIn("— 2 running", result["friendly"])
        self.assertIn("Running now (2):", result["detailed"])

    def test_wait_finished_reports_remaining(self):
        quick = self.tool(action="run", name="quick", command="true", notify=False)
        quick_pid = int(_PID_RE.search(quick["friendly"]).group(1))
        other, _ = run_job(self.ctx, "other")
        self.pids.append(other)
        result = self.tool(action="wait", pid=quick_pid, timeout=20)
        self.assertIn("finished", result["detailed"].lower())
        self.assertIn("— 1 running", result["friendly"])
        self.assertIn("other", result["detailed"])

    def test_history_empty_reports_running(self):
        pid, _ = run_job(self.ctx, "hist")
        self.pids.append(pid)
        result = self.tool(action="history")
        self.assertIn("— 1 running", result["friendly"])
        self.assertIn("Running now (1):", result["detailed"])

    def test_kill_all_reports_none_running(self):
        a, _ = run_job(self.ctx, "a")
        b, _ = run_job(self.ctx, "b")
        self.pids.extend([a, b])
        result = self.tool(action="kill_all")
        self.assertIn("Killed 2", result["friendly"])
        self.assertIn("— none running", result["friendly"])
        self.assertNotIn("Running now", result["detailed"])


if __name__ == "__main__":
    unittest.main()
