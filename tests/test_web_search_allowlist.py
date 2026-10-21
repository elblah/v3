"""Tests for the WEB_SEARCH_URL_ALLOW gate in the web_search plugin.

The allowlist is a newline-separated list of regexes matched against the full
URL of a get_url_content call. Unset/empty means no restriction; a URL that
matches no pattern is refused before any fetcher (gateway included) runs.
Configured-but-broken (no valid regex) fails closed.
"""

import os

import pytest


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


def _fake_gateway(tmp_path, marker="GATEWAY-HIT"):
    """Executable stub used in place of the real fetch gateway (no network)."""
    script = tmp_path / "fake-gw"
    script.write_text(f'#!/usr/bin/env bash\necho "{marker}:$2"\n')
    script.chmod(0o755)
    return str(script)


@pytest.fixture
def ctx(monkeypatch):
    """Plugin instance with the fetch gateway stubbed out (no network access)."""
    monkeypatch.delenv("WEB_SEARCH_URL_ALLOW", raising=False)
    monkeypatch.delenv("WEB_SEARCH_PROVIDERS", raising=False)
    from aicoder.plugins import web_search

    made = _make_ctx()
    web_search.create_plugin(made)
    return made


def _hook(ctx):
    return ctx.hooks["before_approval_prompt"][0]


def _call(ctx, args):
    return ctx.registered["get_url_content"]["fn"](args)


def test_unset_allowlist_fetches_normally(ctx, monkeypatch, tmp_path):
    monkeypatch.setenv("WEB_SEARCH_SCRIPT", _fake_gateway(tmp_path))
    res = _call(ctx, {"url": "https://example.com/x"})
    assert "GATEWAY-HIT:https://example.com/x" in res["detailed"]


def test_matching_url_passes(ctx, monkeypatch, tmp_path):
    monkeypatch.setenv("WEB_SEARCH_SCRIPT", _fake_gateway(tmp_path))
    monkeypatch.setenv(
        "WEB_SEARCH_URL_ALLOW", r"https://([a-z0-9-]+\.)*github\.com/"
    )
    res = _call(ctx, {"url": "https://gist.github.com/abc"})
    assert "GATEWAY-HIT:https://gist.github.com/abc" in res["detailed"]


def test_non_matching_url_refused_before_fetch(ctx, monkeypatch, tmp_path):
    monkeypatch.setenv("WEB_SEARCH_SCRIPT", _fake_gateway(tmp_path))
    monkeypatch.setenv(
        "WEB_SEARCH_URL_ALLOW", r"https://([a-z0-9-]+\.)*github\.com/"
    )
    res = _call(ctx, {"url": "https://example.com/x"})
    assert "GATEWAY-HIT" not in res["detailed"]
    assert "refused by project allowlist" in res["detailed"]
    assert "github" in res["detailed"]  # patterns echoed so the AI can adapt


def test_raw_fetch_is_gated_too(ctx, monkeypatch):
    monkeypatch.setenv("WEB_SEARCH_URL_ALLOW", r"https://github\.com/")
    res = _call(ctx, {"url": "https://example.com/x", "raw": True})
    assert "refused by project allowlist" in res["detailed"]


def test_comments_and_blank_lines_ignored(ctx, monkeypatch, tmp_path):
    monkeypatch.setenv("WEB_SEARCH_SCRIPT", _fake_gateway(tmp_path))
    monkeypatch.setenv(
        "WEB_SEARCH_URL_ALLOW",
        "# project allowlist\n\n   https://github\\.com/   \n# trailing note\n",
    )
    allowed = _call(ctx, {"url": "https://github.com/a/b"})
    assert "GATEWAY-HIT" in allowed["detailed"]
    blocked = _call(ctx, {"url": "https://gitlab.com/a/b"})
    assert "refused by project allowlist" in blocked["detailed"]


def test_no_valid_regex_fails_closed(ctx):
    # Set but unusable -> refuse everything rather than silently allow all.
    os.environ["WEB_SEARCH_URL_ALLOW"] = "[unclosed"
    try:
        from aicoder.plugins import web_search

        fresh = _make_ctx()
        web_search.create_plugin(fresh)
        res = _call(fresh, {"url": "https://github.com/a/b"})
        assert "no valid regex" in res["detailed"]
    finally:
        os.environ.pop("WEB_SEARCH_URL_ALLOW", None)


# --- approval prompt behaviour -------------------------------------------
# Denied URLs must not reach the prompt: the hook returns the refusal text,
# which the executor hands to the model as the tool result.


def test_hook_denies_off_list_url_with_reason(ctx, monkeypatch):
    monkeypatch.setenv(
        "WEB_SEARCH_URL_ALLOW", r"https://([a-z0-9-]+\.)*github\.com/"
    )
    verdict = _hook(ctx)("get_url_content", {"url": "https://example.com/x"})
    assert isinstance(verdict, str)
    assert "refused" in verdict
    assert "github" in verdict  # pattern list echoed so the model can retry


def test_hook_returns_none_for_allowed_url(ctx, monkeypatch):
    monkeypatch.setenv(
        "WEB_SEARCH_URL_ALLOW", r"https://([a-z0-9-]+\.)*github\.com/"
    )
    assert _hook(ctx)("get_url_content", {"url": "https://github.com/a/b"}) is None


def test_hook_returns_none_when_allowlist_unset(ctx):
    assert _hook(ctx)("get_url_content", {"url": "https://example.com/x"}) is None


def test_hook_ignores_other_tools(ctx, monkeypatch):
    monkeypatch.setenv("WEB_SEARCH_URL_ALLOW", r"https://github\.com/")
    assert _hook(ctx)("web_search", {"query": "https://example.com"}) is None
    assert _hook(ctx)("read_file", {"path": "/etc/passwd"}) is None


# --- multiline env values -------------------------------------------------
# The natural way to write this in a shell starts and ends with a blank line:
#   export WEB_SEARCH_URL_ALLOW="
#   regex1
#   regex2
#   "
# Empty lines anywhere (leading, trailing, in between) carry no pattern and
# must be skipped, not treated as an "everything matches" or a bad entry.


def test_leading_and_trailing_blank_lines_ignored(ctx, monkeypatch, tmp_path):
    monkeypatch.setenv("WEB_SEARCH_SCRIPT", _fake_gateway(tmp_path))
    monkeypatch.setenv(
        "WEB_SEARCH_URL_ALLOW",
        "\n" r"https://github\.com/" "\n" r"https://docs\.python\.org/" "\n",
    )
    hook = _hook(ctx)

    assert hook("get_url_content", {"url": "https://github.com/a/b"}) is None
    assert hook("get_url_content", {"url": "https://docs.python.org/3/"}) is None

    verdict = hook("get_url_content", {"url": "https://example.com/x"})
    assert isinstance(verdict, str) and "refused" in verdict

    hit = _call(ctx, {"url": "https://github.com/a/b"})
    assert "GATEWAY-HIT" in hit["detailed"]
    blocked = _call(ctx, {"url": "https://example.com/x"})
    assert "refused by project allowlist" in blocked["detailed"]


def test_whitespace_only_value_is_unrestricted(ctx, monkeypatch, tmp_path):
    # "\n\n" holds no pattern at all: treat it as "no allowlist configured"
    # rather than as a non-empty allowlist that would deny everything.
    monkeypatch.setenv("WEB_SEARCH_SCRIPT", _fake_gateway(tmp_path))
    monkeypatch.setenv("WEB_SEARCH_URL_ALLOW", "\n\n")
    assert _hook(ctx)("get_url_content", {"url": "https://example.com/x"}) is None
    assert "GATEWAY-HIT" in _call(ctx, {"url": "https://example.com/x"})["detailed"]
