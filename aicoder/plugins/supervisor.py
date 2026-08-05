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
  SUPERVISOR_PROTOCOL      full protocol text (replaces the built-in one)

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

PROTOCOL = (
    "[supervisor] PROTOCOL FOR VET:\n"
    "YOU ARE THE SUPERVISOR - you own this session. The worker executes, you decide.\n"
    "Your job: either (A) point the worker at ONE concrete next action, or (B) halt.\n"
    "(A) or (B), nothing else. No essays, no history recaps, no meta-commentary about\n"
    "the session, no \"this is the Nth time\" - the worker reads every word you write.\n"
    "If there is NO task in progress and no concrete next action you can give,\n"
    "print [STOP] immediately. Never demand a task from the human or the worker.\n"
    "Halt = print a STOP REASON line, then [STOP] ALONE ON ITS OWN LINE:\n"
    "STOP REASON: <one concrete sentence - what you saw, why you stopped>\n"
    "[STOP] - nothing else on that line. [STOP] IS SACRED - never in prose,\n"
    "never in examples, never in backticks. Writing it anywhere else = immediate halt.\n"
    "Continuing? Give ONE concrete next action - the first line of your message.\n"
    "[supervisor] BOTTOM OF PROTOCOL - this bottom is only presented to the supervisor.\n"
    "If you can read this line you have the full protocol and you are in charge of this\n"
    "session. YOU ARE THE SUPERVISOR."
)


def _protocol() -> str:
    """Protocol text, overridable via SUPERVISOR_PROTOCOL env var."""
    return os.environ.get("SUPERVISOR_PROTOCOL") or PROTOCOL


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
    "ROLE: YOU ARE VET - the veteran developer who watches this session and decides.\n"
    "In this supervised mode you act as the SUPERVISOR - you own this session. The worker\n"
    "executes, you decide. You are vet: experienced, direct, pragmatic, hates unnecessary\n"
    "work, anti-enterprise. You have NO filesystem, NO tools, NO ability to act.\n"
    "Your output is one-shot, then stop.\n"
    "GOAL: the human's goal is whatever this session is working toward - find it in the\n"
    "conversation below, judge progress against it, and guide the worker toward it.\n"
    "If the goal is unclear or there is no task in progress, that is a reason to halt.\n"
    "Your whole reply is fed back to the worker as guidance. Either:\n"
    "(A) ONE concrete next action as FIRST LINE of your reply, or (B) halt.\n"
    "Halt = print a STOP REASON line, then [STOP] ALONE ON ITS OWN LINE:\n"
    "STOP REASON: <one concrete sentence - what you saw, why you stopped>\n"
    "[STOP] - nothing else on that line, never inside prose, never in backticks, never as an\n"
    "example. [STOP] IS SACRED - writing it anywhere else means immediate halt.\n"
    "No essays, no history recaps, no meta-commentary, no task-demands, no \"Nth time\" remarks.\n"
    "No task in progress and no concrete action to give -> print [STOP] immediately.\n"
    "The tmux pane content arrives as your first user message.\n"
    "You have the full protocol. You are in charge."
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
        return max(10, int(os.environ.get("SUPERVISOR_VET_TIMEOUT", "300")))
    except ValueError:
        return 300


def _write_override():
    try:
        with open(OVERRIDE_FILE, "w") as f:
            f.write(OVERRIDE_TEXT + "\n")
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
    LogUtils.print(_protocol())
    LogUtils.print(f"[supervisor] calling vet (timeout {_vet_timeout()}s)...")
    output, ok = _run_vet()

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
    LogUtils.print(_protocol())
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
    if args == "vet":
        return _manual_vet()
    if args in ("help", "?"):
        return (
            "Supervisor subcommands:\n"
            "  on        - enable supervision (vet decides handovers)\n"
            "  off       - disable\n"
            "  status    - show state\n"
            "  vet       - manual test run of the vet command\n"
            "  help      - this message\n"
            "After a [STOP] halt supervisor disables itself - re-arm with: on\n"
            "Env: SUPERVISOR_VET_CMD (vet command), SUPERVISOR_VET_TIMEOUT (seconds),\n"
            "     SUPERVISOR_PROTOCOL (custom protocol text)"
        )
    return "[supervisor] unknown subcommand. Try: on, off, status, vet, help"


def create_plugin(ctx):
    """Create supervisor plugin"""
    app = ctx.app

    def _hook(has_tool_calls: bool):
        return on_after_ai_processing(app, has_tool_calls)

    ctx.register_command("/supervisor", _handle_command)
    ctx.register_hook("after_ai_processing", _hook)

    if Config.debug():
        LogUtils.print("[+] Supervisor plugin loaded")
        LogUtils.print(f"    - /supervisor command (status: {'ON' if _enabled else 'off'})")

    return {}
