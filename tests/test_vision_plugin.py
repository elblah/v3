"""Tests for vision plugin"""

import os
import sys
import tempfile
import base64

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

    result = create_plugin(mock_ctx)
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
    f = tempfile.NamedTemporaryFile(suffix=".png", delete=False)
    f.write(base64.b64decode(_MIN_PNG))
    f.close()
    return f.name


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
        assert img in result["detailed"]
    finally:
        if old is None:
            os.environ.pop("VISION_SCRIPT", None)
        else:
            os.environ["VISION_SCRIPT"] = old
        os.unlink(script)
        os.unlink(img)


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
