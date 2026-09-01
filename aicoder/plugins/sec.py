"""
Sandbox sealing plugin.

Wraps every run_shell_command payload in a nested bwrap sandbox
("sealed" mode). Sealed = the shell cannot reach host services
(tmux socket, dbus, X11, dtx, pulse) or /proc — only recipes the
user lifts at runtime restore specific access.
SEC_PRINT_STATUS=1 enables the [sec] status line printed before each
command (default off).
SEC_BADGE=0 disables the seal|net context-bar badge (default on).
The context bar appends a two-slot seal|net badge: [S|N] = bwrap +
net; U = unsealed, X = net off, N = net on. ASCII-only (wide emoji
break tmux rendering); green = safe (sealed / net off), bold yellow =
warning (unsealed / net on). Legend always printed by /sec status.

State is runtime-only: sessions start sealed, no recipes, no network.
SANDBOX=0 (master kill switch) starts unsealed with net allowed;
/sec seal on / net off re-tighten.
Launcher-env overrides (read once at plugin load, parent env only):
SEC_SEAL=0 starts unsealed, SEC_NET_ALLOW=1 starts with network.
/sec seal|net on|off, /sec allow (named recipes), and
/sec allow ro|rw <path> (generic dir binds) are the runtime escape hatches.

Sealed shells run with bwrap --clearenv: only a keep-list survives
(PATH/HOME/TERM/SHELL/LANG/LC_ALL/LC_*/TMUX_PANE — host-neutral or
needed for vet); host-service vars and anything else (API keys, tokens)
are absent until a recipe restores them. /sec allow env re-injects the
full launcher env captured at plugin load, minus the strip vars (those
have purpose-built recipes) and minus the forever-blocked cleared vars
(AICODER_SHELL_CLEAR_VARS from the launcher, substring-matched on the name —
these never cross, even via /sec allow env).
TMPDIR is deliberately not kept — the
launcher sets it to $XDG_RUNTIME_DIR/tmp, which is not bound inside the
seal; dropping it lets temp writes fall back to /tmp (writable + shared).

HOME defaults to an empty writable tmpfs (ephemeral caches) with only
the cwd bind visible from the real home tree; /sec allow home restores
the old full-home read-only bind (writable .cache tmpfs on top).
"""

import os
import shlex
import shutil
import sys

from aicoder.core.config import Config
from aicoder.utils.bool_utils import env_bool, parse_bool

RT = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
HOME = os.environ.get("HOME") or ""

# gocache recipe: bind GOCACHE (defaults to /mnt/gocache, the outer
# bwrap's rw mount of the real store) read-write inside the seal on
# /sec allow gocache. Not bound by default -> invisible (deny-by-default).
_GOCACHE = os.environ.get("GOCACHE", "/mnt/gocache")
# Same for the module cache; both live under the gocache bind (rw), so
# restoring the var alone is enough once that recipe is lifted.
_GOMODCACHE = os.environ.get("GOMODCACHE", "")

RECIPES = ("proc", "tmux", "dtx", "dbrowser", "dbus", "x11", "rt", "adb", "gocache", "home", "env")

# Env vars that leak host-service access: absent in sealed mode (clearenv
# drops everything; these are also never re-injected by /sec allow env),
# restored by recipes from the values captured at plugin load.
# TMUX_PANE is intentionally kept (keep-list below): it's just a pane ID
# string (e.g. "%3") — no socket path, no host access — and the AI needs
# it to call vet via dtx. The tmux recipe (socket) stays required for
# actual tmux access.
_STRIP_VARS = (
    "TMUX",
    "AICODER_TMUX_PANE",
    "DISPLAY",
    "WAYLAND_DISPLAY",
    "DBUS_SESSION_BUS_ADDRESS",
    "ADB_SERVER_SOCKET",
    # OPTS = outer sandbox wrapper's bwrap argv — info leak, nothing
    # inside the seal legitimately reads it. No recipe restores it.
    "OPTS",
)
_ORIG_ENV: dict[str, str] = {v: os.environ[v] for v in _STRIP_VARS if v in os.environ}

# Whitelist kept under --clearenv: host-neutral vars, or ones the seal
# needs to function (PATH/HOME for binaries and cwd, TMUX_PANE for vet).
# TMPDIR is deliberately NOT kept: the launcher sets it to
# $XDG_RUNTIME_DIR/tmp, which is not bound inside the seal — dropping it
# makes temp writes fall back to /tmp (writable + shared) instead of
# failing on a nonexistent path.
_KEEP_VARS = ("PATH", "HOME", "TERM", "SHELL", "LANG", "LC_ALL", "TMUX_PANE")

# Vars that must never reach the sealed shell: AICODER_SHELL_CLEAR_VARS from
# the launcher (comma-separated). Rule: an env var is hidden if its NAME
# CONTAINS any list entry as a substring — "OPENAI_" hides OPENAI_API_KEY/
# OPENAI_ORG..., "_KEY" hides anything with KEY in the name. No prefix/suffix
# syntax, no heuristics. Read at load — the sealed shell can't inject here.
_CLEAR_SUBSTRINGS = tuple(
    v.strip()
    for v in os.environ.get("AICODER_SHELL_CLEAR_VARS", "").split(",")
    if v.strip()
)


def _hidden(name: str) -> bool:
    """True if env var `name` must stay out of the sealed shell forever."""
    # The clear-list var itself is always hidden — the list is a
    # config detail, nobody inside the seal needs to see it.
    if name == "AICODER_SHELL_CLEAR_VARS":
        return True
    return any(s in name for s in _CLEAR_SUBSTRINGS)


# Filtered at capture — hidden vars never enter the snapshot, so no
# recipe (/sec allow env, keep-list, restores) can re-inject them.
_CAPTURED_ENV = {k: v for k, v in os.environ.items() if not _hidden(k)}

# adb server spec: explicit env wins; else the canonical localfilesystem
# default (host .bashrc sets TMPDIR=$XDG_RUNTIME_DIR/tmp, socket adb.sock).
# Captured at load — the sealed env strips ADB_SERVER_SOCKET, and aicoder
# may predate the export.
_ADB_SPEC = os.environ.get(
    "ADB_SERVER_SOCKET",
    f"localfilesystem:{RT}/tmp/adb.sock",
)

# Directories to shadow so the adb client binary dangles. which()+realpath
# finds the real install; the /lib twin matters because bwrap's
# --ro-bind /lib /lib resolves the host's usr-merge symlink into a REAL
# directory inside the seal - covering /usr/lib alone leaves /bin/adb's
# ../lib/... symlink target alive (verified live).
_ADB_COVERS = tuple({
    d
    for d in (
        os.path.dirname(os.path.realpath(shutil.which("adb") or "")),
        "/usr/lib/android-sdk/platform-tools",
        "/lib/android-sdk/platform-tools",
    )
    if d and os.path.isdir(d)
})

# Extra files/sockets bound into the seal alongside dtx-server.sock
# when the dtx recipe is allowed (comma-separated list, user-set in
# the aicoder launcher env, e.g.
# SEC_DTX_RECIPE_ENABLE=/run/user/1000/tmp/dbrowser.sock). Only paths
# that exist when the recipe is lifted are bound. The sealed sandbox
# cannot inject values here — os.environ is the parent aicoder env.
_DTX_EXTRA = tuple(
    p.strip()
    for p in os.environ.get("SEC_DTX_RECIPE_ENABLE", "").split(",")
    if p.strip()
)

def _env_flag(name: str, default: bool) -> bool:
    """Launcher-env override; bad value warns and falls back to the safe default."""
    try:
        return env_bool(name, default)
    except ValueError as e:
        print(f"sec: {e}; ignoring, using default", file=sys.stderr)
        return default


# Read from the parent aicoder env at load — a sealed command cannot
# inject these (same property as _DTX_EXTRA).
# SANDBOX=0 (master kill switch, same var the /sec plugin load checks):
# starts unsealed with net allowed; /sec seal on / net off re-tighten at runtime.
_SANDBOX_OFF = not _env_flag("SANDBOX", True)
_state = {
    "sealed": _env_flag("SEC_SEAL", not _SANDBOX_OFF),  # start sealed unless SEC_SEAL=0 or SANDBOX=0
    "allowed": set(),  # recipe names lifted at runtime
    "net": _env_flag("SEC_NET_ALLOW", _SANDBOX_OFF),  # net off by default (on if SANDBOX=0)
    "binds": {},  # abs path -> "ro" | "rw" (generic dir binds: /sec allow ro|rw <path>)
}

# [sec] Net/Seal/Allowed status line before each command; SEC_PRINT_STATUS=1 enables (default off).
_PRINT_STATUS = _env_flag("SEC_PRINT_STATUS", False)
# [sec] Seal|net context-bar badge; SEC_BADGE=0 disables (default on).
_BADGE_ON = _env_flag("SEC_BADGE", True)


def _blocked(msg: str) -> list[str]:
    """Argv that prints an error and fails — fail-closed block."""
    return ["/bin/sh", "-c", f"echo {shlex.quote('sec: ' + msg)} >&2; exit 126"]


def _tmux_socket() -> str | None:
    t = _ORIG_ENV.get("TMUX", "")
    return t.split(",", 1)[0] if t else None


def _build_argv(command: str) -> list[str]:
    cwd = os.getcwd()
    allowed: set[str] = _state["allowed"]

    argv = [
        "bwrap",
        "--ro-bind", "/usr", "/usr",
        "--ro-bind", "/bin", "/bin",
        "--ro-bind", "/lib", "/lib",
        "--ro-bind", "/etc", "/etc",
        "--dev", "/dev",
        "--die-with-parent",
        # Isolated PID namespace: host processes invisible (inner
        # process only sees itself + pid 1). killpg/timeout-kill from
        # the ancestor namespace still works (verified live).
        "--unshare-pid",
    ]

    # Faithful nesting: binding outer's $HOME subtree carries its
    # submounts (tmpfs + ro-binds + rw workdir) with their own flags.
    # HOME is a bind overlay problem: the old default ro-bound the whole
    # home (source readable everywhere). Default now: an empty writable
    # tmpfs HOME (ephemeral caches), and only the cwd bind below is
    # visible from the real home tree. /sec allow home restores the old
    # full-home ro-bind (writable .cache still tmpfs on top).
    if HOME:
        if "home" in allowed:
            # Full-home ro-bind (the old default); writable .cache stays
            # tmpfs on top so uv & friends can cache.
            argv += ["--ro-bind", HOME, HOME]
            argv += ["--tmpfs", os.path.join(HOME, ".cache")]
        else:
            # Empty writable tmpfs HOME (ephemeral caches); only the cwd
            # bind below is visible from the real home tree.
            argv += ["--tmpfs", HOME]

    argv += ["--bind", cwd, cwd]

    # /tmp must stay writable and shared with the outer sandbox
    # (write_file("/tmp/x.py") -> run python3 /tmp/x.py).
    argv += ["--bind", "/tmp", "/tmp"]
    if "x11" not in allowed:
        # Cover the X11 sockets inherited with /tmp.
        argv += ["--tmpfs", "/tmp/.X11-unix"]

    # Generic directory binds (/sec allow ro|rw <path>). Nothing bound
    # here stays invisible inside the seal. rw implies read.
    for path in sorted(_state["binds"]):
        if not os.path.isdir(path):
            continue
        argv += ["--bind", path, path] if _state["binds"][path] == "rw" \
            else ["--ro-bind", path, path]

    # Clearenv + keep-list: the sealed shell starts with a minimal,
    # host-neutral env instead of inheriting the parent aicoder env
    # (API keys, tokens, host-service vars, ...). Recipes re-add the
    # specific vars they lift; ordering relative to mounts is fine.
    argv += ["--clearenv"]
    for v in _KEEP_VARS:
        if v in os.environ:
            argv += ["--setenv", v, os.environ[v]]
    for k, val in os.environ.items():
        if k.startswith("LC_"):
            argv += ["--setenv", k, val]

    # /sec allow env: full launcher env back, minus the host-service
    # strip vars (those have purpose-built recipes: tmux/dtx/dbus/x11/adb)
    # and the forever-blocked cleared vars (already filtered at capture).
    # TMPDIR is excluded too even here: it points at the unbound
    # $XDG_RUNTIME_DIR/tmp — restoring it would re-break temp writes.
    if "env" in allowed:
        for v, val in _CAPTURED_ENV.items():
            if v not in _STRIP_VARS and v != "TMPDIR":
                argv += ["--setenv", v, val]

    if not _state["net"]:
        # Isolated netns: loopback only, and it starts DOWN — no
        # egress, no LAN, no localhost services, no DNS.
        argv += ["--unshare-net"]

    if "adb" not in allowed:
        # Inverse recipe: denied by default, restored by /sec allow adb.
        # The adb client never talks to the LAN itself - the host adb
        # server (localhost:5037) holds that connection, which the
        # seal's egress filter can't see. Shadowing the client binary
        # closes the practical path only; a hand-rolled client against
        # the TCP port still works. Full fix: run the server on a
        # filesystem unix socket (ADB_SERVER_SOCKET=localfilesystem:...)
        # - the recipe below binds it back in when allowed.
        for d in _ADB_COVERS:
            argv += ["--tmpfs", d]

    if "adb" in allowed:
        if _ADB_SPEC.startswith("localfilesystem:"):
            sock = _ADB_SPEC.split(":", 1)[1]
            if os.path.exists(sock):
                argv += ["--ro-bind", sock, sock]
        argv += ["--setenv", "ADB_SERVER_SOCKET", _ADB_SPEC]

    if "proc" in allowed:
        argv += ["--proc", "/proc"]

    if "tmux" in allowed:
        sock = _tmux_socket()
        if sock and os.path.exists(sock):
            argv += ["--ro-bind", sock, sock]
        for v in ("TMUX", "AICODER_TMUX_PANE"):
            if v in _ORIG_ENV:
                argv += ["--setenv", v, _ORIG_ENV[v]]

    if "dtx" in allowed:
        sock = f"{RT}/tmp/dtx-server.sock"
        if os.path.exists(sock):
            argv += ["--ro-bind", sock, sock]
        for path in _DTX_EXTRA:
            if os.path.exists(path):
                argv += ["--ro-bind", path, path]

    if "dbrowser" in allowed:
        sock = f"{RT}/tmp/dbrowser.sock"
        if os.path.exists(sock):
            argv += ["--ro-bind", sock, sock]

    if "dbus" in allowed:
        bus = f"{RT}/bus"
        if os.path.exists(bus):
            argv += ["--ro-bind", bus, bus]
        if "DBUS_SESSION_BUS_ADDRESS" in _ORIG_ENV:
            argv += ["--setenv", "DBUS_SESSION_BUS_ADDRESS", _ORIG_ENV["DBUS_SESSION_BUS_ADDRESS"]]

    if "x11" in allowed:
        if os.path.exists("/tmp/.X11-unix"):
            argv += ["--ro-bind", "/tmp/.X11-unix", "/tmp/.X11-unix"]
        if "DISPLAY" in _ORIG_ENV:
            argv += ["--setenv", "DISPLAY", _ORIG_ENV["DISPLAY"]]

    if "rt" in allowed and os.path.isdir(RT):
        argv += ["--ro-bind", RT, RT]

    if "gocache" in allowed:
        # Read-write: write Go build cache artifacts. Not bound otherwise,
        # so GOCACHE stays invisible inside the seal (deny-by-default).
        # For read-only exposure instead, use --ro-bind below.
        argv += ["--bind", _GOCACHE, _GOCACHE]
        # clearenv drops GOCACHE/GOMODCACHE with the rest of the env —
        # restore both (both live under the bind above) so the Go
        # toolchain still finds its caches.
        argv += ["--setenv", "GOCACHE", _GOCACHE]
        if _GOMODCACHE:
            argv += ["--setenv", "GOMODCACHE", _GOMODCACHE]

    argv += ["/bin/bash", "-c", command]
    return argv


def _state_log() -> str:
    parts = [r for r in RECIPES if r in _state["allowed"]]
    parts += [f"{_state['binds'][p]} {p}" for p in sorted(_state["binds"])]
    allowed = ", ".join(parts) or "(none)"
    c = Config.colors
    return (f"{c['bold']}{c['yellow']}[sec]{c['reset']} Net: {'on' if _state['net'] else 'off'} - "
            f"Seal: {'on' if _state['sealed'] else 'off'} - Allowed: {allowed}")


# Tools whose every execution routes through on_before_run_shell_command
# (sealed via resolve_command). grep is auto-approved today so the
# approval hook won't fire for it, but kept for correctness.
_SHELL_TOOLS = {"run_shell_command", "grep"}


def _on_before_run_shell_command(command):
    if _PRINT_STATUS:
        print(_state_log(), file=sys.stderr)
    if not _state["sealed"]:
        return None
    try:
        return _build_argv(command)
    except Exception as e:  # noqa: BLE001 — fail-closed: any seal failure blocks the command
        return _blocked(f"seal error ({e}); command blocked (fail-closed)")


def _on_before_approval_prompt(tool_name, arguments):
    """Print the [sec] state before the user approves a shell tool, so
    they see what sandbox state the command would run in. Return None:
    the user still answers the normal approval prompt."""
    if _PRINT_STATUS and tool_name in _SHELL_TOOLS:
        print(_state_log(), file=sys.stderr)


def _badge() -> str:
    """Two-slot context-bar badge: [S|X]. ASCII-only (wide emoji break
    tmux rendering); green = safe (sealed / net off), bold yellow = warning
    (unsealed / net on)."""
    c = Config.colors
    warn = c["bold"] + c["yellow"]
    seal = (c["brightGreen"] + "S" + c["reset"]) if _state["sealed"] \
        else (warn + "U" + c["reset"])
    net = (c["brightGreen"] + "X" + c["reset"]) if not _state["net"] \
        else (warn + "N" + c["reset"])
    return f"{c['dim']}[{c['reset']}{seal}{c['dim']}|{c['reset']}{net}{c['dim']}]{c['reset']}"


def _on_context_bar():
    """Hook: append the seal|net badge to the context bar."""
    return _badge()


def _status() -> str:
    bwrap_ok = shutil.which("bwrap") is not None
    lines = []
    if not _state["sealed"]:
        lines.append("sec: UNSEALED - shell commands run without bwrap")
        lines.append("  net: host (unsealed - full network, net toggle has no effect)")
    else:
        lines.append("sec: sealed - shell commands run in nested bwrap")
        lines.append(
            "  net: on" if _state["net"]
            else "  net: OFF (isolated netns - no egress, no localhost, no DNS)"
        )
    rec = " ".join(
        (r + "*") if r in _state["allowed"] else r for r in RECIPES
    ) or "(none)"
    lines.append(f"  recipes: {rec}   (* = allowed)")
    binds = " ".join(
        f"{p}({_state['binds'][p]})" for p in sorted(_state["binds"])
    ) or "(none)"
    lines.append(f"  binds: {binds}")
    lines.append("  badge: [S|X]  S=sealed U=unsealed  X=net off N=net on")
    lines.append("         green = safe, bold yellow = warning")
    if not bwrap_ok:
        lines.append("  WARNING: bwrap not found - commands are BLOCKED (fail-closed)")
    return "\n".join(lines)


def _handle_sec(args: str):
    parts = args.strip().split()

    if not parts or parts[0] == "status":
        return _status()

    cmd = parts[0]

    # Glued on/off form: "/sec net1" == "/sec net 1"
    if cmd.startswith(("seal", "net")):
        word = "seal" if cmd.startswith("seal") else "net"
        if len(cmd) > len(word):
            parts = [word, cmd[len(word):]] + parts[1:]
            cmd = word
            args = " ".join(parts)

    if cmd in ("seal", "net"):
        # Accept "/sec net 1" and glued "/sec net1"; parse_bool validates.
        stripped = args.strip()
        rest = stripped[len(cmd):].strip() if stripped.startswith(cmd) else ""
        try:
            val = parse_bool(rest)
        except ValueError:
            val = None
        if val is None:
            return f"usage: /sec {cmd} on|off|1|0|true|false|yes|no"
        if cmd == "seal":
            _state["sealed"] = val
            return "sealed: nested bwrap active" if val else \
                "UNSEALED: shell commands run without bwrap"
        _state["net"] = val
        return "net: ON (network available)" if val else \
            "net: OFF (isolated netns - no egress, no localhost services)"

    if cmd in ("allow", "deny"):
        if len(parts) < 2:
            return f"usage: /sec {cmd} <recipe> | /sec allow ro|rw <path>  (recipes: {', '.join(RECIPES)})"
        arg = parts[1]

        # Generic directory bind: /sec allow ro <path> | /sec allow rw <path>
        if cmd == "allow" and arg in ("ro", "rw"):
            if len(parts) < 3:
                return "usage: /sec allow ro|rw <abs-path>"
            path = parts[2]
            if not path.startswith("/"):
                return f"not an absolute path: '{path}'"
            if not os.path.isdir(path):
                return f"not a directory: '{path}'"
            _state["binds"][path] = arg
            mode = "read-only" if arg == "ro" else "read-write"
            return f"allowed {mode} bind '{path}'"

        # Generic unbind by path: /sec deny <abs-path>
        if cmd == "deny" and arg.startswith("/"):
            if arg not in _state["binds"]:
                return f"no bind for '{arg}'"
            del _state["binds"][arg]
            return f"denied bind '{arg}'"

        name = arg
        if name not in RECIPES:
            return f"unknown recipe '{name}'. recipes: {', '.join(RECIPES)}"
        if cmd == "allow":
            _state["allowed"].add(name)
            note = ""
            if name == "tmux":
                sock = _tmux_socket()
                note = f" (socket: {sock or 'NOT FOUND'})"
            elif name == "dtx":
                note = f" (socket: {RT}/tmp/dtx-server.sock" + \
                    (", present)" if os.path.exists(f"{RT}/tmp/dtx-server.sock") else ", MISSING)")
                if _DTX_EXTRA:
                    bound = sum(1 for p in _DTX_EXTRA if os.path.exists(p))
                    note += f" + {bound}/{len(_DTX_EXTRA)} extra bind(s)"
            elif name == "dbrowser":
                note = f" (socket: {RT}/tmp/dbrowser.sock" + \
                    (", present)" if os.path.exists(f"{RT}/tmp/dbrowser.sock") else ", MISSING)")
            elif name == "adb":
                spec = _ORIG_ENV.get("ADB_SERVER_SOCKET")
                note = f" (server: {spec})" if spec else \
                    f" (binary: {shutil.which('adb') or 'not found'})"
            elif name == "dbus":
                note = f" (bus: {RT}/bus" + \
                    (", present)" if os.path.exists(f"{RT}/bus") else ", MISSING)")
            return f"allowed recipe '{name}'{note}"
        _state["allowed"].discard(name)
        return f"denied recipe '{name}'"

    return "usage: /sec seal on|off | /sec net on|off | /sec allow|deny <recipe> | /sec allow ro|rw <path> | /sec deny <path> | /sec status"


def create_plugin(ctx):
    # SANDBOX=0 does NOT disable the plugin: it starts unsealed + net
    # allowed (see _SANDBOX_OFF) and /sec can re-tighten at runtime.
    if not shutil.which("bwrap"):
        # No bwrap -> install nothing: no seal hook, no /sec command.
        return
    ctx.register_hook("on_before_run_shell_command", _on_before_run_shell_command)
    ctx.register_hook("before_approval_prompt", _on_before_approval_prompt)
    if _BADGE_ON:
        ctx.register_hook("on_context_bar", _on_context_bar)

    ctx.register_command(
        "sec",
        _handle_sec,
        "Sandbox sealing control (seal on|off, net on|off, allow|deny <recipe>, allow ro|rw <path>, status)",
    )
