"""
Sandbox sealing plugin.

Wraps every run_shell_command payload in a nested bwrap sandbox
("sealed" mode). Sealed = the shell cannot reach host services
(tmux socket, dbus, X11, dtx, pulse) or /proc — only recipes the
user lifts at runtime restore specific access.

State is runtime-only: every session starts sealed with no recipes.
/seal off is the explicit escape hatch. Fail-closed: if the wrapper
cannot be built, the command is blocked, never run unsealed.
"""

import os
import shlex
import shutil

RT = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
HOME = os.environ.get("HOME") or ""

RECIPES = ("proc", "tmux", "dtx", "dbus", "x11", "rt", "adb")

# Env vars that leak host-service access: stripped in sealed mode,
# restored by recipes from the values captured at plugin load.
_STRIP_VARS = (
    "TMUX",
    "TMUX_PANE",
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

_state = {
    "sealed": True,  # always start sealed
    "allowed": set(),  # recipe names lifted at runtime
    "net": True,  # network enabled by default; /sec net off -> bwrap --unshare-net
}


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
    if HOME:
        argv += ["--ro-bind", HOME, HOME]
        # Writable ephemeral cache (uv & friends) inside the ro home.
        argv += ["--tmpfs", os.path.join(HOME, ".cache")]

    argv += ["--bind", cwd, cwd]

    # /tmp must stay writable and shared with the outer sandbox
    # (write_file("/tmp/x.py") -> run python3 /tmp/x.py).
    argv += ["--bind", "/tmp", "/tmp"]
    if "x11" not in allowed:
        # Cover the X11 sockets inherited with /tmp.
        argv += ["--tmpfs", "/tmp/.X11-unix"]

    if os.path.isdir("/mnt/shared"):
        argv += ["--bind", "/mnt/shared", "/mnt/shared"]

    # Strip host-service env vars (recipes restore the ones they lift).
    for v in _STRIP_VARS:
        if v in os.environ:
            argv += ["--unsetenv", v]

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
        for v in ("TMUX", "TMUX_PANE", "AICODER_TMUX_PANE"):
            if v in _ORIG_ENV:
                argv += ["--setenv", v, _ORIG_ENV[v]]

    if "dtx" in allowed:
        sock = f"{RT}/tmp/dtx-server.sock"
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

    argv += ["/bin/bash", "-c", command]
    return argv


def _on_before_run_shell_command(command):
    if not _state["sealed"]:
        return None
    try:
        return _build_argv(command)
    except Exception as e:  # noqa: BLE001 — fail-closed: any seal failure blocks the command
        return _blocked(f"seal error ({e}); command blocked (fail-closed)")


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
    if not bwrap_ok:
        lines.append("  WARNING: bwrap not found - commands are BLOCKED (fail-closed)")
    return "\n".join(lines)


def _handle_sec(args: str):
    parts = args.strip().split()

    if not parts or parts[0] == "status":
        return _status()

    cmd = parts[0]

    if cmd == "seal":
        if len(parts) < 2 or parts[1] not in ("on", "off"):
            return "usage: /sec seal on|off"
        _state["sealed"] = parts[1] == "on"
        return "sealed: nested bwrap active" if _state["sealed"] else \
            "UNSEALED: shell commands run without bwrap"

    if cmd == "net":
        if len(parts) < 2 or parts[1] not in ("on", "off"):
            return "usage: /sec net on|off"
        _state["net"] = parts[1] == "on"
        return "net: ON (network available)" if _state["net"] else \
            "net: OFF (isolated netns - no egress, no localhost services)"

    if cmd in ("allow", "deny"):
        if len(parts) < 2:
            return f"usage: /sec {cmd} <recipe>  (recipes: {', '.join(RECIPES)})"
        name = parts[1]
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

    return "usage: /sec seal on|off | /sec net on|off | /sec allow|deny <recipe> | /sec status"


def create_plugin(ctx):
    if shutil.which("bwrap"):
        ctx.register_hook("on_before_run_shell_command", _on_before_run_shell_command)
    else:
        # Fail-closed even when bwrap is missing: block everything.
        ctx.register_hook(
            "on_before_run_shell_command",
            lambda command: _blocked(
                "bwrap not found; command blocked (fail-closed). '/sec seal off' to disable sealing"
            ),
        )

    ctx.register_command(
        "sec",
        _handle_sec,
        "Sandbox sealing control (seal on|off, net on|off, allow|deny <recipe>, status)",
    )
