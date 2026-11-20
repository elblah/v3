"""tmux-share plugin - serve one tmux pane over HTTP/S.

Lets a browser (desktop or phone) watch and type into a single tmux pane.
The pane defaults to the one aicoder itself runs in (``TMUX_PANE``), so a
remote viewer sees the very session the AI is talking to.

The HTTP server runs as daemon threads inside the aicoder process, not as a
child process: nothing is ever printed (all output goes to a ring buffer and
a log file), the port is released automatically when aicoder exits, and no
pid/kill switch is needed.

Commands:
    /tmux-share [start] [--port N] [--user U] [--password P | --genpass [N]]
           [--bind ADDR] [--pane %N] [--interval S] [--idle-interval S]
           [--max-auth-fails N] [--webroot PATH] [--force] [--noauth]
    /tmux-share stop | status | restart | log [N] | help

A password is mandatory: without --password/--genpass the server refuses to
start, unless --noauth is given explicitly.

The password is kept in memory only. It is never written to the state file,
never passed through argv or the environment, and never logged.
"""

import atexit
import base64
import hmac
import json
import os
import queue
import re
import secrets
import shlex
import socket
import string
import subprocess
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from socketserver import ThreadingTCPServer

from aicoder.core.config import Config
from aicoder.utils.log import LogUtils

PLUGIN_DIR = Path(__file__).resolve().parent

DEFAULT_PORT = 8080
DEFAULT_BIND = "127.0.0.1"
DEFAULT_INTERVAL = 0.2
DEFAULT_IDLE_INTERVAL = 1.0
DEFAULT_MAX_AUTH_FAILS = 5
DEFAULT_MAX_AUTH_FAILS_PER_IP = 0
DEFAULT_GENPASS_LEN = 24
DEFAULT_USER = "share"

LOOPBACK_NAMES = ("127.0.0.1", "localhost", "::1", "")

SUBCOMMANDS = ("start", "stop", "status", "restart", "log", "help")

VALUE_FLAGS = {
    "--port": "port",
    "--user": "user",
    "--password": "password",
    "--bind": "bind",
    "--pane": "pane",
    "--interval": "interval",
    "--idle-interval": "idle_interval",
    "--max-auth-fails": "max_auth_fails",
    "--max-auth-fails-per-ip": "max_auth_fails_per_ip",
    "--webroot": "webroot",
}

HELP_TEXT = """\
/tmux-share - share one tmux pane in a browser

Usage:
  /tmux-share [start] [options]     start sharing (default subcommand)
  /tmux-share stop                  stop the server
  /tmux-share status                show state, counters and connected clients
  /tmux-share restart [options]     stop then start again (keeps credentials)
  /tmux-share log [N]               tail the share log (default 40 lines)
  /tmux-share help                  this text

Options:
  --port N              listen port                  (default 8080)
  --bind ADDR           listen address               (default 127.0.0.1)
  --pane %N             tmux pane to share           (default $TMUX_PANE)
  --user U --password P protect the page with basic auth (default: required)
  --genpass [N]         generate a random password (default 24 chars),
                        user defaults to "share"; shown once, never logged
  --noauth              share WITHOUT authentication (explicit opt-in:
                        anyone reaching the port can type into the pane)
  --interval S          poll interval with viewers   (default 0.2)
  --idle-interval S     poll interval with no viewers (default 1.0, 0 = off)
  --max-auth-fails N    bad logins (all clients) before the server STOPS
                        itself (default 5, 0 = never stop); requests that
                        carry no user/password are refused and logged but
                        never counted
  --max-auth-fails-per-ip N
                        optional per-IP lockout: bad logins from one address
                        before it is blocked (default 0 = off); blocks
                        escalate 60s, 120s, 240s ... capped at 900s,
                        a correct password clears that IP's counter
  --webroot PATH        serve the page under a URL prefix, e.g.
                        --webroot /svr/terminal -> 127.0.0.1:PORT/svr/terminal;
                        any other path gets no reply at all (default: none)
  --force               stop a running share first

Binding to a non-loopback address without credentials means anyone on the
network can type into the pane. That is your call, but it is warned about.

Secrets live in memory only: `restart` (and `start --force`) keep the current
credentials, `stop` forgets them, so the next start needs --genpass or
--password again.
"""

PASSWORD_ALPHABET = string.ascii_letters + string.digits + "-_"


# ------------------------------------------------------------- the server
# The HTTP/SSE server deliberately lives in this very file: a plugin is one
# self-contained module, with no sidecar package or data files next to it.
# The viewer page is embedded at the bottom of the file as HTML_PAGE.

PROTOCOL_VERSION = 1
LOG_MAX_BYTES = 256 * 1024
AUTH_BLOCK_SECONDS = 60.0
AUTH_BLOCK_MAX_SECONDS = 900.0   # cap for the escalating per-IP block



def _norm_webroot(path):
    """Normalise a URL prefix: 'svr/terminal/' -> '/svr/terminal'; '' -> ''."""
    if not path:
        return ""
    p = "/" + str(path).strip().strip("/")
    return "" if p == "/" else p


class ShareError(Exception):
    """Raised for configuration problems the caller is expected to report."""


def _tmux(args, timeout=5):
    return subprocess.run(
        ["tmux"] + args,
        capture_output=True,
        text=True,
        errors="replace",
        timeout=timeout,
    )


def pane_exists(pane):
    """True if tmux knows the pane id (e.g. '%3')."""
    if not pane:
        return False
    try:
        return _tmux(["display-message", "-p", "-t", pane, "#{pane_id}"]).returncode == 0
    except Exception:
        return False


def capture_state(pane):
    """Full pane snapshot: geometry, cursor and text with escape sequences."""
    cap = _tmux(["capture-pane", "-p", "-e", "-t", pane])
    if cap.returncode != 0:
        return None
    pos = _tmux(
        ["display-message", "-p", "-t", pane,
         "#{pane_width} #{pane_height} #{cursor_x} #{cursor_y}"]
    )
    cols, rows, cx, cy = 100, 30, 0, 0
    if pos.returncode == 0:
        try:
            parts = pos.stdout.strip().split()
            cols = int(parts[0])
            rows = int(parts[1])
            cx = int(parts[2])
            cy = int(parts[3])
        except Exception:
            pass
    return {"cols": cols, "rows": rows, "cx": cx, "cy": cy, "data": cap.stdout}


def _ts():
    return time.strftime("%Y-%m-%d %H:%M:%S")


def _decode_input(raw):
    """Turn a POST body into text for the pane.

    The bundled viewer sends ``{"input": "h"}``; plain text is also accepted so
    ``curl -d 'x'`` keeps working.
    """
    text = raw.decode("utf-8", "replace")
    stripped = text.strip()
    if stripped.startswith("{"):
        try:
            obj = json.loads(stripped)
        except ValueError:
            return text
        if isinstance(obj, dict):
            value = obj.get("input")
            if isinstance(value, str):
                return value
            return ""
    return text


class ShareServer:
    """Serve one tmux pane over HTTP using daemon threads."""

    def __init__(self, pane, port=8080, bind="127.0.0.1", interval=0.2,
                 idle_interval=1.0, user=None, password=None,
                 max_auth_fails=DEFAULT_MAX_AUTH_FAILS, max_auth_fails_per_ip=0,
                 webroot="", log_path=None, log_lines=1000, on_auth_fail=None,
                 allow_noauth=False):
        if bool(user) != bool(password):
            raise ShareError("need both user and password, or neither")
        if not (user and password) and not allow_noauth:
            raise ShareError("refusing to serve without authentication: "
                             "pass user and password (allow_noauth to override)")
        self.pane = pane
        self.port = int(port)
        self.bind = bind or "127.0.0.1"
        self.webroot = _norm_webroot(webroot)
        self.interval = max(0.02, float(interval))
        self.idle_interval = float(idle_interval or 0)
        self.user = user
        self.max_auth_fails = int(max_auth_fails or 0)
        self.max_auth_fails_per_ip = int(max_auth_fails_per_ip or 0)
        self.on_auth_fail = on_auth_fail
        self.log_path = log_path
        self.ring = deque(maxlen=max(50, int(log_lines)))

        self._auth_header = None
        self._auth_cookie = None
        if user and password:
            raw = (str(user) + ":" + str(password)).encode()
            self._auth_header = "Basic " + base64.b64encode(raw).decode()
            self._auth_cookie = secrets.token_urlsafe(16)

        self._clients = {}           # queue -> peer ip
        self._conns = set()          # live client sockets (closed on stop)
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._wake = threading.Event()
        self._force = False
        self._srv = None
        self._serve_thread = None
        self._poll_thread = None
        self._heartbeat_thread = None

        self.started_at = None
        self.frames_sent = 0
        self.last_capture_ts = 0.0
        self.last_error = None
        self.last_payload = None
        self._last_cursor = None
        self.auth_fails = 0
        self.stopped_by_auth = False
        self._fails_by_ip = {}       # ip -> [count, blocked_until, strikes]

    # ------------------------------------------------------------------ log

    def log(self, msg):
        line = "[" + _ts() + "] " + str(msg)
        self.ring.append(line)
        if self.log_path:
            try:
                p = Path(self.log_path)
                try:
                    too_big = p.stat().st_size > LOG_MAX_BYTES
                except OSError:
                    too_big = False
                if too_big:
                    os.replace(str(p), str(p) + ".1")
                p.parent.mkdir(parents=True, exist_ok=True)
                with open(str(p), "a", errors="replace") as fh:
                    fh.write(line + "\n")
            except Exception:
                pass

    def log_tail(self, n=40):
        with self._lock:
            lines = list(self.ring)
        return lines[-int(n):] if n else lines

    # -------------------------------------------------------------- clients

    @property
    def clients(self):
        with self._lock:
            return len(self._clients)

    def client_list(self):
        with self._lock:
            return list(self._clients.values())

    def _send(self, payload):
        with self._lock:
            targets = list(self._clients.keys())
        slow = []
        for q in targets:
            try:
                q.put_nowait(payload)
            except queue.Full:
                slow.append(q)
        if slow:
            with self._lock:
                for q in slow:
                    self._clients.pop(q, None)

    # ----------------------------------------------------------------- auth

    def _authorized(self, headers):
        if not self._auth_header:
            return True
        got = headers.get("Authorization", "")
        if got and hmac.compare_digest(got, self._auth_header):
            return True
        if self._auth_cookie:
            for part in headers.get("Cookie", "").split(";"):
                name, _, value = part.strip().partition("=")
                if name == "tmuxauth" and hmac.compare_digest(
                        value.strip(), self._auth_cookie):
                    return True
        return False

    def _ip_blocked(self, ip):
        with self._lock:
            rec = self._fails_by_ip.get(ip)
            if not rec:
                return False
            if time.time() < rec[1]:
                return True
            if rec[1]:
                # block expired: hand out a fresh set of attempts (strikes stay)
                rec[0] = 0
                rec[1] = 0.0
            return False

    def _note_auth_ok(self, ip):
        """A correct password clears that IP's failure count and strike history."""
        with self._lock:
            rec = self._fails_by_ip.get(ip)
            if not rec or time.time() < rec[1]:
                return          # unknown ip, or still inside an active block
            self._fails_by_ip.pop(ip, None)

    @staticmethod
    def _creds_filled(headers):
        """True when the client actually sent a user and/or a password.

        Both fields empty (no Authorization header, an unparsable one, or a
        bare ":") means the request is only knocking on the door: it is
        refused and logged, but never counted as a bad login.
        """
        raw = (headers.get("Authorization") or "").strip()
        if raw[:6].lower() != "basic ":
            return False
        try:
            decoded = base64.b64decode(
                raw[6:].strip(), validate=True).decode("utf-8", "replace")
        except Exception:
            return False
        user, _, password = decoded.partition(":")
        return bool(user.strip() or password.strip())

    def _note_auth_failure(self, ip):
        now = time.time()
        shutdown = False
        with self._lock:
            self.auth_fails += 1
            total = self.auth_fails
            count = 0
            strikes, blocked_until, blocked = 0, 0.0, 0.0
            per_ip = self.max_auth_fails_per_ip
            if per_ip:
                rec = self._fails_by_ip.setdefault(ip, [0, 0.0, 0])
                rec[0] += 1
                count = rec[0]
                if rec[0] >= per_ip:
                    rec[2] += 1
                    blocked = min(AUTH_BLOCK_MAX_SECONDS,
                                  AUTH_BLOCK_SECONDS * (2 ** (rec[2] - 1)))
                    rec[1] = now + blocked
                    rec[0] = 0
                strikes, blocked_until = rec[2], rec[1]
            if self.max_auth_fails and total >= self.max_auth_fails \
                    and not self.stopped_by_auth:
                self.stopped_by_auth = True
                shutdown = True
        self.log("AUTH FAIL %d from %s (ip count %d, strikes %d%s%s)"
                 % (total, ip, count, strikes,
                    ", blocked %ds" % int(blocked) if blocked else "",
                    ", stopping server" if shutdown else ""))
        if shutdown:
            # stop() joins threads, so it must not run in this handler thread
            threading.Thread(target=self.stop, name="auth-stop",
                             daemon=True).start()
        if self.on_auth_fail is not None:
            try:
                self.on_auth_fail({"ip": ip, "total": total, "count": count,
                                   "counted": True,
                                   "strikes": strikes, "blocked": int(blocked),
                                   "blocked_until": blocked_until,
                                   "limit": self.max_auth_fails,
                                   "limit_per_ip": self.max_auth_fails_per_ip,
                                   "stopped": shutdown})
            except Exception:
                pass

    def _note_auth_probe(self, ip, path):
        """Refused for lack of credentials: log it, do not count it."""
        self.log("refused %s from %s (no credentials, not counted)" % (path, ip))
        if self.on_auth_fail is not None:
            try:
                self.on_auth_fail({"ip": ip, "path": path, "counted": False,
                                   "total": self.auth_fails,
                                   "limit": self.max_auth_fails,
                                   "limit_per_ip": self.max_auth_fails_per_ip})
            except Exception:
                pass

    def blocked_ips(self):
        now = time.time()
        with self._lock:
            return {ip: rec[1] for ip, rec in self._fails_by_ip.items()
                    if rec[1] and rec[1] > now}

    def _ip(self, handler):
        xff = handler.headers.get("X-Forwarded-For", "").split(",")[0].strip()
        cf = handler.headers.get("CF-Connecting-IP", "").strip()
        return cf or xff or handler.client_address[0]

    # ---------------------------------------------------------------- start

    def start(self):
        if self._srv is not None:
            raise ShareError("already running")
        if not pane_exists(self.pane):
            raise ShareError("bad pane: " + str(self.pane))

        share = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def log_message(self, *a):
                pass

            def setup(self):
                super().setup()
                with share._lock:
                    share._conns.add(self.connection)

            def finish(self):
                with share._lock:
                    share._conns.discard(self.connection)
                try:
                    super().finish()
                except Exception:
                    pass

            def _dying(self):
                """True once the server is shutting down: refuse and hang up."""
                if not share._stop.is_set():
                    return False
                self.close_connection = True
                try:
                    self.send_error(503)
                except Exception:
                    pass
                return True

            def deny(self):
                ip = share._ip(self)
                if share._auth_header and share._creds_filled(self.headers):
                    share._note_auth_failure(ip)
                else:
                    share._note_auth_probe(ip, self.path)
                self.send_response(429 if share._ip_blocked(ip) else 401)
                self.send_header("WWW-Authenticate", 'Basic realm="tmux-share"')
                self.send_header("Content-Length", "0")
                self.end_headers()

            def _route(self):
                """Map self.path onto the inner paths, or None if outside webroot."""
                root = share.webroot
                path = self.path.split("?", 1)[0].split("#", 1)[0]
                if not root:
                    return path
                if path == root or path == root + "/":
                    return "/"
                if path.startswith(root + "/"):
                    return path[len(root):]
                return None

            def do_GET(self):
                if self._dying():
                    return
                path = self._route()
                if path is None:
                    share.log("ignored request for %r (outside %r)"
                              % (self.path, share.webroot))
                    self.close_connection = True
                    return
                if share._ip_blocked(share._ip(self)):
                    self.send_error(429)
                    return
                if not share._authorized(self.headers):
                    self.deny()
                    return
                share._note_auth_ok(share._ip(self))
                if path == "/events":
                    self.handle_events()
                    return
                if path in ("/", "/index.html"):
                    try:
                        body = INDEX_BYTES
                    except Exception:
                        self.send_error(404)
                        return
                    self.send_response(200)
                    self.send_header("Content-Type", "text/html; charset=utf-8")
                    self.send_header("Content-Length", str(len(body)))
                    if share._auth_header and share._auth_cookie:
                        self.send_header(
                            "Set-Cookie",
                            "tmuxauth=" + share._auth_cookie
                            + "; Path=" + (share.webroot or "/")
                            + "; HttpOnly; SameSite=Lax")
                    self.end_headers()
                    self.wfile.write(body)
                    return
                self.send_error(404)

            def handle_events(self):
                self.send_response(200)
                self.send_header("Content-Type", "text/event-stream")
                self.send_header("Cache-Control", "no-cache")
                self.send_header("Transfer-Encoding", "chunked")
                self.end_headers()
                q = queue.Queue(maxsize=64)
                ip = share._ip(self)
                share._add_client(q, ip)
                try:
                    self._write_event(
                        json.dumps({"type": "meta", "auth": bool(share._auth_header),
                                    "version": PROTOCOL_VERSION}))
                    if share.last_payload:
                        self._write_event(share.last_payload)
                    while not share._stop.is_set():
                        try:
                            payload = q.get(timeout=15)
                        except queue.Empty:
                            payload = '{"type": "ping"}'
                        self._write_event(payload)
                except Exception:
                    pass
                finally:
                    share._drop_client(q)
                self.close_connection = True

            def _write_event(self, payload):
                body = ("data: " + payload + "\n\n").encode("utf-8")
                self.wfile.write(("%x\r\n" % len(body)).encode() + body + b"\r\n")
                self.wfile.flush()

            def do_POST(self):
                if self._dying():
                    return
                path = self._route()
                if path is None:
                    share.log("ignored POST for %r (outside %r)"
                              % (self.path, share.webroot))
                    self.close_connection = True
                    return
                ip = share._ip(self)
                if share._ip_blocked(ip):
                    self.send_error(429)
                    return
                if not share._authorized(self.headers):
                    self.deny()
                    return
                share._note_auth_ok(ip)
                if path != "/input":
                    self.send_error(404)
                    return
                try:
                    n = int(self.headers.get("Content-Length", "0"))
                except Exception:
                    n = 0
                if n <= 0 or n > 65536:
                    self.send_error(400)
                    return
                body = self.rfile.read(n)
                share.send_input(_decode_input(body))
                self.send_response(204)
                self.send_header("Content-Length", "0")
                self.end_headers()

        ThreadingTCPServer.allow_reuse_address = True
        ThreadingTCPServer.daemon_threads = True

        class Server(ThreadingTCPServer):
            def handle_error(self, request, client_address):
                try:
                    import sys
                    et, ev, tb = sys.exc_info()
                    if et is not None and issubclass(et, (ConnectionError, OSError)):
                        return  # normal disconnect noise
                    share.log("handler error %s: %s" % (et, ev))
                except Exception:
                    pass

        try:
            self._srv = Server((self.bind, self.port), Handler)
        except OSError as e:
            self._srv = None
            raise ShareError("cannot bind %s:%d (%s)" % (self.bind, self.port, e))

        self.started_at = time.time()
        self._stop.clear()
        self._serve_thread = threading.Thread(
            target=self._srv.serve_forever, kwargs={"poll_interval": 0.2},
            name="tmux-share-http", daemon=True)
        self._serve_thread.start()
        self._poll_thread = threading.Thread(
            target=self._poll_loop, name="tmux-share-poll", daemon=True)
        self._poll_thread.start()
        self._heartbeat_thread = threading.Thread(
            target=self._heartbeat_loop, name="tmux-share-hb", daemon=True)
        self._heartbeat_thread.start()

        self.log("serving pane %s on %s:%d (auth=%s, webroot=%s)"
                 % (self.pane, self.bind, self.port,
                    "on" if self._auth_header else "OFF",
                    self.webroot or "/"))
        if self.bind not in LOOPBACK_NAMES and not self._auth_header:
            self.log("WARNING: bound to %s without a password - anyone reaching "
                     "this port can see and type into the pane" % self.bind)
        return self

    def _add_client(self, q, ip):
        with self._lock:
            self._clients[q] = ip
            n = len(self._clients)
        self._force = True
        self._wake.set()
        self.log("SSE client connected from %s (%d total)" % (ip, n))

    def _drop_client(self, q):
        with self._lock:
            self._clients.pop(q, None)
            n = len(self._clients)
        self.log("SSE client gone (%d left)" % n)

    # ----------------------------------------------------------------- poll

    def _next_interval(self):
        if self.clients:
            return self.interval
        if self._force:
            return 0.01
        if self.idle_interval > 0:
            return self.idle_interval
        return None

    def _poll_loop(self):
        last_data = None
        last_geom = None
        fails = 0
        while not self._stop.is_set():
            interval = self._next_interval()
            if interval is not None:
                try:
                    st = capture_state(self.pane)
                except Exception as e:
                    st = None
                    self.last_error = "capture exception: %r" % (e,)
                if st is None:
                    fails += 1
                    self.last_error = "capture failed x%d" % fails
                    if fails == 1 or fails % 300 == 0:
                        self.log("capture FAILED x%d (pane gone? tmux busy?)" % fails)
                else:
                    if fails:
                        self.log("capture recovered after %d fails" % fails)
                    fails = 0
                    self.last_error = None
                    self.last_capture_ts = time.time()
                    self._force = False
                    geom = (st["cols"], st["rows"])
                    if last_data is None or st["data"] != last_data or geom != last_geom:
                        last_data = st["data"]
                        last_geom = geom
                        self._last_cursor = (st["cx"], st["cy"])
                        self.last_payload = json.dumps({
                            "type": "screen", "cols": st["cols"], "rows": st["rows"],
                            "cx": st["cx"], "cy": st["cy"], "data": st["data"]})
                        self.frames_sent += 1
                        self._send(self.last_payload)
                    elif (st["cx"], st["cy"]) != self._last_cursor:
                        self._last_cursor = (st["cx"], st["cy"])
                        self._send(json.dumps({"type": "cursor",
                                               "cx": st["cx"], "cy": st["cy"]}))
                wait = interval
            else:
                wait = 5.0
            self._wake.wait(wait)
            self._wake.clear()

    def _heartbeat_loop(self):
        while not self._stop.is_set():
            self._stop.wait(300)
            if self._stop.is_set():
                break
            if self.clients:
                self.log("hb clients=%d frames=%d threads=%d"
                         % (self.clients, self.frames_sent, threading.active_count()))

    # ---------------------------------------------------------------- input

    def send_input(self, text):
        if not text or self._stop.is_set():
            return
        try:
            _tmux(["send-keys", "-t", self.pane, "-l", "--", text], timeout=5)
        except Exception as e:
            self.log("input failed: %r" % (e,))

    # ----------------------------------------------------------------- stop

    def _close_connections(self):
        """Drop every open client socket; keep-alive sessions die with it."""
        with self._lock:
            conns = list(self._conns)
            self._conns.clear()
        for conn in conns:
            try:
                conn.shutdown(socket.SHUT_RDWR)
            except Exception:
                pass
            try:
                conn.close()
            except Exception:
                pass

    def stop(self, timeout=3.0):
        srv = self._srv
        if srv is None:
            return False
        self._stop.set()
        self._wake.set()
        try:
            self._send('{"type": "ping"}')
        except Exception:
            pass
        try:
            # shutdown() only stops accept(); live keep-alive handler threads
            # would keep answering requests, so close their sockets too.
            self._close_connections()
            srv.shutdown()
        except Exception:
            pass
        finally:
            try:
                srv.server_close()
            except Exception:
                pass
            self._srv = None
        for th in (self._serve_thread, self._poll_thread):
            if th is not None:
                th.join(timeout)
        self.log("stopped")
        return True

    def snapshot(self):
        return {
            "pane": self.pane,
            "bind": self.bind,
            "port": self.port,
            "auth": bool(self._auth_header),
            "clients": self.clients,
            "client_ips": self.client_list(),
            "frames_sent": self.frames_sent,
            "auth_fails": self.auth_fails,
            "max_auth_fails": self.max_auth_fails,
            "max_auth_fails_per_ip": self.max_auth_fails_per_ip,
            "webroot": self.webroot,
            "stopped_by_auth": self.stopped_by_auth,
            "blocked_ips": self.blocked_ips(),
            "last_capture_ts": self.last_capture_ts,
            "last_error": self.last_error,
            "started_at": self.started_at,
            "uptime": (time.time() - self.started_at) if self.started_at else 0.0,
            "interval": self.interval,
            "idle_interval": self.idle_interval,
            "running": self._srv is not None,
        }


class _ArgsError(Exception):
    """Bad /tmux-share arguments."""


def _aicoder_dir():
    """`.aicoder/` under the current working directory (created on demand)."""
    d = Path(os.getcwd()) / ".aicoder"
    try:
        d.mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
    return d


def _state_path():
    return _aicoder_dir() / "tmux-share.json"


def _log_path():
    return _aicoder_dir() / "tmux-share.log"


def _valid_pane(pane):
    return bool(pane) and re.match(r"^%[0-9]+$", str(pane)) is not None


def _genpass(n):
    return "".join(secrets.choice(PASSWORD_ALPHABET) for _ in range(n))


def _int_value(text):
    """Parse an integer argument; None when it is not a whole number."""
    text = str(text).strip()
    try:
        return int(text)
    except ValueError:
        try:
            number = float(text)
        except ValueError:
            return None
        return int(number) if number.is_integer() else None


def _lan_ips():
    """Best-effort IPv4 addresses of this host (empty list on failure)."""
    try:
        out = subprocess.run(["hostname", "-I"], capture_output=True,
                            text=True, timeout=3)
    except Exception:
        return []
    ips = []
    for tok in (out.stdout or "").split():
        if "." in tok and not tok.startswith("127."):
            ips.append(tok)
    return ips


def _parse_args(args_str):
    """Parse `/tmux-share` arguments into (subcommand, options dict)."""
    try:
        toks = shlex.split(args_str or "")
    except ValueError as e:
        raise _ArgsError("bad quoting: " + str(e))

    sub = "start"
    if toks and toks[0] in SUBCOMMANDS:
        sub = toks.pop(0)

    opts = {}
    rest = []
    i = 0
    while i < len(toks):
        tok = toks[i]
        i += 1

        if tok in ("-h", "--help"):
            opts["help"] = True
            continue
        if tok == "--force":
            opts["force"] = True
            continue
        if tok == "--noauth":
            opts["noauth"] = True
            continue
        if tok == "--genpass":
            n = DEFAULT_GENPASS_LEN
            if i < len(toks) and toks[i].isdigit():
                n = int(toks[i])
                i += 1
            opts["genpass"] = max(8, min(256, n))
            continue

        name, value = tok, None
        if tok.startswith("--") and "=" in tok:
            name, value = tok.split("=", 1)
        elif tok.startswith("--"):
            if i >= len(toks):
                raise _ArgsError(tok + " needs a value")
            value = toks[i]
            i += 1
        else:
            rest.append(tok)
            continue

        key = VALUE_FLAGS.get(name)
        if key is None:
            raise _ArgsError("unknown option: " + name)
        opts[key] = value

    if "port" in opts:
        port = _int_value(opts["port"])
        if port is None or not (1 <= port <= 65535):
            raise _ArgsError("bad --port: " + str(opts["port"]))
        opts["port"] = port
    for key in ("interval", "idle_interval"):
        if key in opts:
            try:
                opts[key] = float(opts[key])
            except ValueError:
                raise _ArgsError("bad --%s: %s"
                                 % (key.replace("_", "-"), opts[key]))
            if opts[key] < 0:
                raise _ArgsError("bad --%s: negative" % key.replace("_", "-"))
    for key in ("max_auth_fails", "max_auth_fails_per_ip"):
        if key in opts:
            n = _int_value(opts[key])
            if n is None or n < 0:
                raise _ArgsError("bad --%s: %s"
                                 % (key.replace("_", "-"), opts[key]))
            opts[key] = n
    if "webroot" in opts:
        root = str(opts["webroot"]).strip()
        if any(c in root for c in " ?#") or "://" in root:
            raise _ArgsError("bad --webroot: " + str(opts["webroot"]))
        opts["webroot"] = _norm_webroot(root)
    if "pane" in opts and not _valid_pane(opts["pane"]):
        raise _ArgsError("bad --pane (expected %N, e.g. %0): " + str(opts["pane"]))
    if "genpass" in opts and "password" in opts:
        raise _ArgsError("use either --password or --genpass, not both")
    if opts.get("noauth") and ("password" in opts or "genpass" in opts
                               or "user" in opts):
        raise _ArgsError("use either --noauth or credentials, not both")

    return sub, opts, rest


def create_plugin(ctx):
    """tmux-share: serve the current tmux pane to a browser."""

    colors = Config.colors
    lock = threading.RLock()
    state = {
        "server": None,      # ShareServer instance (in-process)
        "password": None,    # kept in memory only
        "user": None,
        "noauth": False,     # explicit --noauth of the running server
        "config": {},        # last used config, reused by `restart`
        "closed": False,
    }

    # ------------------------------------------------------------- helpers

    def _read_state_file():
        try:
            with open(_state_path(), "r", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return None

    def _write_state_file(cfg, srv):
        data = {
            "pid": os.getpid(),
            "port": cfg["port"],
            "bind": cfg["bind"],
            "pane": cfg["pane"],
            "user": cfg.get("user"),
            "auth": bool(cfg.get("user")),
            "noauth": bool(cfg.get("noauth")),
            "interval": cfg["interval"],
            "idle_interval": cfg["idle_interval"],
            "max_auth_fails": cfg["max_auth_fails"],
            "max_auth_fails_per_ip": cfg["max_auth_fails_per_ip"],
            "webroot": cfg.get("webroot", ""),
            "started": time.strftime("%Y-%m-%d %H:%M:%S"),
            "log": str(_log_path()),
        }
        path = _state_path()
        tmp = str(path) + ".tmp"
        try:
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=2)
            os.replace(tmp, path)
            try:
                os.chmod(path, 0o600)
            except OSError:
                pass
        except OSError as e:
            return "state file not written: %s" % (e,)
        return None

    def _remove_state_file():
        try:
            os.unlink(_state_path())
        except OSError:
            pass

    def _resolve_config(opts):
        """Merge flags over the last config, then over defaults."""
        prev = dict(state["config"]) if state["config"] else {}
        stale = _read_state_file() or {}
        if not prev:
            for key in ("port", "bind", "pane", "interval", "idle_interval",
                        "max_auth_fails", "max_auth_fails_per_ip", "user",
                        "webroot"):
                if key in stale:
                    prev[key] = stale[key]

        cfg = {
            "port": opts.get("port", prev.get("port", DEFAULT_PORT)),
            "bind": opts.get("bind", prev.get("bind", DEFAULT_BIND)),
            "pane": opts.get("pane") or prev.get("pane")
                    or os.environ.get("TMUX_PANE"),
            "interval": opts.get("interval",
                                 prev.get("interval", DEFAULT_INTERVAL)),
            "idle_interval": opts.get(
                "idle_interval", prev.get("idle_interval", DEFAULT_IDLE_INTERVAL)),
            "max_auth_fails": opts.get(
                "max_auth_fails", prev.get("max_auth_fails", DEFAULT_MAX_AUTH_FAILS)),
            "max_auth_fails_per_ip": opts.get(
                "max_auth_fails_per_ip",
                prev.get("max_auth_fails_per_ip", DEFAULT_MAX_AUTH_FAILS_PER_IP)),
            "webroot": _norm_webroot(
                opts.get("webroot", prev.get("webroot", ""))),
            "user": opts.get("user", prev.get("user", state["user"])),
        }

        if not _valid_pane(cfg["pane"]):
            raise _ArgsError(
                "no pane: TMUX_PANE is unset and no --pane given "
                "(aicoder must run inside tmux, or pass --pane %N)")

        # Credentials: flags win, otherwise reuse the in-memory pair.
        if opts.get("noauth"):
            cfg["user"] = None      # explicit opt-out beats remembered creds
        password = opts.get("password")
        if password is None and cfg["user"] and state["password"] \
                and cfg["user"] == state["user"]:
            # reuse the in-memory secret (restart / --force) without persisting
            password = state["password"]
        if "genpass" in opts:
            password = _genpass(opts["genpass"])
            if not cfg["user"]:
                cfg["user"] = DEFAULT_USER
        if password and not cfg["user"]:
            cfg["user"] = DEFAULT_USER
        if bool(cfg["user"]) != bool(password):
            raise _ArgsError("authentication needs both --user and "
                             "--password (or --genpass)")
        # No credentials is a hard error unless the user asks for it: --noauth
        # ("allow noauth") or the same choice remembered from the last start.
        if not (cfg["user"] and password):
            cfg["noauth"] = bool(opts.get("noauth")
                                 or prev.get("noauth"))
            if not cfg["noauth"]:
                raise _ArgsError(
                    "no password: pass --password P (or --genpass [N]) to "
                    "protect the page, or --noauth to share without it")
        else:
            cfg["noauth"] = False
        cfg["password"] = password
        return cfg

    def _urls(cfg):
        port = cfg["port"]
        tail = (cfg.get("webroot") or "") + "/"
        if cfg["bind"] in LOOPBACK_NAMES:
            return ["http://127.0.0.1:%d%s" % (port, tail)]
        urls = []
        for ip in _lan_ips():
            urls.append("http://%s:%d%s" % (ip, port, tail))
        if not urls:
            urls.append("http://<this-host>:%d%s" % (port, tail))
        return urls

    def _notify_auth_fail(info):
        """Bad password seen by the share server -> loud on-screen line."""
        tag = "%s%s[tmux-share]%s" % (colors["bold"], colors["red"], colors["reset"])
        if not info.get("counted", True):
            # no user/password supplied: refused and logged, counter untouched
            LogUtils.print("%s %srequest without credentials from %s for %s "
                           "refused (not counted)%s"
                           % (tag, colors["red"], info.get("ip"),
                              info.get("path") or "/", colors["reset"]))
            return
        parts = ["bad password #%d from %s" % (info.get("total", 0), info.get("ip"))]
        limit = info.get("limit") or 0
        if limit:
            parts.append("(%d/%d)" % (info.get("total", 0), limit))
        if info.get("blocked"):
            parts.append("BLOCKED %ds" % info["blocked"])
        elif info.get("count"):
            parts.append("%d/%d from this IP"
                         % (info.get("count", 0),
                            info.get("limit_per_ip") or 0))
        if info.get("stopped"):
            parts.append("-- SERVER STOPPED, share is down")
        LogUtils.print("%s %s%s%s" % (tag, colors["red"], " ".join(parts),
                                      colors["reset"]))
        if info.get("stopped"):
            # the server killed itself; drop the local handles quietly
            def _cleanup():
                with lock:
                    state["server"] = None
                    state["password"] = None
                    state["user"] = None
                    state["config"].pop("user", None)
                _remove_state_file()
            threading.Thread(target=_cleanup, name="tmux-share-cleanup",
                             daemon=True).start()

    def _start(opts):
        lines = []
        srv = state["server"]
        if srv is not None:
            if not opts.get("force"):
                return ("already sharing on port %d (clients: %d)\n"
                        "use /tmux-share stop, /tmux-share restart or --force"
                        % (srv.port, srv.clients))
            _stop(keep_auth=True)

        cfg = _resolve_config(opts)

        srv = ShareServer(
            pane=cfg["pane"],
            port=cfg["port"],
            bind=cfg["bind"],
            interval=cfg["interval"],
            idle_interval=cfg["idle_interval"],
            user=cfg["user"],
            password=cfg.get("password"),
            max_auth_fails=cfg["max_auth_fails"],
            max_auth_fails_per_ip=cfg["max_auth_fails_per_ip"],
            webroot=cfg["webroot"],
            log_path=str(_log_path()),
            on_auth_fail=_notify_auth_fail,
            allow_noauth=bool(cfg.get("noauth")),
        )
        try:
            srv.start()
        except ShareError as e:
            raise _ArgsError(str(e))
        except OSError as e:
            raise _ArgsError("cannot start server: %s" % (e,))

        with lock:
            state["server"] = srv
            state["config"] = {k: v for k, v in cfg.items() if k != "password"}
            state["user"] = cfg["user"]
            state["password"] = cfg.get("password")
            state["noauth"] = bool(cfg.get("noauth"))

        warn_msg = _write_state_file(cfg, srv)

        lines.append("sharing pane %s on %s:%d"
                     % (cfg["pane"], cfg["bind"], cfg["port"]))
        for url in _urls(cfg):
            lines.append("  " + url)
        if cfg["user"]:
            lines.append("  auth: user %r" % (cfg["user"],))
            if "genpass" in opts:
                lines.append("  password: %s  (shown once, not logged)"
                             % (cfg["password"],))
        else:
            lines.append("  auth: OFF (--noauth) - anyone who can reach the "
                         "port can type into the pane")
            srv.log("WARNING: serving without authentication (--noauth)")
            if cfg["bind"] not in LOOPBACK_NAMES:
                lines.append("  WARNING: bound to %s without credentials"
                             % (cfg["bind"],))
                srv.log("WARNING: bound to %s with no authentication" % cfg["bind"])
        if warn_msg:
            lines.append("  " + warn_msg)
        lines.append("viewers: %d | idle poll: %.1fs | active poll: %.2fs"
                     % (srv.clients, cfg["idle_interval"], cfg["interval"]))
        lines.append("stop with /tmux-share stop, inspect with /tmux-share status")
        return "\n".join(lines)

    def _stop(keep_auth=False):
        srv = state["server"]
        if srv is None:
            _remove_state_file()
            return "not sharing"
        try:
            srv.stop()
        finally:
            with lock:
                state["server"] = None
                if not keep_auth:
                    state["password"] = None
                    state["user"] = None
                    state["noauth"] = False
                    if state["config"]:
                        # keep port/pane/intervals, forget the identity
                        state["config"].pop("user", None)
                        state["config"].pop("noauth", None)
            _remove_state_file()
        return "stopped sharing on port %d" % srv.port

    def _status():
        srv = state["server"]
        if srv is None:
            stale = _read_state_file()
            if stale:
                ours = stale.get("pid") == os.getpid()
                return ("not sharing in this session (pid %s, port %s, pane %s%s)\n"
                        "state file: %s"
                        % (stale.get("pid"), stale.get("port"),
                           stale.get("pane"),
                           "" if ours else " - stale, left by an older run",
                           _state_path()))
            return "not sharing\nstate file: %s (absent)" % (_state_path(),)

        snap = srv.snapshot()
        lines = [
            "sharing pane %s on %s:%d" % (snap["pane"], snap["bind"], snap["port"]),
            "  uptime:      %.0fs" % snap["uptime"],
            "  clients:     %d%s" % (snap["clients"],
                                     (" (" + ", ".join(snap["client_ips"]) + ")")
                                     if snap["client_ips"] else ""),
            "  auth:        %s" % ("on (user %r)" % state["user"] if snap["auth"] else "OFF"),
            "  url prefix:  %s" % (snap.get("webroot") or "/ (none)"),
            "  frames:      %d" % snap["frames_sent"],
            "  auth fails:  %d (server stops at %s; per-IP lockout %s)" % (
                snap["auth_fails"], snap["max_auth_fails"] or "never",
                ("after %d" % snap["max_auth_fails_per_ip"])
                if snap["max_auth_fails_per_ip"] else "off"),
            "  poll:        %.2fs active / %.1fs idle" % (snap["interval"],
                                                         snap["idle_interval"]),
            "  last frame:  %s" % (("%.1fs ago" % (time.time() - snap["last_capture_ts"]))
                                   if snap["last_capture_ts"] else "none yet"),
        ]
        if snap["last_error"]:
            lines.append("  last error:  %s" % snap["last_error"])
        if snap.get("blocked_ips"):
            lines.append("  blocked:     %s" % ", ".join(
                "%s(%ds)" % (ip, max(0, int(until - time.time())))
                for ip, until in sorted(snap["blocked_ips"].items())))
        lines.append("  log:         %s" % (_log_path(),))
        return "\n".join(lines)

    def _log_tail(n):
        srv = state["server"]
        if srv is not None:
            lines = srv.log_tail(n)
            if lines:
                return "\n".join(lines)
        path = _log_path()
        try:
            with open(path, "r", encoding="utf-8", errors="replace") as fh:
                tail = fh.readlines()[-n:]
        except OSError:
            return "no log yet (%s)" % (path,)
        return "".join(tail).rstrip("\n") or "(log empty)"

    # ------------------------------------------------------------ command

    def cmd_share(args_str):
        try:
            sub, opts, rest = _parse_args(args_str)
        except _ArgsError as e:
            return "error: %s\n/tmux-share help" % (e,)

        if sub == "help" or opts.get("help"):
            return HELP_TEXT

        if rest and sub != "log":
            return "error: unexpected argument(s): %s\n/tmux-share help" % (" ".join(rest),)

        try:
            if sub == "start":
                return _start(opts)
            if sub == "stop":
                return _stop()
            if sub == "restart":
                _stop(keep_auth=True)
                return _start(opts)
            if sub == "status":
                return _status()
            if sub == "log":
                n = 40
                if rest:
                    parsed = _int_value(rest[0])
                    if parsed is None or parsed < 1:
                        return "error: bad line count: " + rest[0]
                    n = min(parsed, 2000)
                return _log_tail(n)
        except _ArgsError as e:
            return "error: %s" % (e,)
        except Exception as e:                       # never leak a traceback to stdout
            return "error: %s: %s" % (type(e).__name__, e)
        return "error: unknown subcommand: " + sub

    ctx.register_command("tmux-share", cmd_share, "Share a tmux pane over HTTP")

    # --------------------------------------------------------- context bar

    def on_context_bar():
        srv = state["server"]
        if srv is None:
            return None
        try:
            snap = srv.snapshot()
        except Exception:
            return None
        color = colors["red"] if snap["last_error"] else colors["yellow"]
        dot = "\u25cf"
        clients = snap["clients"]
        text = "share:%d %s%d" % (snap["port"], dot, clients)
        if snap["last_error"]:
            text = "share:%d !%d" % (snap["port"], clients)
        return "%s%s%s%s" % (color, colors["bold"], text, colors["reset"])

    ctx.register_hook("on_context_bar", on_context_bar)

    # -------------------------------------------------------------- teardown

    def shutdown():
        with lock:
            if state["closed"]:
                return
            state["closed"] = True
            srv = state["server"]
            state["server"] = None
            state["password"] = None
        if srv is not None:
            try:
                srv.stop(timeout=2.0)
            except Exception:
                pass
            _remove_state_file()

    atexit.register(shutdown)
    return {"name": "tmux_share", "cleanup": shutdown}


# --------------------------------------------------------------------- page
# Viewer HTML, inlined so the plugin needs no files besides itself.
# Served verbatim at "/" (see Handler.do_GET); INDEX_BYTES is the UTF-8 form.

HTML_PAGE = r"""<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>tmux-share</title>
<style>
html, body { margin: 0; padding: 0; height: 100%; background: #222222; color: #ffffff; }
#screen {
  font-family: "Fira Code Nerd Font", "Fira Code", monospace;
  font-size: 14px; line-height: 1.25;
  white-space: pre; margin: 0; padding: 8px;
  min-height: calc(100vh - 28px); box-sizing: border-box;
  outline: none;
}
#bar { height: 28px; padding: 4px 8px; box-sizing: border-box;
  font-family: monospace; font-size: 12px; color: #9a9996; }
#bar .warn { color: #fd9997; font-weight: bold; }
.cursor { background: #ffffff; color: #222222; }
#kbd { position: fixed; top: 0; left: 0; width: 1px; height: 1px; font-size: 16px; opacity: 0; border: 0; padding: 0; resize: none; }
#keys { display: none; }
body.mobile #keys { display: flex; flex-wrap: wrap; gap: 4px; position: fixed; left: 0; right: 0; bottom: 28px; padding: 4px 8px; background: #222222; }
#keys button { flex: 1 0 auto; min-width: 44px; height: 42px; font-family: monospace; font-size: 16px; color: #e4e4e4; background: #333333; border: 1px solid #5a5a5a; border-radius: 6px; }
#keys button.active { background: #76fefe; color: #222222; border-color: #76fefe; }
body.mobile #bar { position: fixed; left: 0; right: 0; bottom: 0; background: #222222; }
body.mobile #screen { padding-bottom: 130px; }
</style>
</head>
<body>
<pre id="screen" tabindex="0"></pre>
<textarea id="kbd" rows="1" autocomplete="off" autocorrect="off" autocapitalize="off" spellcheck="false"></textarea>
<div id="keys"></div>
<div id="bar">connecting...</div>
<script>
var PAL = {
  black: '#222222', red: '#fd9997', green: '#97ff97', yellow: '#cbcc00',
  blue: '#fa9e9e', magenta: '#fefefe', cyan: '#76fefe', white: '#e4e4e4',
  brightBlack: '#9a9996', brightRed: '#fd9997', brightGreen: '#a8ffa9',
  brightYellow: '#fefe00', brightBlue: '#fe8887', brightMagenta: '#fe8887',
  brightCyan: '#00fffd', brightWhite: '#fefefe'
};
var FG = { 30: 'black', 31: 'red', 32: 'green', 33: 'yellow', 34: 'blue', 35: 'magenta', 36: 'cyan', 37: 'white' };
var BFG = { 90: 'brightBlack', 91: 'brightRed', 92: 'brightGreen', 93: 'brightYellow', 94: 'brightBlue', 95: 'brightMagenta', 96: 'brightCyan', 97: 'brightWhite' };
var BG = { 40: 'black', 41: 'red', 42: 'green', 43: 'yellow', 44: 'blue', 45: 'magenta', 46: 'cyan', 47: 'white' };
var BBG = { 100: 'brightBlack', 101: 'brightRed', 102: 'brightGreen', 103: 'brightYellow', 104: 'brightBlue', 105: 'brightMagenta', 106: 'brightCyan', 107: 'brightWhite' };

function esc(s) { return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;'); }

function css256(n) {
  if (n >= 0 && n < 8) return PAL[['black','red','green','yellow','blue','magenta','cyan','white'][n]];
  if (n >= 8 && n < 16) return PAL[['brightBlack','brightRed','brightGreen','brightYellow','brightBlue','brightMagenta','brightCyan','brightWhite'][n - 8]];
  if (n >= 16 && n < 232) {
    var v = n - 16, b = v % 6, g = ((v / 6) | 0) % 6, r = ((v / 36) | 0) % 6;
    function lv(c) { return c ? c * 40 + 55 : 0; }
    return 'rgb(' + lv(r) + ',' + lv(g) + ',' + lv(b) + ')';
  }
  if (n >= 232 && n < 256) { var gr = 8 + (n - 232) * 10; return 'rgb(' + gr + ',' + gr + ',' + gr + ')'; }
  return null;
}

function lineToHtml(line, fg, bg, bold, dim) {
  var out = '', buf = '';
  function flush() {
    if (!buf) return;
    var st = '';
    if (fg) st += 'color:' + (PAL[fg] || fg) + ';';
    if (bg) st += 'background:' + (PAL[bg] || bg) + ';';
    if (bold) st += 'font-weight:bold;';
    if (dim) st += 'opacity:0.5;';
    out += st ? '<span style="' + st + '">' + esc(buf) + '</span>' : esc(buf);
    buf = '';
  }
  var re = /\x1b\[([0-9;]*)m|\x1b\[[?0-9;]*[A-Za-z]|\x1b[()][0-9A-Z]|\x1b[=>M78]|\x0f/g, m, last = 0;
  while ((m = re.exec(line))) {
    buf += line.slice(last, m.index);
    var seq = m[0];
    if (seq.indexOf('[', 1) > 0 && seq[seq.length - 1] === 'm') {
      flush();
      var parts = seq.slice(2, -1).split(';');
      if (parts.length === 1 && parts[0] === '') parts = ['0'];
      for (var i = 0; i < parts.length; i++) {
        var n = parseInt(parts[i], 10);
        if (isNaN(n) || n === 0) { fg = null; bg = null; bold = false; dim = false; }
        else if (n === 1) bold = true;
        else if (n === 2) dim = true;
        else if (n === 22) { bold = false; dim = false; }
        else if (n === 23) dim = false;
        else if (FG[n]) fg = FG[n];
        else if (BFG[n]) fg = BFG[n];
        else if (n === 39) fg = null;
        else if (BG[n]) bg = BG[n];
        else if (BBG[n]) bg = BBG[n];
        else if (n === 49) bg = null;
        else if (n === 38 || n === 48) {
          var isFg = (n === 38);
          var mode = parseInt(parts[i + 1], 10), css = null;
          if (mode === 5 && i + 2 < parts.length) { css = css256(parseInt(parts[i + 2], 10)); i += 2; }
          else if (mode === 2 && i + 4 < parts.length) {
            css = 'rgb(' + ((parseInt(parts[i + 2], 10)) | 0) + ',' + ((parseInt(parts[i + 3], 10)) | 0) + ',' + ((parseInt(parts[i + 4], 10)) | 0) + ')';
            i += 4;
          }
          if (css) { if (isFg) fg = css; else bg = css; }
        }
      }
    }
    last = m.index + seq.length;
  }
  buf += line.slice(last);
  flush();
  return { html: out, fg: fg, bg: bg, bold: bold, dim: dim };
}

function ansiToHtml(data, cx, cy) {
  var lines = String(data || '').split('\n');
  var fg = null, bg = null, bold = false, dim = false, html = [];
  for (var r = 0; r < lines.length; r++) {
    var res = lineToHtml(lines[r], fg, bg, bold, dim);
    fg = res.fg; bg = res.bg; bold = res.bold; dim = res.dim;
    var cell = res.html;
    if (r === cy) {
      var vis = lines[r].replace(/\x1b\[[0-9;]*m/g, '').replace(/\x1b\[[?0-9;]*[A-Za-z]/g, '');
      var idx = Math.min(cx, vis.length), count = 0, out2 = '', buf2 = '', k = 0;
      var parts = cell.split(/(<[^>]+>)/g);
      var done = false;
      for (var p = 0; p < parts.length; p++) {
        var part = parts[p];
        if (!part) continue;
        if (part[0] === '<') { out2 += part; continue; }
        var txt = part.replace(/&amp;/g, '&').replace(/&lt;/g, '<').replace(/&gt;/g, '>');
        for (k = 0; k < txt.length; k++) {
          if (count === idx && !done) { out2 += '<span class="cursor">' + esc(txt[k] || ' ') + '</span>'; done = true; }
          else out2 += esc(txt[k]);
          count++;
        }
      }
      if (!done) out2 += '<span class="cursor"> </span>';
      cell = out2;
    }
    html.push(cell || ' ');
  }
  return html.join('\n');
}

var screen = document.getElementById('screen');
var bar = document.getElementById('bar');
// Page may live under a URL prefix (/svr/terminal); keep API calls relative to it.
var BASE = location.pathname.replace(/\/index\.html$/, '').replace(/\/+$/, '');
var es = null;
var dead = false;
var lastMsg = 0;
var statusText = 'connecting...';
var noAuth = false;
var lastFrame = null;   // { data, cx, cy, cols, rows }

// Compose the status bar: optional NO AUTH warning, connection state, geometry.
function updateBar() {
  var html = esc(statusText);
  if (lastFrame) {
    html += ' \u2014 ' + lastFrame.cols + 'x' + lastFrame.rows +
            ' cursor ' + lastFrame.cx + ',' + lastFrame.cy;
  }
  if (noAuth) html = '<span class="warn">NO AUTH \u2014 anyone can type</span> ' + html;
  bar.innerHTML = html;
}

function draw() {
  if (!lastFrame) return;
  screen.innerHTML = ansiToHtml(lastFrame.data, lastFrame.cx, lastFrame.cy);
}

function connect() {
  es = new EventSource(BASE + '/events');
  es.onopen = function() {
    lastMsg = Date.now();
    statusText = IS_MOBILE ? 'connected \u2014 tap screen to type' : 'connected \u2014 click here then type';
    updateBar();
    if (!IS_MOBILE) screen.focus();
  };
  es.onerror = function() {
    if (dead) { statusText = 'SESSION ENDED \u2014 server killed the session'; updateBar(); return; }
    statusText = 'reconnecting\u2026';
    updateBar();
  };
  es.onmessage = function(ev) {
    lastMsg = Date.now();
    var msg;
    try { msg = JSON.parse(ev.data); } catch (e) { return; }
    if (msg.type === 'ping') return;
    if (msg.type === 'meta') {
      // Server tells us whether authentication is enforced.
      noAuth = !msg.auth;
      updateBar();
      return;
    }
    if (msg.type === 'dead') {
      dead = true;
      statusText = 'SESSION ENDED \u2014 server killed the session';
      updateBar();
      try { es.close(); } catch (e) {}
      return;
    }
    if (msg.type === 'cursor') {
      // Cheap cursor-only update: reuse the cached frame, no full redraw needed.
      if (!lastFrame) return;
      lastFrame.cx = msg.cx || 0;
      lastFrame.cy = msg.cy || 0;
      draw();
      updateBar();
      return;
    }
    if (msg.type !== 'screen') return;
    lastFrame = { data: msg.data, cx: msg.cx || 0, cy: msg.cy || 0,
                  cols: msg.cols, rows: msg.rows };
    draw();
    updateBar();
  };
}

// watchdog: server pings every 15s; no traffic for 40s -> reconnect (server resends last frame)
setInterval(function() {
  if (!dead && es && Date.now() - lastMsg > 40000) {
    statusText = 'reconnecting\u2026';
    updateBar();
    try { es.close(); } catch (e) {}
    connect();
  }
}, 5000);

function send(s) {
  if (dead) return;
  fetch(BASE + '/input', { method: 'POST', body: JSON.stringify({ input: s }) }).catch(function() {});
}

var KEYS = {
  Enter: '\r', Backspace: '\x7f', Tab: '\t', Escape: '\x1b', Delete: '\x1b[3~',
  ArrowUp: '\x1b[A', ArrowDown: '\x1b[B', ArrowRight: '\x1b[C', ArrowLeft: '\x1b[D',
  Home: '\x1b[H', End: '\x1b[F', PageUp: '\x1b[5~', PageDown: '\x1b[6~'
};

screen.addEventListener('keydown', function(e) {
  if (dead) { e.preventDefault(); return; }
  if (e.ctrlKey && e.key.length === 1) {
    var c = e.key.toUpperCase().charCodeAt(0);
    if (c >= 64 && c <= 95) { send(String.fromCharCode(c - 64)); e.preventDefault(); return; }
  }
  if (KEYS[e.key]) { send(KEYS[e.key]); e.preventDefault(); return; }
  if (e.key.length === 1 && !e.metaKey) { send(e.key); e.preventDefault(); }
});
var IS_MOBILE = /Android|iPhone|iPad|iPod|Mobile/i.test(navigator.userAgent) || location.search.indexOf('mobile=1') >= 0;
var ctrlSticky = false;
var btnCtrl = null;
var kbd = document.getElementById('kbd');
var keysbar = document.getElementById('keys');

function sendKey(ch) {
  var armed = ctrlSticky;
  ctrlSticky = false;
  if (btnCtrl) btnCtrl.className = '';
  if (armed) {
    var c = ch.toUpperCase().charCodeAt(0);
    if (c >= 64 && c <= 95) { send(String.fromCharCode(c - 64)); return; }
  }
  send(ch === '\n' ? '\r' : ch);
}

if (IS_MOBILE) {
  document.body.className = 'mobile';
  kbd.value = '\u00a0';
  var KB = [
    ['Esc', '\x1b'], ['Tab', '\t'], ['Ctrl', 'ctrl'], ['\u232b', '\x7f'],
    ['\u2190', '\x1b[D'], ['\u2191', '\x1b[A'], ['\u2193', '\x1b[B'], ['\u2192', '\x1b[C'], ['\u23ce', '\r']
  ];
  for (var i = 0; i < KB.length; i++) {
    (function(label, val) {
      var b = document.createElement('button');
      b.textContent = label;
      b.setAttribute('tabindex', '-1');
      if (val === 'ctrl') {
        btnCtrl = b;
        b.addEventListener('pointerdown', function(e) {
          e.preventDefault();
          ctrlSticky = !ctrlSticky;
          b.className = ctrlSticky ? 'active' : '';
        });
      } else {
        b.addEventListener('pointerdown', function(e) {
          e.preventDefault();
          if (!dead) sendKey(val);
        });
      }
      keysbar.appendChild(b);
    })(KB[i][0], KB[i][1]);
  }
  kbd.addEventListener('input', function() {
    var v = kbd.value.split('\u00a0').join('');
    kbd.value = '\u00a0';
    if (dead) return;
    if (!v) { send('\x7f'); return; }
    for (var j = 0; j < v.length; j++) sendKey(v[j]);
  });
  document.addEventListener('click', function(e) {
    for (var t = e.target; t; t = t.parentNode) { if (t.id === 'keys') return; }
    kbd.focus();
  });
}

screen.addEventListener('click', function() { if (!IS_MOBILE) screen.focus(); });
connect();
if (!IS_MOBILE) screen.focus();
</script>
</body>
</html>
"""

INDEX_BYTES = HTML_PAGE.encode("utf-8")
