"""Free text-to-image generation through the Pollinations Classic API.

The AI calls the ``generate_image`` tool with a prompt and the path where the
picture must be saved. The image is downloaded with the standard library (no
dependencies), verified to really be an image, and written atomically to disk.
The tool returns the saved path, so the AI can inspect the result with the
``read_image`` tool and, if the picture is wrong, call the tool again with a
better prompt or another seed.

Service behaviour (measured Nov 2026 against the live API, see APIDOCS.md of
the pollinations repo):

- endpoint: ``https://image.pollinations.ai/prompt/<url-encoded prompt>``
- free, no API key needed, rate limited per IP: ONE image every 45 seconds.
  A request inside that window answers HTTP 402 with a ``Retry-After`` header
  (seconds) and a JSON body repeating the same number.
- the classic endpoint serves a single image model ("sana" behind the ``flux``
  name), always JPEG, and caps the area at 768x768 while keeping the aspect
  ratio (measured: 2048x2048 -> 768x768, 1600x400 -> 1536x384). A small
  "pollinations.ai" logo is baked into the bottom-right corner; the ``nologo``
  flag is sent but does not remove it on the free tier.
- identical prompt + size + seed is served from cache (instant, and it does not
  count against the 45 second window).
- models that belong to the paid API (kontext, seedream, nanobanana, ...)
  answer HTTP 403 "isn't part of the Classic API"; that is permanent, not a
  rate limit, so the tool fails fast instead of wasting the wait. An unknown
  model name is NOT rejected: the service silently serves the classic backend
  model (measured: model=bogusmodel -> 200, EXIF manufacturer=sana). The local
  allowlist therefore exists only to catch typos and paid-model names early.

Because one image per 45 seconds is slow, the tool can wait for the next free
slot and retry automatically (``wait`` + ``max_wait``). When it does not wait it
reports the exact number of seconds to wait, so the caller decides.

Environment variables:

- ``POLLINATIONS_MODELS``   - comma separated list of allowed models, use it
  when the service adds or drops names (default "flux,sana,turbo").
- ``POLLINATIONS_TIMEOUT``  - single request timeout in seconds (default 120).
- ``POLLINATIONS_MAX_WAIT`` - default upper bound for automatic waiting (90).
- ``POLLINATIONS_TOKEN``    - optional pollen key, sent as a bearer token for
  callers that want it; the classic endpoint does not need one.
- ``POLLINATIONS_DISABLED`` - set to a truthy value to keep the tool out.
"""

from __future__ import annotations

import os
import random
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Dict, Optional, Tuple

from aicoder.utils.bool_utils import env_bool
from aicoder.utils.log import LogUtils

BASE_URL = "https://image.pollinations.ai/prompt/"

# Classic API defaults, straight from the published docs.
DEFAULT_MODEL = "flux"
DEFAULT_WIDTH = 1024
DEFAULT_HEIGHT = 1024
REQUEST_MIN_SIDE = 16
REQUEST_MAX_SIDE = 4096
# The free tier caps the pixel AREA at 768*768 and keeps the aspect ratio.
FREE_MAX_AREA = 768 * 768
RATE_LIMIT_SECONDS = 45

FALLBACK_MODELS = ("flux", "sana", "turbo")

DESCRIPTION = (
    "Generate an image from a text prompt with the free Pollinations API and "
    "save it to a file. Give the prompt and the destination path (relative to "
    "the working directory, e.g. 'assets/hero.jpg'). The tool downloads a real "
    "JPEG/PNG and returns the path, the actual pixel size and the seed used. "
    "Afterwards read the saved file with the read_image tool to check whether "
    "the picture is acceptable; if not, call generate_image again with a better "
    "prompt or another seed (same prompt + same seed + same size = same image). "
    "The free service allows ONE image every 45 seconds per IP: with wait=true "
    "(default) the tool sleeps for the next free slot up to max_wait seconds; "
    "with wait=false it returns immediately telling how many seconds remain. "
    "Free images are capped at an area of 768x768 with the aspect ratio kept "
    "and carry a small logo. Models outside the classic tier (kontext, "
    "seedream, nanobanana, ...) are rejected by the service and fail fast."
)

PARAMETERS = {
    "type": "object",
    "properties": {
        "prompt": {
            "type": "string",
            "description": (
                "Text description of the image. Be concrete: subject, style, "
                "lighting, colors, composition, camera framing."
            ),
        },
        "path": {
            "type": "string",
            "description": (
                "Destination file, relative to the working directory "
                "(e.g. 'out/cover.jpg'). Missing extension becomes '.jpg'. "
                "Missing parent directories are created. Absolute paths are "
                "only accepted inside the writable roots."
            ),
        },
        "width": {
            "type": "integer",
            "description": (
                f"Requested width in pixels ({REQUEST_MIN_SIDE}-"
                f"{REQUEST_MAX_SIDE}). The free tier rescales to a maximum "
                "area of 768x768, aspect ratio kept."
            ),
        },
        "height": {
            "type": "integer",
            "description": f"Requested height in pixels ({REQUEST_MIN_SIDE}-{REQUEST_MAX_SIDE}).",
        },
        "seed": {
            "type": "integer",
            "description": (
                "Seed for reproducibility. Omitted = random, and the chosen "
                "seed is reported so the image can be re-requested or varied."
            ),
        },
        "model": {
            "type": "string",
            "description": (
                "Model name. The classic free endpoint serves 'flux' (default). "
                "Paid-only models are refused by the service. Unknown names are "
                "silently served by the classic backend."
            ),
        },
        "safe": {
            "type": "boolean",
            "description": "Ask the server for stricter content filtering.",
        },
        "wait": {
            "type": "boolean",
            "description": (
                "Wait for the next free slot when rate limited (default true). "
                "Set false to get the retry delay back immediately."
            ),
        },
        "max_wait": {
            "type": "integer",
            "description": (
                "Upper bound in seconds for automatic waiting (default 90). "
                "If the service asks for longer, the tool returns instead."
            ),
        },
        "overwrite": {
            "type": "boolean",
            "description": "Replace an existing file (default false).",
        },
    },
    "required": ["prompt", "path"],
}


class ImageError(RuntimeError):
    """Base error for image generation failures."""


class RateLimitError(ImageError):
    """The free per-IP window is closed; nothing was downloaded."""

    def __init__(self, message: str, retry_after: int):
        super().__init__(message)
        self.retry_after = retry_after


# --------------------------------------------------------------- image sniff

_JPEG_SOF = {0xC0, 0xC1, 0xC2, 0xC3, 0xC5, 0xC6, 0xC7, 0xC9, 0xCA, 0xCB, 0xCD, 0xCE, 0xCF}


def image_info(data: bytes) -> Optional[Tuple[str, int, int]]:
    """Return (format, width, height) for JPEG/PNG/GIF/WebP, else None.

    Works on the downloaded bytes only: no ffmpeg, no Pillow. This doubles as
    the "is it really an image" check and as the source of the real size (the
    server silently rescales to the free tier cap).
    """
    if len(data) < 32:
        return None

    if data.startswith(b"\x89PNG\r\n\x1a\n") and data[12:16] == b"IHDR":
        width = int.from_bytes(data[16:20], "big")
        height = int.from_bytes(data[20:24], "big")
        return ("png", width, height) if width and height else None

    if data.startswith(b"GIF8"):
        width = int.from_bytes(data[6:8], "little")
        height = int.from_bytes(data[8:10], "little")
        return ("gif", width, height) if width and height else None

    if data.startswith(b"RIFF") and data[8:12] == b"WEBP":
        return ("webp", 0, 0)

    if data.startswith(b"\xff\xd8"):
        index = 2
        limit = len(data)
        while index + 9 < limit:
            if data[index] != 0xFF:
                index += 1
                continue
            marker = data[index + 1]
            if marker in (0xD8, 0x01) or 0xD0 <= marker <= 0xD7:
                index += 2
                continue
            if marker == 0xD9:
                break
            segment_length = int.from_bytes(data[index + 2:index + 4], "big")
            if segment_length < 2:
                break
            if marker in _JPEG_SOF:
                height = int.from_bytes(data[index + 5:index + 7], "big")
                width = int.from_bytes(data[index + 7:index + 9], "big")
                return ("jpg", width, height) if width and height else ("jpg", 0, 0)
            index += 2 + segment_length
        return ("jpg", 0, 0)

    return None


# ---------------------------------------------------------------------- urls


def allowed_models() -> Tuple[str, ...]:
    """Model allowlist: configurable through POLLINATIONS_MODELS."""
    raw = os.environ.get("POLLINATIONS_MODELS", "").strip()
    if not raw:
        return FALLBACK_MODELS
    names = tuple(part.strip() for part in raw.split(",") if part.strip())
    return names or FALLBACK_MODELS


def build_url(
    prompt: str,
    width: int,
    height: int,
    model: str,
    seed: int,
    safe: bool = False,
) -> str:
    """Build the Pollinations GET URL for one image."""
    encoded = urllib.parse.quote(prompt.strip(), safe="")
    query = {
        "width": str(width),
        "height": str(height),
        "model": model,
        "seed": str(seed),
        "nologo": "true",
    }
    if safe:
        query["safe"] = "true"
    return f"{BASE_URL}{encoded}?{urllib.parse.urlencode(query)}"


def resolve_destination(path: str, root: Optional[str] = None) -> str:
    """Resolve the output path and keep it inside the writable roots.

    Anything else is rejected before a single byte is fetched.
    """
    if not isinstance(path, str) or not path.strip():
        raise ValueError("path is required (e.g. 'out/cover.jpg')")

    root_path = os.path.realpath(root or os.getcwd())
    raw = os.path.expanduser(path.strip())
    target = raw if os.path.isabs(raw) else os.path.join(root_path, raw)
    target = os.path.realpath(target)

    allowed = (root_path, os.path.realpath("/mnt/shared"), os.path.realpath("/tmp"))
    if not any(target == base or target.startswith(base + os.sep) for base in allowed):
        raise ValueError(
            f"path '{path}' resolves to '{target}', outside the writable roots "
            f"({', '.join(sorted(allowed))})"
        )
    if os.path.isdir(target):
        raise ValueError(f"path '{path}' is an existing directory")
    return target


# ------------------------------------------------------------------ download


def _retry_after_seconds(headers: Any, body: str) -> int:
    """Seconds until the next free slot, from Retry-After or the JSON body."""
    header = ""
    try:
        header = (headers or {}).get("Retry-After", "") or ""
    except Exception:
        header = ""
    match = re.search(r"\d+", header)
    if match:
        return max(1, int(match.group(0)))
    match = re.search(r"Retry after (\d+)s", body)
    if match:
        return max(1, int(match.group(1)))
    match = re.search(r'"retry_after"\s*:\s*(\d+)', body)
    if match:
        return max(1, int(match.group(1)))
    return RATE_LIMIT_SECONDS


def _describe_http_error(code: int, reason: str, body: str) -> str:
    """Translate an HTTP error into an actionable one-line explanation."""
    detail = body.strip()
    if '"message"' in detail:
        match = re.search(r'"message"\s*:\s*"([^"]{0,300})"', detail)
        if match:
            detail = match.group(1)
    detail = detail[:300]

    if code in (401, 402, 429):
        return f"rate limited by the free tier (HTTP {code}): {detail or reason}"
    if code == 403:
        if "classic api" in detail.lower():
            return (
                f"HTTP 403: the service refuses this model on the free classic "
                f"endpoint ({detail}). Pick another model instead of retrying."
            )
        return f"HTTP 403 forbidden: {detail or reason}"
    if code == 404:
        return f"HTTP 404: endpoint or prompt path not found ({detail or reason})"
    if 400 <= code < 500:
        return f"HTTP {code} rejected by the service: {detail or reason}"
    return f"HTTP {code} server error: {detail or reason}"


def _fetch(url: str, timeout: float) -> Tuple[bytes, Dict[str, str]]:
    """One GET. Returns (body, headers). Maps every failure to ImageError."""
    headers = {
        "User-Agent": "aicoder-pollinations-plugin/1.0",
        "Accept": "image/*",
    }
    token = os.environ.get("POLLINATIONS_TOKEN", "").strip()
    if token:
        headers["Authorization"] = f"Bearer {token}"

    request = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            body = response.read()
            response_headers = {k: v for k, v in response.headers.items()}
            return body, response_headers
    except urllib.error.HTTPError as exc:
        try:
            body_text = exc.read(600).decode("utf-8", "replace")
        except Exception:
            body_text = ""
        if exc.code in (401, 402, 429):
            seconds = _retry_after_seconds(exc.headers, body_text)
            raise RateLimitError(
                f"the free tier allows one image every {RATE_LIMIT_SECONDS} "
                f"seconds per IP; next free slot in {seconds}s. Nothing was "
                f"saved.",
                seconds,
            )
        raise ImageError(_describe_http_error(exc.code, str(exc.reason), body_text))
    except urllib.error.URLError as exc:
        reason = str(exc.reason)
        if "Temporary failure in name resolution" in reason or "Name or service" in reason:
            reason += " (DNS blocked? the shell sandbox runs with net off)"
        raise ImageError(f"cannot reach the service: {reason}")
    except TimeoutError:
        raise ImageError(
            f"no response from the service within {timeout:.0f}s; generation may "
            f"still be queued server-side - retrying the same URL is cheap "
            f"because it is cached"
        )
    except OSError as exc:
        raise ImageError(f"network error: {exc}")


def download_image(
    url: str,
    destination: str,
    overwrite: bool = False,
    timeout: float = 120.0,
    wait: bool = True,
    max_wait: int = 90,
    server_attempts: int = 2,
) -> Dict[str, Any]:
    """Fetch the image at ``url`` and write it to ``destination``.

    Handles the rate-limit window itself: when ``wait`` is true it sleeps for
    the next free slot (bounded by ``max_wait``) and retries; otherwise it
    raises RateLimitError with the remaining seconds.
    """
    if os.path.exists(destination) and not overwrite:
        raise FileExistsError(
            f"'{destination}' already exists (pass overwrite=true to replace it)"
        )

    waited_total = 0.0
    server_failures = 0
    while True:
        started = time.monotonic()
        try:
            body, headers = _fetch(url, timeout)
        except RateLimitError as exc:
            if not wait:
                raise
            remaining = exc.retry_after
            if waited_total + remaining > max_wait:
                raise RateLimitError(
                    f"{exc} Waiting that long needs max_wait >= "
                    f"{int(waited_total + remaining)}s (now {max_wait}s), or call "
                    f"again later.",
                    remaining,
                )
            LogUtils.printc(
                f"  rate limited: sleeping {remaining}s for the next free slot "
                f"({int(waited_total)}s/{max_wait}s budget)",
                color="yellow",
            )
            time.sleep(remaining + 0.5)
            waited_total += remaining
            continue
        except ImageError as exc:
            server_failures += 1
            if server_failures < server_attempts and "HTTP 5" in str(exc):
                time.sleep(2 * server_failures)
                continue
            raise

        info = image_info(body)
        if info is None:
            preview = body[:200].decode("utf-8", "replace").strip()
            content_type = headers.get("Content-Type", "unknown")
            server_failures += 1
            message = (
                f"the service answered with {content_type}, not an image "
                f"({len(body)} bytes): {preview or '(empty body)'}"
            )
            if not body.strip():
                message = "the service returned an empty body (nothing to save)"
            if server_failures < server_attempts:
                time.sleep(2 * server_failures)
                continue
            raise ImageError(message)

        parent = os.path.dirname(destination) or "."
        os.makedirs(parent, exist_ok=True)
        temp_path = f"{destination}.part"
        with open(temp_path, "wb") as handle:
            handle.write(body)
        os.replace(temp_path, destination)

        fmt, real_width, real_height = info
        return {
            "path": destination,
            "bytes": len(body),
            "format": fmt,
            "width": real_width,
            "height": real_height,
            "elapsed": round(time.monotonic() - started, 2),
            "waited": round(waited_total, 1),
            "cache": headers.get("x-cache", ""),
        }


# ---------------------------------------------------------------- tool entry


def _validate_side(value: Any, name: str) -> int:
    if value is None or value == "":
        return DEFAULT_WIDTH if name == "width" else DEFAULT_HEIGHT
    try:
        number = int(value)
    except (TypeError, ValueError):
        raise ValueError(f"{name} must be an integer, got {value!r}")
    if number < REQUEST_MIN_SIDE or number > REQUEST_MAX_SIDE:
        raise ValueError(
            f"{name} must be between {REQUEST_MIN_SIDE} and {REQUEST_MAX_SIDE}"
        )
    return number


def generate_image(args: Dict[str, Any]) -> Dict[str, Any]:
    """Tool entry point: validate, build URL, download, save, report."""
    if not isinstance(args, dict):
        raise TypeError("generate_image arguments must be an object")

    prompt = args.get("prompt")
    if not isinstance(prompt, str) or not prompt.strip():
        raise ValueError(
            "prompt is required and must be a non-empty string (describe the "
            "image: subject, style, lighting, colors, framing)"
        )

    width = _validate_side(args.get("width"), "width")
    height = _validate_side(args.get("height"), "height")
    overwrite = bool(args.get("overwrite"))
    safe = bool(args.get("safe"))
    wait = args.get("wait")
    wait = True if wait is None else bool(wait)

    model = str(args.get("model") or DEFAULT_MODEL).strip()
    models = allowed_models()
    if model not in models:
        raise ValueError(
            f"model '{model}' is not in the classic free list {list(models)}. "
            f"Use one of those, or extend the list with POLLINATIONS_MODELS."
        )

    seed = args.get("seed")
    if seed is None or seed == "":
        seed = random.randint(1, 2_147_483_647)
    else:
        try:
            seed = int(seed)
        except (TypeError, ValueError):
            raise ValueError(f"seed must be an integer, got {seed!r}")

    destination = resolve_destination(str(args.get("path") or ""))
    if not os.path.splitext(destination)[1]:
        destination += ".jpg"

    default_max_wait = int(os.environ.get("POLLINATIONS_MAX_WAIT", "90") or 90)
    raw_max_wait = args.get("max_wait")
    max_wait = int(raw_max_wait) if raw_max_wait not in (None, "") else default_max_wait
    if max_wait < 0:
        raise ValueError("max_wait must be zero or positive")
    timeout = float(os.environ.get("POLLINATIONS_TIMEOUT", "120") or 120)

    url = build_url(prompt.strip(), width, height, model, seed, safe)

    LogUtils.printc(
        f"> image {width}x{height} {model} seed={seed} -> {destination}",
        color="cyan",
        bold=True,
    )

    try:
        result = download_image(
            url,
            destination,
            overwrite=overwrite,
            timeout=timeout,
            wait=wait,
            max_wait=max_wait,
        )
    except RateLimitError as exc:
        raise RateLimitError(
            f"nothing saved to '{destination}'. {exc} The same prompt can be "
            f"retried with wait=true (or a larger max_wait), or call again after "
            f"the delay.",
            exc.retry_after,
        )

    rel = os.path.relpath(result["path"], os.getcwd())
    requested_area = width * height
    size_note = ""
    if requested_area > FREE_MAX_AREA and result["width"] and result["height"]:
        size_note = (
            f" (requested {width}x{height}; the free tier caps the area at "
            f"768x768 and kept the aspect ratio)"
        )
    wait_note = (
        f", waited {result['waited']}s for the rate-limit slot" if result["waited"] else ""
    )
    header = result["cache"]
    cache_note = f", x-cache={header}" if header else ""
    summary = (
        f"saved {rel} ({result['bytes'] / 1024:.1f} KB, {result['format']}, "
        f"{result['width'] or '?'}x{result['height'] or '?'}, model={model}, "
        f"seed={seed}, {result['elapsed']}s{cache_note}{wait_note}){size_note}\n"
        f"url: {url}\n"
        f'next: read_image on "{rel}" to judge the result; same prompt with the '
        f"same seed and size reproduces it, another seed varies it."
    )
    return {
        "tool": "generate_image",
        "friendly": summary,
        "detailed": summary,
        "path": result["path"],
        "relative_path": rel,
        "bytes": result["bytes"],
        "format": result["format"],
        "width": result["width"],
        "height": result["height"],
        "model": model,
        "seed": seed,
        "url": url,
        "waited": result["waited"],
    }


def _format_arguments(args: Dict[str, Any]) -> str:
    prompt = str(args.get("prompt") or "")
    if len(prompt) > 70:
        prompt = prompt[:67] + "..."
    return f"{args.get('path')} <- {prompt}"


def _generate_preview(args: Dict[str, Any]) -> Dict[str, Any]:
    seed = args.get("seed")
    lines = [
        f"Prompt: {args.get('prompt')}",
        f"Save to: {args.get('path')}",
        f"Size: {args.get('width') or DEFAULT_WIDTH}x"
        f"{args.get('height') or DEFAULT_HEIGHT} (free tier caps the area at 768x768)",
        f"Model: {args.get('model') or DEFAULT_MODEL}",
        f"Seed: {seed if seed not in (None, '') else 'random'}",
        f"Wait for free slot: {'no' if args.get('wait') is False else 'yes'}",
    ]
    return {"tool": "generate_image", "content": "\n".join(lines), "can_approve": True}


def create_plugin(ctx):
    """Register the free image generation tool."""
    if env_bool("POLLINATIONS_DISABLED"):
        return

    ctx.register_tool(
        "generate_image",
        generate_image,
        DESCRIPTION,
        PARAMETERS,
        auto_approved=False,
        format_arguments=_format_arguments,
        generate_preview=_generate_preview,
    )

    if env_bool("DEBUG"):
        print("  - generate_image tool")
