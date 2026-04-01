"""
Timeit Plugin

Tracks time per task and since session start.
Commands:
  /timeit start [name]  - Start tracking a task
  /timeit stop          - Stop current task, print elapsed
  /timeit stats         - Show current session stats
  /timeit history       - Show task history
  /timeit reset         - Clear history
  /timeit               - Toggle display (on/off)

Also prints a dimmed timing line before each user/AI prompt when enabled.
"""

import time
from aicoder.core.config import Config
from aicoder.utils.log import LogUtils
from aicoder.utils.shell_utils import execute_command_sync


def create_plugin(ctx):
    """Plugin entry point"""

    # Session start time
    session_start = time.time()

    # Display toggle
    display_enabled = False

    # Current task state
    current_task = None  # None means no task tracking
    task_start = 0
    task_name = ""
    task_count = 0

    # Completed tasks history
    task_history = []

    # Accumulated API time for task and session
    task_api_time_sum = 0
    session_api_time_baseline = 0
    task_turn_start_api_counter = 0

    def fmt_duration(seconds):
        """Format seconds into human readable duration"""
        seconds = max(0, seconds)
        if seconds < 60:
            return f"{int(seconds)}s"
        mins = int(seconds // 60)
        secs = int(seconds % 60)
        if mins < 60:
            return f"{mins}m{secs}s"
        hours = mins // 60
        mins = mins % 60
        return f"{hours}h{mins}m{secs}s"

    def get_task_elapsed():
        """Get elapsed time for current task"""
        if not current_task:
            return 0
        return time.time() - task_start

    def get_session_elapsed():
        """Get elapsed time since aicoder started"""
        return time.time() - session_start

    def get_task_api_time():
        """Get API time spent on current task"""
        stats = ctx.app.stats
        if not stats or not current_task:
            return 0
        return (stats.api_time_spent - task_api_time_sum)

    def get_stats():
        """Get a stats reference"""
        return ctx.app.stats

    def print_timing_line():
        """Print a dimmed timing line before each interaction"""
        elapsed = get_session_elapsed()
        if current_task:
            task_elapsed = get_task_elapsed()
            task_api = get_task_api_time()
            api_str = f"api:{fmt_duration(task_api)}"
            line = f"[{task_name}] {fmt_duration(task_elapsed)} ({api_str}) | Session: {fmt_duration(elapsed)}"
        elif display_enabled:
            line = f"Session: {fmt_duration(elapsed)}"
        else:
            return  # No task and display off — stay quiet

        LogUtils.print(f"{Config.colors['dim']}\u23f1  {line}{Config.colors['reset']}")

    def handle_timeit_command(args_raw):
        """Handle /timeit command"""
        nonlocal current_task, task_start, task_name, task_count, task_history
        nonlocal display_enabled, task_api_time_sum

        args = args_raw.strip().split() if args_raw else []
        action = args[0] if args else ""
        rest = " ".join(args[1:]).strip()

        if action == "" or action == "status":
            # Show current status
            elapsed = get_session_elapsed()
            if current_task:
                task_elapsed = get_task_elapsed()
                task_api = get_task_api_time()
                LogUtils.print(
                    f"{Config.colors['cyan']}Current task:{Config.colors['reset']} "
                    f"{Config.colors['yellow']}{task_name}{Config.colors['reset']} "
                    f"- {fmt_duration(task_elapsed)} elapsed, {fmt_duration(task_api)} API time"
                )
            else:
                LogUtils.print(f"{Config.colors['dim']}No active task tracking{Config.colors['reset']}")
            display = f"{Config.colors['green']}ON{Config.colors['reset']}" if display_enabled else f"{Config.colors['dim']}OFF{Config.colors['reset']}"
            LogUtils.print(f"Display: {display}")
            LogUtils.print(f"Session total: {fmt_duration(elapsed)}")

        elif action == "start":
            # Auto-stop any running task before starting a new one
            if current_task:
                elapsed = get_task_elapsed()
                task_api = get_task_api_time()
                total = elapsed
                rest_time = total - task_api
                task_history.append({
                    "name": task_name,
                    "total": elapsed,
                    "api": task_api,
                    "rest": rest_time,
                })
                LogUtils.print(f"{Config.colors['yellow']}[!] Auto-stopped previous task:{Config.colors['reset']} {Config.colors['dim']}{task_name}{Config.colors['reset']} ({fmt_duration(elapsed)})")
            name = rest if rest else f"task-{task_count + 1}"
            current_task = name
            task_name = name
            task_start = time.time()
            task_count += 1
            stats = get_stats()
            task_api_time_sum = stats.api_time_spent if stats else 0
            LogUtils.print(f"{Config.colors['green']}[+] Started tracking:{Config.colors['reset']} {Config.colors['yellow']}{name}{Config.colors['reset']}")

        elif action == "stop":
            if not current_task:
                LogUtils.print(f"{Config.colors['yellow']}No active task to stop{Config.colors['reset']}")
                return
            elapsed = get_task_elapsed()
            task_api = get_task_api_time()
            total = elapsed
            rest_time = total - task_api
            task_history.append({
                "name": task_name,
                "total": elapsed,
                "api": task_api,
                "rest": rest_time,
            })
            LogUtils.print(f"{Config.colors['green']}[+] Stopped task:{Config.colors['reset']} {Config.colors['yellow']}{task_name}{Config.colors['reset']}")
            LogUtils.print(f"    Total: {fmt_duration(elapsed)} | API: {fmt_duration(task_api)} | Rest: {fmt_duration(rest_time)}")
            current_task = None
            task_name = ""
            task_start = 0
            task_api_time_sum = 0

        elif action == "stats":
            elapsed = get_session_elapsed()
            stats = get_stats()
            api_total = stats.api_time_spent if stats else 0
            rest = elapsed - api_total
            LogUtils.print(f"{Config.colors['cyan']}=== Timeit Stats ==={Config.colors['reset']}")
            LogUtils.print(f"Session: {fmt_duration(elapsed)}")
            LogUtils.print(f"  AI working: {fmt_duration(api_total)} ({int(api_total/elapsed*100) if elapsed > 0 else 0}%)")
            LogUtils.print(f"  Other:      {fmt_duration(rest)} ({int(rest/elapsed*100) if elapsed > 0 else 0}%)")
            if current_task:
                task_elapsed = get_task_elapsed()
                task_api = get_task_api_time()
                LogUtils.print(f"Current task: {Config.colors['yellow']}{task_name}{Config.colors['reset']}")
                LogUtils.print(f"  Elapsed: {fmt_duration(task_elapsed)} | API: {fmt_duration(task_api)}")
            if task_history:
                LogUtils.print(f"Completed tasks: {len(task_history)}")
                total_completed = sum(t["total"] for t in task_history)
                LogUtils.print(f"  Total tracked: {fmt_duration(total_completed)}")

        elif action == "history":
            if not task_history:
                LogUtils.print(f"{Config.colors['dim']}No completed tasks{Config.colors['reset']}")
                return
            LogUtils.print(f"{Config.colors['cyan']}=== Task History ==={Config.colors['reset']}")
            for i, t in enumerate(task_history, 1):
                api_pct = int(t["api"] / t["total"] * 100) if t["total"] > 0 else 0
                LogUtils.print(
                    f"  {i}. {Config.colors['yellow']}{t['name']}{Config.colors['reset']} "
                    f"- {fmt_duration(t['total'])} (api: {fmt_duration(t['api'])}, {api_pct}%)"
                )
            total_tracked = sum(t["total"] for t in task_history)
            LogUtils.print(f"  Total: {len(task_history)} tasks, {fmt_duration(total_tracked)} tracked")

        elif action == "reset":
            task_history.clear()
            task_count = 0
            LogUtils.print(f"{Config.colors['green']}[+] Timeit history cleared{Config.colors['reset']}")

        else:
            # Toggle display on/off if no args
            if action in ("on", "enable"):
                display_enabled = True
                LogUtils.print(f"{Config.colors['green']}[+] Timing display: ON{Config.colors['reset']}")
            elif action in ("off", "disable"):
                display_enabled = False
                LogUtils.print(f"{Config.colors['dim']}[-] Timing display: OFF{Config.colors['reset']}")
            elif action == "help" or action not in ("start", "stop", "stats", "history", "reset"):
                LogUtils.print(f"{Config.colors['cyan']}=== /timeit Commands ==={Config.colors['reset']}")
                LogUtils.print("  /timeit              - Show current status")
                LogUtils.print("  /timeit start [name] - Start tracking a task")
                LogUtils.print("  /timeit stop          - Stop current task, show time")
                LogUtils.print("  /timeit stats         - Show session stats")
                LogUtils.print("  /timeit history       - Show task history")
                LogUtils.print("  /timeit reset         - Clear history")
                LogUtils.print("  /timeit [on|off]      - Toggle prompt timing line")

        # Show the timing line after command output if display is on
        if display_enabled:
            print_timing_line()

    # Hook before user prompt - timing line
    def _before_prompt_hook():
        if current_task or display_enabled:
            print_timing_line()

    ctx.register_hook("before_user_prompt", _before_prompt_hook)

    # Hook before AI processing - timing line right after submit
    def _before_ai_hook():
        if current_task or display_enabled:
            print_timing_line()

    ctx.register_hook("before_ai_processing", _before_ai_hook)

    # Register the /timeit command
    ctx.register_command("timeit", handle_timeit_command, "Time tracking for tasks")

    return {}
