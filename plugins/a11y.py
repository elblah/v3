"""
Accessibility Plugin - Screen reader support for blind users

Features:
- Read AI responses (no/minimal word limit)
- Read tool results (file reads, search results, command outputs)
- Echo user prompts
- Read error messages
- Read system status updates
- Configurable via environment variables
- Interrupt mode (kill previous speech when new arrives)
- HDMI audio sink detection
"""

import os
import re
import subprocess
import shutil
from typing import Optional

from aicoder.core.config import Config
from aicoder.utils.log import LogUtils

# Default settings
DEFAULT_ENGINE = "espeak"
DEFAULT_VOICE = "en-us+m3"  # Clear male voice
DEFAULT_SPEED = 160  # Slightly slower for clarity
DEFAULT_ENABLED = False

# What to read
DEFAULT_READ_AI = True
DEFAULT_READ_CODE = True
DEFAULT_READ_TOOLS = True
DEFAULT_READ_USER = True
DEFAULT_READ_ERRORS = True
DEFAULT_READ_STATUS = True

# Limits
DEFAULT_WORD_LIMIT = 500  # 0 = no limit
DEFAULT_TOOL_LIMIT = 2000  # Words for tool outputs
DEFAULT_DETAILED_MODE = False  # Read detailed outputs (only in debug mode by default)


def create_plugin(ctx):
    """Accessibility plugin"""

    # Configuration from env vars
    engine = os.environ.get("A11Y_ENGINE", DEFAULT_ENGINE).lower()
    voice = os.environ.get("A11Y_VOICE", DEFAULT_VOICE)
    speed = int(os.environ.get("A11Y_SPEED", str(DEFAULT_SPEED)))
    word_limit = int(os.environ.get("A11Y_WORD_LIMIT", str(DEFAULT_WORD_LIMIT)))
    tool_limit = int(os.environ.get("A11Y_TOOL_LIMIT", str(DEFAULT_TOOL_LIMIT)))

    # What to read
    read_ai = os.environ.get("A11Y_READ_AI", "1" if DEFAULT_READ_AI else "0") == "1"
    read_code = os.environ.get("A11Y_READ_CODE", "1" if DEFAULT_READ_CODE else "0") == "1"
    read_tools = os.environ.get("A11Y_READ_TOOLS", "1" if DEFAULT_READ_TOOLS else "0") == "1"
    read_user = os.environ.get("A11Y_READ_USER", "1" if DEFAULT_READ_USER else "0") == "1"
    read_errors = os.environ.get("A11Y_READ_ERRORS", "1" if DEFAULT_READ_ERRORS else "0") == "1"
    read_status = os.environ.get("A11Y_READ_STATUS", "1" if DEFAULT_READ_STATUS else "0") == "1"

    # Detailed mode: read full output instead of friendly summary
    # Follows DEBUG mode by default, but can be overridden with A11Y_DETAILED
    detailed_mode = Config.debug() or os.environ.get("A11Y_DETAILED", "1" if DEFAULT_DETAILED_MODE else "0") == "1"

    enabled = os.environ.get("A11Y_ENABLED", "1" if DEFAULT_ENABLED else "0") == "1"

    # Audio sink detection (HDMI preferred)
    current_sink = "pipewire/combined"

    # Track current TTS process for interruption
    current_process: Optional[subprocess.Popen] = None

    # Exclude phrases - filter out common filler phrases
    # Format: pipe-separated list, one phrase per line
    exclude_phrases_str = os.environ.get("A11Y_EXCLUDE", "")
    exclude_phrases = []
    if exclude_phrases_str:
        # Split by pipe or newlines
        exclude_phrases = [p.strip() for p in re.split(r'[|\n]', exclude_phrases_str) if p.strip()]

    def detect_audio_sink():
        """Detect audio sink (HDMI preferred, fallback to pipewire)"""
        nonlocal current_sink
        try:
            result = subprocess.run(
                ["pactl", "list", "sinks", "short"],
                capture_output=True,
                text=True
            )
            for line in result.stdout.split("\n"):
                if "hdmi" in line.lower():
                    parts = line.split()
                    if len(parts) >= 2:
                        current_sink = parts[1]
                        return
        except:
            pass
        current_sink = "pipewire/combined"

    def get_available_engines():
        """Check which TTS engines are available"""
        engines = []
        if shutil.which("espeak"):
            engines.append("espeak")
        if shutil.which("flite"):
            engines.append("flite")
        return engines

    def list_voices():
        """List available voices for current engine"""
        if engine == "espeak":
            try:
                result = subprocess.run(
                    ["espeak", "--voices=en"],
                    capture_output=True,
                    text=True
                )
                return result.stdout.strip()
            except:
                return "Could not list espeak voices"
        elif engine == "flite":
            try:
                result = subprocess.run(
                    ["flite", "-lv"],
                    capture_output=True,
                    text=True
                )
                return result.stdout.strip()
            except:
                return "Could not list flite voices"
        return "Unknown engine"

    def strip_markdown(text: str) -> str:
        """Remove markdown formatting for speech"""
        # Remove headers
        text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)
        # Remove bold/italic
        text = re.sub(r'\*+([^*]+)\*+', r'\1', text)
        # Remove links (keep text)
        text = re.sub(r'\[([^\]]+)\]\([^)]+\)', r'\1', text)
        # Remove list markers
        text = re.sub(r'^\s*[-*+]\s+', '', text, flags=re.MULTILINE)
        text = re.sub(r'^\s*\d+\.\s+', '', text, flags=re.MULTILINE)
        return text.strip()

    def apply_exclude_filter(text: str) -> str:
        """Remove excluded phrases from text (case-insensitive)"""
        if not exclude_phrases:
            return text

        result = text
        for phrase in exclude_phrases:
            # Case-insensitive replacement
            pattern = re.compile(re.escape(phrase), re.IGNORECASE)
            result = pattern.sub('', result)

        # Clean up extra whitespace left after removal
        result = re.sub(r'\s+', ' ', result).strip()
        return result

    def truncate_tool_result(text: str, max_words: int) -> str:
        """Truncate tool result showing beginning and end"""
        words = text.split()
        if len(words) <= max_words:
            return text

        # Show first part and last part
        first_words = max_words // 2
        last_words = max_words - first_words

        truncated = ' '.join(words[:first_words])
        truncated += "... " + ' '.join(words[-last_words:])
        return truncated

    def truncate_to_word_limit(text: str, limit: int) -> str:
        """Truncate text to word limit at sentence boundary"""
        if limit == 0:
            return text  # No limit

        words = text.split()
        if len(words) <= limit:
            return text

        # Take up to limit words
        truncated = ' '.join(words[:limit])

        # Try to end at sentence boundary
        sentence_end = max(
            truncated.rfind('.'),
            truncated.rfind('!'),
            truncated.rfind('?')
        )
        if sentence_end > len(truncated) * 0.5:
            truncated = truncated[:sentence_end + 1]
        else:
            truncated += "..."

        return truncated

    def speak_espeak(text: str):
        """Speak using espeak"""
        env = os.environ.copy()
        env["PULSE_SINK"] = current_sink
        return subprocess.Popen(
            ["espeak", "-v", voice, "-s", str(speed), text],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

    def speak_flite(text: str):
        """Speak using flite (simple version)"""
        env = os.environ.copy()
        env["PULSE_SINK"] = current_sink
        return subprocess.Popen(
            ["flite", "-voice", voice, text],
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

    def speak(text: str):
        """Speak text using configured engine (interrupts previous)"""
        nonlocal current_process

        if not enabled or not text.strip():
            return

        # Apply exclude filter to remove filler phrases
        text = apply_exclude_filter(text)

        if not text.strip():
            return

        # Kill previous speech
        if current_process and current_process.poll() is None:
            current_process.terminate()
            try:
                current_process.wait(timeout=0.5)
            except:
                current_process.kill()

        # Speak
        if engine == "espeak":
            current_process = speak_espeak(text)
        elif engine == "flite":
            current_process = speak_flite(text)

    def process_ai_message(content: str) -> str:
        """Process AI message for speech"""
        if not read_code:
            # Remove code blocks
            content = re.sub(r'```[\s\S]*?```', '', content)
            content = re.sub(r'`[^`]+`', '', content)

        content = strip_markdown(content)
        content = truncate_to_word_limit(content, word_limit)
        return content.strip()

    def on_after_assistant_message(assistant_message: dict):
        """Hook: Read AI responses"""
        if not read_ai:
            return

        content = assistant_message.get("content", "")
        if content:
            text = process_ai_message(content)
            if text:
                speak(text)

    def on_after_user_message_added(message: dict):
        """Hook: Echo user input"""
        if not read_user:
            return

        content = message.get("content", "")
        if content:
            # Don't echo commands (starts with /)
            if not content.startswith('/'):
                speak(content)

    def on_after_tool_results(tool_results: list):
        """Hook: Read tool results"""
        if not read_tools:
            return

        # Read each tool result
        for tool_result in tool_results:
            # The tool_result structure: tool_call_id and content
            # The content is the detailed output that goes to the AI
            content = tool_result.get("content", "")

            if content:
                # Read the content (tool output)
                text = truncate_tool_result(content, tool_limit)
                speak(text)

    def handle_a11y_command(args_str: str):
        """Handle /a11y command"""
        nonlocal enabled, engine, voice, word_limit, tool_limit, speed
        nonlocal read_ai, read_code, read_tools, read_user, read_errors, read_status
        nonlocal detailed_mode

        if not args_str:
            # Show status
            status = "enabled" if enabled else "disabled"
            return (f"Accessibility: {status}\n"
                    f"  Engine: {engine}\n"
                    f"  Voice: {voice}\n"
                    f"  Speed: {speed} wpm\n"
                    f"  AI word limit: {word_limit if word_limit else 'none'}\n"
                    f"  Tool limit: {tool_limit}\n"
                    f"  Detailed mode: {detailed_mode}\n"
                    f"  Read AI: {read_ai}\n"
                    f"  Read code: {read_code}\n"
                    f"  Read tools: {read_tools}\n"
                    f"  Read user: {read_user}\n"
                    f"  Read errors: {read_errors}\n"
                    f"  Read status: {read_status}")

        parts = args_str.strip().split()
        if not parts:
            return "Usage: /a11y [on|off|status|voice|limit|tool-limit|speed|read-*|engine]"

        cmd = parts[0].lower()

        if cmd == "on":
            enabled = True
            return "Accessibility enabled"
        elif cmd == "off":
            enabled = False
            return "Accessibility disabled"
        elif cmd == "status":
            status = "enabled" if enabled else "disabled"
            return (f"Accessibility: {status}\n"
                    f"  Engine: {engine}\n"
                    f"  Voice: {voice}\n"
                    f"  Speed: {speed} wpm\n"
                    f"  AI word limit: {word_limit if word_limit else 'none'}\n"
                    f"  Tool limit: {tool_limit}\n"
                    f"  Detailed mode: {detailed_mode}\n"
                    f"  Read AI: {read_ai}\n"
                    f"  Read code: {read_code}\n"
                    f"  Read tools: {read_tools}\n"
                    f"  Read user: {read_user}\n"
                    f"  Read errors: {read_errors}\n"
                    f"  Read status: {read_status}")
        elif cmd == "voice":
            if len(parts) < 2:
                return f"Current voice: {voice}\nAvailable voices:\n{list_voices()}"
            voice = parts[1]
            return f"Voice set to: {voice}"
        elif cmd == "limit":
            if len(parts) < 2:
                return f"Current AI word limit: {word_limit if word_limit else 'none'}"
            try:
                val = int(parts[1])
                word_limit = val
                return f"AI word limit set to: {val if val else 'none'}"
            except ValueError:
                return "Invalid limit. Usage: /a11y limit <number|0>"
        elif cmd == "tool-limit":
            if len(parts) < 2:
                return f"Current tool limit: {tool_limit}"
            try:
                tool_limit = int(parts[1])
                return f"Tool limit set to: {tool_limit}"
            except ValueError:
                return "Invalid limit. Usage: /a11y tool-limit <number>"
        elif cmd == "speed":
            if len(parts) < 2:
                return f"Current speed: {speed} wpm"
            try:
                speed = int(parts[1])
                return f"Speed set to: {speed} wpm"
            except ValueError:
                return "Invalid speed. Usage: /a11y speed <wpm>"
        elif cmd == "read-code":
            if len(parts) < 2:
                return f"Read code blocks: {'on' if read_code else 'off'}"
            val = parts[1].lower()
            if val in ("on", "1", "true", "yes"):
                read_code = True
                return "Read code blocks: on"
            elif val in ("off", "0", "false", "no"):
                read_code = False
                return "Read code blocks: off"
            return "Usage: /a11y read-code on|off"
        elif cmd == "read-tools":
            if len(parts) < 2:
                return f"Read tool results: {'on' if read_tools else 'off'}"
            val = parts[1].lower()
            if val in ("on", "1", "true", "yes"):
                read_tools = True
                return "Read tool results: on"
            elif val in ("off", "0", "false", "no"):
                read_tools = False
                return "Read tool results: off"
            return "Usage: /a11y read-tools on|off"
        elif cmd == "read-user":
            if len(parts) < 2:
                return f"Read user input: {'on' if read_user else 'off'}"
            val = parts[1].lower()
            if val in ("on", "1", "true", "yes"):
                read_user = True
                return "Read user input: on"
            elif val in ("off", "0", "false", "no"):
                read_user = False
                return "Read user input: off"
            return "Usage: /a11y read-user on|off"
        elif cmd == "read-errors":
            if len(parts) < 2:
                return f"Read errors: {'on' if read_errors else 'off'}"
            val = parts[1].lower()
            if val in ("on", "1", "true", "yes"):
                read_errors = True
                return "Read errors: on"
            elif val in ("off", "0", "false", "no"):
                read_errors = False
                return "Read errors: off"
            return "Usage: /a11y read-errors on|off"
        elif cmd == "read-status":
            if len(parts) < 2:
                return f"Read status: {'on' if read_status else 'off'}"
            val = parts[1].lower()
            if val in ("on", "1", "true", "yes"):
                read_status = True
                return "Read status: on"
            elif val in ("off", "0", "false", "no"):
                read_status = False
                return "Read status: off"
            return "Usage: /a11y read-status on|off"
        elif cmd == "detailed":
            if len(parts) < 2:
                return f"Detailed mode: {'on' if detailed_mode else 'off'} (reads full tool output)"
            val = parts[1].lower()
            if val in ("on", "1", "true", "yes"):
                detailed_mode = True
                return "Detailed mode: on (will read full tool output)"
            elif val in ("off", "0", "false", "no"):
                detailed_mode = False
                return "Detailed mode: off (will read friendly summaries only)"
            return "Usage: /a11y detailed on|off"
        elif cmd == "engine":
            available = get_available_engines()
            if len(parts) < 2:
                return f"Current engine: {engine}\nAvailable: {', '.join(available)}"
            new_engine = parts[1].lower()
            if new_engine not in available:
                return f"Engine '{new_engine}' not available. Available: {', '.join(available)}"
            engine = new_engine
            voice = os.environ.get("A11Y_VOICE", DEFAULT_VOICE)
            return f"Engine set to: {engine}\nVoice: {voice}"
        else:
            return ("Usage: /a11y [on|off|status|voice|limit|tool-limit|speed|read-*|detailed|engine]\n"
                    "  /a11y on              - Enable accessibility\n"
                    "  /a11y off             - Disable accessibility\n"
                    "  /a11y status          - Show current settings\n"
                    "  /a11y voice <name>    - Set voice\n"
                    "  /a11y limit <n>       - AI word limit (0 = none)\n"
                    "  /a11y tool-limit <n>  - Tool output limit\n"
                    "  /a11y speed <wpm>     - Speech speed\n"
                    "  /a11y read-code on|off    - Read code blocks\n"
                    "  /a11y read-tools on|off   - Read tool results\n"
                    "  /a11y read-user on|off    - Echo user input\n"
                    "  /a11y read-errors on|off  - Read errors\n"
                    "  /a11y read-status on|off  - Read status\n"
                    "  /a11y detailed on|off     - Read full tool output (vs friendly)\n"
                    "  /a11y engine <name>   - Switch engine")

    # Initialize
    detect_audio_sink()

    # Validate engine
    available = get_available_engines()
    if engine not in available:
        if available:
            engine = available[0]
            voice = os.environ.get("A11Y_VOICE", DEFAULT_VOICE)
            if Config.debug():
                LogUtils.print(f"A11Y: Engine '{os.environ.get('A11Y_ENGINE', DEFAULT_ENGINE)}' not available, using {engine}")
        else:
            if Config.debug():
                LogUtils.error("A11Y: No TTS engine available (install espeak or flite)")
            return

    # Register hooks and commands
    ctx.register_hook("after_assistant_message_added", on_after_assistant_message)
    ctx.register_hook("after_user_message_added", on_after_user_message_added)
    ctx.register_hook("after_tool_results", on_after_tool_results)
    ctx.register_command("/a11y", handle_a11y_command, description="Accessibility settings")

    if Config.debug():
        LogUtils.print("  - after_assistant_message_added hook (A11Y)")
        LogUtils.print("  - after_user_message_added hook (A11Y)")
        LogUtils.print("  - after_tool_results hook (A11Y)")
        LogUtils.print(f"  - /a11y command (engine: {engine}, voice: {voice})")
