"""Direct access to the dtx host-side command server.

dtx is a dynamic command server on the host machine. It exposes a Unix
socket (normally /run/user/1000/tmp/dtx-server.sock); one command line per
connection is written to the socket and the raw result text is returned.
The command set is dynamic -- commands come and go -- so always run
`help` first to discover what is available, and `help <command>` for the
usage of a specific command. This plugin is a dumb forwarder: any command
line is passed through unchanged and the raw output is returned.
"""

import os
import subprocess

from aicoder.utils.bool_utils import env_bool

SOCKET_PATH = "/run/user/1000/tmp/dtx-server.sock"

DTX_DESCRIPTION = (
    "Direct access to the host-side dtx command server. "
    "dtx is a dynamic command server exposing a Unix socket "
    "(/run/user/1000/tmp/dtx-server.sock); one command per connection is "
    "sent and its raw result returned. The command set is dynamic -- "
    "commands come and go -- so always run 'help' first to discover "
    "available commands and 'help <command>' for usage. Output format: "
    "'Exit code: N', followed by 'Output:' and 'Stderr:' sections. "
    "Typical commands may include vet, vision, holler, youtube, gobrow, "
    "archive, ai-rank, dbrowser-start."
)


def _socket_path() -> str:
    tmpdir = os.environ.get("TMP")
    if tmpdir:
        return os.path.join(tmpdir, "dtx-server.sock")
    return SOCKET_PATH


def _request(cmdline: str) -> str:
    """Send one dtx command line to the socket; return raw result text."""
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


def create_plugin(ctx):
    if env_bool("DTX_DISABLED"):
        return

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
        DTX_DESCRIPTION + " When calling as a tool, pass the full command line in 'command'.",
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

    ctx.register_command("dtx", dtx_command, DTX_DESCRIPTION)

    if env_bool("DEBUG"):
        print("  - dtx tool")
        print("  - /dtx command")