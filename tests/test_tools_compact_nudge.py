"""
Focused tests for the tools_compact nudge path.
Kept in cwd (not /tmp) — /tmp is sandbox-wiped between sessions.

Nudge semantics (hard demand): ONE <system-reminder> per loop cycle, fired
when LOOP COST (live tool pairs since the AI last finished its turn), NOT
total prompt size, reaches TOOLS_COMPACT_LOOP_PCT % of the context budget.
nudge_fired resets when the AI finishes its turn (after_ai_processing(False))
and after tag consumption — a fresh loop may warrant a new demand. User
messages deliberately do NOT reset: a Ctrl+C interrupt followed by a new
instruction must not destroy the accumulated loop budget. Text is imperative
("THIS IS MANDATORY"); no light/optional nudges exist anymore.

Default test env: TOOLS_COMPACT_LOOP_PCT=2 -> threshold = 200 tokens at
10000; LOOP_PCT=1 -> threshold = 100 tokens.

Token math: empty-content parent = 1 token; TOOL_MSG ("x"*200) = 50 tokens
-> pair = 51; LONG_CONTENT ("y"*400) = 100 tokens.

IMPORTANT: env must be set BEFORE creating the plugin (cfg is captured at
create_plugin time).

Run: python3 tests/test_tools_compact_nudge.py
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ["CONTEXT_SIZE"] = "10000"          # before aicoder imports
os.environ["TOOLS_COMPACT_LOOP_PCT"] = "2"
os.environ["TOOLS_COMPACT_ENABLED"] = "1"
os.environ["TOOLS_COMPACT_DEBUG"] = "1"

from aicoder.plugins import tools_compact


class FakeStats:
    current_prompt_size = 0


class FakeHistory:
    def __init__(self, msgs):
        self._msgs = list(msgs)

    def get_messages(self):
        return self._msgs

    def add_user_message(self, content):
        self._msgs.append({"role": "user", "content": content})

    def set_messages(self, msgs):
        self._msgs = list(msgs)

    def replace_messages(self, msgs):
        self._msgs = msgs

    def increment_compaction_count(self):
        pass


class FakeApp:
    def __init__(self, msgs):
        self.stats = FakeStats()
        self.message_history = FakeHistory(msgs)

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


ASSISTANT_PARENT = {
    "role": "assistant",
    "tool_calls": [{"id": "call_1", "name": "fake", "arguments": "{}"}],
}
OPEN_CHAIN = {
    "role": "assistant",
    "tool_calls": [{"id": "call_2", "name": "fake", "arguments": "{}"}],
}
TOOL_MSG = {"role": "tool", "tool_call_id": "call_1", "content": "x" * 200}
PLAIN_REPLY = {"role": "assistant", "content": "done"}
TAG_REPLY = {"role": "assistant", "content": "[COMPACT_SUMMARY:TOOLS]\nsummary"}
USER_MSG = {"role": "user", "content": "keep going"}
LONG_CONTENT = "y" * 400  # 100 tokens


def make_env(msgs, prompt_size):
    app = FakeApp(msgs)
    ctx = FakeCtx(app)
    plugin = tools_compact.create_plugin(ctx)
    app.stats.current_prompt_size = prompt_size
    return app, ctx, plugin


def new_pair(call_id, content):
    """Fresh assistant parent + tool result for call_id (distinct ids so the
    loop-cost parent counter counts it)."""
    parent = {
        "role": "assistant",
        "tool_calls": [{"id": call_id, "name": "fake", "arguments": "{}"}],
    }
    result = {"role": "tool", "tool_call_id": call_id, "content": content}
    return parent, result


class NudgeTests(unittest.TestCase):
    def setUp(self):
        # Under pytest, conftest imports aicoder modules before this file's
        # env block runs -> Config._context_size frozen at the DEFAULT. Force
        # the test value here so the file passes under BOTH runners.
        from aicoder.core.config import Config

        self._saved_ctx_size = Config.context_size()
        Config.set_context_size(10000)

    def tearDown(self):
        from aicoder.core.config import Config

        Config.set_context_size(self._saved_ctx_size)

    def _last_content(self, msgs):
        return msgs[-1].get("content", "")

    def test_nudge_fires_once_at_threshold(self):
        """Loop cost reaching the 200-token threshold (2% of 10000) -> ONE
        hard demand; further growth -> no refire within the same cycle."""
        app, ctx, _ = make_env([ASSISTANT_PARENT, TOOL_MSG], 2000)
        fire = ctx.hooks["after_tool_results_added"]

        big = dict(TOOL_MSG, content=LONG_CONTENT)
        app.message_history._msgs.append(big)
        fire(big)  # loop 151 -> below threshold (200), no nudge
        self.assertEqual(len(app.message_history._msgs), 3)
        self.assertNotIn("system-reminder", self._last_content(app.message_history._msgs))

        big2 = dict(TOOL_MSG, content=LONG_CONTENT)
        app.message_history._msgs.append(big2)
        fire(big2)  # loop 251 -> threshold reached -> nudge
        self.assertEqual(len(app.message_history._msgs), 5)
        self.assertIn("<system-reminder>", self._last_content(app.message_history._msgs))
        self.assertIn("[NUDGE:COMPACTION]", self._last_content(app.message_history._msgs))

        app.message_history._msgs.append(TOOL_MSG)
        fire(TOOL_MSG)  # loop 302 -> same cycle -> no repeat, but the result
        # lands after the nudge and its parent is before it -> the nudge is
        # RELOCATED to the tail (it must never split a parent's result chain)
        self.assertEqual(len(app.message_history._msgs), 6)
        nudges = [m for m in app.message_history._msgs
                  if "system-reminder" in m.get("content", "")]
        self.assertEqual(len(nudges), 1)  # relocated, not re-fired
        self.assertIn("system-reminder", self._last_content(app.message_history._msgs))
        # no user message between the parent and any of its results
        for m in app.message_history._msgs[1:5]:
            self.assertNotIn("system-reminder", m.get("content", ""))

    def test_nudge_text_is_hard_mandatory(self):
        """The demand is imperative, states the exact cost, and forbids
        continuing without compacting — no optional/conditional wording."""
        os.environ["TOOLS_COMPACT_LOOP_PCT"] = "1"  # threshold = 100 tokens
        app, ctx, _ = make_env([ASSISTANT_PARENT, TOOL_MSG], 2000)
        big = dict(TOOL_MSG, content=LONG_CONTENT)
        app.message_history._msgs.append(big)
        ctx.hooks["after_tool_results_added"](big)  # loop 101 -> nudge
        content = self._last_content(app.message_history._msgs)
        self.assertIn("TOOLS COMPACTION REQUIRED NOW", content)
        self.assertIn("THIS IS MANDATORY", content)
        self.assertIn("do not continue working without compacting it", content)
        self.assertIn("has consumed 101 tokens", content)
        self.assertIn("10000-token context window", content)
        self.assertNotIn("you may", content)
        self.assertNotIn("If you are done", content)

    def test_user_message_does_not_reset_loop_cycle(self):
        """A real user message does NOT reset the cycle (Ctrl+C interrupt +
        new instruction must not destroy the accumulated budget); only the AI
        finishing its turn does. First nudge -> user msg -> more loop -> no
        refire; after_ai_processing(False) -> fresh cycle fires again."""
        os.environ["TOOLS_COMPACT_LOOP_PCT"] = "1"  # threshold = 100 tokens
        try:
            app, ctx, _ = make_env([ASSISTANT_PARENT, TOOL_MSG], 2000)
            fire = ctx.hooks["after_tool_results_added"]

            big = dict(TOOL_MSG, content=LONG_CONTENT)
            app.message_history._msgs.append(big)
            fire(big)  # loop 101 -> first nudge
            self.assertIn("system-reminder",
                          self._last_content(app.message_history._msgs))

            app.message_history._msgs.append(USER_MSG)
            parent, result = new_pair("call_3", TOOL_MSG["content"])  # 51 tokens
            app.message_history._msgs.append(parent)
            app.message_history._msgs.append(result)
            fire(result)  # loop 152 -> same cycle, user msg must NOT reset
            nudges = [m for m in app.message_history._msgs
                      if "system-reminder" in m.get("content", "")]
            self.assertEqual(len(nudges), 1)  # still the first-cycle nudge

            ctx.hooks["after_ai_processing"](False)  # AI finished -> reset
            parent, result = new_pair("call_4", LONG_CONTENT)  # 101 tokens
            app.message_history._msgs.append(parent)
            app.message_history._msgs.append(result)
            fire(result)  # fresh loop 101 -> second nudge
            nudges = [m for m in app.message_history._msgs
                      if "system-reminder" in m.get("content", "")]
            self.assertEqual(len(nudges), 2)
        finally:
            os.environ["TOOLS_COMPACT_LOOP_PCT"] = "2"

    def test_after_ai_processing_with_tool_calls_does_not_reset(self):
        """after_ai_processing(True) (AI kept working, made tool calls) is
        NOT a turn boundary — the loop budget and nudge_fired survive."""
        os.environ["TOOLS_COMPACT_LOOP_PCT"] = "1"  # threshold = 100 tokens
        try:
            app, ctx, _ = make_env([ASSISTANT_PARENT, TOOL_MSG], 2000)
            fire = ctx.hooks["after_tool_results_added"]

            big = dict(TOOL_MSG, content=LONG_CONTENT)
            app.message_history._msgs.append(big)
            fire(big)  # loop 101 -> first nudge
            self.assertIn("system-reminder",
                          self._last_content(app.message_history._msgs))

            ctx.hooks["after_ai_processing"](True)  # AI continued with tools
            parent, result = new_pair("call_3", TOOL_MSG["content"])  # 51 tokens
            app.message_history._msgs.append(parent)
            app.message_history._msgs.append(result)
            fire(result)  # loop 152 -> same cycle, no refire
            nudges = [m for m in app.message_history._msgs
                      if "system-reminder" in m.get("content", "")]
            self.assertEqual(len(nudges), 1)
        finally:
            os.environ["TOOLS_COMPACT_LOOP_PCT"] = "2"

    def test_late_result_relocates_nudge_to_tail(self):
        """Regression (provider 400): parent with 2 parallel calls, first
        result (cancelled) arrives, second result crosses the threshold and
        gets the nudge appended after it, then the LATE second result of the
        cancelled call lands AFTER the nudge — nudge would sit between the
        parent and its result. Must be relocated to the tail; repeated late
        results re-relocate it. Loop cost keeps accumulating. (The initial
        r_cancelled is never fired, so the crossing pair alone is 101 tokens.)"""
        os.environ["TOOLS_COMPACT_LOOP_PCT"] = "1"  # threshold = 100 tokens
        os.environ["TOOLS_COMPACT_SHOW_BUDGET"] = "1"
        try:
            parent = {
                "role": "assistant",
                "tool_calls": [
                    {"id": "call_a", "name": "fake", "arguments": "{}"},
                    {"id": "call_b", "name": "fake", "arguments": "{}"},
                ],
            }
            r_cancelled = {"role": "tool", "tool_call_id": "call_a",
                           "content": "x" * 200}  # 50 tokens
            r_crossing = {"role": "tool", "tool_call_id": "call_b",
                          "content": LONG_CONTENT}  # 100 tokens
            app, ctx, _ = make_env([parent, r_cancelled], 2000)
            fire = ctx.hooks["after_tool_results_added"]

            app.message_history._msgs.append(r_crossing)
            fire(r_crossing)  # loop 101 -> threshold -> nudge at tail
            msgs = app.message_history._msgs
            self.assertEqual(len(msgs), 4)
            self.assertIn("TOOLS COMPACTION REQUIRED NOW",
                          self._last_content(msgs))

            # LATE second result of the cancelled call lands after the nudge
            r_late = {"role": "tool", "tool_call_id": "call_a",
                      "content": "z" * 200}  # 50 tokens
            app.message_history._msgs.append(r_late)
            fire(r_late)
            msgs = app.message_history._msgs
            self.assertEqual(len(msgs), 5)
            self.assertEqual([m.get("role") for m in msgs],
                             ["assistant", "tool", "tool", "tool", "user"])
            self.assertIn("TOOLS COMPACTION REQUIRED NOW",
                          self._last_content(msgs))
            # no user message between the parent and any of its results
            self.assertNotIn("system-reminder",
                             msgs[1].get("content", ""))
            self.assertNotIn("system-reminder",
                             msgs[2].get("content", ""))
            self.assertNotIn("system-reminder",
                             msgs[3].get("content", ""))
            # loop cost keeps counting the late result
            self.assertIn("lb:151", ctx.hooks["on_context_bar"]())

            # a second late result re-relocates the nudge again
            r_late2 = {"role": "tool", "tool_call_id": "call_b",
                       "content": "w" * 200}  # 50 tokens
            app.message_history._msgs.append(r_late2)
            fire(r_late2)
            msgs = app.message_history._msgs
            self.assertEqual([m.get("role") for m in msgs],
                             ["assistant", "tool", "tool", "tool", "tool",
                              "user"])
            self.assertIn("TOOLS COMPACTION REQUIRED NOW",
                          self._last_content(msgs))
            self.assertIn("lb:201", ctx.hooks["on_context_bar"]())
        finally:
            os.environ["TOOLS_COMPACT_LOOP_PCT"] = "2"
            os.environ.pop("TOOLS_COMPACT_SHOW_BUDGET", None)

    def test_loop_band_uses_loop_cost_not_prompt_size(self):
        """Regression: huge prompt (50% of budget) with a tiny loop -> NO
        nudge. The trigger is loop cost, not total prompt size."""
        os.environ["TOOLS_COMPACT_LOOP_PCT"] = "2"  # self-contained: threshold 200
        app, ctx, _ = make_env([ASSISTANT_PARENT, TOOL_MSG], 50000)
        big = dict(TOOL_MSG, content=LONG_CONTENT)
        app.message_history._msgs.append(big)
        ctx.hooks["after_tool_results_added"](big)  # loop 101 -> below 200
        self.assertEqual(len(app.message_history._msgs), 3)
        self.assertNotIn("system-reminder", self._last_content(app.message_history._msgs))

    def test_nudge_disabled_when_master_off(self):
        """TOOLS_COMPACT_ENABLED != '1' -> create_plugin returns None, nothing
        registered (no hooks, no /toolcompact command), history untouched."""
        os.environ["TOOLS_COMPACT_ENABLED"] = "0"
        try:
            os.environ["TOOLS_COMPACT_LOOP_PCT"] = "1"  # threshold = 100 tokens
            app, ctx, plugin = make_env([ASSISTANT_PARENT, TOOL_MSG], 2000)
            self.assertIsNone(plugin)
            self.assertEqual(ctx.hooks, {})
            self.assertNotIn("toolcompact", ctx.commands)
            self.assertEqual(len(app.message_history._msgs), 2)
        finally:
            os.environ["TOOLS_COMPACT_ENABLED"] = "1"
            os.environ["TOOLS_COMPACT_LOOP_PCT"] = "2"

    def test_no_nudge_when_result_not_at_tail(self):
        """Result inserted mid-history (open chain after it) -> nudge NOT
        injected: it would sit between the open chain and its pending results."""
        os.environ["TOOLS_COMPACT_LOOP_PCT"] = "1"  # threshold = 100 tokens
        try:
            app, ctx, _ = make_env([ASSISTANT_PARENT, TOOL_MSG, OPEN_CHAIN], 2000)
            big = dict(TOOL_MSG, content=LONG_CONTENT)
            ctx.hooks["after_tool_results_added"](big)  # loop 101 -> threshold, blocked
            self.assertEqual(len(app.message_history._msgs), 3)
            self.assertNotIn("system-reminder", self._last_content(app.message_history._msgs))
        finally:
            os.environ["TOOLS_COMPACT_LOOP_PCT"] = "2"

    def test_deferred_nudge_delivered_on_next_plain_reply(self):
        """Blocked nudge is deferred, not dropped: delivered when the next
        completed assistant reply lands at the tail."""
        os.environ["TOOLS_COMPACT_LOOP_PCT"] = "1"  # threshold = 100 tokens
        try:
            app, ctx, _ = make_env([ASSISTANT_PARENT, TOOL_MSG, OPEN_CHAIN], 2000)
            big = dict(TOOL_MSG, content=LONG_CONTENT)
            ctx.hooks["after_tool_results_added"](big)  # loop 101 -> threshold, blocked
            self.assertEqual(len(app.message_history._msgs), 3)  # blocked

            app.message_history._msgs.append(PLAIN_REPLY)
            ctx.hooks["after_assistant_message_added"](PLAIN_REPLY)
            self.assertEqual(len(app.message_history._msgs), 5)  # +plain reply +nudge
            self.assertIn("<system-reminder>", self._last_content(app.message_history._msgs))
            self.assertIn("TOOLS COMPACTION REQUIRED NOW",
                          self._last_content(app.message_history._msgs))
        finally:
            os.environ["TOOLS_COMPACT_LOOP_PCT"] = "2"

    def test_quoted_tag_reply_does_not_consume(self):
        """Aug 8 dogfood regression: the AI quoted the tag in backticks at
        line start while explaining the mechanism. Markdown wrappers are
        byte-identical to a quoted tag, so the detection is whitespace-only
        prefix — a quoted tag must NOT consume the loop."""
        os.environ["TOOLS_COMPACT_LOOP_PCT"] = "1"  # threshold = 100 tokens
        quoted = dict(PLAIN_REPLY, content="`[COMPACT_SUMMARY:TOOLS]` is for tool loops")
        app, ctx, _ = make_env([ASSISTANT_PARENT, TOOL_MSG, OPEN_CHAIN, quoted], 2000)
        big = dict(TOOL_MSG, content=LONG_CONTENT)
        ctx.hooks["after_tool_results_added"](big)  # loop 101 -> threshold, blocked
        ctx.hooks["after_assistant_message_added"](quoted)
        msgs = app.message_history._msgs
        # loop untouched: parent + tool + chain + quoted reply + nudge = 5
        self.assertEqual(len(msgs), 5)
        self.assertEqual(msgs[3], quoted)

    def test_pending_nudge_superseded_by_tag_compaction(self):
        """A tag reply clears the deferred nudge and compacts normally —
        the nudge must not land after the kept summary."""
        os.environ["TOOLS_COMPACT_LOOP_PCT"] = "1"  # threshold = 100 tokens
        app, ctx, _ = make_env([ASSISTANT_PARENT, TOOL_MSG, OPEN_CHAIN, TAG_REPLY], 2000)
        big = dict(TOOL_MSG, content=LONG_CONTENT)
        ctx.hooks["after_tool_results_added"](big)  # loop 101 -> threshold, blocked
        ctx.hooks["after_assistant_message_added"](TAG_REPLY)
        msgs = app.message_history._msgs
        self.assertEqual(len(msgs), 1)  # pairs consumed, summary kept
        self.assertNotIn("system-reminder", msgs[0].get("content", ""))

    def test_tag_reply_with_tool_calls_consumes_immediately(self):
        """Live bug: the AI writes the tag AND continues with tool calls in
        one reply. The old deferral waited for a plain reply that never came
        -> consume never ran and context kept growing. Now the pairs are
        consumed right away; the reply's own results append after the kept
        summary, and no "Continue." is injected (the native loop already
        continues — after_ai_processing(True) eats the armed flag)."""
        os.environ["TOOLS_COMPACT_LOOP_PCT"] = "1"  # threshold = 100 tokens
        tag_tool_reply = {
            "role": "assistant",
            "content": "[COMPACT_SUMMARY:TOOLS]\nsummary",
            "tool_calls": [{"id": "call_3", "name": "fake", "arguments": "{}"}],
        }
        parent2, result2 = new_pair("call_2", TOOL_MSG["content"])
        app, ctx, _ = make_env(
            [ASSISTANT_PARENT, TOOL_MSG, parent2, result2], 2000
        )
        app.message_history._msgs.append(tag_tool_reply)
        ctx.hooks["after_assistant_message_added"](tag_tool_reply)
        msgs = app.message_history._msgs
        self.assertEqual(len(msgs), 1)  # both pairs consumed, summary kept
        self.assertEqual(msgs[0]["content"], tag_tool_reply["content"])

        # the reply's own pending results land after the kept summary
        result3 = {"role": "tool", "tool_call_id": "call_3", "content": "x" * 50}
        msgs.append(result3)
        self.assertEqual(msgs[1], result3)

        # armed continuation is eaten by the tool_calls processing hook —
        # no stray "Continue." when the turn later ends
        self.assertIsNone(ctx.hooks["after_ai_processing"](True))
        self.assertIsNone(ctx.hooks["after_ai_processing"](False))

    def test_two_cycle_consume_keeps_previous_summary(self):
        """A second [COMPACT_SUMMARY:TOOLS] reply must only consume the loop
        since the previous summary. The first summary often carries its own
        tool_calls (the AI continues working after the tag) — the scan must
        treat it as a boundary, not as a pair parent, or cycle 2 silently
        drops summary1 and its tool results from history."""
        p1, r1 = new_pair("call_1", TOOL_MSG["content"])
        p2, r2 = new_pair("call_2", TOOL_MSG["content"])
        app, ctx, _ = make_env([USER_MSG, p1, r1, p2, r2], 2000)
        h = app.message_history._msgs

        # cycle 1: tag reply + own tool_calls -> consume the first loop
        s1 = dict(
            TAG_REPLY,
            content="[COMPACT_SUMMARY:TOOLS]\nsummary ONE",
            tool_calls=[{"id": "call_3", "name": "fake", "arguments": "{}"}],
        )
        h.append(s1)
        ctx.hooks["after_assistant_message_added"](s1)
        h = app.message_history._msgs
        self.assertEqual(len(h), 2)  # USER_MSG + s1
        r3 = {"role": "tool", "tool_call_id": "call_3", "content": "x" * 50}
        ctx.hooks["after_tool_results_added"](r3)
        h.append(r3)

        # cycle 2: more loop work, then another tag reply with tool_calls
        p4, r4 = new_pair("call_4", TOOL_MSG["content"])
        p5, r5 = new_pair("call_5", TOOL_MSG["content"])
        for m in (p4, r4, p5, r5):
            h.append(m)
        s2 = dict(
            TAG_REPLY,
            content="[COMPACT_SUMMARY:TOOLS]\nsummary TWO",
            tool_calls=[{"id": "call_6", "name": "fake", "arguments": "{}"}],
        )
        h.append(s2)
        ctx.hooks["after_assistant_message_added"](s2)
        msgs = app.message_history._msgs

        contents = [m.get("content", "") for m in msgs]
        self.assertIn("[COMPACT_SUMMARY:TOOLS]\nsummary ONE", contents)  # survives
        self.assertIn("[COMPACT_SUMMARY:TOOLS]\nsummary TWO", contents)
        self.assertIn(r3, msgs)                  # its tool result survives (no orphan)
        self.assertNotIn(r4, msgs)               # only loop-2 pairs consumed
        self.assertNotIn(p4, msgs)
        # no dangling parent: every kept tool result has its parent in history
        kept_ids = {
            tc.get("id")
            for m in msgs
            if m.get("role") == "assistant"
            for tc in (m.get("tool_calls") or [])
        }
        for m in msgs:
            if m.get("role") == "tool":
                self.assertIn(m["tool_call_id"], kept_ids)

    def test_reasoning_only_tag_promoted_and_consumed(self):
        """Some models write the tag+summary into reasoning_content while the
        visible reply misses the tag. Without a fix: no consume, no re-nudge
        (once-per-cycle), loop survives -> next request repeats it (wasted
        turn). Now the hook promotes the reasoning summary into the visible
        content and consumes on the SAME message. The full promoted summary
        must be PRINTED (user can't see the reasoning with show-reasoning
        off) and the accept log must say it came from the reasoning field."""
        import contextlib
        import io

        os.environ["TOOLS_COMPACT_LOOP_PCT"] = "1"  # threshold = 100 tokens
        reply = {
            "role": "assistant",
            "content": "visible text without tag",
            "reasoning_content": "[COMPACT_SUMMARY:TOOLS]\nsummary from reasoning",
        }
        app, ctx, _ = make_env([ASSISTANT_PARENT, TOOL_MSG], 2000)
        app.message_history._msgs.append(reply)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            ctx.hooks["after_assistant_message_added"](reply)
        msgs = app.message_history._msgs
        self.assertEqual(len(msgs), 1)  # pair consumed on the same message
        self.assertEqual(
            msgs[0]["content"],
            "[COMPACT_SUMMARY:TOOLS]\nsummary from reasoning\n\nvisible text without tag",
        )
        self.assertNotIn("reasoning_content", msgs[0])  # no duplicate tokens on resend
        printed = out.getvalue()
        # user sees the full promoted summary even with show-reasoning off
        self.assertIn("[COMPACT_SUMMARY:TOOLS]\nsummary from reasoning", printed)
        # accept log names the source field
        self.assertIn("accepted [COMPACT_SUMMARY:TOOLS] (from reasoning field)", printed)

    def test_reasoning_only_tag_empty_visible_promoted(self):
        """Reasoning tag with empty visible content: promotion also covers it
        (real empty replies go through empty-retry and never reach this hook,
        but a hook-level call must not double the tag)."""
        os.environ["TOOLS_COMPACT_LOOP_PCT"] = "1"
        reply = {
            "role": "assistant",
            "content": "",
            "reasoning_content": "thinking\n[COMPACT_SUMMARY:TOOLS]\nsummary",
        }
        app, ctx, _ = make_env([ASSISTANT_PARENT, TOOL_MSG], 2000)
        app.message_history._msgs.append(reply)
        ctx.hooks["after_assistant_message_added"](reply)
        msgs = app.message_history._msgs
        self.assertEqual(len(msgs), 1)
        self.assertEqual(
            msgs[0]["content"], "[COMPACT_SUMMARY:TOOLS]\nsummary"
        )
        self.assertNotIn("reasoning_content", msgs[0])

    def test_reasoning_tag_not_at_line_start_no_promote(self):
        """Tag quoted/explained mid-reasoning (not at line start) must NOT
        promote — same false-positive protection as visible content."""
        os.environ["TOOLS_COMPACT_LOOP_PCT"] = "1"
        reply = {
            "role": "assistant",
            "content": "explaining the mechanism",
            "reasoning_content": "I could emit [COMPACT_SUMMARY:TOOLS] here",
        }
        app, ctx, _ = make_env([ASSISTANT_PARENT, TOOL_MSG], 2000)
        app.message_history._msgs.append(reply)
        ctx.hooks["after_assistant_message_added"](reply)
        msgs = app.message_history._msgs
        self.assertEqual(len(msgs), 3)  # untouched — no consume, no promote
        self.assertEqual(msgs[2]["content"], "explaining the mechanism")
        self.assertIn("reasoning_content", msgs[2])

    def test_reasoning_tag_with_tool_calls_no_promote(self):
        """A reply that keeps working (tool_calls) is not a summary attempt —
        promotion must not hijack a continuing turn into a compaction."""
        os.environ["TOOLS_COMPACT_LOOP_PCT"] = "1"
        reply = {
            "role": "assistant",
            "content": "continuing work",
            "tool_calls": [{"id": "call_9", "name": "fake", "arguments": "{}"}],
            "reasoning_content": "[COMPACT_SUMMARY:TOOLS]\nsummary",
        }
        app, ctx, _ = make_env([ASSISTANT_PARENT, TOOL_MSG], 2000)
        app.message_history._msgs.append(reply)
        ctx.hooks["after_assistant_message_added"](reply)
        msgs = app.message_history._msgs
        self.assertEqual(len(msgs), 3)  # untouched
        self.assertEqual(msgs[2]["content"], "continuing work")

    def test_after_compaction_resets_loop_state(self):
        """Core compaction fires after_compaction: the live-loop cost is
        stale afterwards — no nudge may fire until a fresh loop builds up.
        The second nudge at 101 proves the reset really cleared nudge_fired."""
        os.environ["TOOLS_COMPACT_LOOP_PCT"] = "1"  # threshold = 100 tokens
        app, ctx, _ = make_env([ASSISTANT_PARENT, TOOL_MSG], 2000)
        fire = ctx.hooks["after_tool_results_added"]

        big = dict(TOOL_MSG, content=LONG_CONTENT)
        app.message_history._msgs.append(big)
        fire(big)  # loop 101 -> first nudge
        self.assertIn("system-reminder", self._last_content(app.message_history._msgs))

        ctx.hooks["after_compaction"]()  # core compact path (message_history)
        parent, result = new_pair("call_3", TOOL_MSG["content"])  # 51 tokens
        app.message_history._msgs.append(parent)
        app.message_history._msgs.append(result)
        fire(result)  # fresh loop 51 -> stale 101 cost must be gone
        self.assertEqual(len(app.message_history._msgs), 6)
        self.assertNotIn("system-reminder", self._last_content(app.message_history._msgs))

        parent, result = new_pair("call_4", LONG_CONTENT)  # 101 tokens
        app.message_history._msgs.append(parent)
        app.message_history._msgs.append(result)
        fire(result)  # fresh loop 101 -> second nudge (reset worked)
        self.assertIn("system-reminder", self._last_content(app.message_history._msgs))

    def test_after_messages_set_resets_loop_state(self):
        """cache_compact._compact replaces history via set_messages and NEVER
        fires after_compaction — after_messages_set is its only signal.
        Simulate it: nudge fired -> set_messages -> small result, no stale
        nudge."""
        os.environ["TOOLS_COMPACT_LOOP_PCT"] = "1"  # threshold = 100 tokens
        app, ctx, _ = make_env([ASSISTANT_PARENT, TOOL_MSG], 2000)
        fire = ctx.hooks["after_tool_results_added"]

        big = dict(TOOL_MSG, content=LONG_CONTENT)
        app.message_history._msgs.append(big)
        fire(big)  # loop 101 -> nudge
        self.assertIn("system-reminder", self._last_content(app.message_history._msgs))

        # cache_compact._compact -> set_messages(new_msgs) -> after_messages_set
        ctx.hooks["after_messages_set"](app.message_history.get_messages())
        parent, result = new_pair("call_3", TOOL_MSG["content"])  # 51 tokens
        app.message_history._msgs.append(parent)
        app.message_history._msgs.append(result)
        fire(result)  # fresh loop 51 -> no stale nudge
        self.assertEqual(len(app.message_history._msgs), 6)
        self.assertNotIn("system-reminder", self._last_content(app.message_history._msgs))

    def test_no_stale_nudge_after_set_messages_compaction(self):
        """Reported scenario: heavy loop (202) fires a nudge, then a full
        compaction replaces the history (cache_compact._compact path). The
        next tool result must NOT re-fire the nudge with the dead loop cost."""
        os.environ["TOOLS_COMPACT_LOOP_PCT"] = "1"  # threshold = 100 tokens
        app, ctx, _ = make_env([ASSISTANT_PARENT, TOOL_MSG], 2000)
        fire = ctx.hooks["after_tool_results_added"]

        big = dict(TOOL_MSG, content=LONG_CONTENT)
        app.message_history._msgs.append(big)
        fire(big)  # loop 101
        self.assertIn("system-reminder", self._last_content(app.message_history._msgs))

        big2 = dict(TOOL_MSG, content=LONG_CONTENT)
        app.message_history._msgs.append(big2)
        fire(big2)  # loop 202 -> same cycle, no repeat
        nudges = [m for m in app.message_history._msgs
                  if "system-reminder" in m.get("content", "")]
        self.assertEqual(len(nudges), 1)

        # full compaction: set_messages(new history) fires after_messages_set
        ctx.hooks["after_messages_set"]([ASSISTANT_PARENT])
        parent, result = new_pair("call_3", TOOL_MSG["content"])  # 51 tokens
        app.message_history._msgs.append(parent)
        app.message_history._msgs.append(result)
        fire(result)  # fresh loop 51 -> dead 202 cost must not nudge
        self.assertNotIn("system-reminder", self._last_content(app.message_history._msgs))
        nudges = [m for m in app.message_history._msgs
                  if "system-reminder" in m.get("content", "")]
        self.assertEqual(len(nudges), 1)  # only the pre-compaction nudge


    def test_context_bar_shows_loop_budget_when_enabled(self):
        """TOOLS_COMPACT_SHOW_BUDGET=1 -> on_context_bar returns a dimmed
        lb:N suffix with the live loop cost."""
        os.environ["TOOLS_COMPACT_SHOW_BUDGET"] = "1"
        try:
            os.environ["TOOLS_COMPACT_LOOP_PCT"] = "1"  # threshold = 100 tokens
            app, ctx, _ = make_env([ASSISTANT_PARENT, TOOL_MSG], 2000)
            big = dict(TOOL_MSG, content=LONG_CONTENT)
            app.message_history._msgs.append(big)
            ctx.hooks["after_tool_results_added"](big)  # loop 101
            result = ctx.hooks["on_context_bar"]()
            self.assertIsNotNone(result)
            self.assertIn("lb:101", result)
        finally:
            os.environ.pop("TOOLS_COMPACT_SHOW_BUDGET", None)
            os.environ.pop("TOOLS_COMPACT_LOOP_PCT", None)

    def test_context_bar_loop_budget_hidden_when_off(self):
        """/toolcompact off hides the lb: suffix; on restores it. Loop cost is
        not accumulated while disabled (bar shows lb:0 after re-enable)."""
        os.environ["TOOLS_COMPACT_SHOW_BUDGET"] = "1"
        os.environ["TOOLS_COMPACT_LOOP_PCT"] = "1"
        try:
            app, ctx, _ = make_env([ASSISTANT_PARENT, TOOL_MSG], 2000)
            ctx.commands["toolcompact"]("off")
            big = dict(TOOL_MSG, content=LONG_CONTENT)
            app.message_history._msgs.append(big)
            ctx.hooks["after_tool_results_added"](big)  # would be loop 101
            self.assertIsNone(ctx.hooks["on_context_bar"]())
            ctx.commands["toolcompact"]("on")
            self.assertIn("lb:0", ctx.hooks["on_context_bar"]())
        finally:
            os.environ.pop("TOOLS_COMPACT_SHOW_BUDGET", None)
            os.environ.pop("TOOLS_COMPACT_LOOP_PCT", None)


    def test_toolcompact_command_status_default(self):
        """/toolcompact (no args) reports env-default budget."""
        os.environ["TOOLS_COMPACT_LOOP_PCT"] = "2"
        try:
            _, ctx, _ = make_env([], 2000)
            status = ctx.commands["toolcompact"]("")
            self.assertIn("ENABLED", status)
            self.assertIn("2%", status)  # env TOOLS_COMPACT_LOOP_PCT=2
        finally:
            os.environ.pop("TOOLS_COMPACT_LOOP_PCT", None)

    def test_toolcompact_command_absolute_budget(self):
        """/toolcompact 1k -> nudge at 1000 tokens regardless of pct."""
        app, ctx, _ = make_env([], 2000)
        ctx.commands["toolcompact"]("1k")
        for i in range(10):  # 10 pairs x 101 tokens = 1010 >= 1000
            parent, result = new_pair(f"call_b{i}", LONG_CONTENT)
            app.message_history._msgs.append(parent)
            app.message_history._msgs.append(result)
            ctx.hooks["after_tool_results_added"](result)
        nudges = [
            m for m in app.message_history._msgs
            if "<system-reminder>" in m.get("content", "")
            and "[NUDGE:COMPACTION]" in m.get("content", "")
        ]
        self.assertEqual(len(nudges), 1)

    def test_toolcompact_command_off_suppresses_nudge(self):
        """/toolcompact off silences the nudge; on re-arms it."""
        app, ctx, _ = make_env([], 2000)
        ctx.commands["toolcompact"]("off")
        for i in range(5):  # 505 tokens, way past the 200 env threshold
            parent, result = new_pair(f"call_c{i}", LONG_CONTENT)
            app.message_history._msgs.append(parent)
            app.message_history._msgs.append(result)
            ctx.hooks["after_tool_results_added"](result)
        nudges = [
            m for m in app.message_history._msgs
            if "<system-reminder>" in m.get("content", "")
            and "[NUDGE:COMPACTION]" in m.get("content", "")
        ]
        self.assertEqual(nudges, [])
        self.assertIn("DISABLED", ctx.commands["toolcompact"](""))
        ctx.commands["toolcompact"]("on")
        parent, result = new_pair("call_c9", LONG_CONTENT)
        app.message_history._msgs.append(parent)
        app.message_history._msgs.append(result)
        ctx.hooks["after_tool_results_added"](result)  # 606 >= 200 again
        nudges = [
            m for m in app.message_history._msgs
            if "<system-reminder>" in m.get("content", "")
            and "[NUDGE:COMPACTION]" in m.get("content", "")
        ]
        self.assertEqual(len(nudges), 1)

    def test_toolcompact_command_pct_override(self):
        """/toolcompact pct 1 -> threshold = 1% of 10000 = 100 tokens."""
        app, ctx, _ = make_env([], 2000)
        ctx.commands["toolcompact"]("pct 1")
        parent, result = new_pair("call_d", LONG_CONTENT)  # 101 tokens
        app.message_history._msgs.append(parent)
        app.message_history._msgs.append(result)
        ctx.hooks["after_tool_results_added"](result)
        nudges = [
            m for m in app.message_history._msgs
            if "<system-reminder>" in m.get("content", "")
            and "[NUDGE:COMPACTION]" in m.get("content", "")
        ]
        self.assertEqual(len(nudges), 1)
        self.assertIn("= 100", ctx.commands["toolcompact"](""))

    def test_toolcompact_command_reset_and_validation(self):
        """/toolcompact reset restores env defaults; bad input rejected."""
        os.environ["TOOLS_COMPACT_LOOP_PCT"] = "2"
        try:
            _, ctx, _ = make_env([], 2000)
            ctx.commands["toolcompact"]("1k")
            ctx.commands["toolcompact"]("pct 1")
            ctx.commands["toolcompact"]("reset")
            self.assertIn("2%", ctx.commands["toolcompact"](""))
            self.assertIn("too small", ctx.commands["toolcompact"]("5"))
            self.assertIn("invalid budget", ctx.commands["toolcompact"]("abc"))
            self.assertIn("0..100", ctx.commands["toolcompact"]("pct 500"))
        finally:
            os.environ.pop("TOOLS_COMPACT_LOOP_PCT", None)


    def test_empty_reply_hook_signals_takeover_when_tag_in_reasoning(self):
        """Live bug: the AI put the tag in reasoning_content only, visible
        reply came back empty. empty_retry fires on_empty_assistant_message
        with the reasoning fields — the listener must return truthy so the
        retry happens DIRECTLY (no nudge message between the tool pairs and
        the retried tag reply, which would block the backward scan)."""
        app, ctx, _ = make_env([ASSISTANT_PARENT, TOOL_MSG], 2000)
        hook = ctx.hooks["on_empty_assistant_message"]
        self.assertTrue(hook(reasoning_content="thinking about it\n[COMPACT_SUMMARY:TOOLS]\nsummary", reasoning_field=""))
        self.assertTrue(hook(reasoning_content="", reasoning_field="\n[COMPACT_SUMMARY:TOOLS]"))
        self.assertIsNone(hook(reasoning_content="no tag here", reasoning_field=""))
        self.assertIsNone(hook(reasoning_content=None, reasoning_field=None))

    def test_empty_reply_hook_does_not_react_to_other_tags(self):
        """cache_compact's [COMPACT_SUMMARY] (no :TOOLS) must NOT trigger the
        takeover — disjoint tag, disjoint state machine."""
        app, ctx, _ = make_env([ASSISTANT_PARENT, TOOL_MSG], 2000)
        hook = ctx.hooks["on_empty_assistant_message"]
        self.assertIsNone(hook(reasoning_content="[COMPACT_SUMMARY]\nsummary", reasoning_field=""))

    def test_empty_reply_hook_registered_only_when_enabled(self):
        """TOOLS_COMPACT_ENABLED != '1' -> no listener registered."""
        os.environ["TOOLS_COMPACT_ENABLED"] = "0"
        try:
            app, ctx, plugin = make_env([ASSISTANT_PARENT, TOOL_MSG], 2000)
            self.assertIsNone(plugin)
            self.assertNotIn("on_empty_assistant_message", ctx.hooks)
        finally:
            os.environ["TOOLS_COMPACT_ENABLED"] = "1"


    def test_empty_reply_hook_claims_when_summary_expected(self):
        """Genuinely empty reply (tag in NEITHER visible NOR reasoning) right
        after the hard nudge: the AI's next visible reply was supposed to be
        the tag summary but came back empty. The listener must claim so
        empty_retry retries directly — otherwise the nudge message would sit
        between the tool pairs and the retried tag reply and block the
        backward scan (breaks at real user content), killing the consume."""
        os.environ["TOOLS_COMPACT_LOOP_PCT"] = "1"  # threshold = 100 tokens
        try:
            app, ctx, _ = make_env([ASSISTANT_PARENT, TOOL_MSG], 2000)
            fire = ctx.hooks["after_tool_results_added"]
            big = dict(TOOL_MSG, content=LONG_CONTENT)
            app.message_history._msgs.append(big)
            fire(big)  # loop 101 -> nudge delivered -> awaiting_summary
            self.assertIn("system-reminder", self._last_content(app.message_history._msgs))

            hook = ctx.hooks["on_empty_assistant_message"]
            self.assertTrue(hook(reasoning_content="", reasoning_field=""))  # claim

            # AI replies properly -> expectation over -> no claim anymore
            ctx.hooks["after_assistant_message_added"](PLAIN_REPLY)
            self.assertIsNone(hook(reasoning_content="", reasoning_field=""))
        finally:
            os.environ["TOOLS_COMPACT_LOOP_PCT"] = "2"

    def test_empty_reply_hook_claim_cleared_by_turn_end(self):
        """The AI finishing its turn (after_ai_processing(False)) resets the
        summary expectation — a later empty reply is no longer a lost
        summary attempt."""
        os.environ["TOOLS_COMPACT_LOOP_PCT"] = "1"  # threshold = 100 tokens
        try:
            app, ctx, _ = make_env([ASSISTANT_PARENT, TOOL_MSG], 2000)
            fire = ctx.hooks["after_tool_results_added"]
            big = dict(TOOL_MSG, content=LONG_CONTENT)
            app.message_history._msgs.append(big)
            fire(big)  # loop 101 -> nudge
            hook = ctx.hooks["on_empty_assistant_message"]
            self.assertTrue(hook(reasoning_content="", reasoning_field=""))

            ctx.hooks["after_ai_processing"](False)  # turn over -> reset
            self.assertIsNone(hook(reasoning_content="", reasoning_field=""))
        finally:
            os.environ["TOOLS_COMPACT_LOOP_PCT"] = "2"


if __name__ == "__main__":
    unittest.main(verbosity=2)
