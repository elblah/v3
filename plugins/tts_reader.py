"""
TTS Reader Plugin - Read AI responses aloud using espeak or flite

Features:
- Supports espeak and flite engines
- Configurable via environment variables
- Interrupt mode (kills previous TTS when new message arrives)
- HDMI audio sink detection with fallback
- Skip code blocks
- Word limit for responses
- Speed control (espeak native, flite via ffmpeg)
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
DEFAULT_VOICE = "en-us+f3"  # espeak default
DEFAULT_VOICE_FLITE = "slt"  # flite default
DEFAULT_WORD_LIMIT = 40
DEFAULT_SPEED = 175
DEFAULT_SKIP_CODE = True
DEFAULT_ENABLED = False


def create_plugin(ctx):
    """TTS Reader plugin"""

    # Configuration from env vars
    engine = os.environ.get("TTS_ENGINE", DEFAULT_ENGINE).lower()
    word_limit = int(os.environ.get("TTS_WORD_LIMIT", DEFAULT_WORD_LIMIT))
    speed = int(os.environ.get("TTS_SPEED", DEFAULT_SPEED))
    skip_code = os.environ.get("TTS_SKIP_CODE", "1" if DEFAULT_SKIP_CODE else "0") == "1"
    enabled = os.environ.get("TTS_ENABLED", "1" if DEFAULT_ENABLED else "0") == "1"

    # Voice selection based on engine
    default_voice = DEFAULT_VOICE if engine == "espeak" else DEFAULT_VOICE_FLITE
    voice = os.environ.get("TTS_VOICE", default_voice)

    # Audio sink detection (HDMI preferred)
    current_sink = "pipewire/combined"

    # Track current TTS process for interruption
    current_process: Optional[subprocess.Popen] = None

    # Exclude phrases - filter out common filler phrases
    # Format: pipe-separated list, one phrase per line
    exclude_phrases_str = os.environ.get("TTS_EXCLUDE", "")
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

    def strip_code_blocks(text: str) -> str:
        """Remove code blocks from text"""
        if not skip_code:
            return text
        # Remove fenced code blocks
        text = re.sub(r'```[\s\S]*?```', '', text)
        # Remove inline code
        text = re.sub(r'`[^`]+`', '', text)
        return text.strip()

    def strip_markdown(text: str) -> str:
        """Remove markdown formatting"""
        # Remove headers
        text = re.sub(r'^#+\s+', '', text, flags=re.MULTILINE)
        # Remove bold/italic
        text = re.sub(r'\*+([^*]+)\*+', r'\1', text)
        # Remove links
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

    def truncate_to_word_limit(text: str) -> str:
        """Truncate text to word limit at sentence boundary"""
        words = text.split()
        if len(words) <= word_limit:
            return text

        # Take up to word_limit words
        truncated = ' '.join(words[:word_limit])

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
        """Speak using flite (with optional speed via ffmpeg)"""
        tempo = speed / 175.0  # Convert wpm to tempo multiplier

        if abs(tempo - 1.0) < 0.05:
            # Normal speed - no ffmpeg needed
            env = os.environ.copy()
            env["PULSE_SINK"] = current_sink
            return subprocess.Popen(
                ["flite", "-voice", voice, text],
                env=env,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        else:
            # Speed adjustment via ffmpeg
            import tempfile
            with tempfile.NamedTemporaryFile(suffix='.wav', delete=False) as tmp:
                tmp_path = tmp.name

            try:
                # Generate audio file
                subprocess.run(
                    ["flite", "-voice", voice, text, tmp_path],
                    capture_output=True
                )

                # Play with tempo adjustment using paplay with env var
                env = os.environ.copy()
                env["PULSE_SINK"] = current_sink
                proc = subprocess.Popen(
                    ["ffmpeg", "-i", tmp_path, "-af", f"atempo={tempo:.2f}", "-f", "wav", "-"],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.DEVNULL
                )
                # Pipe to paplay
                paplay = subprocess.Popen(
                    ["paplay", f"--device={current_sink}"],
                    stdin=proc.stdout,
                    env=env,
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL
                )
                # Close pipe in parent
                proc.stdout.close()

                # Clean up file after playback
                def cleanup():
                    try:
                        os.unlink(tmp_path)
                    except:
                        pass

                # Schedule cleanup (simple approach)
                import threading
                threading.Timer(5, cleanup).start()

                return proc
            except Exception as e:
                if Config.debug():
                    LogUtils.error(f"TTS flite error: {e}")
                return None

    def extract_tts_content(text: str) -> Optional[str]:
        """Extract content from first <tts> to last </tts> - AI should use only ONE tts block"""
        # Check if both tags exist
        if '<tts>' not in text or '</tts>' not in text:
            return None

        # Find first <tts> and last </tts>
        start_idx = text.find('<tts>')
        end_idx = text.rfind('</tts>')

        if start_idx >= end_idx:
            return None

        # Extract EVERYTHING between tags (including any text between multiple <tts>...</tts> blocks)
        content = text[start_idx + 5:end_idx]
        return content.strip() if content.strip() else None

    def speak(text: str):
        """Speak text using configured engine (interrupts previous)"""
        nonlocal current_process

        if not enabled:
            return

        # Kill previous TTS
        if current_process and current_process.poll() is None:
            current_process.terminate()
            try:
                current_process.wait(timeout=0.5)
            except:
                current_process.kill()

        # Check for [TTS]...[/TTS] tags first
        tts_content = extract_tts_content(text)
        if tts_content:
            text = tts_content
        else:
            # No tags - process text normally
            text = strip_code_blocks(text)
            text = strip_markdown(text)
            text = truncate_to_word_limit(text)

        # Apply exclude filter to remove filler phrases
        text = apply_exclude_filter(text)

        if not text.strip():
            return

        # Speak
        if engine == "espeak":
            current_process = speak_espeak(text)
        elif engine == "flite":
            current_process = speak_flite(text)
        else:
            if Config.debug():
                LogUtils.error(f"Unknown TTS engine: {engine}")

    def generate_tts_instructions() -> str:
        """Generate [TTS_INSTRUCTIONS] message"""
        return """[TTS_INSTRUCTIONS] Text-to-speech is enabled. When you want to emphasize or ensure something is read aloud, wrap it in <tts>...</tts> tags.

IMPORTANT: Use ONLY ONE <tts>...</tts> block per message. The TTS reads everything from the first <tts> to the last </tts>.

Examples:
- End with a question: <tts>What do you think about this approach?</tts>
- Highlight key point: <tts>The most important thing is to backup your data first.</tts>
- Summarize: <tts>So in summary, we need to update three files and restart the server.</tts>

Use a single <tts>...</tts> block for questions, important warnings, or key summaries. Without tags, normal TTS behavior applies."""

    def before_user_prompt():
        """
        Ensure [TTS_INSTRUCTIONS] message exists in history when TTS is enabled
        - Replaces existing [TTS_INSTRUCTIONS] message
        - Adds new one if missing (when enabled)
        - Removes it if TTS is disabled
        """
        message_history = ctx.app.message_history

        if not enabled:
            # Remove [TTS_INSTRUCTIONS] message if present
            for idx, msg in enumerate(message_history.messages):
                content = msg.get("content", "")
                if msg.get("role") == "user" and content.startswith("[TTS_INSTRUCTIONS]"):
                    message_history.messages.pop(idx)
                    return
            return

        # TTS is enabled - ensure message exists
        tts_text = generate_tts_instructions()

        # Find and replace existing [TTS_INSTRUCTIONS] message
        for idx, msg in enumerate(message_history.messages):
            content = msg.get("content", "")
            if msg.get("role") == "user" and content.startswith("[TTS_INSTRUCTIONS]"):
                message_history.messages[idx]["content"] = tts_text
                return

        # Add if missing (after system message at index 0, before first user message)
        insert_idx = 1
        message_history.messages.insert(insert_idx, {
            "role": "user",
            "content": tts_text
        })

    def on_after_assistant_message(assistant_message: dict):
        """Hook: Called after AI adds assistant message"""
        content = assistant_message.get("content", "")
        if content:
            speak(content)

    def handle_tts_command(args_str: str):
        """Handle /tts command"""
        nonlocal enabled, engine, voice, word_limit, speed, skip_code

        if not args_str:
            # Show status
            status = "enabled" if enabled else "disabled"
            return (f"TTS Reader: {status}\n"
                    f"  Engine: {engine}\n"
                    f"  Voice: {voice}\n"
                    f"  Word limit: {word_limit}\n"
                    f"  Speed: {speed} wpm\n"
                    f"  Skip code: {skip_code}\n"
                    f"  Audio sink: {current_sink}")

        parts = args_str.strip().split()
        if not parts:
            return "Usage: /tts [on|off|status|voice|limit|speed|skip-code|engine]"

        cmd = parts[0].lower()

        if cmd == "on":
            enabled = True
            return "TTS enabled"
        elif cmd == "off":
            enabled = False
            return "TTS disabled"
        elif cmd == "status":
            status = "enabled" if enabled else "disabled"
            return (f"TTS Reader: {status}\n"
                    f"  Engine: {engine}\n"
                    f"  Voice: {voice}\n"
                    f"  Word limit: {word_limit}\n"
                    f"  Speed: {speed} wpm\n"
                    f"  Skip code: {skip_code}")
        elif cmd == "voice":
            if len(parts) < 2:
                return f"Current voice: {voice}\nAvailable voices:\n{list_voices()}"
            if parts[1] == "?" or parts[1] == "list":
                return f"Available voices:\n{list_voices()}"
            voice = parts[1]
            return f"Voice set to: {voice}"
        elif cmd == "limit":
            if len(parts) < 2:
                return f"Current word limit: {word_limit}"
            try:
                word_limit = int(parts[1])
                return f"Word limit set to: {word_limit}"
            except ValueError:
                return "Invalid limit. Usage: /tts limit <number>"
        elif cmd == "speed":
            if len(parts) < 2:
                return f"Current speed: {speed} wpm"
            try:
                speed = int(parts[1])
                return f"Speed set to: {speed} wpm"
            except ValueError:
                return "Invalid speed. Usage: /tts speed <wpm>"
        elif cmd == "skip-code":
            if len(parts) < 2:
                return f"Skip code blocks: {'on' if skip_code else 'off'}"
            val = parts[1].lower()
            if val in ("on", "1", "true", "yes"):
                skip_code = True
                return "Skip code blocks: on"
            elif val in ("off", "0", "false", "no"):
                skip_code = False
                return "Skip code blocks: off"
            return "Usage: /tts skip-code on|off"
        elif cmd == "engine":
            available = get_available_engines()
            if len(parts) < 2:
                return f"Current engine: {engine}\nAvailable: {', '.join(available)}"
            new_engine = parts[1].lower()
            if new_engine not in available:
                return f"Engine '{new_engine}' not available. Available: {', '.join(available)}"
            engine = new_engine
            # Reset voice to default for new engine
            default = DEFAULT_VOICE if engine == "espeak" else DEFAULT_VOICE_FLITE
            voice = os.environ.get("TTS_VOICE", default)
            return f"Engine set to: {engine}\nVoice reset to: {voice}"
        else:
            return ("Usage: /tts [on|off|status|voice|limit|speed|skip-code|engine]\n"
                    "  /tts on          - Enable TTS\n"
                    "  /tts off         - Disable TTS\n"
                    "  /tts status      - Show current settings\n"
                    "  /tts voice <name> - Set voice (use ? to list)\n"
                    "  /tts limit <n>   - Max words to read (default: 40)\n"
                    "  /tts speed <wpm> - Speed in words per minute (default: 175)\n"
                    "  /tts skip-code on|off - Skip code blocks (default: on)\n"
                    "  /tts engine <name> - Switch engine (espeak/flite)")

    # Initialize
    detect_audio_sink()

    # Validate engine
    available = get_available_engines()
    if engine not in available:
        if available:
            engine = available[0]
            default = DEFAULT_VOICE if engine == "espeak" else DEFAULT_VOICE_FLITE
            voice = default
            if Config.debug():
                LogUtils.print(f"TTS: Engine '{os.environ.get('TTS_ENGINE', DEFAULT_ENGINE)}' not available, using {engine}")
        else:
            if Config.debug():
                LogUtils.error("TTS: No TTS engine available (install espeak or flite)")
            return

    # Register hooks and commands
    ctx.register_hook("before_user_prompt", before_user_prompt)
    ctx.register_hook("after_assistant_message_added", on_after_assistant_message)
    ctx.register_command("/tts", handle_tts_command, description="Text-to-speech settings")

    if Config.debug():
        LogUtils.print("  - after_assistant_message_added hook (TTS reader)")
        LogUtils.print(f"  - /tts command (engine: {engine}, voice: {voice})")
