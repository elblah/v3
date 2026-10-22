"""Tests for the pure-stdlib HTML->text fallback in the web_search plugin.

The sandbox can block execvp, which kills lynx. In that case get_url_content
must still return readable text: fetch the HTML with urllib and strip it down
with html.parser. No network and no external binary is used here.
"""

import io

import pytest


# ---------------------------------------------------------------- html_to_text


def test_html_to_text_strips_script_and_style():
    from aicoder.plugins.web_search import html_to_text

    html = (
        "<html><head><style>body{color:red}</style>"
        "<script>var x = 1;</script></head>"
        "<body><p>Hello world</p></body></html>"
    )
    text = html_to_text(html)
    assert "Hello world" in text
    assert "var x" not in text
    assert "color:red" not in text


def test_html_to_text_skips_nested_skip_tags():
    from aicoder.plugins.web_search import html_to_text

    html = "<div><script><p>hidden</p></script><p>shown</p></div>"
    text = html_to_text(html)
    assert "hidden" not in text
    assert "shown" in text


def test_html_to_text_unescapes_entities():
    from aicoder.plugins.web_search import html_to_text

    assert "a < b & c > d" in html_to_text("<p>a &lt; b &amp; c &gt; d</p>")


def test_html_to_text_keeps_inline_word_spacing():
    from aicoder.plugins.web_search import html_to_text

    assert html_to_text("<p><b>junior</b> <i>developer</i></p>") == "junior developer"


def test_html_to_text_block_tags_become_line_breaks():
    from aicoder.plugins.web_search import html_to_text

    text = html_to_text("<h1>Title</h1><p>One</p><p>Two</p>")
    assert text.split("\n") == ["Title", "One", "Two"]


def test_html_to_text_collapses_whitespace_and_drops_blank_lines():
    from aicoder.plugins.web_search import html_to_text

    text = html_to_text("<p>  a   b\n\t c  </p><div></div><p></p>")
    assert text == "a b c"


def test_html_to_text_renders_external_links():
    from aicoder.plugins.web_search import html_to_text

    text = html_to_text('<p>see <a href="https://example.com/x">docs</a></p>')
    assert "docs <https://example.com/x>" in text


def test_html_to_text_skips_relative_and_anchor_links():
    from aicoder.plugins.web_search import html_to_text

    text = html_to_text('<a href="/local">home</a> <a href="#top">top</a>')
    assert "home" in text and "top" in text
    assert "/local" not in text and "#top" not in text


def test_html_to_text_list_items_are_bulleted():
    from aicoder.plugins.web_search import html_to_text

    lines = html_to_text("<ul><li>one<li>two</ul>").split("\n")
    assert lines == ["- one", "- two"]


def test_html_to_text_plain_text_passthrough():
    from aicoder.plugins.web_search import html_to_text

    assert html_to_text("just text") == "just text"


def test_html_to_text_empty_input():
    from aicoder.plugins.web_search import html_to_text

    assert html_to_text("") == ""


# ----------------------------------------------------------------- fetch_urllib


class _FakeResponse:
    def __init__(self, body: bytes, charset=None, length=None):
        headers = {}
        if charset:
            headers["Content-Type"] = f"text/html; charset={charset}"
        if length is not None:
            headers["Content-Length"] = str(length)

        class _Headers(dict):
            def get_content_charset(self):
                return charset

        self.headers = _Headers(headers)
        self._body = body

    def read(self, size=-1):
        if size is None or size < 0:
            data, self._body = self._body, b""
            return data
        data, self._body = self._body[:size], self._body[size:]
        return data

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


def _patch_urlopen(monkeypatch, response=None, error=None):
    import urllib.request

    def fake_urlopen(req, timeout=None):
        if error is not None:
            raise error
        return response

    monkeypatch.setattr(urllib.request, "urlopen", fake_urlopen)


def test_fetch_urllib_returns_decoded_html(monkeypatch):
    from aicoder.plugins.web_search import fetch_urllib

    _patch_urlopen(monkeypatch, _FakeResponse(b"<p>hi</p>", charset="utf-8"))
    text, error = fetch_urllib("https://example.com/")
    assert error is None
    assert text == "<p>hi</p>"


def test_fetch_urllib_honours_declared_charset(monkeypatch):
    from aicoder.plugins.web_search import fetch_urllib

    body = "caf\u00e9".encode("latin-1")
    _patch_urlopen(monkeypatch, _FakeResponse(body, charset="latin-1"))
    text, error = fetch_urllib("https://example.com/")
    assert error is None
    assert text == "caf\u00e9"


def test_fetch_urllib_falls_back_to_latin1_on_bad_utf8(monkeypatch):
    from aicoder.plugins.web_search import fetch_urllib

    _patch_urlopen(monkeypatch, _FakeResponse(b"\xff\xfe bad utf8"))
    text, error = fetch_urllib("https://example.com/")
    assert error is None
    assert "bad utf8" in text


def test_fetch_urllib_rejects_oversize_content_length(monkeypatch):
    from aicoder.plugins.web_search import MAX_HTML_BYTES, fetch_urllib

    _patch_urlopen(
        monkeypatch, _FakeResponse(b"x", length=MAX_HTML_BYTES + 1)
    )
    text, error = fetch_urllib("https://example.com/")
    assert text == ""
    assert "too large" in error.lower()


def test_fetch_urllib_rejects_oversize_stream(monkeypatch):
    from aicoder.plugins.web_search import MAX_HTML_BYTES, fetch_urllib

    # No Content-Length: the streaming cap must catch it.
    body = b"x" * (MAX_HTML_BYTES + 1024)
    _patch_urlopen(monkeypatch, _FakeResponse(body))
    text, error = fetch_urllib("https://example.com/")
    assert text == ""
    assert "too large" in error.lower()


def test_fetch_urllib_reports_http_error(monkeypatch):
    from aicoder.plugins.web_search import fetch_urllib

    exc = OSError("blocked")
    _patch_urlopen(monkeypatch, error=exc)
    text, error = fetch_urllib("https://example.com/")
    assert text == ""
    assert "blocked" in error


# ------------------------------------------------------- fetch_url_text fallback


def _make_ctx():
    class Ctx:
        def __init__(self):
            self.registered = {}
            self.hooks = {}

        def register_tool(self, name, fn, **kwargs):
            self.registered[name] = {"fn": fn, **kwargs}

        def register_hook(self, name, fn):
            self.hooks.setdefault(name, []).append(fn)

    return Ctx()


@pytest.fixture
def no_lynx(monkeypatch):
    """Plugin instance where lynx is reported missing (and never executed)."""
    monkeypatch.delenv("WEB_SEARCH_SCRIPT", raising=False)
    monkeypatch.delenv("WEB_SEARCH_URL_ALLOW", raising=False)
    monkeypatch.delenv("WEB_SEARCH_PROVIDERS", raising=False)
    from aicoder.plugins import web_search

    real_which = web_search.shutil.which
    monkeypatch.setattr(
        web_search.shutil,
        "which",
        lambda name, *a, **k: None if name == "lynx" else real_which(name, *a, **k),
    )
    ctx = _make_ctx()
    web_search.create_plugin(ctx)
    return ctx, web_search


def test_fetch_url_text_uses_stdlib_when_lynx_missing(no_lynx, monkeypatch):
    ctx, module = no_lynx
    monkeypatch.setattr(
        module,
        "fetch_urllib",
        lambda url, timeout=30: ("<h1>Title</h1><p>Body text</p>", None),
    )
    res = ctx.registered["get_url_content"]["fn"]({"url": "https://example.com/"})
    assert "Body text" in res["detailed"]
    assert "Title" in res["detailed"]


def test_fetch_url_text_stdlib_error_is_returned(no_lynx, monkeypatch):
    ctx, module = no_lynx
    monkeypatch.setattr(
        module,
        "fetch_urllib",
        lambda url, timeout=30: ("", "Error fetching URL: HTTP Error 403"),
    )
    res = ctx.registered["get_url_content"]["fn"]({"url": "https://example.com/"})
    assert "403" in res["detailed"]


def test_fetch_url_text_stdlib_empty_page_is_reported(no_lynx, monkeypatch):
    ctx, module = no_lynx
    monkeypatch.setattr(
        module, "fetch_urllib", lambda url, timeout=30: ("<script>x()</script>", None)
    )
    res = ctx.registered["get_url_content"]["fn"]({"url": "https://example.com/"})
    assert "no readable text" in res["detailed"]


def test_fetch_url_text_keeps_blocking_warning(no_lynx, monkeypatch):
    ctx, module = no_lynx
    monkeypatch.setattr(
        module,
        "fetch_urllib",
        lambda url, timeout=30: ("<p>Please verify you are human</p>", None),
    )
    res = ctx.registered["get_url_content"]["fn"]({"url": "https://example.com/"})
    assert "blocked this request as bot traffic" in res["detailed"]


def test_format_shows_stdlib_mode_without_lynx(no_lynx):
    ctx, _module = no_lynx
    fmt = ctx.registered["get_url_content"]["format_arguments"]
    out = fmt({"url": "https://example.com/"})
    assert "stdlib" in out
    assert "lynx" not in out


# ------------------------------------------------------------- raw HTML fallback


def test_fetch_url_raw_uses_stdlib_fetch(no_lynx, monkeypatch):
    ctx, module = no_lynx
    real_which = module.shutil.which
    # Hide gorl/curl as well so the urllib branch is exercised.
    monkeypatch.setattr(
        module.shutil,
        "which",
        lambda name, *a, **k: None
        if name in ("lynx", "gorl", "curl")
        else real_which(name, *a, **k),
    )
    monkeypatch.setattr(
        module, "fetch_urllib", lambda url, timeout=30: ("<p>raw</p>", None)
    )
    res = ctx.registered["get_url_content"]["fn"](
        {"url": "https://example.com/", "raw": True}
    )
    assert "<p>raw</p>" in res["detailed"]


def test_fetch_url_raw_stdlib_error_is_returned(no_lynx, monkeypatch):
    ctx, module = no_lynx
    real_which = module.shutil.which
    monkeypatch.setattr(
        module.shutil,
        "which",
        lambda name, *a, **k: None
        if name in ("lynx", "gorl", "curl")
        else real_which(name, *a, **k),
    )
    monkeypatch.setattr(
        module, "fetch_urllib", lambda url, timeout=30: ("", "Error: nope")
    )
    res = ctx.registered["get_url_content"]["fn"](
        {"url": "https://example.com/", "raw": True}
    )
    assert "Error: nope" in res["detailed"]


def test_fetch_urllib_module_import_shape():
    from aicoder.plugins import web_search

    assert callable(web_search.fetch_urllib)
    assert callable(web_search.html_to_text)
    assert web_search.MAX_HTML_BYTES > 0
    assert io  # keep io import used by future stream tests
