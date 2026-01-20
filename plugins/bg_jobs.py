"""
Background Jobs Plugin

Allows running long-lived background processes like web servers, databases, etc.
Provides both AI tool (bg_jobs) and user command (/bg-jobs) interfaces.

Features:
- Start background jobs with friendly names
- List running jobs
- Kill individual jobs or all jobs
- Auto-cleanup on AI Coder exit
- Process group management to prevent orphans
"""

import os
import subprocess
import signal
import shlex
import time
from datetime import datetime
from typing import Dict, Any, Optional, List

from aicoder.core.config import Config
from aicoder.utils.log import LogUtils


def create_plugin(ctx):
    """
    Background jobs plugin - manage long-running processes
    """

    # In-memory job storage
    # Key: pid, Value: {name, process, command, started_at}
    jobs: Dict[int, Dict[str, Any]] = {}

    def start_background_job(name: str, command: str) -> int:
        """Start a background job with proper process group handling"""
        # Start with new session/process group (like run_shell_command does)
        process = subprocess.Popen(
            ["bash", "-c", command],
            preexec_fn=os.setsid,  # Create new process group
            stdout=None,
            stderr=None,
        )

        # Store job info
        jobs[process.pid] = {
            "name": name,
            "process": process,
            "command": command,
            "started_at": datetime.now(),
        }

        return process.pid

    def kill_job(pid: int) -> bool:
        """Kill a background job and its entire process group"""
        if pid not in jobs:
            return False

        job = jobs[pid]

        try:
            # Kill entire process group (like run_shell_command does)
            os.killpg(os.getpgid(pid), signal.SIGTERM)
            time.sleep(0.5)  # Give it a moment to cleanup gracefully
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except ProcessLookupError:
            pass  # Process already dead
        except OSError:
            pass  # Other error, just continue

        # Wait for the process to finish
        job["process"].wait()

        # Remove from jobs dict
        del jobs[pid]
        return True

    def kill_all_jobs() -> int:
        """Kill all background jobs"""
        pids = list(jobs.keys())
        killed = 0
        for pid in pids:
            if kill_job(pid):
                killed += 1
        return killed

    def cleanup_dead_jobs() -> None:
        """Remove dead jobs from the jobs dict"""
        dead_pids = []
        for pid, job in jobs.items():
            if job["process"].poll() is not None:
                dead_pids.append(pid)

        for pid in dead_pids:
            del jobs[pid]

    def format_relative_time(dt: datetime) -> str:
        """Format a datetime as relative time (e.g., '2 minutes ago')"""
        delta = datetime.now() - dt
        seconds = int(delta.total_seconds())

        if seconds < 60:
            return "just now"
        elif seconds < 3600:
            minutes = seconds // 60
            return f"{minutes} minute(s) ago"
        elif seconds < 86400:
            hours = seconds // 3600
            return f"{hours} hour(s) ago"
        else:
            days = seconds // 86400
            return f"{days} day(s) ago"

    def format_absolute_time(dt: datetime) -> str:
        """Format a datetime as absolute time"""
        return dt.strftime("%Y-%m-%d %H:%M:%S")

    def format_time(dt: datetime) -> str:
        """Format a datetime as 'absolute (relative)'"""
        return f"{format_absolute_time(dt)} ({format_relative_time(dt)})"

    def format_bg_jobs_args(args: Dict[str, Any]) -> str:
        """Format arguments for bg_jobs tool approval"""
        lines = []
        action = args.get("action", "")
        lines.append(f"Action: {action}")
        
        if action == "run":
            name = args.get("name", "")
            command = args.get("command", "")
            lines.append(f"Name: {name}")
            lines.append(f"Command: {command}")
        elif action == "kill":
            pid = args.get("pid", "")
            lines.append(f"PID: {pid}")
        
        return "\n".join(lines)

    # ==================== Tool: bg_jobs ====================

    def bg_jobs_tool(args: Dict[str, Any]) -> Dict[str, Any]:
        """AI tool for background job management"""
        action = args.get("action")

        if action == "run":
            name = args.get("name")
            command = args.get("command")

            if not name or not command:
                return {
                    "tool": "bg_jobs",
                    "friendly": "Error: 'run' action requires 'name' and 'command'",
                    "detailed": "Missing required parameters for 'run' action"
                }

            # Clean up dead jobs first
            cleanup_dead_jobs()

            pid = start_background_job(name, command)
            return {
                "tool": "bg_jobs",
                "friendly": f"Started background job: {name} (pid: {pid})",
                "detailed": f"Background job started\nName: {name}\nPID: {pid}\nCommand: {command}"
            }

        elif action == "list":
            # Clean up dead jobs first
            cleanup_dead_jobs()

            if not jobs:
                return {
                    "tool": "bg_jobs",
                    "friendly": "No background jobs running",
                    "detailed": "No background jobs are currently running"
                }

            job_list = []
            for idx, (pid, job) in enumerate(jobs.items(), 1):
                job_list.append(f"{idx}) {job['name']} (pid: {pid})")

            job_info = "\n".join(job_list)
            return {
                "tool": "bg_jobs",
                "friendly": f"Found {len(jobs)} running background job(s)",
                "detailed": f"Background Jobs ({len(jobs)} running):\n\n{job_info}"
            }

        elif action == "kill":
            pid = args.get("pid")

            if not pid:
                return {
                    "tool": "bg_jobs",
                    "friendly": "Error: 'kill' action requires 'pid'",
                    "detailed": "Missing required parameter 'pid' for 'kill' action"
                }

            # Check if pid is a number
            try:
                pid = int(pid)
            except (ValueError, TypeError):
                return {
                    "tool": "bg_jobs",
                    "friendly": f"Error: Invalid pid: {pid}",
                    "detailed": f"PID must be a number, got: {pid}"
                }

            # Clean up dead jobs first
            cleanup_dead_jobs()

            if pid not in jobs:
                return {
                    "tool": "bg_jobs",
                    "friendly": f"Error: No running job with pid: {pid}",
                    "detailed": f"Cannot find running job with pid: {pid}"
                }

            job_name = jobs[pid]["name"]
            if kill_job(pid):
                return {
                    "tool": "bg_jobs",
                    "friendly": f"Killed background job: {job_name} (pid: {pid})",
                    "detailed": f"Successfully killed background job\nName: {job_name}\nPID: {pid}"
                }
            else:
                return {
                    "tool": "bg_jobs",
                    "friendly": f"Error: Failed to kill job with pid: {pid}",
                    "detailed": f"Failed to kill background job\nPID: {pid}"
                }

        elif action == "kill_all":
            # Clean up dead jobs first
            cleanup_dead_jobs()

            killed = kill_all_jobs()
            return {
                "tool": "bg_jobs",
                "friendly": f"Killed {killed} background job(s)",
                "detailed": f"Successfully killed {killed} background job(s)"
            }

        else:
            return {
                "tool": "bg_jobs",
                "friendly": f"Error: Unknown action: {action}",
                "detailed": f"Valid actions are: run, list, kill, kill_all"
            }

    # Register the bg_jobs tool
    ctx.register_tool(
        name="bg_jobs",
        fn=bg_jobs_tool,
        description="Manage background long-running processes (web servers, databases, etc.)",
        parameters={
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": ["run", "list", "kill", "kill_all"],
                    "description": "Action to perform"
                },
                "name": {
                    "type": "string",
                    "description": "Friendly name for the job (required for 'run' action)"
                },
                "command": {
                    "type": "string",
                    "description": "Bash command to run (required for 'run' action)"
                },
                "pid": {
                    "type": "integer",
                    "description": "Process ID to kill (required for 'kill' action)"
                }
            },
            "required": ["action"]
        },
        auto_approved=False,  # Killing jobs should require approval
        format_arguments=format_bg_jobs_args
    )

    # ==================== Command: /bg-jobs ====================

    def parse_pid_or_seq(identifier: str) -> Optional[int]:
        """Parse a pid or sequence number and return the actual pid"""
        if not identifier:
            return None

        # Try as a PID directly
        try:
            pid = int(identifier)
            if pid in jobs:
                return pid
        except ValueError:
            pass

        # Try as a sequence number (1-indexed)
        try:
            seq = int(identifier)
            if 1 <= seq <= len(jobs):
                # Get the pid at this sequence position
                job_list = list(jobs.items())
                return job_list[seq - 1][0]
        except ValueError:
            pass

        return None

    def handle_bg_jobs_command(args_str: str) -> None:
        """Handle /bg-jobs command"""
        # Use shlex to handle quotes properly
        args = shlex.split(args_str.strip()) if args_str.strip() else []

        if not args or args[0] == "help":
            LogUtils.print("""
Background Jobs Commands:
  /bg-jobs list              - List all running jobs
  /bg-jobs status <pid|seq>  - Show job details
  /bg-jobs kill <pid|seq>    - Kill a specific job
  /bg-jobs kill-all          - Kill all jobs
  /bg-jobs run <name> <cmd>  - Start a new background job

Examples:
  /bg-jobs list
  /bg-jobs status 1
  /bg-jobs kill 2312
  /bg-jobs kill-all
  /bg-jobs run Webserver "python -m http.server 8000"
""")
            return

        action = args[0].lower()

        # Clean up dead jobs first
        cleanup_dead_jobs()

        if action == "list":
            if not jobs:
                LogUtils.print(f"{Config.colors['yellow']}No background jobs running{Config.colors['reset']}")
            else:
                LogUtils.print(f"{Config.colors['brightGreen']}Background Jobs ({len(jobs)} running):{Config.colors['reset']}")
                for idx, (pid, job) in enumerate(jobs.items(), 1):
                    LogUtils.print(f"  [{idx}] {job['name']:<20} (pid: {pid})")

        elif action == "status":
            if len(args) < 2:
                LogUtils.print(f"{Config.colors['yellow']}Error: /bg-jobs status requires pid or sequence number{Config.colors['reset']}")
                return

            identifier = args[1]
            pid = parse_pid_or_seq(identifier)

            if pid is None or pid not in jobs:
                LogUtils.print(f"{Config.colors['yellow']}Error: No running job found: {identifier}{Config.colors['reset']}")
                return

            job = jobs[pid]
            LogUtils.print(f"""
{Config.colors['brightGreen']}Job: {job['name']}{Config.colors['reset']}
PID: {pid}
Status: running
Command: {job['command']}
Started: {format_time(job['started_at'])}
""")

        elif action == "kill":
            if len(args) < 2:
                LogUtils.print(f"{Config.colors['yellow']}Error: /bg-jobs kill requires pid or sequence number{Config.colors['reset']}")
                return

            identifier = args[1]
            pid = parse_pid_or_seq(identifier)

            if pid is None or pid not in jobs:
                LogUtils.print(f"{Config.colors['yellow']}Error: No running job found: {identifier}{Config.colors['reset']}")
                return

            job_name = jobs[pid]["name"]
            if kill_job(pid):
                LogUtils.print(f"{Config.colors['brightGreen']}Killed job: {job_name} (pid: {pid}){Config.colors['reset']}")
            else:
                LogUtils.print(f"{Config.colors['yellow']}Error: Failed to kill job: {job_name}{Config.colors['reset']}")

        elif action == "kill-all":
            killed = kill_all_jobs()
            LogUtils.print(f"{Config.colors['brightGreen']}Killed {killed} background job(s){Config.colors['reset']}")

        elif action == "run":
            if len(args) < 3:
                LogUtils.print(f"{Config.colors['yellow']}Error: /bg-jobs run requires name and command{Config.colors['reset']}")
                LogUtils.print(f"{Config.colors['dim']}Usage: /bg-jobs run <name> <command>{Config.colors['reset']}")
                return

            name = args[1]
            command = " ".join(args[2:])  # Everything after name is the command

            pid = start_background_job(name, command)
            LogUtils.print(f"{Config.colors['brightGreen']}Started job: {name} (pid: {pid}){Config.colors['reset']}")
            LogUtils.print(f"{Config.colors['dim']}Command: {command}{Config.colors['reset']}")

        else:
            LogUtils.print(f"{Config.colors['yellow']}Error: Unknown command: {action}{Config.colors['reset']}")
            LogUtils.print(f"{Config.colors['dim']}Use /bg-jobs help to see available commands{Config.colors['reset']}")

    # Register the /bg-jobs command
    ctx.register_command(
        "bg-jobs",
        handle_bg_jobs_command,
        "Manage background long-running processes"
    )

    # ==================== Cleanup ====================

    def cleanup_all_jobs() -> None:
        """Kill all background jobs on shutdown"""
        if jobs:
            killed = kill_all_jobs()
            LogUtils.print(f"[background_jobs] Killed {killed} background job(s) on shutdown")

    if Config.debug():
        LogUtils.print("[+] Background jobs plugin loaded")
        LogUtils.print("    - bg_jobs tool")
        LogUtils.print("    - /bg-jobs command")

    # Return cleanup handler
    return {"cleanup": cleanup_all_jobs}
