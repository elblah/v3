"""Secretary mode: coordinate AICoder workers through the workplace tool."""

import base64
import os
import subprocess
from typing import Any

SECRETARY_INSTRUCTIONS = """
You are operating as the user's secretary for coordinating AICoder workers.

Use the workplace tool for worker coordination. The user remains the decision
maker: do not silently create, stop, or redirect workers. Give workers clear,
bounded goals, inspect their results, and verify completion before reporting it.
Prefer one worker per independent task. Avoid unnecessary status polling.

Before `create_worker`, ensure name, role, project, and goal are all present. If
project is missing, ask the user; never retry the same call with guessed or
missing fields. Do not pass name to `list_workers` or `overview`. Only capture
or message a worker while it is running. A stopped worker has no retrievable
screen through this tool; report that clearly instead of repeatedly retrying.

You may inspect and modify project files with the tools available to you. Keep
coordination concise and summarize concrete worker results for the user.
""".strip()

SECRETARY_SKILL = """---
name: secretary
description: >
  Practical guidance for coordinating AICoder workers with the workplace tool.
---

# Secretary workflow

The user decides what work should be delegated. Coordinate workers; do not
silently expand their goals or create autonomous work.

## Delegation

- Use one worker for each independent task.
- Give the worker a specific role, project directory, goal, and stopping
  condition.
- Ask for changed files, tests run, and unresolved issues in the result.

## Monitoring

- Use `overview` before deciding what needs attention.
- Use `capture_worker_screen` when a worker's current state or result matters.
- A worker waiting for input is ready for a bounded follow-up.
- Do not repeatedly poll an active worker without a reason.

## Reporting

Do not claim work is complete based only on a worker's claim. Inspect files or
run the relevant checks when verification matters. Report worker identity,
concrete results, verification performed, and remaining problems.
"""

ACTIONS = (
    "list_workers",
    "overview",
    "create_worker",
    "capture_worker_screen",
    "send_worker",
    "stop_worker",
)


def _encoded(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise ValueError(f"{field} must be a non-empty string")
    return base64.b64encode(value.encode()).decode()


def create_plugin(ctx):
    if os.environ.get("SECRETARY") != "1":
        return

    tmpdir = os.environ.get("TMP")
    if not tmpdir:
        raise RuntimeError("TMP must point to the DTX socket directory")
    socket_path = os.path.join(tmpdir, "dtx-server.sock")

    def workplace(args: dict) -> dict:
        if not isinstance(args, dict):
            raise TypeError("workplace arguments must be an object")

        action = args.get("action")
        if action not in ACTIONS:
            raise ValueError(f"action must be one of: {', '.join(ACTIONS)}")

        request = ["workplace", action]
        if action == "create_worker":
            for field in ("name", "role", "project", "goal"):
                if field not in args:
                    raise ValueError(f"{field} is required for {action}")
            request.extend([
                args["name"],
                _encoded(args["role"], "role"),
                args["project"],
                _encoded(args["goal"], "goal"),
            ])
        elif action in ("capture_worker_screen", "send_worker", "stop_worker"):
            name = args.get("name")
            if not isinstance(name, str) or not name:
                raise ValueError(f"name is required for {action}")
            request.append(name)
            if action == "send_worker":
                request.append(_encoded(args.get("message"), "message"))
        elif action in ("list_workers", "overview"):
            unexpected = set(args) - {"action"}
            if unexpected:
                raise ValueError(f"unexpected arguments: {', '.join(sorted(unexpected))}")

        result = subprocess.run(
            ["nc", "-N", "-U", socket_path],
            input=" ".join(request) + "\n",
            text=True,
            capture_output=True,
            timeout=300,
            check=False,
        )
        if result.returncode != 0:
            detail = result.stderr.strip() or "workplace request failed"
            raise RuntimeError(detail)

        output = result.stdout
        return {"tool": "workplace", "friendly": output, "detailed": output}

    ctx.register_tool(
        "workplace",
        workplace,
        "Coordinate AICoder workers. Inspect, create, direct, and stop workers.",
        {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": list(ACTIONS),
                    "description": "The worker operation to perform.",
                },
                "name": {
                    "type": "string",
                    "description": "Worker name, which is also its ID.",
                },
                "role": {
                    "type": "string",
                    "description": "Worker role, used when creating a worker.",
                },
                "project": {
                    "type": "string",
                    "description": "Project directory where the worker starts.",
                },
                "goal": {
                    "type": "string",
                    "description": "Bounded worker goal, used when creating a worker.",
                },
                "message": {
                    "type": "string",
                    "description": "Instruction to send to a worker.",
                },
            },
            "required": ["action"],
        },
    )

    def on_system_prompt_append():
        return SECRETARY_INSTRUCTIONS

    def on_internal_skills():
        return {
            "secretary": {
                "description": (
                    "Practical guidance for coordinating AICoder workers."
                ),
                "files": {"SKILL.md": SECRETARY_SKILL},
            }
        }

    ctx.register_hook("on_system_prompt_append", on_system_prompt_append)
    ctx.register_hook("on_internal_skills", on_internal_skills)

    if os.environ.get("DEBUG") == "1":
        print("  - workplace tool")
        print("  - secretary system instructions")
        print("  - secretary internal skill")