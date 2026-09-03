"""
Remote control plugin - drive one aicoder instance from another.

/remote serve [port] [--control]
                       - listen for one peer. Default: you are CONTROLLED
                         (the peer drives you, your prompt vanishes).
                         --control: you stay the CONTROLLER (prompt stays
                         local; once the peer dials in, your prompts run there).
/remote connect <host> [port]
                       - dial a server. The server's mode decides your role:
                         it is the complement of what the server chose.
/remote off            - stop serving / disconnect / release control.

The server fixes the control role at serve time and proof-binds it into the
handshake; the client cannot choose (a dial-only device can still be the
controlled side). YOLO is forced on the CONTROLLED side while a peer is
connected. One rule while connected: only the controller has a prompt; the
controlled side is a pure mirror and Ctrl+C releases.

Transport: raw TCP JSON-lines over TLS (ephemeral self-signed cert).
Auth: passkey (never sent); scrypt-derived key; mutual HMAC proof bound to
the server cert fingerprint AND the negotiated mode (MITM-safe).

Events controlled->controller: user_msg, assistant_msg, tool_result, status.
Controller->controlled: prompt, inject, stop, ping.
"""

import atexit
import builtins
import getpass
import hashlib
import hmac
import json
import os
import secrets
import signal
import socket
import ssl
import subprocess
import threading
import time
from collections import deque

from aicoder.core.config import Config
from aicoder.core.markdown_colorizer import MarkdownColorizer
from aicoder.utils.log import LogUtils

DEFAULT_PORT = 8000
SALT = b"aicoder-remote-v1"
MAX_LINE = 1024 * 1024
CERT_DIR = "/tmp/aicoder-remote"

_app = None


class _State:
    active = False           # engaged: serving or connected
    want = None              # server-side control role fixed at serve time
    role = None              # control role while connected: "controlled"|"controller"
    dialer = False           # True if we dialed (connect) vs listened (serve)
    conn = None              # ssl socket to peer
    role_conn = None         # conn that owns the current role (release key)
    pending = deque()        # prompts from peer awaiting next turn
    lock = threading.Lock()  # guards pending
    send_lock = threading.Lock()
    last_sent = [None]       # controller: last prompt sent (echo suppression)
    busy = False             # controller: peer is processing a prompt
    yolo_prev = None
    listener = None
    listener_thread = None
    srv_ctx = None
    cert_fp = None          # sha256 of OUR cert der (channel binding anchor)


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

def _server_serve(port, mode):
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
    _st.want = mode
    _st.srv_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    _st.srv_ctx.load_cert_chain(cert, key)
    with open(cert, "rb") as fh:
        _st.cert_fp = _fp(ssl.PEM_cert_to_DER_cert(fh.read().decode()))

    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        srv.bind(("0.0.0.0", port))
    except OSError as e:
        _st.want = None
        LogUtils.printc(f"[Remote] bind failed: {e}", color="red")
        return
    srv.listen(1)
    srv.settimeout(1.0)
    _st.listener = srv
    _st.dialer = False
    _st.active = True
    _st.listener_thread = threading.Thread(target=_serve_loop, daemon=True)
    _st.listener_thread.start()
    if mode == "controlled":
        LogUtils.printc(f"[Remote] serving on 0.0.0.0:{port} - waiting for a driver (Ctrl+C cancels)",
                        color="green")
    else:
        LogUtils.printc(f"[Remote] serving on 0.0.0.0:{port} - prompt stays local until a peer dials in",
                        color="green")


def _serve_loop():
    srv = _st.listener
    while _st.active:
        try:
            sock, addr = srv.accept()
        except TimeoutError:
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
        f_handshake = _server_handshake(tls)
        if f_handshake is None:
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

    if _st.role == "controlled":
        LogUtils.printc(f"[Remote] {addr[0]} connected - peer is driving now. Ctrl+C releases.",
                        color="green")
        _force_yolo()
        threading.Thread(target=_controlled_reader, args=(tls, f_handshake), daemon=True).start()
    else:
        LogUtils.printc(f"[Remote] {addr[0]} connected - your prompts now run there. /remote off releases.",
                        color="green")
        threading.Thread(target=_controller_event_reader, args=(tls, f_handshake), daemon=True).start()
        _nudge_main()


def _send_raw(sock, obj):
    try:
        sock.sendall((json.dumps(obj) + "\n").encode("utf-8"))
    except Exception:
        pass


def _server_handshake(tls):
    nonce_s = secrets.token_hex(16)
    fp_s = _st.cert_fp
    mode = _st.want
    # Single file object for the socket's whole lifetime: a second makefile
    # could lose lines already buffered by the handshake read.
    f = tls.makefile("r", encoding="utf-8")
    _send_raw(tls, {"t": "hello", "nonce": nonce_s, "fp": fp_s, "mode": mode})
    msg = _readline(f)
    if msg.get("t") != "proof":
        return None
    fp_seen = msg.get("fp", "")
    # hello.mode is informational only; the authoritative mode is _st.want and
    # is proof-bound into "ready" so a MITM cannot flip it.
    expected = _proof(_st.key, nonce_s, msg.get("nonce", ""), "client", fp_seen)
    if fp_seen != fp_s or not hmac.compare_digest(msg.get("proof", ""), expected):
        _send_raw(tls, {"t": "error", "msg": "auth failed"})
        return None
    _st.conn = tls
    _st.role = mode
    _st.role_conn = tls
    _send_raw(tls, {"t": "ready", "mode": mode,
                    "proof": _proof(_st.key, nonce_s, msg.get("nonce", ""), "server", fp_s, mode)})
    return f


# ---------------------------------------------------------------- controlled side

def _nudge_main():
    """SIGINT the main thread out of a blocking input() so controller takeover
    applies immediately. Without it, a line typed while the peer dials in runs
    on the local LLM (prompt-cycle hooks already fired for that iteration)."""
    if _st.role != "controller":
        return
    sm = getattr(_app, "session_manager", None)
    if bool(getattr(sm, "is_processing", False)) or bool(getattr(_app, "is_processing", False)):
        return
    tid = threading.main_thread().ident
    if not tid or tid == threading.get_ident():
        return
    try:
        signal.pthread_kill(tid, signal.SIGINT)
    except Exception:
        pass


def _controlled_reader(conn, f):
    """Inbound pump while controlled: prompts/stop/ping from the controller."""
    try:
        while True:
            msg = _readline(f)
            t = msg.get("t")
            if t == "prompt":
                text = str(msg.get("text", "")).strip()
                if text:
                    with _st.lock:
                        _st.pending.append(text)
                    LogUtils.printc(f"[Remote] prompt received: {text}", color="cyan")
            elif t == "inject":
                text = str(msg.get("text", ""))
                if text:
                    while _app.message_history.is_compacting:
                        time.sleep(0.05)
                    _app.message_history.insert_user_message_at_appropriate_position(text)
                    LogUtils.printc(f"[Remote] injected: {text}", color="cyan")
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
    _st.want = None
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

_colorizer = None


def _client_print_event(msg, last_sent):
    """Controller mirror: render events exactly like the local app would."""
    global _colorizer
    t = msg.get("t")
    if t == "user_msg":
        text = msg.get("text", "")
        if last_sent[0] is not None and text == last_sent[0]:
            last_sent[0] = None
            return
        LogUtils.print()
        LogUtils.print(text)
    elif t == "assistant_msg":
        if _colorizer is None:
            _colorizer = MarkdownColorizer()
        LogUtils.print()
        if Config.show_ai_prefix():
            LogUtils.printc(Config.ai_prefix(), color="cyan", bold=True)
        builtins.print(_colorizer.process_with_colorization(msg.get("text", "")))
    elif t == "tool_result":
        text = msg.get("text", "")
        LogUtils.print()
        if text == "[*] Done":
            LogUtils.success(text)
        else:
            LogUtils.print(text)
    elif t == "status":
        with _st.lock:
            _st.busy = bool(msg.get("processing"))
    elif t == "error":
        LogUtils.printc(f"[Remote] {msg.get('msg', 'error')}", color="red")


def _event_reader(conn, f, last_sent):
    try:
        while True:
            _client_print_event(_readline(f), last_sent)
    except Exception:
        pass


def _controller_event_reader(conn, f):
    _event_reader(conn, f, _st.last_sent)
    _release_conn(conn)


def _wait_peer_idle(conn):
    """Park the controller while the peer runs. Ctrl+C stops the peer like a
    local interrupt; a second Ctrl+C force-releases control."""
    interrupted = False
    while _st.conn is conn:
        with _st.lock:
            busy = _st.busy
        if not busy:
            return True
        try:
            time.sleep(0.05)
        except KeyboardInterrupt:
            if interrupted:
                return False
            print()
            _send({"t": "stop"})
            interrupted = True
    return False


def _controller_drive(conn):
    """Take over the local prompt: every line runs on the peer."""
    while _st.conn is conn:
        try:
            line = _app.input_handler.get_user_input()
        except (KeyboardInterrupt, EOFError):
            print()
            break
        text = line.strip()
        if not text:
            continue
        if text == "/remote" or text.startswith("/remote "):
            if text in ("/remote off", "/remote quit"):
                _stop_serving()
                break
            continue
        _st.last_sent[0] = text
        with _st.lock:
            _st.busy = True
        _send_raw(conn, {"t": "prompt", "text": text})
        if not _wait_peer_idle(conn):
            break


# ---------------------------------------------------------------- client transport

def _client_connect(host, port):
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
        f = conn.makefile("r", encoding="utf-8")
        hello = _readline(f)
        if hello.get("t") != "hello":
            raise ConnectionError("bad handshake")
        nonce_c = secrets.token_hex(16)
        # Channel binding: hash the cert OUR TLS connection actually received.
        # A relayed MITM presents its own cert, so this cannot match hello.fp.
        fp_real = _fp(conn.getpeercert(True) or b"")
        fp_seen = hello.get("fp", "")
        if not hmac.compare_digest(fp_seen, fp_real):
            raise ConnectionError("server cert mismatch (possible MITM)")
        conn.sendall((json.dumps({
            "t": "proof", "nonce": nonce_c, "fp": fp_real,
            "proof": _proof(key, hello.get("nonce", ""), nonce_c, "client", fp_real),
        }) + "\n").encode("utf-8"))

        reply = _readline(f)
        if reply.get("t") == "error":
            raise ConnectionError(reply.get("msg", "auth failed"))
        if reply.get("t") != "ready":
            raise ConnectionError("bad handshake")
        mode = reply.get("mode")
        if mode not in ("controller", "controlled"):
            raise ConnectionError("server sent unknown mode")
        expected = _proof(key, hello.get("nonce", ""), nonce_c, "server", fp_seen, mode)
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
    if mode == "controlled":
        # ready.mode is the SERVER's role; we take the complement.
        _st.role = "controller"
        LogUtils.printc(f"[Remote] driving {host}:{port} - lines run there. /remote off or Ctrl+C releases.",
                        color="green")
        threading.Thread(target=_controller_event_reader, args=(conn, f), daemon=True).start()
        return
    _st.role = "controlled"
    _force_yolo()
    LogUtils.printc(f"[Remote] connected - {host} is driving. Mirroring output. Ctrl+C releases.",
                    color="green")
    threading.Thread(target=_controlled_reader, args=(conn, f), daemon=True).start()


# ---------------------------------------------------------------- hooks

def on_before_user_prompt():
    """Controller takeover: once a peer is attached, the local prompt drives it."""
    if _st.role != "controller" or _st.conn is None:
        return
    conn = _st.conn
    _controller_drive(conn)
    if _st.conn is conn:
        _release_conn(conn, quiet=True)
        LogUtils.printc("[Remote] control released - local use restored", color="yellow")


def _serve_wait():
    """Park the prompt while serving in controlled mode and no driver yet."""
    try:
        while _st.active and _st.conn is None and _st.listener is not None:
            time.sleep(0.2)
    except KeyboardInterrupt:
        print()
        _stop_serving()


def _controlled_dispatch():
    """Park until the controller sends a prompt, then feed it to the main loop."""
    # Peer idle: previous turn ended. Commands that fail early (e.g. /es
    # outside tmux) never run the AI cycle, so no processing hooks fire and
    # the controller would park forever. Announce idle whenever we truly
    # park (no prompt pending or queued).
    if not _app.has_next_prompt():
        with _st.lock:
            if not _st.pending:
                _send({"t": "status", "processing": False})
    LogUtils.printc("[Remote] waiting for peer input (Ctrl+C to disconnect)", color="cyan")
    try:
        while _st.conn is not None and not _app.has_next_prompt():
            with _st.lock:
                if _st.pending:
                    break
            time.sleep(0.2)
    except KeyboardInterrupt:
        print()
        _stop_serving()
        return
    with _st.lock:
        if _st.pending:
            _app.set_next_prompt(_st.pending.popleft())


def on_prompt_available():
    """Prompt about to block on local input - remote business parks here.

    Not gated by the Ctrl+C skip flag, so it fires every loop iteration.
    """
    if _st.want == "controlled" and _st.conn is None and _st.listener is not None:
        _serve_wait()
    if _is_controlled():
        _controlled_dispatch()
        return
    if _st.role == "controller" and _st.conn is not None:
        conn = _st.conn
        _controller_drive(conn)
        if _st.conn is conn:
            _release_conn(conn, quiet=True)
            LogUtils.printc("[Remote] control released - local use restored", color="yellow")


def on_before_ai_processing():
    if _is_controlled():
        _send({"t": "status", "processing": True})


def on_after_ai_processing(has_tool_calls=None):
    if _is_controlled():
        # Keep peer "busy" across recursive tool turns. Only clear busy on the
        # final text turn (no tool calls), so the controller waits for the whole
        # session instead of leaking its next prompt in the gap between turns.
        if not has_tool_calls:
            _send({"t": "status", "processing": False})


def on_inject_user_text(text):
    """Consume local inject-text and forward it to the controlled peer."""
    if _st.role == "controller" and _st.conn is not None:
        _send({"t": "inject", "text": text})
        LogUtils.printc("[Remote] injected to peer", color="cyan")
        return True


def on_user_message(message):
    if _is_controlled():
        _send({"t": "user_msg", "text": message.get("content") or ""})


def on_assistant_message(message):
    if _is_controlled():
        content = message.get("content")
        if content:
            _send({"t": "assistant_msg", "text": content})


def on_single_tool_execution(tool_name, arguments, result):
    if not _is_controlled():
        return
    tool_def = _app.tool_manager.tools.get(tool_name) or {}
    if tool_def.get("hide_results"):
        _send({"t": "tool_result", "text": "[*] Done"})
        return
    friendly = result.get("friendly", "")
    if friendly:
        _send({"t": "tool_result", "text": friendly})


# ---------------------------------------------------------------- command

USAGE = "Usage: /remote serve [port] [--control] | /remote connect <host> [port] | /remote off"


def _cmd_remote(args_str):
    parts = args_str.strip().split()
    if not parts:
        print(USAGE)
        return
    sub = parts[0]
    if sub == "serve":
        port = DEFAULT_PORT
        mode = "controlled"
        for p in parts[1:]:
            if p == "--control":
                mode = "controller"
            else:
                try:
                    port = int(p)
                except ValueError:
                    print(USAGE)
                    return
        _server_serve(port, mode)
    elif sub == "connect":
        args = parts[1:]
        if any(p.startswith("--") for p in args):
            print("[Remote] client role is decided by the server (--control on the serve side)")
            return
        if not args:
            print(USAGE)
            return
        port = DEFAULT_PORT
        if len(args) > 1:
            try:
                port = int(args[1])
            except ValueError:
                print(USAGE)
                return
        _client_connect(args[0], port)
    elif sub == "off":
        _stop_serving()
    else:
        print(USAGE)


def create_plugin(ctx):
    global _app
    _app = ctx.app
    atexit.register(_stop_serving)

    ctx.register_command("remote", _cmd_remote, "Remote control: serve [--control] | connect <host> | off")
    ctx.register_hook("before_user_prompt", on_before_user_prompt)
    ctx.register_hook("on_prompt_available", on_prompt_available)
    ctx.register_hook("before_ai_processing", on_before_ai_processing)
    ctx.register_hook("after_ai_processing", on_after_ai_processing)
    ctx.register_hook("after_user_message_added", on_user_message)
    ctx.register_hook("after_assistant_message_added", on_assistant_message)
    ctx.register_hook("after_single_tool_execution", on_single_tool_execution)
    ctx.register_hook("inject_user_text", on_inject_user_text)

    if Config.debug():
        LogUtils.print("  - /remote command")
        LogUtils.print("  - remote mirror hooks")
