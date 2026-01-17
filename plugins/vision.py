"""
Vision Plugin for AI Coder v3

Enables image input via @/path/to/image syntax.
Supports: PNG, JPEG, GIF, BMP, WebP, TIFF, HEIC

Usage:
    @screenshot.png Analyze this error
    @/absolute/path/to/image.jpg What do you see?
    @a.png @b.jpg Compare these images
"""

import base64
import mimetypes
import os
import re
from typing import Dict, Any, List, Optional


# Supported image formats
SUPPORTED_FORMATS = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".bmp": "image/bmp",
    ".webp": "image/webp",
    ".tiff": "image/tiff",
    ".tif": "image/tiff",
    ".heic": "image/heic",
}


def get_mime_type(file_path: str) -> Optional[str]:
    """Get MIME type for an image file."""
    mime_type, _ = mimetypes.guess_type(file_path)
    if mime_type and mime_type.startswith("image/"):
        return mime_type
    ext = os.path.splitext(file_path)[1].lower()
    return SUPPORTED_FORMATS.get(ext)


def is_supported_image(file_path: str) -> bool:
    """Check if file is a supported image format."""
    ext = os.path.splitext(file_path)[1].lower()
    return ext in SUPPORTED_FORMATS


def encode_image(file_path: str) -> str:
    """Encode image file to base64 string."""
    with open(file_path, "rb") as f:
        binary_data = f.read()
    return base64.b64encode(binary_data).decode("utf-8")


def create_image_content_part(file_path: str) -> Dict[str, Any]:
    """Create an image content part for multimodal API message."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Image not found: {file_path}")

    if not is_supported_image(file_path):
        mime = get_mime_type(file_path)
        raise ValueError(f"Unsupported format: {mime}")

    base64_data = encode_image(file_path)
    mime_type = get_mime_type(file_path)

    return {
        "type": "image_url",
        "image_url": {"url": f"data:{mime_type};base64,{base64_data}"},
    }


def parse_image_references(text: str) -> tuple[str, List[str]]:
    """
    Parse user input for @/path/to/image references.

    Returns:
        tuple: (cleaned_text, list_of_image_paths)
    """
    # Pattern to match @ followed by file path with image extension
    pattern = r"@(\S+\.(?:png|jpe?g|gif|bmp|webp|tiff?|heic))"

    image_paths = []
    for match in re.finditer(pattern, text):
        path = match.group(1)
        image_paths.append(path.strip())

    # Remove @image references from text
    cleaned = re.sub(pattern, "", text).strip()

    return cleaned, image_paths


def create_user_message(text: str, image_paths: List[str]) -> Dict[str, Any]:
    """
    Create a multimodal user message with text and images.

    Args:
        text: Clean user text (without @ references)
        image_paths: List of valid image file paths

    Returns:
        Dict formatted for API (role + content array)
    """
    content_parts = []

    # Add text part if present
    if text.strip():
        content_parts.append({"type": "text", "text": text})

    # Add each valid image
    for path in image_paths:
        try:
            image_part = create_image_content_part(path)
            content_parts.append(image_part)
        except Exception as e:
            # Add error as text part if image fails
            content_parts.append(
                {"type": "text", "text": f"[Error loading image {path}: {e}]"}
            )

    return {"role": "user", "content": content_parts}


def transform_user_input(user_input: str, app) -> Optional[Dict[str, Any]]:
    """
    Hook handler: Transform user input with @image references.

    If images found, returns multimodal message dict.
    If no images, returns None (let core handle normally).
    """
    clean_text, image_paths = parse_image_references(user_input)

    if not image_paths:
        return None  # No images, use normal processing

    # Validate images exist
    valid_images = [p for p in image_paths if os.path.exists(p)]
    missing = [p for p in image_paths if not os.path.exists(p)]

    if not valid_images and missing:
        # Only missing images - return error as text
        error_msgs = " ".join(f"[Image not found: {p}]" for p in missing)
        return {"role": "user", "content": f"{clean_text} {error_msgs}".strip()}

    # Create multimodal message
    message = create_user_message(clean_text, valid_images)

    # Add missing image errors if any
    if missing:
        error_text = " ".join(f"[Image not found: {p}]" for p in missing)
        if message["content"] and isinstance(message["content"], list):
            message["content"].append({"type": "text", "text": error_text})

    return message


def create_plugin(ctx) -> Dict[str, Any]:
    """Create the vision plugin."""

    def after_user_prompt_hook(user_input: str) -> Optional[str]:
        """
        Transform user input containing @image references.

        Returns:
            - None: use original input (no images found)
            - Transformed input string (only errors)
            - Dict: multimodal message (images found)
        """
        result = transform_user_input(user_input, ctx.app)

        # If result is a dict (multimodal message), use add_plugin_message
        if isinstance(result, dict):
            ctx.app.add_plugin_message(result)
            return ""  # Suppress original input

        # If result is a string with errors, return it
        if isinstance(result, str):
            return result

        return None

    ctx.register_hook("after_user_prompt", after_user_prompt_hook)

    return {}
