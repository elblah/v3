"""
Audio Plugin for AI Coder v3

Enables audio input via @/path/to/audio.mp3 syntax.
Supports: MP3, WAV, OGG, FLAC, AAC, M4A

Usage:
    @song.mp3 What's this song?
    @/absolute/path/to/audio.wav Transcribe this
"""

import base64
import os
import re
from typing import Dict, Any, List, Optional


SUPPORTED_FORMATS = {
    ".mp3": "audio/mpeg",
    ".wav": "audio/wav",
    ".ogg": "audio/ogg",
    ".flac": "audio/flac",
    ".aac": "audio/aac",
    ".m4a": "audio/mp4",
    ".opus": "audio/opus",
}


def is_supported_audio(file_path: str) -> bool:
    ext = os.path.splitext(file_path)[1].lower()
    return ext in SUPPORTED_FORMATS


def encode_audio(file_path: str) -> str:
    with open(file_path, "rb") as f:
        return base64.b64encode(f.read()).decode("utf-8")


def create_audio_content_part(file_path: str) -> Dict[str, Any]:
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Audio not found: {file_path}")
    if not is_supported_audio(file_path):
        raise ValueError(f"Unsupported format: {file_path}")

    ext = os.path.splitext(file_path)[1].lower()
    media_type = SUPPORTED_FORMATS[ext]
    data = encode_audio(file_path)

    # Anthropic format vs OpenAI format
    if os.environ.get("API_PROVIDER", "").lower() == "anthropic":
        # NOTE: Anthropic Messages API does NOT officially support audio input.
        # This format is based on GitHub issue #1198 feature request (Feb 2026).
        # May not work until Anthropic adds official support.
        return {
            "type": "audio",
            "source": {
                "type": "base64",
                "media_type": media_type,
                "data": data,
            },
        }
    else:
        # OpenAI and compatible providers (verified working)
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


def create_plugin(ctx) -> Dict[str, Any]:
    def after_user_prompt_hook(user_input: str) -> Optional[str]:
        clean_text, audio_paths = parse_audio_references(user_input)
        if not audio_paths:
            return None

        valid = [p for p in audio_paths if os.path.exists(p)]
        missing = [p for p in audio_paths if not os.path.exists(p)]

        if not valid:
            return {"role": "user", "content": f"{clean_text} {' '.join(f'[Audio not found: {p}]' for p in missing)}"}

        content = [{"type": "text", "text": clean_text}] if clean_text else []
        for path in valid:
            try:
                content.append(create_audio_content_part(path))
            except Exception as e:
                content.append({"type": "text", "text": f"[Error loading audio {path}: {e}]"})

        if missing:
            content.append({"type": "text", "text": " ".join(f"[Audio not found: {p}]" for p in missing)})

        ctx.app.add_plugin_message({"role": "user", "content": content})
        return ""

    ctx.register_hook("after_user_prompt", after_user_prompt_hook)
    return {"name": "audio"}
