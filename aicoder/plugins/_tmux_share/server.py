"""tmux-share server as an importable library (no prints, no argv needed).

Serves one tmux pane over HTTP: a static viewer page, an SSE stream of screen
frames, and a POST endpoint that types into the pane. Designed to be embedded
in another process (the aicoder plugin) -- every message goes through
``ShareServer.log()``, which appends to an in-memory ring buffer and optionally
to a file, so nothing ever reaches the host application's stdout.

Standalone use is still possible:

    python3 server.py --pane %0 --port 8080 [--user u --password p]

Wire protocol (SSE):
    {"type": "meta",   "auth": bool, "version": 1}
    {"type": "screen", "cols": int, "rows": int, "cx": int, "cy": int,
     "data": "<ansi text>"}
    {"type": "cursor", "cx": int, "cy": int}
    {"type": "ping"}
"""

import base64
import hmac
import json
import os
import queue
import secrets
import subprocess
import threading
import time
from collections import deque
from http.server import BaseHTTPRequestHandler
from pathlib import Path
from socketserver import ThreadingTCPServer

HERE = Path(__file__).resolve().parent
INDEX_FILE = HERE / "index.html"
PROTOCOL_VERSION = 1
LOG_MAX_BYTES = 256 * 1024
AUTH_BLOCK_SECONDS = 60.0

LOOPBACK = ("127.0.0.1", "localhost", "::1", "")


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
                 max_auth_fails=10, log_path=None, log_lines=1000):
        if bool(user) != bool(password):
            raise ShareError("need both user and password, or neither")
        self.pane = pane
        self.port = int(port)
        self.bind = bind or "127.0.0.1"
        self.interval = max(0.02, float(interval))
        self.idle_interval = float(idle_interval or 0)
        self.user = user
        self.max_auth_fails = int(max_auth_fails or 0)
        self.log_path = log_path
        self.ring = deque(maxlen=max(50, int(log_lines)))

        self._auth_header = None
        self._auth_cookie = None
        if user and password:
            raw = (str(user) + ":" + str(password)).encode()
            self._auth_header = "Basic " + base64.b64encode(raw).decode()
            self._auth_cookie = secrets.token_urlsafe(16)

        self._clients = {}           # queue -> peer ip
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
        self._fails_by_ip = {}

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
            return time.time() < rec[1]

    def _note_auth_failure(self, ip):
        now = time.time()
        with self._lock:
            self.auth_fails += 1
            count = self._fails_by_ip.get(ip, (0, 0.0))[0] + 1
            blocked_until = now + AUTH_BLOCK_SECONDS if (
                self.max_auth_fails and count >= self.max_auth_fails) else 0.0
            self._fails_by_ip[ip] = (count, blocked_until)
            total = self.auth_fails
        self.log("AUTH FAIL %d from %s (ip count %d%s)"
                 % (total, ip, count,
                    ", blocked %ds" % int(AUTH_BLOCK_SECONDS) if blocked_until else ""))

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

            def deny(self):
                ip = share._ip(self)
                if share._auth_header:
                    share._note_auth_failure(ip)
                self.send_response(429 if share._ip_blocked(ip) else 401)
                self.send_header("WWW-Authenticate", 'Basic realm="tmux-share"')
                self.send_header("Content-Length", "0")
                self.end_headers()

            def do_GET(self):
                if share._ip_blocked(share._ip(self)):
                    self.send_error(429)
                    return
                if not share._authorized(self.headers):
                    self.deny()
                    return
                if self.path == "/events":
                    self.handle_events()
                    return
                if self.path in ("/", "/index.html"):
                    try:
                        body = INDEX_FILE.read_bytes()
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
                            + "; Path=/; HttpOnly; SameSite=Lax")
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
                ip = share._ip(self)
                if share._ip_blocked(ip):
                    self.send_error(429)
                    return
                if not share._authorized(self.headers):
                    self.deny()
                    return
                if self.path != "/input":
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

        self.log("serving pane %s on %s:%d (auth=%s)"
                 % (self.pane, self.bind, self.port, "on" if self._auth_header else "OFF"))
        if self.bind not in LOOPBACK and not self._auth_header:
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

    def stop(self, timeout=3.0):
        if self._srv is None:
            return False
        self._stop.set()
        self._wake.set()
        self._send('{"type": "ping"}')
        try:
            self._srv.shutdown()
        except Exception:
            pass
        try:
            self._srv.server_close()
        except Exception:
            pass
        for th in (self._serve_thread, self._poll_thread):
            if th is not None:
                th.join(timeout)
        self._srv = None
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
            "last_capture_ts": self.last_capture_ts,
            "last_error": self.last_error,
            "started_at": self.started_at,
            "uptime": (time.time() - self.started_at) if self.started_at else 0.0,
            "interval": self.interval,
            "idle_interval": self.idle_interval,
            "running": self._srv is not None,
        }


def main():
    import argparse
    import sys

    ap = argparse.ArgumentParser()
    ap.add_argument("--pane", default=os.environ.get("TMUX_PANE", "%0"))
    ap.add_argument("--port", type=int, default=8080)
    ap.add_argument("--bind", default=os.environ.get("BIND", "127.0.0.1"))
    ap.add_argument("--interval", type=float, default=0.2)
    ap.add_argument("--idle-interval", type=float, default=1.0)
    ap.add_argument("--user", default=None)
    ap.add_argument("--password", default=None)
    ap.add_argument("--max-auth-fails", type=int, default=10)
    ap.add_argument("--log", default=None)
    args = ap.parse_args()
    try:
        srv = ShareServer(
            args.pane, port=args.port, bind=args.bind, interval=args.interval,
            idle_interval=args.idle_interval, user=args.user,
            password=args.password, max_auth_fails=args.max_auth_fails,
            log_path=args.log)
        srv.start()
    except ShareError as e:
        print("tmux-share: %s" % e, file=sys.stderr)
        return 1
    print("serving pane %s on %s:%d" % (srv.pane, srv.bind, srv.port))
    try:
        while True:
            time.sleep(0.5)
    except KeyboardInterrupt:
        srv.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
