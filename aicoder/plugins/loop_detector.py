"""
Loop Detector Plugin - Abort a stream that gets stuck repeating itself.

Failure mode: a model keeps emitting the same fragment over and over — in its
content, in hidden reasoning, or in tool-call arguments. Post-hoc detection is
worthless: the output tokens are already billed, and in YOLO mode the tool
calls that the loop produced have already executed. This plugin watches the
live stream instead and asks the core to abort the response.

Detection is deliberately simple. Per channel the text is buffered and checked
every CHECK_EVERY_CHARS characters against a rolling WINDOW_WORDS-word history;
if the tail of the window is one run of at most NEEDLE_WORDS words repeated
back-to-back MIN_REPEATS times, the channel is looping. Cost is O(window) per
check, a few checks per second — no n-gram tables, no rescans of the response
so far.

The repetitions must be contiguous. Counting a needle that merely occurs
MIN_REPEATS times anywhere in the window aborts legitimate structured output
(SVG shapes, CSS rules, JSON rows), which is repetition by design.

The plugin prints the abort notice itself; the core only honors the request
and returns the prompt.

Disable:
  - command /loop-detector off (session override; on|off, no args shows status)
  - env AICODER_LOOP_DETECTOR=0 (0/false/no/off/disable/...)
  - NVIDIA NIM (free tier): a runaway model costs nothing there, so the
    detector stays off by default.
"""

from aicoder.core.config import Config
from aicoder.utils.bool_utils import TRUTHY, FALSY, env_bool
from aicoder.utils.log import LogUtils

WINDOW_WORDS = 200        # rolling history kept per channel
NEEDLE_WORDS = 30         # longest repeating run that is still searched for
MIN_REPEATS = 3           # contiguous copies of the run needed to trip
CHECK_EVERY_CHARS = 200   # buffered characters per check
MAX_PENDING_CHARS = 1600  # cap for one whitespace-free run (base64 blobs etc.)

# Words are the tokens; punctuation that glues words together in compact JSON
# (tool arguments arrive with no spaces at all) counts as a separator too.
_SEPARATORS = str.maketrans({c: " " for c in '{}[]":,'})


def _repeats(words) -> bool:
    """True when the tail of `words` is one run repeated back-to-back MIN_REPEATS times.

    Contiguous repetition only. Counting occurrences anywhere in the window
    aborts legitimate structured output: an SVG with three similar shapes, a
    CSS sheet, a JSON dataset or a list of test cases all contain the same run
    three times inside 200 words, and a whole turn died on them. A model that
    is genuinely stuck emits the fragment again immediately, so requiring the
    repeats to be adjacent keeps the detection and drops the false positives.

    The repeating run may be shorter than NEEDLE_WORDS: a stuck model usually
    loops on a short phrase, and comparing one fixed NEEDLE_WORDS block against
    the previous one only matches periods that are multiples of it (a 13-word
    loop shifted by 30 never compares equal). So every period is tried, the
    shortest first, and a period whose last MIN_REPEATS copies agree wins.
    """
    for period in range(1, NEEDLE_WORDS + 1):
        span = period * MIN_REPEATS
        if len(words) < span:
            return False
        if words[-period:] * MIN_REPEATS == words[-span:]:
            return True
    return False


def _detector_state() -> tuple[bool, str]:
    """Decide whether the detector runs now: (enabled, reason).

    Re-read per response so a mid-session model switch is honored; the reason
    string is only shown by /loop-detector.
    """
    if not env_bool("AICODER_LOOP_DETECTOR", True):
        return False, "AICODER_LOOP_DETECTOR=0"
    # NVIDIA NIM is a free tier: a looping model there costs nothing.
    if "nvidia" in Config.base_url().lower():
        return False, "off by default on NVIDIA NIM (free tier)"
    return True, "default"


def create_plugin(ctx):
    pending = {}
    window = {}
    enabled = True
    reason = "default"
    override = None  # None = env/default rules; True/False = forced via command

    def _refresh():
        """Recompute enabled/reason; drop buffers when the detector is off."""
        nonlocal enabled, reason
        if override is None:
            enabled, reason = _detector_state()
        else:
            enabled, reason = override, "session override"
        if not enabled:
            pending.clear()
            window.clear()

    def _on_stream_start():
        # Re-evaluated per response: the model/base URL can change mid-session.
        _refresh()
        pending.clear()
        window.clear()

    def _on_stream_text(channel: str, text: str) -> bool:
        if not enabled or not text:
            return False
        buf = pending.get(channel, "") + text.translate(_SEPARATORS)
        if len(buf) > MAX_PENDING_CHARS:
            # Whitespace-free run (binary/base64 arguments): keep the tail only,
            # so the buffer cannot grow into a per-fragment copying cost.
            buf = buf[-MAX_PENDING_CHARS:]
        while len(buf) >= CHECK_EVERY_CHARS:
            # Cut on whitespace only: a word split across chunks must stay
            # intact or a repeated needle would never match twice.
            cut = max(buf.rfind(" "), buf.rfind("\n"), buf.rfind("\t"))
            if cut < 0:
                break  # one long token so far — wait for a separator
            words = (window.get(channel, []) + buf[:cut].split())[-WINDOW_WORDS:]
            buf = buf[cut + 1:]
            window[channel] = words
            if _repeats(words):
                pending.pop(channel, None)
                window.pop(channel, None)
                c = Config.colors
                LogUtils.print(
                    f"\n{c['bold']}{c['yellow']}[loop-detector]{c['reset']}"
                    f" Loop detected on channel '{channel}'... aborting"
                )
                LogUtils.print(
                    "[loop-detector] repeated fragment: "
                    + " ".join(words[-NEEDLE_WORDS:])[:120]
                )
                return True  # loop found — core aborts the stream
        pending[channel] = buf
        return False

    def _handle_command(args_str: str) -> str:
        nonlocal override
        parts = args_str.strip().split() if args_str else []

        if parts:
            if parts[0] in TRUTHY:
                override = True
            elif parts[0] in FALSY:
                override = False
            else:
                return "Usage: /loop-detector [on|off]"

        _refresh()
        return (
            f"Loop detector: {'enabled' if enabled else 'disabled'} ({reason})\n"
            f"- trips when a run of 1-{NEEDLE_WORDS} words repeats "
            f"back-to-back {MIN_REPEATS}x inside a {WINDOW_WORDS}-word window\n"
            f"- /loop-detector on|off - override for this session\n"
            f"- AICODER_LOOP_DETECTOR=0 in the environment - persistent off\n"
        )

    ctx.register_hook("on_stream_start", _on_stream_start)
    ctx.register_hook("on_stream_text", _on_stream_text)
    ctx.register_command(
        "/loop-detector",
        _handle_command,
        description="Loop detector: status / on / off",
    )
