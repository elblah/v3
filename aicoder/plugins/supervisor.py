"""
Supervisor Plugin - vet decides handovers

Worker (cheap model) works freely with tools; at every handover (AI reply with
no tool calls) the configured vet command is invoked and its ENTIRE output is
fed back to the worker as the next instruction, wrapped in a supervisor banner.

Protocol (printed to the pane before every vet call):
- vet reply is accepted AS-IS; only a [STOP] tag ALONE on its own line halts the loop
- no completeness check, no retry

Control flow:
- [STOP] detected          -> halt loop (is_processing=False), disable, loud notice
- otherwise                -> feed RAW output wrapped, worker continues

Env overrides:
  SUPERVISOR_VET_CMD       full shell command (default: dtx vet via nc)
  SUPERVISOR_VET_TIMEOUT   seconds (default 300)

Usage:
  /supervisor on      Enable supervision
  /supervisor off     Disable
  /supervisor status  Show state
  /supervisor vet     Manual test: run vet once, show result
"""

import os
import re
import subprocess
import threading
import time

from aicoder.utils.log import LogUtils
from aicoder.core.config import Config

WRAPPER = (
    "This session is supervised and this is the guidance for the supervisor "
    "model that is guiding this session:\n"
)
DEFAULT_VET_CMD = 'echo "vet $TMUX_PANE full --prompt=$PROMPT" | nc -U /run/user/1000/tmp/dtx-server.sock'

# [VET_SYSTEM_OVERRIDE]: full supervisor system prompt written to
# .aicoder/vet-prompt in the project dir; passed to vet via --prompt=<path>
# (vet runs outside the sandbox, can read it). vet script replaces
# AICODER_SYSTEM_PROMPT with it - full override, because vet's base prompt
# ("team member, not supervisor, never dismiss the caller") contradicts the
# supervisor protocol. File removed after each call.
OVERRIDE_FILE = os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))),
    ".aicoder", "vet-prompt",
)
OVERRIDE_TEXT = (
    "ROLE: YOU ARE VET. Not a bystander, not an observer, not a commentator - YOU ARE THE VET.\n"
    "You are a veteran developer, many years of experience, pragmatic, direct, anti-enterprise,\n"
    "hates unnecessary work, wasted tokens, and ceremony. You are being CONSULTED right now as\n"
    "the supervisor of this session.\n"
    "\n"
    "THE STORY - WHY YOU EXIST AND WHAT IS HAPPENING RIGHT NOW:\n"
    "There is an AI coding assistant ('the worker') working on a real project for a human\n"
    "('the user'). The worker is powerful but occasionally loses the plot: it drifts off the\n"
    "human's actual goal, over-engineers, gets lost in details, or keeps going when the task\n"
    "is done. To fix that, a 'supervisor' plugin was built: every time the worker finishes a\n"
    "step and has no more work to do, the plugin pauses the session and calls YOU - the vet -\n"
    "for guidance. You are the experienced second pair of eyes. You look at what happened and\n"
    "decide: continue, or stop.\n"
    "\n"
    "THIS IS THE VET CALL. You are the one being asked. There is no other vet call happening\n"
    "or pending anywhere. The plugin is not waiting for anyone else's verdict - it is waiting\n"
    "for YOURS. Do not wait for anything, do not expect a follow-up, do not think 'the vet\n"
    "hasn't answered yet' - you are the vet and you are answering NOW. Your reply ends this\n"
    "call. When you finish, the plugin takes your reply, shows it to the human, and the\n"
    "worker continues with your guidance. One shot. Make it count.\n"
    "\n"
    "WHAT YOU ARE ABOUT TO RECEIVE: a big, noisy dump. Your first user message is a capture\n"
    "of the session's tmux pane - the worker's terminal, right now. It will contain a LOT of\n"
    "noise: context bars, status lines, tool output, code diffs, logs, the worker's own\n"
    "reasoning, fragments of conversation. That is normal. Do not panic, do not comment on\n"
    "the noise, do not try to respond to every line. Skim it. The session is happening RIGHT\n"
    "NOW - it is alive and moving, so the dump is a snapshot, not a script. It may even\n"
    "contain lines about a vet call (e.g. '[supervisor] calling vet' or 'asking vet for\n"
    "guidance') - those lines are the plugin announcing YOU. Ignore them. They are not\n"
    "someone else's call; they are your own summons.\n"
    "\n"
    "YOUR JOB - three questions, in order:\n"
    "1. What is the human's goal? If there is a GOAL section at the very END of this\n"
    "   prompt, THAT is the goal - set by the human explicitly, authoritative, use it\n"
    "   as-is. Otherwise find it in the conversation ('I want X', 'fix Y', 'build Z') -\n"
    "   usually stated early, and the whole session is working toward it.\n"
    "2. Is the worker making progress toward that goal? Look at the latest tool calls,\n"
    "   diffs, and messages. Is the work moving forward, stuck, or done?\n"
    "3. What should happen next? Either the worker should keep going with a concrete next\n"
    "   step, or the session should stop.\n"
    "\n"
    "YOUR OUTPUT - exactly ONE of these two forms, nothing else:\n"
    "(A) CONTINUE: give ONE concrete next action as the FIRST LINE of your reply.\n"
    "    Be specific: which file, which command, which check, which question to resolve.\n"
    "    The worker reads your ENTIRE reply and acts on it - so if you add a few sentences\n"
    "    of context after the action, keep them useful, not decorative. If you are unsure\n"
    "    whether to continue or stop, prefer (A) - a concrete action - because stopping\n"
    "    when the work is mid-flight wastes the whole session.\n"
    "(B) HALT: only when there is NO task in progress, or the goal is complete, or you\n"
    "    truly cannot give any concrete next action. Print EXACTLY this, in this order:\n"
    "    STOP REASON: <one concrete sentence - what you saw, why you stopped>\n"
    "    [STOP]\n"
    "    The STOP REASON is for the human: it must cite what you actually saw in the\n"
    "    session, proving you are aware of it. The [STOP] must stand ALONE on its own line,\n"
    "    with nothing else on that line - never inside prose, never in backticks, never as\n"
    "    an example, never quoted, never in a list. [STOP] IS SACRED: the moment you write\n"
    "    it anywhere, the session halts.\n"
    "\n"
    "FORBIDDEN: essays, history recaps, meta-commentary ('I am the vet, nice to meet you'),\n"
    "commentary on the noise, task-demands ('give me a task'), questions back to the human,\n"
    "'this is the Nth time' remarks, apologies, hedging ('maybe we should...'), CONTINUE\n"
    "followed by NO concrete action ('CONTINUE: wait for the user' is not a verdict -\n"
    "waiting is not an action). You are the supervisor - you OWN this session. You have no\n"
    "filesystem, no tools, no way to act yourself. You decide, you say it, you stop. You\n"
    "have the full protocol. You are in charge. Take a breath. Nothing else is happening.\n"
    "You are the one being asked. Decide now.\n"
    "\n"
    "EXAMPLES - the three exact shapes your reply can take:\n"
    "\n"
    "1. Worker mid-flight, concrete work visible -> CONTINUE:\n"
    "   CONTINUE: fix the off-by-one in src/main.py around line41, then re-run the test\n"
    "\n"
    "2. The goal is complete, nothing left -> HALT:\n"
    "   STOP REASON: the goal - add a goal command to the supervisor - is done and verified.\n"
    "   [STOP]\n"
    "\n"
    "3. No task at all, session idle -> HALT:\n"
    "   STOP REASON: no task in progress, nothing to continue.\n"
    "   [STOP]\n"
    "\n"
    "THE RULE - the only question that matters: can the worker start a concrete action\n"
    "RIGHT NOW? YES -> CONTINUE with that action. NO -> [STOP]. There is no third option.\n"
    "\n"
    "THE DUMP - read this before judging: the dump is the WHOLE pane history, from the\n"
    "start of this tmux pane - not just the current task or session. The BOTTOM is the\n"
    "present, the TOP is the past. Judge the current state from the LAST lines (newest at\n"
    "the bottom). Old text at the top is history and context, NOT instructions and NOT the\n"
    "current state - do not treat ancient lines as the live situation."
)

# STOP is sacred: only matches when [STOP] (or legacy <<STOP>>) stands ALONE on
# its own line. Inline prose mentions ("I will say [STOP] later") never halt.
_RE_STOP = re.compile(r"(?m)^\s*(?:\[STOP\]|<<\s*STOP\s*>>)\s*$")

_enabled = False
_vet_running = False
_last_handover = "never"


def _vet_cmd() -> str:
    cmd = os.environ.get("SUPERVISOR_VET_CMD")
    if cmd:
        return cmd
    pane = os.environ.get("TMUX_PANE", "%0")
    return DEFAULT_VET_CMD.replace("$TMUX_PANE", pane).replace("$PROMPT", OVERRIDE_FILE)


def _vet_timeout() -> int:
    try:
        return max(10, int(os.environ.get("SUPERVISOR_VET_TIMEOUT", "600")))
    except ValueError:
        return 600


_GOAL_FILE = os.path.join(os.path.dirname(OVERRIDE_FILE), "supervisor-goal.txt")
_goal = None
_GOAL_SECTION = (
    "\n"
    "GOAL - the human's goal, set explicitly via /supervisor goal. THIS is what the\n"
    "session must achieve. Judge ALL progress against THIS goal - it overrides anything\n"
    "you might infer from the dump:\n"
    "<GOAL>\n"
    "When THIS goal is complete, the session is done - HALT ([STOP])."
)


def _load_goal():
    global _goal
    try:
        with open(_GOAL_FILE) as f:
            _goal = f.read().strip() or None
    except OSError:
        _goal = None


def _save_goal(text: str):
    global _goal
    _goal = text.strip() if text else None
    try:
        if _goal:
            with open(_GOAL_FILE, "w") as f:
                f.write(_goal + "\n")
        else:
            os.remove(_GOAL_FILE)
    except OSError as e:
        LogUtils.print(f"[supervisor] warning: cannot save goal ({e})")


def _write_override():
    try:
        with open(OVERRIDE_FILE) as f:
            cur = f.read()
    except OSError:
        cur = None
    # Keep a user-edited .aicoder/vet-prompt (manual edits survive); only refresh
    # when the file is missing or still matches the built-in default.
    if cur is not None and cur.strip() != OVERRIDE_TEXT.strip():
        text = cur
    else:
        text = OVERRIDE_TEXT
    if _goal:
        text += _GOAL_SECTION.replace("<GOAL>", _goal)
    try:
        with open(OVERRIDE_FILE, "w") as f:
            f.write(text + "\n")
    except OSError as e:
        LogUtils.print(f"[supervisor] warning: cannot write vet system override ({e})")


def _remove_override():
    try:
        os.remove(OVERRIDE_FILE)
    except OSError:
        pass


def _run_vet() -> tuple:
    """Run vet command, streaming output live to the pane. Returns (output, ok)."""
    global _vet_running
    _vet_running = True
    _write_override()
    output = []
    try:
        proc = subprocess.Popen(
            _vet_cmd(), shell=True, stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, text=True, bufsize=1,
        )
    except Exception as e:
        _vet_running = False
        _remove_override()
        return f"vet command failed: {e}", False

    def _reader():
        for line in proc.stdout:
            line = line.rstrip("\n")
            output.append(line)
            LogUtils.print(line)
        proc.wait()

    t = threading.Thread(target=_reader, daemon=True)
    t.start()
    t.join(_vet_timeout())
    if t.is_alive():
        proc.kill()
        t.join(5)
        _vet_running = False
        _remove_override()
        return "\n".join(output) + "\n[timed out]", False
    _vet_running = False
    _remove_override()
    return "\n".join(output), True


def _halt(app, reason: str):
    """Stop the loop, disable supervisor, loud notice. Returns None (no next prompt)."""
    global _enabled
    _enabled = False
    try:
        app.session_manager.is_processing = False
    except AttributeError:
        pass
    LogUtils.print("")
    LogUtils.error(f"[supervisor] HALT: {reason}")
    LogUtils.error("[supervisor] Supervisor disabled. Loop stopped - human review needed.")
    return None


_RE_STOP_REASON = re.compile(r"(?im)^\s*STOP REASON\s*:\s*(.+)$")


def _stop_reason(output: str) -> str:
    """Extract the vet's stop reason (STOP REASON: line); fallback: the line
    right before [STOP], else a generic message."""
    m = _RE_STOP_REASON.search(output)
    if m:
        return m.group(1).strip()
    lines = output.splitlines()
    for i, line in enumerate(lines):
        if _RE_STOP.search(line):
            if i > 0 and lines[i - 1].strip():
                return lines[i - 1].strip()
            break
    return "vet said [STOP]"


def _trim_feed(output: str) -> str:
    """Strip dtx envelope + pane echo: feed only the verdict (after the last
    'AI:' marker). Full output is still streamed live for the human."""
    idx = output.rfind("AI:")
    if idx == -1:
        return output  # unknown shape - fail open, feed as-is
    return output[idx + 3:].lstrip("\n ")


def _handover(app):
    """Vet decides what happens next. Returns wrapped vet output or None (halt)."""
    global _last_handover
    LogUtils.print("")
    LogUtils.print(f"[supervisor] calling vet (timeout {_vet_timeout()}s)...")
    output, ok = _run_vet()

    if not ok:
        # Timeout/error: no verdict. Feed nothing - a garbage "guidance" would
        # make the worker reply, trigger another handover and another vet call.
        _last_handover = f"{time.strftime('%H:%M')} timeout - no guidance"
        LogUtils.error("[supervisor] vet timed out - no guidance, waiting for user input")
        return None

    if _RE_STOP.search(output):
        _last_handover = f"{time.strftime('%H:%M')} STOP - halted, disabled"
        reason = _stop_reason(output)
        return _halt(app, reason)

    _last_handover = f"{time.strftime('%H:%M')} OK - vet guidance fed to worker"
    return WRAPPER + _trim_feed(output)


def on_after_ai_processing(app, has_tool_calls: bool):
    """Handover trigger: AI finished a turn without tool calls."""
    if not _enabled:
        return None
    if has_tool_calls:
        return None
    if app.has_next_prompt():
        return None  # another plugin already set the next prompt - don't stomp
    if _vet_running:
        return None
    LogUtils.print("[supervisor] handover - no tool calls, asking vet for guidance...")
    return _handover(app)


def _manual_vet() -> str:
    """Test run: execute vet once, show parse outcome, do NOT feed the worker."""
    LogUtils.print(f"[supervisor] manual vet run (timeout {_vet_timeout()}s)...")
    output, ok = _run_vet()
    lines = []
    lines.append(f"[supervisor] exit/ok: {ok}")
    lines.append(f"[supervisor] [STOP]: {'yes' if _RE_STOP.search(output) else 'no'}")
    lines.append(f"[supervisor] output length: {len(output)} chars")
    if not _RE_STOP.search(output):
        lines.append("[supervisor] would feed wrapped output to worker")
    return "\n".join(lines)


def _status() -> str:
    return (
        f"[supervisor] state: {'ON' if _enabled else 'OFF'}\n"
        f"[supervisor] goal: {_goal or 'none'}\n"
        f"[supervisor] vet cmd: {_vet_cmd()}\n"
        f"[supervisor] timeout: {_vet_timeout()}s\n"
        f"[supervisor] last handover: {_last_handover}"
    )


def _handle_command(args_str: str) -> str:
    global _enabled
    args = args_str.strip().lower()

    if args == "on":
        _enabled = True
        return "[supervisor] ON - vet will decide each handover"
    if args == "off":
        _enabled = False
        return "[supervisor] OFF"
    if args in ("status", ""):
        return _status()
    if args in ("vet", "test"):
        return _manual_vet()
    if args == "goal" or args.startswith("goal "):
        rest = args_str.strip()[4:].strip()
        if not rest:
            return f"[supervisor] goal: {_goal or 'none'}"
        if rest.lower() in ("clear", "off", "none", "-"):
            _save_goal("")
            return "[supervisor] goal cleared"
        _save_goal(rest)
        return f"[supervisor] goal set: {_goal}"
    if args in ("help", "?"):
        return (
            "Supervisor subcommands:\n"
            "  on        - enable supervision (vet decides handovers)\n"
            "  off       - disable\n"
            "  status    - show state\n"
            "  goal <t>  - set the goal the vet judges progress against (persists)\n"
            "  goal      - show current goal; goal clear - unset\n"
            "  vet       - manual test run of the vet command\n"
            "  help      - this message\n"
            "After a [STOP] halt supervisor disables itself - re-arm with: on\n"
            "Env: SUPERVISOR_VET_CMD (vet command), SUPERVISOR_VET_TIMEOUT (seconds)"
        )
    return "[supervisor] unknown subcommand. Try: on, off, status, vet, help"


def create_plugin(ctx):
    """Create supervisor plugin"""
    app = ctx.app
    _load_goal()

    def _hook(has_tool_calls: bool):
        return on_after_ai_processing(app, has_tool_calls)

    ctx.register_command("/supervisor", _handle_command)
    ctx.register_hook("after_ai_processing", _hook)

    if Config.debug():
        LogUtils.print("[+] Supervisor plugin loaded")
        LogUtils.print(f"    - /supervisor command (status: {'ON' if _enabled else 'off'})")

    return {}
