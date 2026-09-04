"""Direct access to the dtx host-side command server.

dtx is a dynamic command server on the host machine. It exposes a Unix
socket (normally /run/user/1000/tmp/dtx-server.sock);one command line per
connection is written to the socket and the raw result text is returned.

The command set is dynamic -- commands come and go -- so always run
`help` first to discover what is available,and `help <command>` for the
usage of a specific command. This plugin is a dumb forwarder: any command
line is passed through unchanged and the raw output is returned. At plugin
load time it takes a best-effort snapshot of the available commands (via
`list`) and includes it in the tool description.
"""

import os
import subprocess
from typing import Optional

from aicoder.utils.bool_utils import env_bool

SOCKET_PATH = "/run/user/1000/tmp/dtx-server.sock"

DTX_DESCRIPTION = (
    "Direct access to the host-side dtx command server. The command set "
    "is dynamic -- commands come and go -- so always run 'help' first to "
    "discover available commands,and 'help <command>' for a command's "
    "usage. One command per call;the returned text is the server's raw "
    "result."
)


def _socket_path() -> str:
    tmpdir = os.environ.get("TMP")
    if tmpdir:
        return os.path.join(tmpdir, "dtx-server.sock")
    return SOCKET_PATH


def _request(cmdline: str) -> str:
    """Send one dtx command line and return the raw result text."""
    if not cmdline.strip():
        raise ValueError("dtx: empty command line (try 'help')")

    socket_path = _socket_path()
    result = subprocess.run(
        ["nc", "-N", "-U", socket_path],
        input=cmdline + "\n",
        text=True,
        capture_output=True,
        timeout=300,
        check=False,
    )
    if result.returncode != 0:
        detail = result.stderr.strip() or f"socket {socket_path} unreachable"
        raise RuntimeError(f"dtx request failed: {detail}")
    return result.stdout.strip()


def _discover_commands(timeout: float = 5.0) -> Optional[str]:
    """Best-effort snapshot of available dtx commands (via 'list') at plugin init.



    Returns comma-joined names, or None if discovery fails (never raises).
    """
    try:
        result = subprocess.run(
            ["nc", "-N", "-U", _socket_path()],
            input="list\n",
            text=True,
            capture_output=True,
            timeout=timeout,
            check=False,
        )
        if result.returncode != 0:
            return None
        stdout = result.stdout
        if "Output:" in stdout:
            stdout = stdout.split("Output:", 1)[1].split("Stderr:", 1)[0]
        names = [
            line.strip()
            for line in stdout.splitlines()
            if line.strip() and not line.startswith(("Available", "Usage", "Exit"))
        ]
        return ", ".join(names) if names else None
    except Exception:
        return None


def create_plugin(ctx):
    if env_bool("DTX_DISABLED"):
        return

    snapshot = _discover_commands()
    description = DTX_DESCRIPTION
    if snapshot:
        description += (
            f" Current commands (snapshot taken at plugin startup): {snapshot}."
        )

    def dtx_command(args_str: str) -> str:
        return _request(args_str)

    def dtx_tool(args: dict) -> dict:
        if not isinstance(args, dict):
            raise TypeError("dtx arguments must be an object")

        command = args.get("command")
        if not isinstance(command, str) or not command.strip():
            raise ValueError("dtx: 'command' is required (e.g. 'help')")

        output = _request(command)
        return {
            "tool": "dtx",
            "friendly": f"dtx {command}\n{output}",
            "detailed": f"dtx {command}\n{output}",
        }

    ctx.register_tool(
        "dtx",
        dtx_tool,
        description + " When calling as a tool, pass the full command line in 'command'.",
        {
            "type": "object",
            "properties": {
                "command": {
                    "type": "string",
                    "description": (
                        "One full dtx command line, e.g. 'help' or 'help vet'."
                    ),
                },
            },
            "required": ["command"],
        },
        auto_approved=True,
    )

    ctx.register_command("dtx", dtx_command, description)

    if env_bool("DEBUG"):
        print("  - dtx tool")
        print("  - /dtx command")