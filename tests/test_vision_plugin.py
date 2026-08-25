"""Tests for vision plugin"""

import os
import re
import sys
import tempfile
import base64
import random
import struct
import zlib

# Add parent to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from aicoder.core.message_history import MessageHistory
from aicoder.core.stats import Stats


class MockApp:
    """Mock app for testing"""
    def __init__(self):
        self.message_history = None
        self.test_messages = []

    def add_plugin_message(self, message):
        self.test_messages.append(message)


def test_message_history_accepts_dict():
    """Test that message_history.add_user_message accepts dict"""
    stats = Stats()
    history = MessageHistory(stats)

    # Test with string (normal case)
    history.add_user_message("hello")
    assert len(history.messages) == 1
    assert history.messages[0] == {"role": "user", "content": "hello"}

    # Test with dict (multimodal case)
    multimodal = {
        "role": "user",
        "content": [
            {"type": "text", "text": "Analyze this"},
            {"type": "image_url", "image_url": {"url": "data:image/png;base64,abc123"}}
        ]
    }
    history.add_user_message(multimodal)
    assert len(history.messages) == 2
    assert history.messages[1] == multimodal


def test_parse_image_references():
    """Test parsing @image references"""
    from aicoder.plugins.vision import parse_image_references

    # Test single image
    clean, paths = parse_image_references("@screenshot.png Analyze this")
    assert clean == "Analyze this"
    assert paths == ["screenshot.png"]

    # Test absolute path
    clean, paths = parse_image_references("@/home/user/img.jpg What is this?")
    assert clean == "What is this?"
    assert paths == ["/home/user/img.jpg"]

    # Test multiple images
    clean, paths = parse_image_references("@a.png @b.jpg Compare")
    assert clean == "Compare"
    assert paths == ["a.png", "b.jpg"]

    # Test no images
    clean, paths = parse_image_references("Just text")
    assert clean == "Just text"
    assert paths == []

    # Test different formats
    for ext in ["png", "jpg", "jpeg", "gif", "bmp", "webp", "tiff", "tif", "heic"]:
        clean, paths = parse_image_references(f"@test.{ext} image")
        assert clean == "image"
        assert paths == [f"test.{ext}"]


def test_is_supported_image():
    """Test image format support detection"""
    from aicoder.plugins.vision import is_supported_image

    assert is_supported_image("test.png") is True
    assert is_supported_image("test.jpg") is True
    assert is_supported_image("test.jpeg") is True
    assert is_supported_image("test.gif") is True
    assert is_supported_image("test.bmp") is True
    assert is_supported_image("test.webp") is True
    assert is_supported_image("test.tiff") is True
    assert is_supported_image("test.heic") is True
    assert is_supported_image("test.txt") is False
    assert is_supported_image("test.py") is False


def test_encode_image():
    """Test image base64 encoding"""
    from aicoder.plugins.vision import encode_image

    # Create a small test image (1x1 red PNG)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        # Minimal valid PNG
        f.write(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="))
        temp_path = f.name

    try:
        encoded = encode_image(temp_path)
        decoded = base64.b64decode(encoded)
        # Should decode without error
        assert len(decoded) > 0
    finally:
        os.unlink(temp_path)


def test_create_image_content_part():
    """Test creating image content part (provider-aware)"""
    from aicoder.plugins.vision import create_image_content_part

    # Create a small test image
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="))
        temp_path = f.name

    try:
        part = create_image_content_part(temp_path)
        if os.environ.get("API_PROVIDER", "").lower() == "anthropic":
            # Anthropic format
            assert part["type"] == "image"
            assert part["source"]["type"] == "base64"
            assert part["source"]["media_type"] == "image/png"
            assert part["source"]["data"]  # non-empty base64
        else:
            # OpenAI format
            assert part["type"] == "image_url"
            assert "image_url" in part
            assert part["image_url"]["url"].startswith("data:image/png;base64,")
    finally:
        os.unlink(temp_path)


def test_create_user_message():
    """Test creating multimodal user message"""
    from aicoder.plugins.vision import create_user_message

    # Create test images
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJJggg=="))
        img1 = f.name

    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as f:
        f.write(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="))
        img2 = f.name

    try:
        message = create_user_message("Analyze these", [img1, img2])

        assert message["role"] == "user"
        assert len(message["content"]) == 3  # text + 2 images
        assert message["content"][0] == {"type": "text", "text": "Analyze these"}
        if os.environ.get("API_PROVIDER", "").lower() == "anthropic":
            assert message["content"][1]["type"] == "image"
            assert message["content"][1]["source"]["media_type"] == "image/png"
            assert message["content"][2]["type"] == "image"
            assert message["content"][2]["source"]["media_type"] == "image/jpeg"
        else:
            assert message["content"][1]["type"] == "image_url"
            assert message["content"][2]["type"] == "image_url"
    finally:
        os.unlink(img1)
        os.unlink(img2)


def test_transform_user_input():
    """Test the hook transformation"""
    from aicoder.plugins.vision import transform_user_input

    app = MockApp()

    # No images - should return None
    result = transform_user_input("Just text", app)
    assert result is None
    assert len(app.test_messages) == 0

    # Create test image
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="))
        img_path = f.name

    try:
        # Valid image - should return multimodal message dict
        result = transform_user_input(f"@{img_path} Analyze this", app)
        assert isinstance(result, dict)
        assert result["role"] == "user"
        assert "content" in result
        # Should be a list (multimodal content array)
        assert isinstance(result["content"], list)
        # Should have text and image parts
        assert len(result["content"]) == 2

        # Missing image only - should return error message (dict with text content)
        result = transform_user_input("@nonexistent.png Error case", app)
        assert isinstance(result, dict)
        assert result["role"] == "user"
        assert "not found" in str(result.get("content", "")).lower()
    finally:
        os.unlink(img_path)


def test_plugin_integration():
    """Test plugin hooks are callable"""
    from aicoder.plugins.vision import create_plugin

    mock_ctx = type('MockCtx', (), {})()
    mock_ctx.register_hook = lambda name, fn: None
    mock_ctx.register_tool = lambda name, fn, description, parameters, auto_approved=False, format_arguments=None, generate_preview=None: None
    mock_ctx.register_command = lambda name, fn, description=None: None
    mock_ctx.app = MockApp()

    # Hemetic: an ambient VISION_SCRIPT/VISION_ENABLE_TOOL in the test process
    # env triggers auto-registration of read_image, which MockApp cannot serve.
    saved = {k: os.environ.get(k) for k in ("VISION_SCRIPT", "VISION_ENABLE_TOOL")}
    for k in saved:
        os.environ.pop(k, None)
    try:
        result = create_plugin(mock_ctx)
    finally:
        for k, v in saved.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)
    assert isinstance(result, dict)


_MIN_PNG = "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="


def _make_vision_ctx():
    """Build a mock PluginContext that records tools/commands like the real one."""
    from types import SimpleNamespace
    app = MockApp()
    app.tool_manager = SimpleNamespace(tools={})
    commands = {}

    def _register_tool(name, fn, desc, params, auto_approved=False,
                       format_arguments=None, generate_preview=None):
        app.tool_manager.tools[name] = {
            "execute": fn,
            "description": desc,
            "parameters": params,
            "auto_approved": auto_approved,
            "formatArguments": format_arguments,
            "generatePreview": generate_preview,
        }

    ctx = SimpleNamespace()
    ctx.app = app
    ctx.register_hook = lambda name, fn: None
    ctx.register_tool = _register_tool
    ctx.register_command = lambda name, fn, description=None: commands.__setitem__(name, fn)
    ctx._commands = commands
    return ctx


def _write_png():
    f = tempfile.NamedTemporaryFile(dir=os.getcwd(), suffix=".png", delete=False)
    f.write(base64.b64decode(_MIN_PNG))
    f.close()
    return f.name


def _write_noisy_png(width, height, seed=7):
    """Generate a solid-noise RGB PNG (stdlib only, incompressible-ish)."""
    rnd = random.Random(seed)
    raw = b"".join(
        b"\x00" + bytes(rnd.randrange(256) for _ in range(width * 3))
        for _ in range(height)
    )

    def chunk(tag, payload):
        return (
            struct.pack(">I", len(payload)) + tag + payload
            + struct.pack(">I", zlib.crc32(tag + payload) & 0xFFFFFFFF)
        )

    png = (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 2, 0, 0, 0))
        + chunk(b"IDAT", zlib.compress(raw))
        + chunk(b"IEND", b"")
    )
    fd, path = tempfile.mkstemp(dir=os.getcwd(), suffix=".png")
    with os.fdopen(fd, "wb") as f:
        f.write(png)
    return path


def _png_dims(data):
    """Read width/height from a PNG's IHDR (stdlib only)."""
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", data[16:24])


def _vision_strays():
    """Stray .vision.* temp copies left in cwd after a read_image call."""
    return [p for p in os.listdir(os.getcwd()) if p.startswith(".vision")]


def test_vision_gateway_path():
    """read_image bridges to VISION_SCRIPT and returns its stdout as description."""
    with tempfile.NamedTemporaryFile(suffix=".sh", delete=False, mode="w") as sf:
        sf.write("#!/usr/bin/env bash\necho \"GATEWAY_DESC for $1\"\n")
        script = sf.name
    os.chmod(script, 0o755)
    img = _write_png()

    old = os.environ.get("VISION_SCRIPT")
    os.environ["VISION_SCRIPT"] = script
    try:
        from aicoder.plugins.vision import create_plugin
        ctx = _make_vision_ctx()
        create_plugin(ctx)
        assert "read_image" in ctx.app.tool_manager.tools, "auto-register when VISION_SCRIPT set"
        result = ctx.app.tool_manager.tools["read_image"]["execute"]({"path": img})
        assert "GATEWAY_DESC" in result["detailed"]
        # Gateway must only ever see the verified cwd copy, never the original path.
        assert re.search(r"\.vision\.[0-9a-f]{16}\.png", result["detailed"]), result["detailed"]
        # Copy must be cleaned up after use.
        assert not _vision_strays()
    finally:
        if old is None:
            os.environ.pop("VISION_SCRIPT", None)
        else:
            os.environ["VISION_SCRIPT"] = old
        os.unlink(script)
        os.unlink(img)


def test_vision_static_bait_symlink():
    """A planted .vision.* bait symlink must never steer the temp write.

    Round-4 regression (proven live by tester): the predictable
    ``.vision.<ext>`` copy name + plain open('w') let a static symlink
    bait redirect the write to an arbitrary writable path. Round 5 uses an
    unpredictable name with O_CREAT|O_EXCL|O_NOFOLLOW, so the bait is
    ignored and the decoy target stays untouched.
    """
    img = _write_png()
    bait = os.path.join(os.getcwd(), ".vision.png")
    decoy = os.path.join(os.getcwd(), "decoy.probe.png")
    with open(decoy, "wb") as f:
        f.write(b"SENTINEL-UNTOUCHED")
    os.symlink(decoy, bait)
    with tempfile.NamedTemporaryFile(suffix=".sh", delete=False, mode="w") as sf:
        sf.write("#!/usr/bin/env bash\necho \"GATEWAY_DESC for $1\"\n")
        script = sf.name
    os.chmod(script, 0o755)
    old = os.environ.get("VISION_SCRIPT")
    os.environ["VISION_SCRIPT"] = script
    try:
        from aicoder.plugins.vision import create_plugin
        ctx = _make_vision_ctx()
        create_plugin(ctx)
        result = ctx.app.tool_manager.tools["read_image"]["execute"]({"path": img})
        assert "Error" not in result["friendly"], result
        assert re.search(r"\.vision\.[0-9a-f]{16}\.png", result["detailed"])
        with open(decoy, "rb") as f:
            assert f.read() == b"SENTINEL-UNTOUCHED", "bait symlink steered the write"
        # Only the bait itself may remain; the random-named copy is cleaned up.
        assert [p for p in os.listdir(os.getcwd()) if p.startswith(".vision")] == [".vision.png"]
    finally:
        for p in (bait, decoy, img, script):
            try:
                os.unlink(p)
            except OSError:
                pass
        if old is None:
            os.environ.pop("VISION_SCRIPT", None)
        else:
            os.environ["VISION_SCRIPT"] = old


def test_vision_native_injection():
    """Without a gateway, read_image injects the image for native vision models."""
    img = _write_png()
    old_en = os.environ.pop("VISION_ENABLE_TOOL", None)
    vs = os.environ.pop("VISION_SCRIPT", None)
    os.environ["VISION_ENABLE_TOOL"] = "1"
    try:
        from aicoder.plugins.vision import create_plugin
        ctx = _make_vision_ctx()
        create_plugin(ctx)
        assert "read_image" in ctx.app.tool_manager.tools
        before = len(ctx.app.test_messages)
        result = ctx.app.tool_manager.tools["read_image"]["execute"]({"path": img})
        assert "Image loaded" in result["detailed"]
        assert len(ctx.app.test_messages) == before + 1
        injected = ctx.app.test_messages[-1]
        assert injected["role"] == "user"
        assert isinstance(injected["content"], list)
    finally:
        os.environ.pop("VISION_ENABLE_TOOL", None)
        if old_en is not None:
            os.environ["VISION_ENABLE_TOOL"] = old_en
        if vs is not None:
            os.environ["VISION_SCRIPT"] = vs
        os.unlink(img)


def test_vision_command_toggle():
    """/vision on|off|status|help toggles the tool's availability."""
    os.environ.pop("VISION_SCRIPT", None)
    os.environ.pop("VISION_ENABLE_TOOL", None)
    from aicoder.plugins.vision import create_plugin
    ctx = _make_vision_ctx()
    create_plugin(ctx)
    assert "read_image" not in ctx.app.tool_manager.tools, "no auto-register by default"

    handler = ctx._commands["vision"]
    assert "DISABLED" in handler("status")
    assert "ENABLED" in handler("on")
    assert "read_image" in ctx.app.tool_manager.tools
    assert "DISABLED" in handler("off")
    assert "read_image" not in ctx.app.tool_manager.tools
    assert "/vision on" in handler("help")
    assert "Unknown subcommand" in handler("bogus")


def test_vision_script_missing_no_autoregister():
    """VISION_SCRIPT that doesn't resolve must NOT auto-register read_image."""
    os.environ["VISION_SCRIPT"] = "/nonexistent/vision-gateway-xyz"
    old_en = os.environ.pop("VISION_ENABLE_TOOL", None)
    try:
        from aicoder.plugins.vision import create_plugin
        ctx = _make_vision_ctx()
        create_plugin(ctx)
        assert "read_image" not in ctx.app.tool_manager.tools
    finally:
        os.environ.pop("VISION_SCRIPT", None)
        if old_en is not None:
            os.environ["VISION_ENABLE_TOOL"] = old_en


def test_vision_respects_tools_deny():
    """TOOLS_DENY=read_image must block registration even with VISION_SCRIPT set."""
    os.environ["VISION_SCRIPT"] = "/bin/true"
    old_deny = os.environ.pop("TOOLS_DENY", None)
    old_allow = os.environ.pop("TOOLS_ALLOW", None)
    try:
        from aicoder.plugins.vision import create_plugin
        ctx = _make_vision_ctx()
        create_plugin(ctx)
        assert "read_image" in ctx.app.tool_manager.tools, "registers when unfiltered"

        ctx2 = _make_vision_ctx()
        os.environ["TOOLS_DENY"] = "read_image"
        create_plugin(ctx2)
        assert "read_image" not in ctx2.app.tool_manager.tools, "TOOLS_DENY wins"

        ctx3 = _make_vision_ctx()
        os.environ.pop("TOOLS_DENY")
        os.environ["TOOLS_ALLOW"] = "grep,read_file"
        create_plugin(ctx3)
        assert "read_image" not in ctx3.app.tool_manager.tools, "not in TOOLS_ALLOW -> blocked"
    finally:
        os.environ.pop("VISION_SCRIPT", None)
        os.environ.pop("TOOLS_DENY", None)
        os.environ.pop("TOOLS_ALLOW", None)
        if old_deny is not None:
            os.environ["TOOLS_DENY"] = old_deny
        if old_allow is not None:
            os.environ["TOOLS_ALLOW"] = old_allow


def test_vision_max_size_env_parsing():
    """VISION_MAX_SIZE parsing: 0/negative=off, unset/invalid=built-in default."""
    from aicoder.plugins.vision import _DEFAULT_MAX_SIZE, _get_max_size
    old = os.environ.pop("VISION_MAX_SIZE", None)
    try:
        # unset -> built-in default
        assert _get_max_size() == _DEFAULT_MAX_SIZE
        assert _DEFAULT_MAX_SIZE > 0
        os.environ["VISION_MAX_SIZE"] = "640"
        assert _get_max_size() == 640
        os.environ["VISION_MAX_SIZE"] = "0"
        assert _get_max_size() is None
        os.environ["VISION_MAX_SIZE"] = "-5"
        assert _get_max_size() is None
        os.environ["VISION_MAX_SIZE"] = "abc"
        # invalid -> default, resizing stays on
        assert _get_max_size() == _DEFAULT_MAX_SIZE
    finally:
        os.environ.pop("VISION_MAX_SIZE", None)
        if old is not None:
            os.environ["VISION_MAX_SIZE"] = old


def test_vision_max_size_resize():
    """VISION_MAX_SIZE downscales long side before base64; small images untouched."""
    from aicoder.plugins.vision import _resize_image, create_image_content_part
    big = _write_noisy_png(200, 150)
    tiny = _write_noisy_png(10, 8)
    old_en = os.environ.pop("VISION_MAX_SIZE", None)
    old_provider = os.environ.pop("API_PROVIDER", None)
    try:
        # Probe for any usable resize backend (PIL/ImageMagick/ffmpeg/OpenCV/GM).
        probed = _resize_image(big, 50)
        if probed == big:
            os.unlink(big)
            os.unlink(tiny)
            print("No resize backend available - skipping resize assertions")
            return
        os.unlink(probed)

        os.environ["VISION_MAX_SIZE"] = "50"
        part = create_image_content_part(big)
        if part.get("type") == "image":  # anthropic format
            encoded = part["source"]["data"]
        else:  # openai format
            encoded = part["image_url"]["url"].split(",", 1)[1]
        w, h = _png_dims(base64.b64decode(encoded))
        assert max(w, h) <= 50, f"expected longest side <= 50, got {w}x{h}"
        assert (w, h) != (200, 150), "image was not resized"

        # Already-small image must pass through unchanged.
        part_t = create_image_content_part(tiny)
        if part_t.get("type") == "image":
            encoded_t = part_t["source"]["data"]
        else:
            encoded_t = part_t["image_url"]["url"].split(",", 1)[1]
        tw, th = _png_dims(base64.b64decode(encoded_t))
        assert (tw, th) == (10, 8), f"small image changed: {tw}x{th}"
    finally:
        os.unlink(big)
        os.unlink(tiny)
        os.environ.pop("VISION_MAX_SIZE", None)
        if old_en is not None:
            os.environ["VISION_MAX_SIZE"] = old_en
        os.environ.pop("API_PROVIDER", None)
        if old_provider is not None:
            os.environ["API_PROVIDER"] = old_provider


def test_vision_max_size_early_out():
    """Images already within the limit are returned as-is — no re-encode, no temp copy."""
    from aicoder.plugins.vision import _image_dimensions, _resize_image
    small = _write_noisy_png(100, 80)
    try:
        if _image_dimensions(small) is None:
            print("`file` utility unavailable - skipping early-out assertions")
            return
        assert _image_dimensions(small) == (100, 80)
        assert _resize_image(small, 768) == small, "small image should be returned unchanged"
        # Oversized images still go through the resize chain.
        big = _write_noisy_png(200, 150)
        try:
            resized = _resize_image(big, 50)
            assert resized != big, "oversized image should have been resized"
            os.unlink(resized)
        finally:
            os.unlink(big)
    finally:
        os.unlink(small)


def test_vision_header_dims_fallback():
    """In-process PNG/JPEG header parse when `file` is unavailable."""
    from aicoder.plugins.vision import _header_dimensions
    png = _write_noisy_png(120, 90)
    try:
        assert _header_dimensions(png) == (120, 90)
    finally:
        os.unlink(png)
    # Minimal valid JPEG structure: SOI, APP0 (JFIF), SOF0 (200x100).
    jpeg = struct.pack(">2s2sH", b"\xff\xd8", b"\xff\xe0", 16) + b"JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00"
    jpeg += struct.pack(">2sHB", b"\xff\xc0", 17, 8) + struct.pack(">HH", 100, 200) + b"\x03\x01\x11\x00\x02\x11\x01\x03\x11\x01"
    with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as jf:
        jf.write(jpeg)
    try:
        assert _header_dimensions(jf.name) == (200, 100)
    finally:
        os.unlink(jf.name)
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as bogus:
        bogus.write(b"this is not an image at all........")
    try:
        assert _header_dimensions(bogus.name) is None
    finally:
        os.unlink(bogus.name)


def test_vision_parse_file_dimensions():
    """Last-match wins: `file -b` JPEG output carries density BEFORE dims."""
    from aicoder.plugins.vision import _parse_file_dimensions
    jpeg = ("JPEG image data, JFIF standard 1.01, resolution (DPI), density "
            "300x300, segment length 16, Exif Standard: [TIFF image data, "
            "little-endian, direntries=7], progressive, precision 8, "
            "1024x786, components 3")
    assert _parse_file_dimensions(jpeg) == (1024, 786)
    assert _parse_file_dimensions("PNG image data, 232 x 232, 8-bit/color RGBA") == (232, 232)
    assert _parse_file_dimensions("no dimensions here") is None


def run_all_tests():
    """Run all tests"""
    tests = [
        test_message_history_accepts_dict,
        test_parse_image_references,
        test_is_supported_image,
        test_encode_image,
        test_create_image_content_part,
        test_create_user_message,
        test_transform_user_input,
        test_plugin_integration,
        test_vision_gateway_path,
        test_vision_native_injection,
        test_vision_command_toggle,
        test_vision_script_missing_no_autoregister,
        test_vision_max_size_env_parsing,
        test_vision_max_size_resize,
        test_vision_max_size_early_out,
        test_vision_header_dims_fallback,
        test_vision_parse_file_dimensions,
    ]

    passed = 0
    failed = 0

    for test in tests:
        try:
            test()
            print(f"[PASS] {test.__name__}")
            passed += 1
        except Exception as e:
            print(f"[FAIL] {test.__name__}: {e}")
            failed += 1

    print(f"\nResults: {passed} passed, {failed} failed")
    return failed == 0


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
