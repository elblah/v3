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
import os
import re
import shutil
import struct
import subprocess
import tempfile
from typing import Dict, Any, List, Optional

_mime_types_init = False

def _get_mime_types():
    global _mime_types_init
    if not _mime_types_init:
        global mimetypes
        import mimetypes
        _mime_types_init = True
    return mimetypes


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
    mime_type, _ = _get_mime_types().guess_type(file_path)
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


_DEFAULT_MAX_SIZE = 768


def _get_max_size() -> Optional[int]:
    """Parse VISION_MAX_SIZE (longest side). 0/negative = off; unset/invalid = default."""
    raw = os.environ.get("VISION_MAX_SIZE", "").strip()
    if not raw:
        return _DEFAULT_MAX_SIZE
    try:
        n = int(raw)
    except ValueError:
        return _DEFAULT_MAX_SIZE
    return n if n > 0 else None


def _pil_resize(file_path: str, max_size: int) -> str:
    from PIL import Image
    with Image.open(file_path) as im:
        width, height = im.size
        if max(width, height) <= max_size:
            return file_path
        im.thumbnail((max_size, max_size))
        fd, tmp = tempfile.mkstemp(suffix=os.path.splitext(file_path)[1] or ".png")
        os.close(fd)
        try:
            im.save(tmp, quality=85)
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
        return tmp


def _subprocess_resize_tool(tool_args_fn):
    """Factory for subprocess-based resizers: run tool, return temp path or raise."""
    def resize(file_path: str, max_size: int) -> str:
        fd, tmp = tempfile.mkstemp(suffix=os.path.splitext(file_path)[1] or ".png")
        os.close(fd)
        try:
            subprocess.run(
                tool_args_fn(file_path, tmp, max_size),
                check=True, capture_output=True, timeout=60,
            )
            return tmp
        except Exception:
            try:
                os.unlink(tmp)
            except OSError:
                pass
            raise
    return resize


def _imagemagick_resize(file_path: str, max_size: int) -> str:
    for exe in ("magick", "convert"):
        tool = shutil.which(exe)
        if not tool:
            continue
        return _subprocess_resize_tool(
            lambda fp, tmp, ms, t=tool: [t, fp, "-resize", f"{ms}x{ms}>", tmp]
        )(file_path, max_size)
    raise RuntimeError("no imagemagick binary")


def _ffmpeg_resize(file_path: str, max_size: int) -> str:
    tool = shutil.which("ffmpeg")
    if not tool:
        raise RuntimeError("no ffmpeg binary")
    return _subprocess_resize_tool(
        lambda fp, tmp, ms: [
            tool, "-y", "-i", fp,
            "-vf", f"scale={ms}:{ms}:force_original_aspect_ratio=decrease",
            tmp,
        ]
    )(file_path, max_size)


def _graphicsmagick_resize(file_path: str, max_size: int) -> str:
    tool = shutil.which("gm")
    if not tool:
        raise RuntimeError("no gm binary")
    return _subprocess_resize_tool(
        lambda fp, tmp, ms: [tool, "convert", fp, "-resize", f"{ms}x{ms}>", tmp]
    )(file_path, max_size)


def _opencv_resize(file_path: str, max_size: int) -> str:
    import cv2
    img = cv2.imread(file_path, cv2.IMREAD_UNCHANGED)
    if img is None:
        raise ValueError(f"cv2 cannot read {file_path}")
    height, width = img.shape[:2]
    if max(width, height) <= max_size:
        return file_path
    scale = max_size / float(max(width, height))
    new_size = (max(1, round(width * scale)), max(1, round(height * scale)))
    resized = cv2.resize(img, new_size, interpolation=cv2.INTER_AREA)
    fd, tmp = tempfile.mkstemp(suffix=os.path.splitext(file_path)[1] or ".png")
    os.close(fd)
    try:
        if not cv2.imwrite(tmp, resized):
            raise ValueError("cv2.imwrite failed")
        return tmp
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


# External tools first (zero memory footprint on the host process), then the
# cheap in-proc lib, then cv2 last: its 100MB+ import is a heavy last resort.
# rpi3 benchmark (1920x1080 -> <=1024, host wall): ffmpeg 2.2s, convert 2.6s,
# magick 2.9s, PIL 1.4s, cv2 0.3s but +23s cold import / +109MB RSS.
_RESIZE_BACKENDS = (
    _imagemagick_resize,
    _ffmpeg_resize,
    _pil_resize,
    _graphicsmagick_resize,
    _opencv_resize,
)


def _parse_file_dimensions(stdout: str) -> Optional[tuple[int, int]]:
    """Last WxH pair in `file -b` output. JPEG output reads "density 300x300
    ..., precision 8, 1024x786, components 3" — the size always trails the
    density, so take the last match (matches the gateway's greedy sed).
    """
    matches = re.findall(r"(\d+)\s*x\s*(\d+)", stdout)
    if not matches:
        return None
    w, h = matches[-1]
    return int(w), int(h)


def _image_dimensions(file_path: str) -> Optional[tuple[int, int]]:
    """Image dimensions for the early-out. Tries the `file` utility
    (header-only, fast); falls back to an in-process PNG/JPEG header parse
    when `file` is missing. Returns None when the size can't be determined
    (e.g. SVG) — never fatal, the resize chain just runs as before.
    """
    try:
        result = subprocess.run(
            ["file", "-b", file_path],
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        result = None
    if result is not None and result.returncode == 0:
        dims = _parse_file_dimensions(result.stdout)
        if dims is not None:
            return dims
    return _header_dimensions(file_path)


def _header_dimensions(file_path: str) -> Optional[tuple[int, int]]:
    """In-process fallback: PNG + JPEG only (covers the images people actually
    send). Magic-byte verified, so wrong file extensions don't matter.
    """
    try:
        with open(file_path, "rb") as f:
            head = f.read(24)
        if head[:8] == b"\x89PNG\r\n\x1a\n":
            # IHDR: 8 sig + 4 len + 4 "IHDR" + 4+4 = w/h at offset 16.
            return struct.unpack(">II", head[16:24])
        if head[:2] == b"\xff\xd8":
            return _jpeg_dimensions(file_path)
    except Exception:
        return None
    return None


def _jpeg_dimensions(file_path: str) -> Optional[tuple[int, int]]:
    """Scan JPEG segments (skip APPn/COM/DQT/etc by length) until an SOF
    marker; height/width live right after it. 64KB cap, corrupt => None.
    """
    try:
        with open(file_path, "rb") as f:
            data = f.read(65536)
        i = 2
        n = len(data)
        while i + 9 < n:
            if data[i] != 0xFF:
                i += 1
                continue
            marker = data[i + 1]
            if marker in (
                0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7,
                0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF,
            ):
                # FF C0 len(2) precision(1) height(2) width(2)
                h, w = struct.unpack(">HH", data[i + 5 : i + 9])
                return w, h
            if marker == 0xDA:  # reached scan data without an SOF: corrupt
                return None
            if marker in (0xFF, 0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                i += 2  # padding / SOI / TEM / RSTn: no length field
                continue
            seg_len = struct.unpack(">H", data[i + 2 : i + 4])[0]
            if seg_len < 2:
                return None
            i += 2 + seg_len
    except Exception:
        return None
    return None


def _try_backend(backend, file_path: str, max_size: int) -> Optional[str]:
    try:
        return backend(file_path, max_size)
    except Exception:
        return None  # best-effort: next backend, or original path


def _resize_image(file_path: str, max_size: int) -> str:
    """
    Best-effort downscale so the longest side is <= max_size (aspect preserved,
    never upscales). Returns the path to a resized temp copy, or the original
    path when it already fits or no backend can handle it.
    """
    if max_size <= 0:
        return file_path
    dims = _image_dimensions(file_path)
    if dims is not None and max(dims) <= max_size:
        return file_path  # already fits: no re-encode, send as-is
    for backend in _RESIZE_BACKENDS:
        result = _try_backend(backend, file_path, max_size)
        if result is not None:
            return result
    return file_path


def _is_anthropic_provider() -> bool:
    return os.environ.get("API_PROVIDER", "").lower() == "anthropic"


def create_image_content_part(file_path: str) -> Dict[str, Any]:
    """Create an image content part for multimodal API message."""
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"Image not found: {file_path}")

    if not is_supported_image(file_path):
        mime = get_mime_type(file_path)
        raise ValueError(f"Unsupported format: {mime}")

    resize_path = file_path
    max_size = _get_max_size()
    if max_size:
        resize_path = _resize_image(file_path, max_size)
    try:
        base64_data = encode_image(resize_path)
    finally:
        if resize_path != file_path:
            try:
                os.unlink(resize_path)
            except OSError:
                pass
    mime_type = get_mime_type(file_path)

    if _is_anthropic_provider():
        return {
            "type": "image",
            "source": {
                "type": "base64",
                "media_type": mime_type,
                "data": base64_data,
            },
        }

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
        query = args.get("query", "").strip()
        if _vision_script_path():
            mode = "gateway (VISION_SCRIPT)"
        else:
            mode = "native vision (image injection)"
        out = f"Path: {path}\nMode: {mode}"
        if query:
            out += f"\nAsk: {query}"
        return out

    def _vision_script_path():
        """Return the VISION_SCRIPT path if configured and usable, else None."""
        script = os.environ.get("VISION_SCRIPT", "").strip()
        if not script:
            return None
        if os.path.isabs(script):
            return script if os.path.exists(script) else None
        found = shutil.which(script)
        return found if found and os.path.exists(found) else None

    def read_image_tool(args: Dict[str, Any]) -> Dict[str, Any]:
        """
        Read and analyze an image file.

        If VISION_SCRIPT is configured (and exists), the image is sent to that
        gateway script (e.g. dtx vision) and its stdout is returned as the
        description. Otherwise the raw image is injected for native vision models.
        """
        file_path = args.get("path", "")
        query = args.get("query", "").strip()

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

        script = _vision_script_path()
        if script:
            try:
                cmd = [script, file_path]
                if query:
                    cmd.append(query)
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=120
                )
                if result.returncode != 0:
                    detail = result.stderr.strip() or result.stdout.strip() or "gateway returned non-zero exit"
                    return {
                        "tool": "read_image",
                        "friendly": f"Error: vision gateway failed for {file_path}",
                        "detailed": f"Gateway error (exit {result.returncode}): {detail}"
                    }
                description = result.stdout.strip()
                if not description:
                    return {
                        "tool": "read_image",
                        "friendly": f"Error: vision gateway returned no output for {file_path}",
                        "detailed": "The VISION_SCRIPT produced no description on stdout."
                    }
                return {
                    "tool": "read_image",
                    "friendly": f"Image analyzed via gateway: {file_path}",
                    "detailed": f"Vision gateway description of {file_path}:\n{description}"
                }
            except FileNotFoundError:
                return {
                    "tool": "read_image",
                    "friendly": "Error: VISION_SCRIPT not found",
                    "detailed": f"The configured VISION_SCRIPT '{script}' could not be executed."
                }
            except subprocess.TimeoutExpired:
                return {
                    "tool": "read_image",
                    "friendly": "Error: vision gateway timed out",
                    "detailed": "Vision gateway took too long (120s)."
                }
            except Exception as e:
                return {
                    "tool": "read_image",
                    "friendly": f"Error running vision gateway: {e}",
                    "detailed": str(e)
                }
        else:
            # No gateway: inject raw image for native vision models.
            try:
                image_part = create_image_content_part(file_path)
                ask = f"\nYou asked to analyze this image; instruction: {query}" if query else ""
                user_message = {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": f"This is the image you requested: path={file_path}.{ask}"},
                        image_part
                    ]
                }
                ctx.app.add_plugin_message(user_message)

                return {
                    "tool": "read_image",
                    "friendly": f"Image loaded: {file_path} (native vision)",
                    "detailed": f"Image loaded: {file_path}. A user message with the image has been added to the conversation."
                }
            except Exception as e:
                return {
                    "tool": "read_image",
                    "friendly": f"Error loading image: {e}",
                    "detailed": str(e)
                }

    # NOTE: register/unregister manipulate tool_manager.tools DIRECTLY (same
    # pattern as python_runtime). ctx.register_tool writes to plugin_system.tools,
    # which is only synced into tool_manager at startup — a runtime toggle via
    # ctx.register_tool would never reach the API schema or /tools.
    _read_image_tool_def = {
        "execute": read_image_tool,
        "description": ("Read and analyze an image. Uses VISION_SCRIPT gateway if configured, "
                        "otherwise injects the raw image for native vision models. Always pass a "
                        "'query' describing exactly what you want to know or do with the image."),
        "parameters": {
            "type": "object",
            "properties": {
                "path": {
                    "type": "string",
                    "description": "Path to the image file"
                },
                "query": {
                    "type": "string",
                    "description": "What to ask the vision service about the image, e.g. 'what text is on the screen?'"
                }
            },
            "required": ["path"]
        },
        "auto_approved": False,
        "formatArguments": format_read_image_args,
    }

    def _register_read_image():
        """Make read_image available to the AI (idempotent)."""
        if ctx.app and ctx.app.tool_manager and "read_image" not in ctx.app.tool_manager.tools:
            ctx.app.tool_manager.tools["read_image"] = _read_image_tool_def

    def _unregister_read_image():
        """Remove read_image from the AI's available tools (idempotent)."""
        if ctx.app and ctx.app.tool_manager and "read_image" in ctx.app.tool_manager.tools:
            del ctx.app.tool_manager.tools["read_image"]

    def _handle_vision_command(args_str: str) -> str:
        """Handle /vision command: on | off | status | help."""
        sub = args_str.strip()
        if not sub or sub == "help":
            return (
                "Vision Plugin\n\n"
                "Control the read_image tool. The tool is gated and never auto-registers\n"
                "for blind (non-vision) models unless explicitly enabled.\n\n"
                "    /vision on      - Enable read_image tool\n"
                "    /vision off     - Disable read_image tool\n"
                "    /vision status  - Show current state and mode\n"
                "    /vision help    - Show this message\n\n"
                "Mode: if VISION_SCRIPT is set and resolves to an executable, read_image\n"
                "bridges to that gateway (e.g. dtx). Otherwise it injects the image for\n"
                "native vision models.\n\n"
                "Resize: VISION_MAX_SIZE env downscales the longest side before\n"
                "base64 injection (external tools first, best effort). Default 768;\n"
                "use VISION_MAX_SIZE=0 to disable. Example: VISION_MAX_SIZE=1024."
            )
        if sub == "on":
            _register_read_image()
            return "Vision ENABLED — read_image tool is now available."
        if sub == "off":
            _unregister_read_image()
            return "Vision DISABLED — read_image tool removed."
        if sub == "status":
            registered = "read_image" in ctx.app.tool_manager.tools
            script = _vision_script_path()
            env_script = os.environ.get("VISION_SCRIPT", "").strip()
            if script:
                mode = f"gateway: {script}"
            elif env_script:
                mode = f"gateway configured but NOT FOUND: {env_script}"
            else:
                mode = "no gateway (native injection)"
            resize = _get_max_size()
            resize_info = (
                f"longest side <= {resize}px (VISION_MAX_SIZE)" if resize
                else "disabled (no VISION_MAX_SIZE)"
            )
            return (
                f"read_image tool: {'ENABLED' if registered else 'DISABLED'}\n"
                f"Mode: {mode}\n"
                f"Resize before injection: {resize_info}"
            )
        return f"Unknown subcommand: {sub}\nUsage: /vision [on|off|status|help]"

    ctx.register_command("vision", _handle_vision_command, "Control the read_image vision tool (on|off|status)")

    # Auto-enable read_image only when a gateway is configured or explicitly requested.
    if _vision_script_path() or os.environ.get("VISION_ENABLE_TOOL", "0") == "1":
        _register_read_image()

    # Screenshot command
    def has_x11_access():
        """Check if X11 display is accessible."""
        result = subprocess.run(["xset", "q"], capture_output=True)
        return result.returncode == 0

    def _handle_screenshot(args: str):
        """Handle /screenshot and /ss commands."""
        screenshot_path = "/tmp/screenshot.png"

        if not has_x11_access():
            print("Error: No X11 access. Run 'xhost +' on your host.")
            return

        if not shutil.which("flameshot"):
            print("Error: flameshot not found.")
            return

        print("Launching Flameshot...")
        result = subprocess.run(["flameshot", "gui", "--path", screenshot_path])
        if result.returncode != 0 or not os.path.exists(screenshot_path):
            print("Screenshot cancelled.")
            return

        try:
            image_part = create_image_content_part(screenshot_path)
            ctx.app.add_plugin_message({
                "role": "user",
                "content": [
                    {"type": "text", "text": "Screenshot taken:"},
                    image_part
                ]
            })
            print("Screenshot added to conversation.")
        except Exception as e:
            print(f"Error: {e}")
        finally:
            if os.path.exists(screenshot_path):
                os.remove(screenshot_path)

    ctx.register_command("screenshot", _handle_screenshot, "Take a screenshot with flameshot")
    ctx.register_command("ss", _handle_screenshot, "Alias for /screenshot")

    return {}
