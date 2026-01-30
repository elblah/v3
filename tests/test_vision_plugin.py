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
    from plugins.vision import parse_image_references

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
    from plugins.vision import is_supported_image

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
    from plugins.vision import encode_image

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
    """Test creating image content part"""
    from plugins.vision import create_image_content_part

    # Create a small test image
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
        f.write(base64.b64decode("iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8DwHwAFBQIAX8jx0gAAAABJRU5ErkJggg=="))
        temp_path = f.name

    try:
        part = create_image_content_part(temp_path)
        assert part["type"] == "image_url"
        assert "image_url" in part
        assert part["image_url"]["url"].startswith("data:image/png;base64,")
    finally:
        os.unlink(temp_path)


def test_create_user_message():
    """Test creating multimodal user message"""
    from plugins.vision import create_user_message

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
        assert message["content"][1]["type"] == "image_url"
        assert message["content"][2]["type"] == "image_url"
    finally:
        os.unlink(img1)
        os.unlink(img2)


def test_transform_user_input():
    """Test the hook transformation"""
    from plugins.vision import transform_user_input

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
    from plugins.vision import create_plugin

    mock_ctx = type('MockCtx', (), {})()
    mock_ctx.register_hook = lambda name, fn: None
    mock_ctx.register_tool = lambda name, fn, description, parameters, auto_approved=False, format_arguments=None, generate_preview=None: None
    mock_ctx.app = MockApp()

    result = create_plugin(mock_ctx)
    assert isinstance(result, dict)


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
