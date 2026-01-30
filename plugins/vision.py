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

    def format_read_image_args(args):
        """Format read_image arguments for display"""
        path = args.get("path", "")
        full_vision = os.environ.get("AICODER_FULL_VISION", "0") == "1"
        force_ascii = args.get("force_ascii", False)
        if force_ascii:
            mode = "ASCII (forced)"
        else:
            mode = "full vision" if full_vision else "ASCII (chafa)"
        return f"Path: {path}\nMode: {mode}"

    def read_image_tool(args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Read and analyze an image file.

        If AICODER_FULL_VISION=1, sends text confirmation and adds a user message with the image.
        Otherwise, converts the image to ASCII art using chafa.
        """
        file_path = args.get("path", "")

        if not file_path:
            return {
                "tool": "read_image",
                "friendly": "Error: No path provided",
                "detailed": "Please provide a file path to the image."
            }

        if not os.path.exists(file_path):
            return {
                "tool": "read_image",
                "friendly": f"Error: File not found: {file_path}",
                "detailed": f"The file '{file_path}' does not exist."
            }

        if not is_supported_image(file_path):
            return {
                "tool": "read_image",
                "friendly": f"Error: Unsupported image format: {file_path}",
                "detailed": f"Supported formats: {', '.join(SUPPORTED_FORMATS.keys())}"
            }

        full_vision = os.environ.get("AICODER_FULL_VISION", "0") == "1"
        force_ascii = args.get("force_ascii", False)

        if full_vision and not force_ascii:
            try:
                # Add the image as a user message (same as @filename does)
                image_part = create_image_content_part(file_path)
                user_message = {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"This is the image you requested: path={file_path}"},
                        image_part
                    ]
                }
                ctx.app.add_plugin_message(user_message)

                return {
                    "tool": "read_image",
                    "friendly": f"Image loaded: {file_path} (full vision)",
                    "detailed": f"Image loaded: {file_path}. A user message with the image has been added to the conversation."
                }
            except Exception as e:
                return {
                    "tool": "read_image",
                    "friendly": f"Error loading image: {e}",
                    "detailed": str(e)
                }
        else:
            import subprocess
            try:
                result = subprocess.run(
                    ["chafa", "--symbols=block", "--fit-width", "--colors=none", "--size", "120x", file_path],
                    capture_output=True,
                    text=True,
                    timeout=30
                )
                if result.returncode != 0:
                    return {
                        "tool": "read_image",
                        "friendly": f"Error: chafa failed for {file_path}",
                        "detailed": f"chafa error: {result.stderr}"
                    }

                ascii_art = result.stdout
                if len(ascii_art) > 15000:
                    ascii_art = ascii_art[:15000] + "\n[... truncated ...]"

                return {
                    "tool": "read_image",
                    "friendly": f"ASCII representation of {file_path}",
                    "detailed": f"ASCII art of {file_path}:\n```\n{ascii_art}\n```"
                }
            except FileNotFoundError:
                return {
                    "tool": "read_image",
                    "friendly": "Error: chafa not found",
                    "detailed": "chafa is required for ASCII image conversion. Install it or set AICODER_FULL_VISION=1 for full image support."
                }
            except subprocess.TimeoutExpired:
                return {
                    "tool": "read_image",
                    "friendly": "Error: chafa timed out",
                    "detailed": "Image conversion took too long."
                }
            except Exception as e:
                return {
                    "tool": "read_image",
                    "friendly": f"Error converting image: {e}",
                    "detailed": str(e)
                }

    ctx.register_tool(
        "read_image",
        read_image_tool,
        "Read and analyze an image. Uses full vision if AICODER_FULL_VISION=1, otherwise converts to ASCII via chafa.",
        {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the image file"
                },
                "force_ascii": {
                    "type": "boolean",
                    "description": "Force ASCII output even if full vision is available",
                    "default": False
                }
            },
            "required": ["path"]
        },
        format_arguments=format_read_image_args
    )

    return {}
