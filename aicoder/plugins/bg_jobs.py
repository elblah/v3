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
import atexit
import threading
from datetime import datetime
from typing import Dict, Any, Optional

from aicoder.core.config import Config
from aicoder.core.nudges import add_nudge
from aicoder.tools.internal.run_shell_command import resolve_command
from aicoder.utils.bool_utils import env_bool
from aicoder.utils.log import LogUtils, info, dim, warn, success, print

# Completion notification (env-gated: BG_JOBS_NOTIFY, default ON)
NOTIFY_TAG = "BG_JOBS"


def _should_notify(killed=False, notify=True):
    """Decide whether a finished job deserves a completion nudge.

    bg_jobs is for background work (slow compilations, servers, parallel
    tasks), so every job end is significant: default = notify. Silent only
    for explicit kills (the AI performed them itself and sees the 'killed'
    status in the kill result) and per-job opt-out (notify=false).
    """
    return not killed and notify


def create_plugin(ctx):
    """
    Background jobs plugin - manage long-running processes
    """

    # In-memory job storage
    # Key: pid, Value: {name, process, command, started_at, notify}
    jobs: Dict[int, Dict[str, Any]] = {}
    # Completed jobs history: [{name, command, started_at, ended_at, duration_seconds, pid, exit_code, killed, notify}]
    completed_jobs: list = []
    notify_enabled = env_bool("BG_JOBS_NOTIFY", default=True)
    # Archived jobs awaiting one batched nudge at the next context bar
    pending_notifications: list = []
    # Guards all mutation + iteration of storage above (reaper thread runs concurrently)
    _jobs_lock = threading.RLock()
    _reaper = None

    def _emit_running_count() -> None:
        """Fire on_bg_jobs_changed with the running-job count (wintitle tap)."""
        system = getattr(ctx.app, "plugin_system", None)
        if system:
            system.call_hooks("on_bg_jobs_changed", len(jobs))

    def start_background_job(name: str, command: str, notify: bool = True) -> int:
        """Start a background job with proper process group handling"""
        # Start with new session/process group (like run_shell_command does)
        # Redirect stdout/stderr to DEVNULL to prevent output appearing on screen
        # resolve_command applies the same seal hook as run_shell_command
        _, command_argv = resolve_command(command)
        process = subprocess.Popen(
            command_argv if command_argv is not None else ["bash", "-c", command],
            preexec_fn=os.setsid,  # Create new process group
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        # Store job info
        with _jobs_lock:
            jobs[process.pid] = {
                "name": name,
                "process": process,
                "command": command,
                "started_at": datetime.now(),
                "notify": notify,
            }
            _ensure_reaper()
            _emit_running_count()
        return process.pid

    def kill_job(pid: int, timeout: float = 2.0) -> bool:
        """Kill a background job and its entire process group"""
        with _jobs_lock:
            if pid not in jobs:
                return False
            job = jobs[pid]

        try:
            # Kill entire process group (like run_shell_command does)
            os.killpg(os.getpgid(pid), signal.SIGTERM)
            time.sleep(0.1)  # Brief moment for graceful cleanup
            os.killpg(os.getpgid(pid), signal.SIGKILL)
        except ProcessLookupError:
            pass  # Process already dead
        except OSError:
            pass  # Other error, just continue

        # Wait for the process to finish (with timeout to guarantee return)
        try:
            job["process"].wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            # Force kill didn't work, process may be in uninterruptible sleep
            # We can't do more - just mark it as done
            pass

        # Mark as killed so completion notification stays silent
        with _jobs_lock:
            if pid not in jobs:
                return False  # archived concurrently: job died before the kill
            job["killed"] = True
            archive_job(pid)
        return True

    def kill_all_jobs(timeout: float = 2.0) -> int:
        """Kill all background jobs"""
        with _jobs_lock:
            pids = list(jobs.keys())
        killed = 0
        for pid in pids:
            if kill_job(pid, timeout=timeout):
                killed += 1
        return killed

    def archive_job(pid: int) -> None:
        """Move a finished job from running to completed history"""
        with _jobs_lock:
            if pid not in jobs:
                return
            job = jobs[pid]
            ended_at = datetime.now()
            duration = int((ended_at - job["started_at"]).total_seconds())
            record = {
                "name": job["name"],
                "command": job["command"],
                "started_at": job["started_at"],
                "ended_at": ended_at,
                "duration_seconds": duration,
                "pid": pid,
                "exit_code": job["process"].returncode,
                "killed": job.get("killed", False),
                "notify": job.get("notify", True),
            }
            completed_jobs.append(record)
            pending_notifications.append(record)
            del jobs[pid]
            _emit_running_count()

    def cleanup_dead_jobs() -> None:
        """Move dead jobs from running to history"""
        with _jobs_lock:
            dead_pids = [
                pid for pid, job in jobs.items()
                if job["process"].poll() is not None
            ]
        for pid in dead_pids:
            archive_job(pid)

    _REAP_INTERVAL = float(os.environ.get("BG_JOBS_REAP_INTERVAL", "30"))

    def _reaper_loop() -> None:
        """Sweep dead jobs periodically while any job runs; exits when idle."""
        nonlocal _reaper
        while True:
            time.sleep(_REAP_INTERVAL)
            cleanup_dead_jobs()
            with _jobs_lock:
                if not jobs:
                    _reaper = None  # release ownership: next start re-spawns
                    return

    def _ensure_reaper() -> None:
        """Start the reaper thread once; next job start re-spawns it after exit."""
        nonlocal _reaper
        with _jobs_lock:
            if _reaper is not None:
                return
            _reaper = threading.Thread(
                target=_reaper_loop, name="bg-jobs-reaper", daemon=True)
            _reaper.start()

    def format_duration(seconds: int) -> str:
        """Format a duration in seconds to human-readable string"""
        if seconds < 60:
            return f"{seconds}s"
        elif seconds < 3600:
            return f"{seconds // 60}m {seconds % 60}s"
        elif seconds < 86400:
            return f"{seconds // 3600}h {(seconds % 3600) // 60}m"
        else:
            days = seconds // 86400
            return f"{days}d {format_duration(seconds % 86400)}"

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
            if args.get("notify", True) is False:
                lines.append("Notify: off")
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
            notify = args.get("notify", True) is not False

            if not name or not command:
                return {
                    "tool": "bg_jobs",
                    "friendly": "Error: 'run' action requires 'name' and 'command'",
                    "detailed": "Missing required parameters for 'run' action"
                }

            # Clean up dead jobs first
            cleanup_dead_jobs()

            pid = start_background_job(name, command, notify=notify)
            return {
                "tool": "bg_jobs",
                "friendly": f"Started background job: {name} (pid: {pid})",
                "detailed": f"Background job started\nName: {name}\nPID: {pid}\nCommand: {command}"
            }

        elif action == "list":
            # Clean up dead jobs first
            cleanup_dead_jobs()

            with _jobs_lock:
                job_snapshot = list(jobs.items())

            if not job_snapshot:
                return {
                    "tool": "bg_jobs",
                    "friendly": "No background jobs running",
                    "detailed": "No background jobs are currently running"
                }

            job_list = []
            for idx, (pid, job) in enumerate(job_snapshot, 1):
                uptime = int((datetime.now() - job["started_at"]).total_seconds())
                job_list.append(f"{idx}) {job['name']:<20} (pid: {pid}) — running {format_duration(uptime)}")

            job_info = "\n".join(job_list)
            return {
                "tool": "bg_jobs",
                "friendly": f"Found {len(job_snapshot)} running background job(s)",
                "detailed": f"Background Jobs ({len(job_snapshot)} running):\n\n{job_info}"
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

            with _jobs_lock:
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

        elif action == "history":
            if not completed_jobs:
                return {
                    "tool": "bg_jobs",
                    "friendly": "No completed jobs in history",
                    "detailed": "No background jobs have finished yet"
                }

            lines = []
            for i, j in enumerate(completed_jobs, 1):
                d = format_duration(j["duration_seconds"])
                lines.append(f"{i}) {j['name']:<20} (pid: {j['pid']}) — took {d}")

            return {
                "tool": "bg_jobs",
                "friendly": f"Found {len(completed_jobs)} completed job(s)",
                "detailed": f"Completed Jobs ({len(completed_jobs)}):\n\n" + "\n".join(lines)
            }

        else:
            return {
                "tool": "bg_jobs",
                "friendly": f"Error: Unknown action: {action}",
                "detailed": f"Valid actions are: run, list, kill, kill_all, history"
            }

    # Register the bg_jobs tool
    # Schema adapts to the gate: notify param exists only when notifications
    # are enabled (BG_JOBS_NOTIFY unset or != 0).
    tool_properties = {
        "action": {
            "type": "string",
            "enum": ["run", "list", "kill", "kill_all", "history"],
            "description": "Action to perform"
        },
        "name": {
            "type": "string",
            "description": "Friendly name for the job (required for 'run' action)"
        },
        "command": {
            "type": "string",
            "description": (
                "Bash command to run (required for 'run' action). "
                "NOTE: stdout/stderr are discarded. To capture output, "
                "redirect to files: 'cmd > out.log 2>&1'."
            )
        },
        "pid": {
            "type": "integer",
            "description": "Process ID to kill (required for 'kill' action)"
        },
    }
    if notify_enabled:
        tool_properties["notify"] = {
            "type": "boolean",
            "description": (
                "Notify the AI when this job ends (default true; "
                "set false to silence this job). Explicit kills are "
                "always silent (kill status returned in the kill result)."
            )
        }
    tool_description = (
        "Manage background long-running processes (web servers, databases, etc.). "
        "Use 'list' to see running jobs with uptime, 'history' to see finished jobs. "
        "IMPORTANT: stdout and stderr are discarded (sent to /dev/null). "
        "If you need to read the output, redirect it to files in the command, "
        "e.g.: 'mycommand > output.log 2>&1', then read the file later."
    )
    if not notify_enabled:
        tool_description += (
            " Completion notifications are disabled (BG_JOBS_NOTIFY=0); "
            "check 'list' or 'history' for job status."
        )

    ctx.register_tool(
        name="bg_jobs",
        fn=bg_jobs_tool,
        description=tool_description,
        parameters={
            "type": "object",
            "properties": tool_properties,
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

        with _jobs_lock:
            job_by_pid = dict(jobs)

        # Try as a PID directly
        try:
            pid = int(identifier)
            if pid in job_by_pid:
                return pid
        except ValueError:
            pass

        # Try as a sequence number (1-indexed)
        try:
            seq = int(identifier)
            if 1 <= seq <= len(job_by_pid):
                # Get the pid at this sequence position
                return list(job_by_pid)[seq - 1]
        except ValueError:
            pass

        return None

    def handle_bg_jobs_command(args_str: str) -> None:
        """Handle /bg-jobs command"""
        # Use shlex to handle quotes properly
        args = shlex.split(args_str.strip()) if args_str.strip() else []

        if not args or args[0] == "help":
            info("""
Background Jobs Commands:
  /bg-jobs list              - List all running jobs (with uptime)
  /bg-jobs status <pid|seq>  - Show job details
  /bg-jobs history           - List completed jobs (with duration)
  /bg-jobs kill <pid|seq>    - Kill a specific job
  /bg-jobs kill-all          - Kill all jobs
  /bg-jobs run <name> <cmd>  - Start a new background job

Examples:
  /bg-jobs list
  /bg-jobs status 1
  /bg-jobs history
  /bg-jobs kill 2312
  /bg-jobs kill-all
  /bg-jobs run Webserver "python -m http.server 8000"
""")
            return

        action = args[0].lower()

        # Clean up dead jobs first
        cleanup_dead_jobs()

        if action == "list":
            with _jobs_lock:
                job_snapshot = list(jobs.items())
            if not job_snapshot:
                warn("No background jobs running")
            else:
                success(f"Background Jobs ({len(job_snapshot)} running):")
                for idx, (pid, job) in enumerate(job_snapshot, 1):
                    uptime = int((datetime.now() - job["started_at"]).total_seconds())
                    print(f"  [{idx}] {job['name']:<20} (pid: {pid}) — running {format_duration(uptime)}")

        elif action == "status":
            if len(args) < 2:
                warn("/bg-jobs status requires pid or sequence number")
                return

            identifier = args[1]
            pid = parse_pid_or_seq(identifier)

            if pid is None:
                warn(f"No running job found: {identifier}")
                return

            with _jobs_lock:
                if pid not in jobs:
                    warn(f"No running job found: {identifier}")
                    return
                job = {
                    "name": jobs[pid]["name"],
                    "command": jobs[pid]["command"],
                    "started_at": jobs[pid]["started_at"],
                }
            uptime = int((datetime.now() - job["started_at"]).total_seconds())
            info(f"""
Job: {job['name']}
PID: {pid}
Status: running (uptime: {format_duration(uptime)})
Command: {job['command']}
Started: {format_time(job['started_at'])}
""")

        elif action == "kill":
            if len(args) < 2:
                warn("/bg-jobs kill requires pid or sequence number")
                return

            identifier = args[1]
            pid = parse_pid_or_seq(identifier)

            with _jobs_lock:
                if pid is None or pid not in jobs:
                    warn(f"No running job found: {identifier}")
                    return
                job_name = jobs[pid]["name"]
            if kill_job(pid):
                success(f"Killed job: {job_name} (pid: {pid})")
            else:
                warn(f"Failed to kill job: {job_name}")

        elif action == "kill-all":
            killed = kill_all_jobs()
            success(f"Killed {killed} background job(s)")

        elif action == "run":
            if len(args) < 3:
                warn("/bg-jobs run requires name and command")
                dim("Usage: /bg-jobs run <name> <command>")
                return

            name = args[1]
            command = " ".join(args[2:])  # Everything after name is the command

            pid = start_background_job(name, command)
            success(f"Started job: {name} (pid: {pid})")
            dim(f"Command: {command}")

        elif action == "history":
            if not completed_jobs:
                dim("No completed jobs in history")
                return
            success(f"Completed Jobs ({len(completed_jobs)}):")
            for i, j in enumerate(completed_jobs, 1):
                print(f"  [{i}] {j['name']:<20} (pid: {j['pid']}) — took {format_duration(j['duration_seconds'])}")

        else:
            warn(f"Unknown command: {action}")
            dim("Use /bg-jobs help to see available commands")

    # Register the /bg-jobs command
    ctx.register_command(
        "bg-jobs",
        handle_bg_jobs_command,
        "Manage background long-running processes"
    )

    # ==================== Context bar ====================

    def on_context_bar():
        """Hook: show running job count in context bar"""
        cleanup_dead_jobs()  # prune finished jobs (cheap poll, no subprocess)
        # One batched completion nudge per turn for jobs archived since last bar
        with _jobs_lock:
            notifications = list(pending_notifications)
            pending_notifications.clear()
        if notifications:
            lines = []
            if notify_enabled:
                for rec in notifications:
                    if _should_notify(killed=rec["killed"], notify=rec["notify"]):
                        code = rec["exit_code"]
                        if code is None:
                            status = "ended"
                        elif code < 0:
                            status = f"killed by signal {-code}"
                        elif code == 0:
                            status = "finished"
                        else:
                            status = f"exited with code {code}"
                        lines.append(
                            f"- {rec['name']} (pid {rec['pid']}): {status} "
                            f"after {format_duration(rec['duration_seconds'])}"
                        )
            if lines:
                add_nudge(ctx.app, NOTIFY_TAG,
                          "The following background job(s) finished:\n\n"
                          + "\n".join(lines))
        # Self-heal the wintitle on every bar render: fixes stale suffix when
        # a push event (reaper emit) had no effect while parked at the input.
        with _jobs_lock:
            _emit_running_count()
        if not jobs:
            return None
        return f"{Config.colors['yellow']}{Config.colors['bold']}bg:{len(jobs)}{Config.colors['reset']}"

    ctx.register_hook("on_context_bar", on_context_bar)

    # ==================== Cleanup ====================

    def cleanup_all_jobs() -> None:
        """Kill all background jobs on shutdown - guaranteed to complete"""
        if jobs:
            # Use short timeout during cleanup to ensure we don't hang on exit
            killed = kill_all_jobs(timeout=0.5)
            LogUtils.print(f"[background_jobs] Killed {killed} background job(s) on shutdown")

    # Register atexit handler to ensure cleanup on any exit
    atexit.register(cleanup_all_jobs)

    if Config.debug():
        LogUtils.print("[+] Background jobs plugin loaded")
        LogUtils.print("    - bg_jobs tool")
        LogUtils.print("    - /bg-jobs command")
        LogUtils.print("    - on_context_bar hook (running job count)")
        LogUtils.print("    - on_bg_jobs_changed event (count changes → tmux wintitle)")

    # Return cleanup handler (for plugin system integration)
    return {"cleanup": cleanup_all_jobs}
