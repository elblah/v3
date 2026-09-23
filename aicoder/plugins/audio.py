"""
Audio Plugin for AI Coder v3

Enables audio input via @/path/to/audio.mp3 syntax.
Supports: MP3, WAV, OGG, FLAC, AAC, M4A, OPUS

Provider wire formats:
- Default (chat completions): OpenAI `input_audio` content part.
- API_PROVIDER=responses: same part; responses_client converts it into a
  Responses API input_audio item.
- API_PROVIDER=anthropic: Anthropic-format input_audio block with base64
  source (accepted by Anthropic-format endpoints/proxies; the official
  Anthropic Messages API does not accept audio input yet).

Usage:
    @song.mp3 What's this song?
    @/absolute/path/to/audio.wav Transcribe this
"""

import base64
import os
import re
from typing import Dict, Any, List, Optional

# Supported audio formats
SUPPORTED_FORMATS = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".aac": "audio/aac",
    ".m4a": "audio/mp4",
    ".opus": "audio/opus",
}

# Refuse files bigger than this (base64 inflates payload ~33%). Override in MB.
MAX_AUDIO_MB = float(os.environ.get("AICODER_AUDIO_MAX_MB", "25"))


def _is_anthropic_provider() -> bool:
    return os.environ.get("API_PROVIDER", "").lower() == "anthropic"


def is_supported_audio(file_path: str) -> bool:
    ext = os.path.splitext(file_path)[1].lower()
    return ext in SUPPORTED_FORMATS


def encode_audio(file_path: str) -> str:
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def create_audio_content_part(file_path: str) -> Dict[str, Any]:
    """Create an audio content part shaped for the active API provider."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Audio not found: {file_path}")
    if not is_supported_audio(file_path):
        raise ValueError(f"Unsupported format: {file_path}")

    size_mb = os.path.getsize(file_path) / (1024 * 1024)
    if size_mb > MAX_AUDIO_MB:
        raise ValueError(
            f"Audio too large: {size_mb:.1f} MB > {MAX_AUDIO_MB:g} MB cap "
            "(AICODER_AUDIO_MAX_MB)"
        )

    ext = os.path.splitext(file_path)[1].lower()
    media_type = SUPPORTED_FORMATS[ext]
    data = encode_audio(file_path)

    if _is_anthropic_provider():
        # Anthropic-format block: base64 source, mirrors image block layout.
        return {
            "type": "input_audio",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": data,
            },
        }

    # OpenAI chat completions (and Responses input via responses_client).
    return {
        "type": "input_audio",
        "input_audio": {
            "data": data,
            "format": ext.lstrip("."),
        },
    }


def parse_audio_references(text: str) -> tuple[str, List[str]]:
    pattern = r"@(\S+\.(?:mp3|wav|ogg|flac|aac|m4a|opus))"
    audio_paths = [m.group(1) for m in re.finditer(pattern, text)]
    cleaned = re.sub(pattern, "", text).strip()
    return cleaned, audio_paths


def transform_user_input(user_input: str) -> Optional[Any]:
    """Transform user input containing @audio references.

    Returns dict (multimodal message), string (error text), or None (no
    audio found, let other hooks handle the input).
    """
    clean_text, audio_paths = parse_audio_references(user_input)
    if not audio_paths:
        return None

    valid = [p for p in audio_paths if os.path.exists(p)]
    missing = [p for p in audio_paths if not os.path.exists(p)]

    if not valid:
        return f"{clean_text} {' '.join(f'[Audio not found: {p}]' for p in missing)}".strip()

    content = [{"type": "text", "text": clean_text}] if clean_text else []
    for path in valid:
        try:
            content.append(create_audio_content_part(path))
        except Exception as e:
            content.append({"type": "text", "text": f"[Error loading audio {path}: {e}]"})

    if missing:
        content.append({"type": "text", "text": " ".join(f"[Audio not found: {p}]" for p in missing)})

    return {"role": "user", "content": content}


def create_plugin(ctx) -> Dict[str, Any]:
    def after_user_prompt_hook(user_input: str) -> Optional[str]:
        result = transform_user_input(user_input)

        if result is None:
            return None  # No audio, use normal processing

        # Multimodal message: inject it, then return None (NOT ""). The prompt
        # chain passes each hook's return value to the next hook, so returning
        # "" here would starve the vision hook of the original @image text.
        if isinstance(result, dict):
            ctx.app.add_plugin_message(result)
            return None

        # Error text (missing/unsupported files)
        return result

    ctx.register_hook("after_user_prompt", after_user_prompt_hook)
    return {"name": "audio"}
