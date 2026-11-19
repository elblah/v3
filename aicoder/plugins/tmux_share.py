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
           [--max-auth-fails N] [--force]
    /tmux-share stop | status | restart | log [N] | help

The password is kept in memory only. It is never written to the state file,
never passed through argv or the environment, and never logged.
"""

import atexit
import importlib.util
import json
import os
import re
import secrets
import shlex
import string
import subprocess
import threading
import time
from pathlib import Path

from aicoder.core.config import Config
from aicoder.utils.log import LogUtils

PLUGIN_DIR = Path(__file__).resolve().parent
SERVER_FILE = PLUGIN_DIR / "_tmux_share" / "server.py"

DEFAULT_PORT = 8080
DEFAULT_BIND = "127.0.0.1"
DEFAULT_INTERVAL = 0.2
DEFAULT_IDLE_INTERVAL = 1.0
DEFAULT_MAX_AUTH_FAILS = 10
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
  --user U --password P protect the page with basic auth
  --genpass [N]         generate a random password (default 24 chars),
                        user defaults to "share"; shown once, never logged
  --interval S          poll interval with viewers   (default 0.2)
  --idle-interval S     poll interval with no viewers (default 1.0, 0 = off)
  --max-auth-fails N    bad logins per IP before a 60s block (default 10)
  --force               stop a running share first

Binding to a non-loopback address without credentials means anyone on the
network can type into the pane. That is your call, but it is warned about.

Secrets live in memory only: `restart` (and `start --force`) keep the current
credentials, `stop` forgets them, so the next start needs --genpass or
--password again.
"""

PASSWORD_ALPHABET = string.ascii_letters + string.digits + "-_"


class _ArgsError(Exception):
    """Bad /tmux-share arguments."""


def _load_server_module():
    """Import the vendored server as a private module (no package install)."""
    if not SERVER_FILE.exists():
        raise _ArgsError("server file missing: " + str(SERVER_FILE))
    spec = importlib.util.spec_from_file_location(
        "aicoder_tmux_share_server", str(SERVER_FILE))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


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
    if "max_auth_fails" in opts:
        n = _int_value(opts["max_auth_fails"])
        if n is None or n < 1:
            raise _ArgsError("bad --max-auth-fails: " + str(opts["max_auth_fails"]))
        opts["max_auth_fails"] = n
    if "pane" in opts and not _valid_pane(opts["pane"]):
        raise _ArgsError("bad --pane (expected %N, e.g. %0): " + str(opts["pane"]))
    if "genpass" in opts and "password" in opts:
        raise _ArgsError("use either --password or --genpass, not both")

    return sub, opts, rest


def create_plugin(ctx):
    """tmux-share: serve the current tmux pane to a browser."""

    colors = Config.colors
    lock = threading.RLock()
    state = {
        "server": None,      # ShareServer instance (in-process)
        "password": None,    # kept in memory only
        "user": None,
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
            "interval": cfg["interval"],
            "idle_interval": cfg["idle_interval"],
            "max_auth_fails": cfg["max_auth_fails"],
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
                        "max_auth_fails", "user"):
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
            "user": opts.get("user", prev.get("user", state["user"])),
        }

        if not _valid_pane(cfg["pane"]):
            raise _ArgsError(
                "no pane: TMUX_PANE is unset and no --pane given "
                "(aicoder must run inside tmux, or pass --pane %N)")

        # Credentials: flags win, otherwise reuse the in-memory pair.
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
        cfg["password"] = password
        return cfg

    def _urls(cfg):
        port = cfg["port"]
        if cfg["bind"] in LOOPBACK_NAMES:
            return ["http://127.0.0.1:%d/" % port]
        urls = []
        for ip in _lan_ips():
            urls.append("http://%s:%d/" % (ip, port))
        if not urls:
            urls.append("http://<this-host>:%d/" % port)
        return urls

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
        module = _load_server_module()

        srv = module.ShareServer(
            pane=cfg["pane"],
            port=cfg["port"],
            bind=cfg["bind"],
            interval=cfg["interval"],
            idle_interval=cfg["idle_interval"],
            user=cfg["user"],
            password=cfg.get("password"),
            max_auth_fails=cfg["max_auth_fails"],
            log_path=str(_log_path()),
        )
        try:
            srv.start()
        except module.ShareError as e:
            raise _ArgsError(str(e))
        except OSError as e:
            raise _ArgsError("cannot start server: %s" % (e,))

        with lock:
            state["server"] = srv
            state["config"] = {k: v for k, v in cfg.items() if k != "password"}
            state["user"] = cfg["user"]
            state["password"] = cfg.get("password")

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
            lines.append("  auth: OFF - anyone who can reach the port "
                         "can type into the pane")
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
                    if state["config"]:
                        # keep port/pane/intervals, forget the identity
                        state["config"].pop("user", None)
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
            "  frames:      %d" % snap["frames_sent"],
            "  auth fails:  %d" % snap["auth_fails"],
            "  poll:        %.2fs active / %.1fs idle" % (snap["interval"],
                                                         snap["idle_interval"]),
            "  last frame:  %s" % (("%.1fs ago" % (time.time() - snap["last_capture_ts"]))
                                   if snap["last_capture_ts"] else "none yet"),
        ]
        if snap["last_error"]:
            lines.append("  last error:  %s" % snap["last_error"])
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
