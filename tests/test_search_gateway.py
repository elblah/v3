"""
Tests for the search gateway (examples/search-gateway) and the web_search
plugin's optional WEB_SEARCH_SCRIPT routing.

The gateway mirrors the vision-gateway pattern: a bash script that bridges
aicoder -> dtx `gobrow`. If WEB_SEARCH_SCRIPT is set and resolves to an
executable, web_search/get_url_content route through it; otherwise the native
lynx logic is used unchanged.

These tests are self-contained: a mock dtx socket (unix domain) stands in for
the real dtx service, and a tiny fake gateway script exercises the plugin path
without touching the network.
"""

import os
import socket
import subprocess
import tempfile
import threading

import pytest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEARCH_GATEWAY = os.path.join(REPO_ROOT, "examples", "search-gateway")


def _have_transport():
    """The gateway needs nc (with -U) or socat."""
    for tool in ("nc", "socat"):
        if subprocess.run(["which", tool], capture_output=True, check=False).returncode == 0:
            return True
    return False


def _start_mock_dtx(output_text):
    """Spin up a mock dtx socket that replies in the dtx protocol format.

    Reads the incoming command line (until newline), records it, then responds
    with an `Output:` section. Returns (sock_path, captured_dict, thread).
    """
    d = tempfile.mkdtemp()
    sock_path = os.path.join(d, "dtx.sock")
    srv = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    srv.bind(sock_path)
    srv.listen(1)
    captured = {}

    def serve():
        conn, _ = srv.accept()
        buf = b""
        while b"\n" not in buf:
            chunk = conn.recv(4096)
            if not chunk:
                break
            buf += chunk
        captured["cmd"] = buf.decode(errors="replace").strip()
        resp = (
            "Exit code: 0\n\n"
            "Output:\n"
            f"{output_text}\n\n"
            "Stderr:\n"
        )
        conn.sendall(resp.encode())
        conn.close()
        srv.close()

    t = threading.Thread(target=serve, daemon=True)
    t.start()
    return sock_path, captured, t


def _gateway_env(sock_path):
    env = dict(os.environ)
    env["DTX_SOCKET"] = sock_path
    return env


@pytest.mark.skipif(not _have_transport(), reason="need nc or socat")
def test_gateway_search_forwards_gobrow_search():
    sock_path, captured, _ = _start_mock_dtx("Brave\n1. [Result](https://example.com)")
    try:
        out = subprocess.run(
            [SEARCH_GATEWAY, "search", "raspberry pi"],
            capture_output=True, text=True, env=_gateway_env(sock_path), timeout=30, check=False,
        )
        assert out.returncode == 0, out.stderr
        assert "Result" in out.stdout
        assert captured["cmd"] == "gobrow search -max-tokens 8000 raspberry pi"
    finally:
        os.unlink(sock_path)


@pytest.mark.skipif(not _have_transport(), reason="need nc or socat")
def test_gateway_fetch_forwards_gobrow_fetch():
    sock_path, captured, _ = _start_mock_dtx("# Page title\n\nSome markdown body.")
    try:
        out = subprocess.run(
            [SEARCH_GATEWAY, "fetch", "https://example.com/page"],
            capture_output=True, text=True, env=_gateway_env(sock_path), timeout=30, check=False,
        )
        assert out.returncode == 0, out.stderr
        assert "Page title" in out.stdout
        assert captured["cmd"] == "gobrow -max-tokens 8000 https://example.com/page"
    finally:
        os.unlink(sock_path)


@pytest.mark.skipif(not _have_transport(), reason="need nc or socat")
def test_gateway_missing_socket_fails():
    env = _gateway_env("/nonexistent/dir/dtx.sock")
    out = subprocess.run(
        [SEARCH_GATEWAY, "search", "anything"],
        capture_output=True, text=True, env=env, timeout=30, check=False,
    )
    assert out.returncode != 0
    assert "socket not found" in out.stderr


def _make_ctx():
    class Ctx:
        def __init__(self):
            self.registered = {}

        def register_tool(self, name, fn, **kwargs):
            self.registered[name] = {"fn": fn, **kwargs}

    return Ctx()


def _call_tool(ctx, name, args):
    return ctx.registered[name]["fn"](args)


def test_plugin_routes_search_through_gateway():
    gw = os.path.join(tempfile.mkdtemp(), "fake-gw")
    with open(gw, "w") as f:
        f.write('#!/usr/bin/env bash\necho "GW:$1:$2"\n')
    os.chmod(gw, 0o755)
    saved = os.environ.get("WEB_SEARCH_SCRIPT")
    os.environ["WEB_SEARCH_SCRIPT"] = gw
    try:
        from aicoder.plugins import web_search
        ctx = _make_ctx()
        web_search.create_plugin(ctx)
        res = _call_tool(ctx, "web_search", {"query": "hello world"})
        assert "GW:search:hello world" in res["detailed"]
    finally:
        if saved is None:
            os.environ.pop("WEB_SEARCH_SCRIPT", None)
        else:
            os.environ["WEB_SEARCH_SCRIPT"] = saved


def test_plugin_routes_fetch_through_gateway():
    gw = os.path.join(tempfile.mkdtemp(), "fake-gw")
    with open(gw, "w") as f:
        f.write('#!/usr/bin/env bash\necho "GW:$1:$2"\n')
    os.chmod(gw, 0o755)
    saved = os.environ.get("WEB_SEARCH_SCRIPT")
    os.environ["WEB_SEARCH_SCRIPT"] = gw
    try:
        from aicoder.plugins import web_search
        ctx = _make_ctx()
        web_search.create_plugin(ctx)
        res = _call_tool(ctx, "get_url_content", {"url": "https://example.com/x"})
        assert "GW:fetch:https://example.com/x" in res["detailed"]
    finally:
        if saved is None:
            os.environ.pop("WEB_SEARCH_SCRIPT", None)
        else:
            os.environ["WEB_SEARCH_SCRIPT"] = saved


def test_plugin_falls_back_to_native_when_gateway_unset():
    saved = os.environ.get("WEB_SEARCH_SCRIPT")
    os.environ.pop("WEB_SEARCH_SCRIPT", None)
    providers_saved = os.environ.pop("WEB_SEARCH_PROVIDERS", None)
    try:
        from aicoder.plugins import web_search
        ctx = _make_ctx()
        web_search.create_plugin(ctx)
        # No providers + no gateway -> native "not configured" path runs.
        res = _call_tool(ctx, "web_search", {"query": "hello"})
        assert "not configured" in res["detailed"].lower()
    finally:
        if saved is None:
            os.environ.pop("WEB_SEARCH_SCRIPT", None)
        else:
            os.environ["WEB_SEARCH_SCRIPT"] = saved
        if providers_saved is not None:
            os.environ["WEB_SEARCH_PROVIDERS"] = providers_saved


def test_format_arguments_reports_gateway_mode():
    gw = os.path.join(tempfile.mkdtemp(), "fake-gw")
    with open(gw, "w") as f:
        f.write('#!/usr/bin/env bash\necho hi\n')
    os.chmod(gw, 0o755)
    saved = os.environ.get("WEB_SEARCH_SCRIPT")
    os.environ["WEB_SEARCH_SCRIPT"] = gw
    try:
        from aicoder.plugins import web_search
        ctx = _make_ctx()
        web_search.create_plugin(ctx)

        ws_fmt = ctx.registered["web_search"]["format_arguments"]
        assert "gateway (WEB_SEARCH_SCRIPT)" in ws_fmt({"query": "rpi"})
        assert "Query: rpi" in ws_fmt({"query": "rpi"})

        guc_fmt = ctx.registered["get_url_content"]["format_arguments"]
        assert "gateway (WEB_SEARCH_SCRIPT)" in guc_fmt({"url": "https://e.com", "raw": False})
        # raw fetch never uses the gateway
        assert "no gateway" in guc_fmt({"url": "https://e.com", "raw": True})
    finally:
        if saved is None:
            os.environ.pop("WEB_SEARCH_SCRIPT", None)
        else:
            os.environ["WEB_SEARCH_SCRIPT"] = saved


def test_format_arguments_reports_native_mode_without_gateway():
    saved = os.environ.get("WEB_SEARCH_SCRIPT")
    os.environ.pop("WEB_SEARCH_SCRIPT", None)
    try:
        from aicoder.plugins import web_search
        ctx = _make_ctx()
        web_search.create_plugin(ctx)
        ws_fmt = ctx.registered["web_search"]["format_arguments"]
        assert "native" in ws_fmt({"query": "rpi"})
        guc_fmt = ctx.registered["get_url_content"]["format_arguments"]
        assert "native" in guc_fmt({"url": "https://e.com", "raw": False})
    finally:
        if saved is None:
            os.environ.pop("WEB_SEARCH_SCRIPT", None)
        else:
            os.environ["WEB_SEARCH_SCRIPT"] = saved
