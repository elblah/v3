"""
Remote control plugin - control/view one aicoder instance from another.

/remote serve [port]   - this instance accepts one client (forces YOLO)
/remote connect <host> [port] - mirror a remote server (local instance sleeps)
/remote off            - stop serving

Transport: raw TCP JSON-lines over TLS (ephemeral self-signed cert).
Auth: passkey (never sent); scrypt-derived key; mutual HMAC proof bound
to the server cert fingerprint (MITM-safe despite untrusted cert).

Server->client events: user_msg, assistant_msg, tool_result, status.
Client->server: prompt, stop, ping.
"""

import atexit
import getpass
import hashlib
import hmac
import json
import os
import secrets
import socket
import ssl
import subprocess
import sys
import textwrap
import threading
import time
from collections import deque

from aicoder.core.config import Config
from aicoder.utils.log import LogUtils

DEFAULT_PORT = 8765
SALT = b"aicoder-remote-v1"
MAX_LINE = 1024 * 1024
CERT_DIR = "/tmp/aicoder-remote"
TOOL_RESULT_TRUNC = 800

_app = None


class _State:
    active = False           # serving
    conn = None              # ssl socket to client (server role)
    pending = deque()        # prompts from client awaiting next turn
    lock = threading.Lock()  # guards pending
    send_lock = threading.Lock()
    yolo_prev = None
    listener = None
    listener_thread = None
    srv_ctx = None


_st = _State()


# ---------------------------------------------------------------- crypto

def _derive_key(passkey):
    return hashlib.scrypt(passkey.encode(), salt=SALT, n=2 ** 14, r=8, p=1, dklen=32)


def _fp(der):
    return hashlib.sha256(der).hexdigest()


def _proof(key, *parts):
    return hmac.new(key, b"|".join(p.encode() for p in parts), hashlib.sha256).hexdigest()


def _ensure_cert():
    cert = os.path.join(CERT_DIR, "cert.pem")
    key = os.path.join(CERT_DIR, "key.pem")
    if os.path.exists(cert) and os.path.exists(key):
        return cert, key
    os.makedirs(CERT_DIR, exist_ok=True)
    subprocess.run(
        ["openssl", "req", "-x509", "-newkey", "rsa:2048", "-nodes",
         "-days", "3650", "-subj", "/CN=aicoder-remote",
         "-keyout", key, "-out", cert],
        check=True, capture_output=True)
    return cert, key


# ---------------------------------------------------------------- io helpers

def _send(obj):
    with _st.send_lock:
        conn = _st.conn
        if not conn:
            return
        try:
            conn.sendall((json.dumps(obj) + "\n").encode("utf-8"))
        except Exception:
            _drop_conn(conn)


def _drop_conn(conn):
    if _st.conn is conn:
        _st.conn = None
    try:
        conn.close()
    except Exception:
        pass


def _readline(fobj):
    line = fobj.readline(MAX_LINE)
    if not line:
        raise ConnectionError("connection closed")
    return json.loads(line)


def _active():
    return _st.active and _st.conn is not None


# ---------------------------------------------------------------- server role

def _server_serve(port):
    if _st.active:
        LogUtils.printc("[Remote] already serving (Ctrl+C to stop)", color="yellow")
        return
    passkey = getpass.getpass("Remote passkey: ")
    if not passkey:
        return
    try:
        cert, key = _ensure_cert()
    except Exception as e:
        LogUtils.printc(f"[Remote] openssl cert generation failed: {e}", color="red")
        return

    _st.key = _derive_key(passkey)
    _st.srv_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    _st.srv_ctx.load_cert_chain(cert, key)

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind(("0.0.0.0", port))
    except OSError as e:
        LogUtils.printc(f"[Remote] bind failed: {e}", color="red")
        return
    srv.listen(1)
    srv.settimeout(1.0)
    _st.listener = srv
    _st.active = True
    _st.yolo_prev = Config.yolo_mode()
    if not _st.yolo_prev:
        Config.set_yolo_mode(True)
        LogUtils.printc("[Remote] YOLO enabled (all tools auto-approved)", color="yellow")
    _st.listener_thread = threading.Thread(target=_serve_loop, daemon=True)
    _st.listener_thread.start()
    atexit.register(_stop_serving)
    LogUtils.printc(f"[Remote] serving on 0.0.0.0:{port} - Ctrl+C to stop", color="green")


def _serve_loop():
    srv = _st.listener
    while _st.active:
        try:
            sock, addr = srv.accept()
        except socket.timeout:
            continue
        except OSError:
            break
        _accept_client(sock, addr)
    try:
        srv.close()
    except Exception:
        pass


def _accept_client(sock, addr):
    try:
        tls = _st.srv_ctx.wrap_socket(sock, server_side=True)
        tls.settimeout(30)
        if _st.conn is not None:
            _send_raw(tls, {"t": "error", "msg": "server busy: another client connected"})
            tls.close()
            return
        if not _server_handshake(tls):
            tls.close()
            return
        tls.settimeout(None)
    except Exception as e:
        LogUtils.printc(f"[Remote] client handshake failed: {e}", color="red")
        try:
            sock.close()
        except Exception:
            pass
        return

    LogUtils.printc(f"[Remote] client connected from {addr[0]}", color="green")
    threading.Thread(target=_client_reader, args=(tls,), daemon=True).start()


def _send_raw(sock, obj):
    try:
        sock.sendall((json.dumps(obj) + "\n").encode("utf-8"))
    except Exception:
        pass


def _server_handshake(tls):
    nonce_s = secrets.token_hex(16)
    fp_s = _fp(tls.getpeercert(True) or b"")
    _send_raw(tls, {"t": "hello", "nonce": nonce_s, "fp": fp_s})
    msg = _readline(tls.makefile("r", encoding="utf-8"))
    if msg.get("t") != "proof":
        return False
    fp_seen = msg.get("fp", "")
    expected = _proof(_st.key, nonce_s, msg.get("nonce", ""), "client", fp_seen)
    if fp_seen != fp_s or not hmac.compare_digest(msg.get("proof", ""), expected):
        _send_raw(tls, {"t": "error", "msg": "auth failed"})
        return False
    _st.conn = tls
    _send_raw(tls, {"t": "ready", "proof": _proof(_st.key, nonce_s, msg.get("nonce", ""), "server", fp_s)})
    return True


def _client_reader(conn):
    try:
        f = conn.makefile("r", encoding="utf-8")
        while True:
            msg = _readline(f)
            t = msg.get("t")
            if t == "prompt":
                text = str(msg.get("text", "")).strip()
                if text:
                    with _st.lock:
                        _st.pending.append(text)
            elif t == "stop":
                _app.is_processing = False
            elif t == "ping":
                _send({"t": "pong"})
    except Exception:
        pass
    finally:
        was = _st.conn is conn
        _drop_conn(conn)
        if was and _st.active:
            LogUtils.printc("[Remote] client disconnected", color="yellow")


def _stop_serving():
    if not _st.active:
        return
    _st.active = False
    if _st.conn:
        _drop_conn(_st.conn)
    if _st.listener:
        try:
            _st.listener.close()
        except Exception:
            pass
    if _st.yolo_prev is False:
        Config.set_yolo_mode(False)
        LogUtils.printc("[Remote] YOLO restored to off", color="yellow")
    _st.yolo_prev = None
    LogUtils.printc("[Remote] serving stopped", color="yellow")


# ---------------------------------------------------------------- hooks

def on_before_user_prompt():
    """While serving with a client connected: block main loop for remote prompts."""
    if not _active() or _app.has_next_prompt():
        return
    LogUtils.printc("[Remote] waiting for client input (Ctrl+C stops serving)", color="cyan")
    try:
        while _st.active and _st.conn is not None and not _app.has_next_prompt():
            with _st.lock:
                if _st.pending:
                    break
            time.sleep(0.2)
    except KeyboardInterrupt:
        _stop_serving()
        return
    with _st.lock:
        if _st.pending:
            _app.set_next_prompt(_st.pending.popleft())


def on_before_ai_processing():
    if _active():
        _send({"t": "status", "processing": True})


def on_after_ai_processing(has_tool_calls=None):
    if _active():
        _send({"t": "status", "processing": False})


def on_user_message(message):
    if _active():
        _send({"t": "user_msg", "text": message.get("content") or ""})


def on_assistant_message(message):
    if _active():
        content = message.get("content")
        if content:
            _send({"t": "assistant_msg", "text": content})


def on_tool_result(message):
    if _active():
        text = message.get("content") or ""
        if len(text) > TOOL_RESULT_TRUNC:
            text = text[:TOOL_RESULT_TRUNC] + f" ...(+{len(text) - TOOL_RESULT_TRUNC} chars)"
        _send({"t": "tool_result", "text": text})


# ---------------------------------------------------------------- client role

def _wrap_print(tag, text):
    width = max(20, shutil_get_width() - len(tag) - 1)
    body = textwrap.fill(str(text), width, subsequent_indent=" " * (len(tag) + 1))
    print(f"{tag} {body}")


def shutil_get_width():
    try:
        return os.get_terminal_size().columns
    except OSError:
        return 80


def _client_print_event(msg, last_sent):
    t = msg.get("t")
    if t == "user_msg":
        text = msg.get("text", "")
        if last_sent[0] is not None and text == last_sent[0]:
            last_sent[0] = None
            return
        _wrap_print("\x1b[1mUSER>\x1b[0m", text)
    elif t == "assistant_msg":
        _wrap_print("\x1b[1mAI>\x1b[0m", msg.get("text", ""))
    elif t == "tool_result":
        _wrap_print("\x1b[2mTOOL>\x1b[0m", msg.get("text", ""))
    elif t == "status":
        if msg.get("processing"):
            print("\x1b[2m--- processing ---\x1b[0m")
        else:
            print("\x1b[2m--- idle ---\x1b[0m")
    elif t == "error":
        LogUtils.printc(f"[Remote] {msg.get('msg', 'error')}", color="red")


def _client_reader_thread(conn, stop, last_sent):
    try:
        f = conn.makefile("r", encoding="utf-8")
        while not stop.is_set():
            _client_print_event(_readline(f), last_sent)
    except Exception:
        pass
    finally:
        stop.set()


def _client_connect(host, port):
    if _st.active:
        LogUtils.printc("[Remote] cannot connect while serving", color="red")
        return
    passkey = getpass.getpass("Remote passkey: ")
    if not passkey:
        return
    try:
        raw = socket.create_connection((host, port), timeout=15)
    except OSError as e:
        LogUtils.printc(f"[Remote] connect failed: {e}", color="red")
        return
    conn = None
    try:
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        conn = ctx.wrap_socket(raw)
        conn.settimeout(30)
        key = _derive_key(passkey)

        hello = _readline(conn.makefile("r", encoding="utf-8"))
        if hello.get("t") != "hello":
            raise ConnectionError("bad handshake")
        nonce_c = secrets.token_hex(16)
        fp_seen = hello.get("fp", "")
        conn.sendall((json.dumps({
            "t": "proof", "nonce": nonce_c, "fp": fp_seen,
            "proof": _proof(key, hello.get("nonce", ""), nonce_c, "client", fp_seen),
        }) + "\n").encode("utf-8"))

        reply = _readline(conn.makefile("r", encoding="utf-8"))
        if reply.get("t") == "error":
            raise ConnectionError(reply.get("msg", "auth failed"))
        if reply.get("t") != "ready":
            raise ConnectionError("bad handshake")
        expected = _proof(key, hello.get("nonce", ""), nonce_c, "server", fp_seen)
        if not hmac.compare_digest(reply.get("proof", ""), expected):
            raise ConnectionError("server auth failed (possible MITM)")
        conn.settimeout(None)
    except Exception as e:
        LogUtils.printc(f"[Remote] connect failed: {e}", color="red")
        for s in (conn, raw):
            if s:
                try:
                    s.close()
                except Exception:
                    pass
        return

    print(f"[Remote] connected to {host}:{port}. Ctrl+C detaches. Type to chat.")
    stop = threading.Event()
    last_sent = [None]
    threading.Thread(target=_client_reader_thread, args=(conn, stop, last_sent), daemon=True).start()
    try:
        while not stop.is_set():
            line = input()
            text = line.strip()
            if text in ("/detach", "/quit", "/off"):
                break
            if text:
                last_sent[0] = text
                _send_raw(conn, {"t": "prompt", "text": text})
    except KeyboardInterrupt:
        print()
    except EOFError:
        print()
    finally:
        stop.set()
        try:
            conn.close()
        except Exception:
            pass
        print("[Remote] detached")


# ---------------------------------------------------------------- command

def _cmd_remote(args_str):
    parts = args_str.strip().split()
    if not parts:
        print("Usage: /remote serve [port] | /remote connect <host> [port] | /remote off")
        return
    sub = parts[0]
    if sub == "serve":
        port = int(parts[1]) if len(parts) > 1 else DEFAULT_PORT
        _server_serve(port)
    elif sub == "connect":
        if len(parts) < 2:
            print("Usage: /remote connect <host> [port]")
            return
        port = int(parts[2]) if len(parts) > 2 else DEFAULT_PORT
        _client_connect(parts[1], port)
    elif sub == "off":
        _stop_serving()
    else:
        print("Usage: /remote serve [port] | /remote connect <host> [port] | /remote off")


def create_plugin(ctx):
    global _app
    _app = ctx.app

    ctx.register_command("remote", _cmd_remote, "Remote control: serve | connect <host> | off")
    ctx.register_hook("before_user_prompt", on_before_user_prompt)
    ctx.register_hook("before_ai_processing", on_before_ai_processing)
    ctx.register_hook("after_ai_processing", on_after_ai_processing)
    ctx.register_hook("after_user_message_added", on_user_message)
    ctx.register_hook("after_assistant_message_added", on_assistant_message)
    ctx.register_hook("after_tool_results_added", on_tool_result)

    if Config.debug():
        LogUtils.print("  - /remote command")
        LogUtils.print("  - remote mirror hooks")
