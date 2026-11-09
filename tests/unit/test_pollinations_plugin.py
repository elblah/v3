"""Tests for the Pollinations image generation plugin.

The network is never touched: ``urllib.request.urlopen`` and the internal
``_fetch`` helper are replaced by fakes.
"""

import io
import os
import sys
import urllib.error

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from aicoder.plugins import pollinations as pl


# ----------------------------------------------------------------- fixtures


def make_jpeg(width=16, height=24):
    """Minimal JPEG: SOI + SOF0 (with real dimensions) + EOI padding."""
    sof = (
        b"\xff\xc0"
        + (17).to_bytes(2, "big")
        + b"\x08"
        + height.to_bytes(2, "big")
        + width.to_bytes(2, "big")
        + b"\x03\x01\x11\x00\x02\x11\x01\x03\x11\x01"
    )
    return b"\xff\xd8" + sof + b"\x00" * 24 + b"\xff\xd9"


def make_png(width=7, height=9):
    payload = (
        b"\x89PNG\r\n\x1a\n"
        + (13).to_bytes(4, "big")
        + b"IHDR"
        + width.to_bytes(4, "big")
        + height.to_bytes(4, "big")
        + b"\x08\x06\x00\x00\x00"
        + b"\x00" * 16
    )
    return payload


class FakeHeaders(dict):
    def items(self):
        return list(super().items())


class FakeResponse:
    def __init__(self, body, headers=None, status=200):
        self._body = body
        self.headers = FakeHeaders(headers or {})
        self.status = status

    def read(self, _n=None):
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def http_error(code, body=b"", headers=None, reason="error"):
    return urllib.error.HTTPError(
        "https://image.pollinations.ai/prompt/x",
        code,
        reason,
        FakeHeaders(headers or {}),
        io.BytesIO(body),
    )


# --------------------------------------------------------------- image_info


def test_image_info_jpeg():
    assert pl.image_info(make_jpeg(320, 200)) == ("jpg", 320, 200)


def test_image_info_png():
    assert pl.image_info(make_png(64, 48)) == ("png", 64, 48)


def test_image_info_gif():
    data = b"GIF89a" + (5).to_bytes(2, "little") + (6).to_bytes(2, "little") + b"\x00" * 32
    assert pl.image_info(data) == ("gif", 5, 6)


def test_image_info_rejects_non_image():
    assert pl.image_info(b"<html>oops</html>" + b" " * 40) is None
    assert pl.image_info(b"") is None
    assert pl.image_info(b"\xff\xd8") is None  # truncated


# ------------------------------------------------------------------ build_url


def test_build_url_encodes_prompt_and_keeps_params():
    url = pl.build_url("a cat & a dog?", 1024, 768, "flux", 42)
    assert url.startswith(pl.BASE_URL)
    assert "a%20cat%20%26%20a%20dog%3F" in url
    assert "width=1024" in url
    assert "height=768" in url
    assert "model=flux" in url
    assert "seed=42" in url
    assert "safe=" not in url


def test_build_url_adds_safe_when_requested():
    assert "safe=true" in pl.build_url("x", 64, 64, "flux", 1, safe=True)


# ------------------------------------------------------- resolve_destination


def test_resolve_destination_inside_cwd(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    out = pl.resolve_destination("images/a.jpg")
    assert out == os.path.realpath(str(tmp_path / "images" / "a.jpg"))


def test_resolve_destination_rejects_outside_roots(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    for bad in ("/etc/passwd", "/root/x.jpg", "/var/tmp/x.jpg"):
        with pytest.raises(ValueError):
            pl.resolve_destination(bad)


def test_resolve_destination_rejects_empty():
    with pytest.raises(ValueError):
        pl.resolve_destination("   ")


def test_resolve_destination_rejects_directory(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "adir").mkdir()
    with pytest.raises(ValueError):
        pl.resolve_destination("adir")


# ------------------------------------------------------ retry-after parsing


def test_retry_after_from_header():
    assert pl._retry_after_seconds({"Retry-After": "32"}, "") == 32


def test_retry_after_from_body_text():
    body = '{"message": "Free limit reached ... Retry after 17s, ..."}'
    assert pl._retry_after_seconds({}, body) == 17


def test_retry_after_from_json_field():
    assert pl._retry_after_seconds({}, '{"retry_after": 5}') == 5


def test_retry_after_fallback_default():
    assert pl._retry_after_seconds({}, "nonsense") == pl.RATE_LIMIT_SECONDS


# ---------------------------------------------------------------- _fetch


def test_fetch_rate_limit_maps_to_rate_limit_error(monkeypatch):
    def boom(*_a, **_k):
        raise http_error(402, b'{"message":"Retry after 8s"}', {"Retry-After": "8"})

    monkeypatch.setattr(pl.urllib.request, "urlopen", boom)
    with pytest.raises(pl.RateLimitError) as info:
        pl._fetch("https://example.invalid", 5)
    assert info.value.retry_after == 8
    assert "Nothing was saved" in str(info.value)


def test_fetch_paid_model_403_is_not_rate_limit(monkeypatch):
    def boom(*_a, **_k):
        raise http_error(403, b'{"message":"kontext isn\'t part of the Classic API"}')

    monkeypatch.setattr(pl.urllib.request, "urlopen", boom)
    with pytest.raises(pl.ImageError) as info:
        pl._fetch("https://example.invalid", 5)
    assert not isinstance(info.value, pl.RateLimitError)
    assert "classic" in str(info.value).lower()


def test_fetch_server_error_text(monkeypatch):
    def boom(*_a, **_k):
        raise http_error(500, b"", reason="Internal Server Error")

    monkeypatch.setattr(pl.urllib.request, "urlopen", boom)
    with pytest.raises(pl.ImageError) as info:
        pl._fetch("https://example.invalid", 5)
    assert "500" in str(info.value)


def test_fetch_success_returns_body_and_headers(monkeypatch):
    body = make_jpeg(8, 8)
    monkeypatch.setattr(pl.urllib.request, "urlopen", lambda *a, **k: FakeResponse(body, {"x-cache": "HIT"}))
    got, headers = pl._fetch("https://example.invalid", 5)
    assert got == body
    assert headers["x-cache"] == "HIT"


def test_fetch_sends_token(monkeypatch):
    seen = {}

    def fake(request, timeout=None):
        seen["auth"] = request.headers.get("Authorization")
        return FakeResponse(make_jpeg())

    monkeypatch.setenv("POLLINATIONS_TOKEN", "secret")
    monkeypatch.setattr(pl.urllib.request, "urlopen", fake)
    pl._fetch("https://example.invalid", 5)
    assert seen["auth"] == "Bearer secret"


# --------------------------------------------------------- download_image


@pytest.fixture
def no_sleep(monkeypatch):
    slept = []
    monkeypatch.setattr(pl.time, "sleep", lambda s: slept.append(s))
    monkeypatch.setattr(pl.time, "monotonic", lambda: 0.0)
    return slept


def test_download_writes_file_and_reports_size(tmp_path, no_sleep, monkeypatch):
    body = make_jpeg(1024, 576)
    dest = str(tmp_path / "out.jpg")
    monkeypatch.setattr(pl, "_fetch", lambda url, timeout: (body, {"x-cache": "HIT"}))
    result = pl.download_image("http://x", dest)
    assert result["width"] == 1024 and result["height"] == 576
    assert result["format"] == "jpg"
    assert result["cache"] == "HIT"
    assert os.path.exists(dest)
    assert not os.path.exists(dest + ".part")


def test_download_rate_limit_wait_false_raises(tmp_path, no_sleep, monkeypatch):
    def fake(url, timeout):
        raise pl.RateLimitError("limited", 12)

    monkeypatch.setattr(pl, "_fetch", fake)
    dest = str(tmp_path / "o.jpg")
    with pytest.raises(pl.RateLimitError):
        pl.download_image("http://x", dest, wait=False)
    assert not os.path.exists(dest)
    assert no_sleep == []


def test_download_rate_limit_waits_and_retries(tmp_path, no_sleep, monkeypatch):
    calls = {"n": 0}
    body = make_jpeg(64, 64)

    def fake(url, timeout):
        calls["n"] += 1
        if calls["n"] == 1:
            raise pl.RateLimitError("limited", 10)
        return body, {}

    monkeypatch.setattr(pl, "_fetch", fake)
    result = pl.download_image("http://x", str(tmp_path / "o.jpg"), wait=True, max_wait=90)
    assert calls["n"] == 2
    assert result["waited"] == 10
    assert no_sleep and no_sleep[0] >= 10


def test_download_rate_limit_exceeds_max_wait(tmp_path, no_sleep, monkeypatch):
    def fake(url, timeout):
        raise pl.RateLimitError("limited", 120)

    monkeypatch.setattr(pl, "_fetch", fake)
    with pytest.raises(pl.RateLimitError) as info:
        pl.download_image("http://x", str(tmp_path / "o.jpg"), wait=True, max_wait=60)
    assert "max_wait" in str(info.value)
    assert info.value.retry_after == 120


def test_download_non_image_raises(tmp_path, no_sleep, monkeypatch):
    monkeypatch.setattr(pl, "_fetch", lambda url, timeout: (b"<html>nope</html>" * 3, {}))
    with pytest.raises(pl.ImageError) as info:
        pl.download_image("http://x", str(tmp_path / "o.jpg"))
    assert "not an image" in str(info.value) or "empty body" in str(info.value)


def test_download_empty_body_raises(tmp_path, no_sleep, monkeypatch):
    monkeypatch.setattr(pl, "_fetch", lambda url, timeout: (b"", {}))
    with pytest.raises(pl.ImageError) as info:
        pl.download_image("http://x", str(tmp_path / "o.jpg"))
    assert "empty body" in str(info.value)


def test_download_refuses_overwrite(tmp_path, no_sleep):
    dest = tmp_path / "o.jpg"
    dest.write_bytes(b"old")
    with pytest.raises(FileExistsError):
        pl.download_image("http://x", str(dest), overwrite=False)


def test_download_overwrite_allows_replace(tmp_path, no_sleep, monkeypatch):
    body = make_jpeg(4, 4)
    dest = tmp_path / "o.jpg"
    dest.write_bytes(b"old")
    monkeypatch.setattr(pl, "_fetch", lambda url, timeout: (body, {}))
    pl.download_image("http://x", str(dest), overwrite=True)
    assert dest.read_bytes() == body


def test_download_creates_parent_dirs(tmp_path, no_sleep, monkeypatch):
    body = make_jpeg(4, 4)
    dest = tmp_path / "a" / "b" / "o.jpg"
    monkeypatch.setattr(pl, "_fetch", lambda url, timeout: (body, {}))
    pl.download_image("http://x", str(dest))
    assert dest.exists()


# ---------------------------------------------------------- generate_image


def test_generate_image_requires_prompt():
    with pytest.raises(ValueError):
        pl.generate_image({"path": "a.jpg"})


def test_generate_image_requires_path(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError):
        pl.generate_image({"prompt": "a cat"})


def test_generate_image_rejects_model_not_in_allowlist(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError) as info:
        pl.generate_image({"prompt": "a cat", "path": "a.jpg", "model": "seedream"})
    assert "not in the classic free list" in str(info.value)


def test_generate_image_allowlist_from_env(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.setenv("POLLINATIONS_MODELS", "flux,other")
    assert pl.allowed_models() == ("flux", "other")


def test_generate_image_rejects_bad_size(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    with pytest.raises(ValueError):
        pl.generate_image({"prompt": "a cat", "path": "a.jpg", "width": 5})


def _stub_download(monkeypatch, body=None, error=None):
    body = body if body is not None else make_jpeg(1024, 576)

    def fake(url, destination, **kwargs):
        if error:
            raise error
        return {
            "path": destination,
            "bytes": len(body),
            "format": "jpg",
            "width": 1024,
            "height": 576,
            "elapsed": 0.5,
            "waited": kwargs.get("_waited", 0.0),
            "cache": "HIT",
        }

    monkeypatch.setattr(pl, "download_image", fake)


def test_generate_image_success(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _stub_download(monkeypatch)
    result = pl.generate_image({"prompt": "a red fox", "path": "img/fox.jpg", "seed": 7})
    assert result["tool"] == "generate_image"
    assert result["seed"] == 7
    assert result["model"] == pl.DEFAULT_MODEL
    assert result["relative_path"] == os.path.join("img", "fox.jpg")
    assert "seed=7" in result["friendly"]
    assert "read_image" in result["friendly"]


def test_generate_image_reports_size_cap(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _stub_download(monkeypatch)
    result = pl.generate_image(
        {"prompt": "wide", "path": "w.jpg", "width": 1600, "height": 400, "seed": 1}
    )
    assert "768x768" in result["friendly"]


def test_generate_image_random_seed_is_reported(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _stub_download(monkeypatch)
    result = pl.generate_image({"prompt": "x", "path": "x.jpg"})
    assert 1 <= result["seed"] <= 2_147_483_647
    assert str(result["seed"]) in result["friendly"]


def test_generate_image_missing_extension_gets_jpg(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    seen = {}

    def fake(url, destination, **kwargs):
        seen["dest"] = destination
        return {
            "path": destination, "bytes": 10, "format": "jpg",
            "width": 1, "height": 1, "elapsed": 0.1, "waited": 0, "cache": "",
        }

    monkeypatch.setattr(pl, "download_image", fake)
    pl.generate_image({"prompt": "x", "path": "noext"})
    assert seen["dest"].endswith("noext.jpg")


def test_generate_image_rate_limit_propagates_with_hint(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    _stub_download(monkeypatch, error=pl.RateLimitError("limited", 30))
    with pytest.raises(pl.RateLimitError) as info:
        pl.generate_image({"prompt": "x", "path": "x.jpg"})
    assert info.value.retry_after == 30
    assert "nothing saved" in str(info.value).lower()


def test_generate_image_wait_false_passed_through(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    captured = {}

    def fake(url, destination, **kwargs):
        captured.update(kwargs)
        return {
            "path": destination, "bytes": 1, "format": "jpg",
            "width": 1, "height": 1, "elapsed": 0.0, "waited": 0, "cache": "",
        }

    monkeypatch.setattr(pl, "download_image", fake)
    pl.generate_image({"prompt": "x", "path": "x.jpg", "wait": False, "max_wait": 10})
    assert captured["wait"] is False
    assert captured["max_wait"] == 10


# ------------------------------------------------------------- plugin hook


class FakeCtx:
    def __init__(self):
        self.tools = {}

    def register_tool(self, name, fn, description, parameters,
                      auto_approved=False, format_arguments=None,
                      generate_preview=None):
        self.tools[name] = {
            "fn": fn,
            "description": description,
            "parameters": parameters,
            "auto_approved": auto_approved,
            "format_arguments": format_arguments,
            "generate_preview": generate_preview,
        }


def test_create_plugin_registers_tool(monkeypatch):
    monkeypatch.delenv("POLLINATIONS_DISABLED", raising=False)
    ctx = FakeCtx()
    pl.create_plugin(ctx)
    assert "generate_image" in ctx.tools
    tool = ctx.tools["generate_image"]
    assert tool["auto_approved"] is False
    assert tool["parameters"]["required"] == ["prompt", "path"]
    assert tool["format_arguments"] is not None
    assert tool["generate_preview"] is not None


def test_create_plugin_respects_disabled(monkeypatch):
    monkeypatch.setenv("POLLINATIONS_DISABLED", "1")
    ctx = FakeCtx()
    pl.create_plugin(ctx)
    assert ctx.tools == {}


def test_preview_and_format_arguments():
    preview = pl._generate_preview({"prompt": "a cat", "path": "c.jpg", "width": 1600})
    assert "1600x1024" in preview["content"]
    assert preview["can_approve"] is True
    assert pl._format_arguments({"prompt": "a" * 200, "path": "c.jpg"}).startswith("c.jpg <- ")
