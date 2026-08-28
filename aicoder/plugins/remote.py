"""
Remote control plugin - control/view one aicoder instance from another.

/remote serve [port]   - accept one client (default: the client controls you)
/remote connect <host> [port] [--controlled]
                       - dial a server (default: you control the peer;
                         --controlled: the peer controls you)
/remote off            - stop serving / disconnect

Transport role (listen/dial) is decoupled from control role
(controlled/controller): whoever dials declares its control role and the
listener adopts the complement. A dial-only device (e.g. phone behind a
restricting VPN) can therefore be the controlled side. YOLO is forced on
the CONTROLLED side while a peer is connected.

Transport: raw TCP JSON-lines over TLS (ephemeral self-signed cert).
Auth: passkey (never sent); scrypt-derived key; mutual HMAC proof bound
to the server cert fingerprint AND the declared control role (MITM-safe).

Events controlled->controller: user_msg, assistant_msg, tool_result, status.
Controller->controlled: prompt, stop, ping.
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
    active = False           # engaged: serving or connected
    role = None              # control role while connected: "controlled"|"controller"
    dialer = False           # True if we dialed (connect) vs listened (serve)
    conn = None              # ssl socket to peer
    role_conn = None         # conn that owns the current role (release key)
    pending = deque()        # prompts from peer awaiting next turn
    lock = threading.Lock()  # guards pending
    send_lock = threading.Lock()
    last_sent = [None]       # controller: last prompt sent (echo suppression)
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
            _release_conn(conn)


def _release_conn(conn, quiet=False):
    """Drop conn; if it owned the control role, tear the role down (idempotent)."""
    with _st.lock:
        if _st.conn is conn:
            _st.conn = None
        if _st.role_conn is not conn:
            return
        _st.role_conn = None
        was_controlled = _st.role == "controlled"
        _st.role = None
    try:
        conn.close()
    except Exception:
        pass
    if was_controlled:
        _restore_yolo()
        if _st.dialer:
            _st.active = False
    if not quiet:
        LogUtils.printc("[Remote] peer gone - local control restored" if was_controlled
                        else "[Remote] peer disconnected", color="yellow")


def _readline(fobj):
    line = fobj.readline(MAX_LINE)
    if not line:
        raise ConnectionError("connection closed")
    return json.loads(line)


def _is_controlled():
    return _st.role == "controlled" and _st.conn is not None


def _force_yolo():
    _st.yolo_prev = Config.yolo_mode()
    if not _st.yolo_prev:
        Config.set_yolo_mode(True)
        LogUtils.printc("[Remote] YOLO enabled (all tools auto-approved)", color="yellow")


def _restore_yolo():
    if _st.yolo_prev is False:
        Config.set_yolo_mode(False)
        LogUtils.printc("[Remote] YOLO restored to off", color="yellow")
    _st.yolo_prev = None


# ---------------------------------------------------------------- server transport

def _server_serve(port):
    if _st.active:
        LogUtils.printc("[Remote] already engaged (/remote off to stop)", color="yellow")
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
    _st.dialer = False
    _st.active = True
    _st.listener_thread = threading.Thread(target=_serve_loop, daemon=True)
    _st.listener_thread.start()
    LogUtils.printc(f"[Remote] serving on 0.0.0.0:{port}", color="green")


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
        if _server_handshake(tls) is None:
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
    if _st.role == "controlled":
        _force_yolo()
        threading.Thread(target=_controlled_reader, args=(tls,), daemon=True).start()
    else:
        LogUtils.printc("[Remote] peer is controlled - press Enter to take control", color="cyan")
        threading.Thread(target=_controller_event_reader, args=(tls,), daemon=True).start()


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
        return None
    fp_seen = msg.get("fp", "")
    role = msg.get("role", "controller")
    if role not in ("controller", "controlled"):
        role = "controller"
    expected = _proof(_st.key, nonce_s, msg.get("nonce", ""), "client", fp_seen, role)
    if fp_seen != fp_s or not hmac.compare_digest(msg.get("proof", ""), expected):
        _send_raw(tls, {"t": "error", "msg": "auth failed"})
        return None
    _st.conn = tls
    _st.role = "controller" if role == "controlled" else "controlled"
    _st.role_conn = tls
    _send_raw(tls, {"t": "ready", "proof": _proof(_st.key, nonce_s, msg.get("nonce", ""), "server", fp_s)})
    return role


# ---------------------------------------------------------------- controlled side

def _controlled_reader(conn):
    """Inbound pump while controlled: prompts/stop/ping from the controller."""
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
        _release_conn(conn)


def _stop_serving():
    if not _st.active:
        return
    _st.active = False
    had_listener = _st.listener is not None
    if _st.conn:
        _release_conn(_st.conn, quiet=True)
    _st.role = None
    _st.role_conn = None
    if _st.listener:
        try:
            _st.listener.close()
        except Exception:
            pass
        _st.listener = None
    _restore_yolo()
    LogUtils.printc("[Remote] serving stopped" if had_listener else "[Remote] disconnected",
                    color="yellow")


# ---------------------------------------------------------------- controller side

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


def _event_reader(conn, last_sent):
    try:
        f = conn.makefile("r", encoding="utf-8")
        while True:
            _client_print_event(_readline(f), last_sent)
    except Exception:
        pass


def _controller_event_reader(conn):
    _event_reader(conn, _st.last_sent)
    _release_conn(conn)


def _controller_input_loop(conn):
    try:
        while _st.conn is conn:
            line = input()
            text = line.strip()
            if text in ("/detach", "/quit", "/off"):
                break
            if text:
                _st.last_sent[0] = text
                _send_raw(conn, {"t": "prompt", "text": text})
    except (KeyboardInterrupt, EOFError):
        print()


# ---------------------------------------------------------------- client transport

def _client_connect(host, port, controlled):
    if _st.active:
        LogUtils.printc("[Remote] already engaged (/remote off to stop)", color="red")
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
        role = "controlled" if controlled else "controller"

        f = conn.makefile("r", encoding="utf-8")
        hello = _readline(f)
        if hello.get("t") != "hello":
            raise ConnectionError("bad handshake")
        nonce_c = secrets.token_hex(16)
        fp_seen = hello.get("fp", "")
        conn.sendall((json.dumps({
            "t": "proof", "nonce": nonce_c, "fp": fp_seen, "role": role,
            "proof": _proof(key, hello.get("nonce", ""), nonce_c, "client", fp_seen, role),
        }) + "\n").encode("utf-8"))

        reply = _readline(f)
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

    _st.conn = conn
    _st.role_conn = conn
    _st.dialer = True
    _st.active = True
    if controlled:
        _st.role = "controlled"
        _force_yolo()
        LogUtils.printc("[Remote] connected - CONTROLLED by peer. /remote off to disconnect.",
                        color="green")
        threading.Thread(target=_controlled_reader, args=(conn,), daemon=True).start()
        return
    _st.role = "controller"
    LogUtils.printc(f"[Remote] connected to {host}:{port} - type to chat, /detach or Ctrl+C to release",
                    color="green")
    threading.Thread(target=_controller_event_reader, args=(conn,), daemon=True).start()
    _controller_input_loop(conn)
    if _st.conn is conn:
        _release_conn(conn, quiet=True)
        print("[Remote] detached")


# ---------------------------------------------------------------- hooks

def on_before_user_prompt():
    """Park the local main loop while a peer is connected."""
    if _st.conn is None or _st.role is None:
        return
    if _st.role == "controller":
        conn = _st.conn
        _controller_input_loop(conn)
        if _st.conn is conn:
            _release_conn(conn, quiet=True)
            LogUtils.printc("[Remote] control released - local use restored", color="yellow")
        return
    # controlled: block until the controller sends a prompt
    LogUtils.printc("[Remote] waiting for peer input (Ctrl+C to disconnect)", color="cyan")
    try:
        while _st.conn is not None and not _app.has_next_prompt():
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
    if _is_controlled():
        _send({"t": "status", "processing": True})


def on_after_ai_processing(has_tool_calls=None):
    if _is_controlled():
        _send({"t": "status", "processing": False})


def on_user_message(message):
    if _is_controlled():
        _send({"t": "user_msg", "text": message.get("content") or ""})


def on_assistant_message(message):
    if _is_controlled():
        content = message.get("content")
        if content:
            _send({"t": "assistant_msg", "text": content})


def on_tool_result(message):
    if _is_controlled():
        text = message.get("content") or ""
        if len(text) > TOOL_RESULT_TRUNC:
            text = text[:TOOL_RESULT_TRUNC] + f" ...(+{len(text) - TOOL_RESULT_TRUNC} chars)"
        _send({"t": "tool_result", "text": text})


# ---------------------------------------------------------------- command

def _cmd_remote(args_str):
    parts = args_str.strip().split()
    if not parts:
        print("Usage: /remote serve [port] | /remote connect <host> [port] [--controlled] | /remote off")
        return
    sub = parts[0]
    if sub == "serve":
        port = int(parts[1]) if len(parts) > 1 else DEFAULT_PORT
        _server_serve(port)
    elif sub == "connect":
        args = [p for p in parts[1:] if p != "--controlled"]
        controlled = len(args) != len(parts) - 1
        if not args:
            print("Usage: /remote connect <host> [port] [--controlled]")
            return
        port = int(args[1]) if len(args) > 1 else DEFAULT_PORT
        _client_connect(args[0], port, controlled)
    elif sub == "off":
        _stop_serving()
    else:
        print("Usage: /remote serve [port] | /remote connect <host> [port] [--controlled] | /remote off")


def create_plugin(ctx):
    global _app
    _app = ctx.app
    atexit.register(_stop_serving)

    ctx.register_command("remote", _cmd_remote, "Remote control: serve | connect <host> [--controlled] | off")
    ctx.register_hook("before_user_prompt", on_before_user_prompt)
    ctx.register_hook("before_ai_processing", on_before_ai_processing)
    ctx.register_hook("after_ai_processing", on_after_ai_processing)
    ctx.register_hook("after_user_message_added", on_user_message)
    ctx.register_hook("after_assistant_message_added", on_assistant_message)
    ctx.register_hook("after_tool_results_added", on_tool_result)

    if Config.debug():
        LogUtils.print("  - /remote command")
        LogUtils.print("  - remote mirror hooks")
