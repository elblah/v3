"""
Tasks Plugin - Simple task tracking for long autonomous sessions

Inspired by Claude Code's task system, this plugin provides:
- Persistent task storage in .aicoder/tasks.json
- AI tools to create, update, list, and complete tasks
- User commands to view task status
- Optional pending tasks display before prompt

This helps maintain the "harness" - external state that keeps AI focused
on what it's doing, reducing drift during long sessions.

Tools:
- add_task: Create a new task (AI callable)
- update_task: Change task status (AI callable)
- list_tasks: Show all tasks (AI callable)
- delete_task: Remove a task (AI callable)

Commands:
- /tasks - Show all tasks
- /task <id> - Show task details
- /task done <id> - Mark task as completed
- /task cancel <id> - Mark task as cancelled

Storage:
- .aicoder/tasks.json - Persistent task storage
"""

import os
import json
from typing import Dict, Any, Optional, List

from aicoder.core.config import Config
from aicoder.utils.log import LogUtils


# Task statuses
STATUS_PENDING = "pending"
STATUS_IN_PROGRESS = "in_progress"
STATUS_COMPLETED = "completed"
STATUS_CANCELLED = "cancelled"

VALID_STATUSES = [STATUS_PENDING, STATUS_IN_PROGRESS, STATUS_COMPLETED, STATUS_CANCELLED]


class TaskStore:
    """Simple task storage using JSON file"""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.tasks: List[Dict[str, Any]] = []
        self._load()

    def _load(self):
        """Load tasks from JSON file"""
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, 'r') as f:
                    self.tasks = json.load(f)
            except Exception as e:
                LogUtils.error(f"[tasks] Failed to load tasks: {e}")
                self.tasks = []
        else:
            self.tasks = []

    def _save(self):
        """Save tasks to JSON file"""
        try:
            # Ensure directory exists
            os.makedirs(os.path.dirname(self.filepath), exist_ok=True)
            with open(self.filepath, 'w') as f:
                json.dump(self.tasks, f, indent=2)
        except Exception as e:
            LogUtils.error(f"[tasks] Failed to save tasks: {e}")

    def add(self, subject: str, description: str = "") -> int:
        """Add a new task, returns task ID"""
        task_id = len(self.tasks) + 1
        task = {
            "id": task_id,
            "subject": subject,
            "description": description,
            "status": STATUS_PENDING,
        }
        self.tasks.append(task)
        self._save()
        return task_id

    def update(self, task_id: int, **kwargs) -> bool:
        """Update task fields, returns True if task exists"""
        for task in self.tasks:
            if task["id"] == task_id:
                task.update(kwargs)
                self._save()
                return True
        return False

    def delete(self, task_id: int) -> bool:
        """Delete a task, returns True if task existed"""
        for i, task in enumerate(self.tasks):
            if task["id"] == task_id:
                del self.tasks[i]
                self._save()
                return True
        return False

    def get(self, task_id: int) -> Optional[Dict[str, Any]]:
        """Get a task by ID"""
        for task in self.tasks:
            if task["id"] == task_id:
                return task
        return None

    def list_all(self) -> List[Dict[str, Any]]:
        """Get all tasks"""
        return self.tasks.copy()

    def list_by_status(self, status: str) -> List[Dict[str, Any]]:
        """Get tasks by status"""
        return [t for t in self.tasks if t["status"] == status]

    def clear_all(self):
        """Delete all tasks"""
        self.tasks = []
        self._save()


def create_plugin(ctx):
    """Task tracking plugin for maintaining focus during long sessions"""

    # Task storage in closure
    TASKS_FILE = ".aicoder/tasks.json"
    store = TaskStore(TASKS_FILE)

    # Configuration
    show_pending_in_prompt = True  # Show pending tasks before user prompt

    def format_task(task: Dict[str, Any], verbose: bool = False) -> str:
        """Format a task for display"""
        status_symbol = {
            STATUS_PENDING: "[ ]",
            STATUS_IN_PROGRESS: "[->]",
            STATUS_COMPLETED: "[✓]",
            STATUS_CANCELLED: "[✗]",
        }
        symbol = status_symbol.get(task["status"], "[?]")

        result = f"{symbol} #{task['id']}: {task['subject']}"

        if verbose and task.get("description"):
            result += f"\n    {task['description']}"

        return result

    def add_task(args: Dict[str, Any]) -> Dict[str, Any]:
        """Add a new task"""
        subject = args.get("subject", "").strip()
        description = args.get("description", "").strip()

        if not subject:
            return {
                "tool": "add_task",
                "friendly": "Error: Subject cannot be empty",
                "detailed": "Cannot create task without a subject",
            }

        task_id = store.add(subject, description)

        return {
            "tool": "add_task",
            "friendly": f"Created task #{task_id}: {subject}",
            "detailed": f"Task created:\n{format_task(store.get(task_id), verbose=True)}",
        }

    def update_task(args: Dict[str, Any]) -> Dict[str, Any]:
        """Update task status or fields"""
        task_id = args.get("task_id")
        status = args.get("status", "").strip()
        subject = args.get("subject", "").strip()
        description = args.get("description", "").strip()

        if not task_id:
            return {
                "tool": "update_task",
                "friendly": "Error: Task ID required",
                "detailed": "Must specify task_id to update",
            }

        # Build update dict
        updates = {}
        if status:
            if status not in VALID_STATUSES:
                return {
                    "tool": "update_task",
                    "friendly": f"Error: Invalid status '{status}'",
                    "detailed": f"Valid statuses: {', '.join(VALID_STATUSES)}",
                }
            updates["status"] = status
        if subject:
            updates["subject"] = subject
        if description:
            updates["description"] = description

        if not updates:
            return {
                "tool": "update_task",
                "friendly": "Error: Nothing to update",
                "detailed": "Specify status, subject, or description to update",
            }

        if store.update(task_id, **updates):
            task = store.get(task_id)
            return {
                "tool": "update_task",
                "friendly": f"Updated task #{task_id}",
                "detailed": f"Task updated:\n{format_task(task, verbose=True)}",
            }

        return {
            "tool": "update_task",
            "friendly": f"Error: Task #{task_id} not found",
            "detailed": f"Task with ID {task_id} does not exist",
        }

    def list_tasks(args: Dict[str, Any]) -> Dict[str, Any]:
        """List all tasks, optionally filtered by status"""
        status = args.get("status", "").strip()

        if status:
            if status not in VALID_STATUSES:
                return {
                    "tool": "list_tasks",
                    "friendly": f"Error: Invalid status '{status}'",
                    "detailed": f"Valid statuses: {', '.join(VALID_STATUSES)}",
                }
            tasks = store.list_by_status(status)
        else:
            tasks = store.list_all()

        if not tasks:
            status_msg = f" ({status})" if status else ""
            return {
                "tool": "list_tasks",
                "friendly": f"No tasks found{status_msg}",
                "detailed": "No tasks to display",
            }

        # Format all tasks
        lines = [format_task(t, verbose=True) for t in tasks]
        status_msg = f" ({status})" if status else ""
        count = len(tasks)

        return {
            "tool": "list_tasks",
            "friendly": f"{count} task(s){status_msg}",
            "detailed": f"Tasks{status_msg}:\n\n" + "\n\n".join(lines),
        }

    def delete_task(args: Dict[str, Any]) -> Dict[str, Any]:
        """Delete a task"""
        task_id = args.get("task_id")

        if not task_id:
            return {
                "tool": "delete_task",
                "friendly": "Error: Task ID required",
                "detailed": "Must specify task_id to delete",
            }

        task = store.get(task_id)
        if not task:
            return {
                "tool": "delete_task",
                "friendly": f"Error: Task #{task_id} not found",
                "detailed": f"Task with ID {task_id} does not exist",
            }

        if store.delete(task_id):
            return {
                "tool": "delete_task",
                "friendly": f"Deleted task #{task_id}: {task['subject']}",
                "detailed": f"Task removed: {format_task(task)}",
            }

        return {
            "tool": "delete_task",
            "friendly": f"Error: Failed to delete task #{task_id}",
            "detailed": "Unknown error deleting task",
        }

    def clear_all_tasks(args: Dict[str, Any]) -> Dict[str, Any]:
        """Clear all tasks"""
        count = len(store.list_all())
        store.clear_all()

        return {
            "tool": "clear_all_tasks",
            "friendly": f"Cleared {count} task(s)",
            "detailed": f"All {count} tasks have been deleted",
        }

    # ===== Commands =====

    def handle_tasks_command(args_str: str) -> str:
        """Handle /tasks command"""
        parts = args_str.strip().split()

        # Handle /tasks clear
        if parts and parts[0] == "clear":
            count = len(store.list_all())
            store.clear_all()
            return f"Cleared {count} task(s). Ready for new tasks."

        tasks = store.list_all()

        if not tasks:
            return "No tasks. Use add_task tool to create tasks."

        # Count by status
        pending = store.list_by_status(STATUS_PENDING)
        in_progress = store.list_by_status(STATUS_IN_PROGRESS)
        completed = store.list_by_status(STATUS_COMPLETED)
        cancelled = store.list_by_status(STATUS_CANCELLED)

        lines = [
            f"Tasks: {len(tasks)} total",
            f"  [ ] Pending: {len(pending)}",
            f"  [->] In Progress: {len(in_progress)}",
            f"  [✓] Completed: {len(completed)}",
            f"  [✗] Cancelled: {len(cancelled)}",
            "",
            "Commands:",
            "  /tasks - Show this summary",
            "  /tasks clear - Delete all tasks",
            "  /task <id> - Show task details",
            "  /task done <id> - Mark as completed",
            "  /task cancel <id> - Mark as cancelled",
        ]

        if pending:
            lines.append("\nPending tasks:")
            for task in pending:
                lines.append(f"  {format_task(task)}")

        if in_progress:
            lines.append("\nIn progress:")
            for task in in_progress:
                lines.append(f"  {format_task(task)}")

        return "\n".join(lines)

    def handle_task_command(args_str: str) -> str:
        """Handle /task command"""
        parts = args_str.strip().split()

        if not parts:
            # Show all tasks
            return handle_tasks_command("")

        # Parse command
        action = parts[0]

        if action == "done" and len(parts) >= 2:
            task_id = int(parts[1])
            task = store.get(task_id)
            if not task:
                return f"Task #{task_id} not found"

            store.update(task_id, status=STATUS_COMPLETED)
            return f"Marked task #{task_id} as completed: {task['subject']}"

        elif action == "cancel" and len(parts) >= 2:
            task_id = int(parts[1])
            task = store.get(task_id)
            if not task:
                return f"Task #{task_id} not found"

            store.update(task_id, status=STATUS_CANCELLED)
            return f"Cancelled task #{task_id}: {task['subject']}"

        else:
            # Show task details
            try:
                task_id = int(action)
            except ValueError:
                return f"Usage: /task <id> | /task done <id> | /task cancel <id>"

            task = store.get(task_id)
            if not task:
                return f"Task #{task_id} not found"

            lines = [
                f"Task #{task['id']}",
                f"Status: {task['status']}",
                f"Subject: {task['subject']}",
            ]
            if task.get("description"):
                lines.append(f"Description: {task['description']}")
            return "\n".join(lines)

    # ===== Hooks =====

    def before_user_prompt() -> Optional[str]:
        """Show pending tasks before user prompt"""
        if not show_pending_in_prompt:
            return None

        pending = store.list_by_status(STATUS_PENDING)
        in_progress = store.list_by_status(STATUS_IN_PROGRESS)

        if not pending and not in_progress:
            return None

        lines = []
        if in_progress:
            lines.append("[Tasks - In Progress]")
            for task in in_progress:
                lines.append(f"  {format_task(task)}")
        if pending:
            if in_progress:
                lines.append("")
            lines.append("[Tasks - Pending]")
            for task in pending[:5]:  # Show max 5 pending
                lines.append(f"  {format_task(task)}")
            if len(pending) > 5:
                lines.append(f"  ... and {len(pending) - 5} more")

        return "\n" + "\n".join(lines) + "\n"

    # ===== Register everything =====

    # Tools for AI
    ctx.register_tool(
        name="add_task",
        fn=add_task,
        description="Create a new task to track work",
        parameters={
            "type": "object",
            "properties": {
                "subject": {
                    "type": "string",
                    "description": "Brief task title (imperative form, e.g., 'Fix authentication bug')"
                },
                "description": {
                    "type": "string",
                    "description": "Detailed task description with context and acceptance criteria"
                }
            },
            "required": ["subject"]
        },
        auto_approved=True
    )

    ctx.register_tool(
        name="update_task",
        fn=update_task,
        description="Update task status, subject, or description",
        parameters={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "integer",
                    "description": "ID of the task to update"
                },
                "status": {
                    "type": "string",
                    "enum": VALID_STATUSES,
                    "description": f"New status: {', '.join(VALID_STATUSES)}"
                },
                "subject": {
                    "type": "string",
                    "description": "New task title"
                },
                "description": {
                    "type": "string",
                    "description": "New task description"
                }
            },
            "required": ["task_id"]
        },
        auto_approved=True
    )

    ctx.register_tool(
        name="list_tasks",
        fn=list_tasks,
        description="List all tasks, optionally filtered by status",
        parameters={
            "type": "object",
            "properties": {
                "status": {
                    "type": "string",
                    "enum": VALID_STATUSES,
                    "description": f"Filter by status: {', '.join(VALID_STATUSES)}"
                }
            }
        },
        auto_approved=True
    )

    ctx.register_tool(
        name="delete_task",
        fn=delete_task,
        description="Delete a task by ID",
        parameters={
            "type": "object",
            "properties": {
                "task_id": {
                    "type": "integer",
                    "description": "ID of the task to delete"
                }
            },
            "required": ["task_id"]
        },
        auto_approved=True
    )

    ctx.register_tool(
        name="clear_all_tasks",
        fn=clear_all_tasks,
        description="Delete all tasks (use with caution)",
        parameters={
            "type": "object",
            "properties": {}
        },
        auto_approved=True
    )

    # User commands
    ctx.register_command("/tasks", handle_tasks_command, description="Show all tasks")
    ctx.register_command("/task", handle_task_command, description="Manage tasks")

    # Hook to show tasks in prompt
    ctx.register_hook("before_user_prompt", before_user_prompt)

    if Config.debug():
        LogUtils.print("  - add_task tool (auto-approved)")
        LogUtils.print("  - update_task tool (auto-approved)")
        LogUtils.print("  - list_tasks tool (auto-approved)")
        LogUtils.print("  - delete_task tool (auto-approved)")
        LogUtils.print("  - clear_all_tasks tool (auto-approved)")
        LogUtils.print("  - /tasks command")
        LogUtils.print("  - /task command")
        LogUtils.print("  - before_user_prompt hook")
