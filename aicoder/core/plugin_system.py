"""
Ultra-fast plugin system for AI Coder v3

Design principles:
- Startup speed: Load plugins only when .aicoder/plugins/ exists
- Minimalism: Single create_plugin(context) function (duck typing)
- Per-project: Plugins live in .aicoder/plugins/ (not global)
- No dependencies: Pure Python stdlib only
- Closure state: Plugin state in closures, no complex state mgmt
"""

import os
import sys
import importlib.util
import threading
import subprocess
from typing import Any, Callable, Dict, List, Optional, Set
from pathlib import Path


class PluginContext:
    """Context object passed to plugins - minimal API surface"""

    def __init__(self):
        # Callbacks set by plugin system
        self._register_tool_fn: Optional[Callable] = None
        self._register_command_fn: Optional[Callable] = None
        self._register_hook_fn: Optional[Callable] = None
        self._run_shell_fn: Optional[Callable] = None
        self._add_user_message_fn: Optional[Callable] = None

    def register_tool(
        self,
        name: str,
        fn: Callable,
        description: str,
        parameters: Dict[str, Any],
        auto_approved: bool = False,
        format_arguments: Optional[Callable] = None,
    ) -> None:
        """Register a tool for AI to use"""
        if self._register_tool_fn:
            self._register_tool_fn(name, fn, description, parameters, auto_approved, format_arguments)

    def register_command(
        self, name: str, handler: Callable, description: Optional[str] = None
    ) -> None:
        """Register a user command (e.g., /ruff, /web)"""
        if self._register_command_fn:
            self._register_command_fn(name, handler, description)

    def register_hook(self, event_name: str, handler: Callable) -> None:
        """Register an event hook"""
        if self._register_hook_fn:
            self._register_hook_fn(event_name, handler)

    def run_shell(self, command: str, timeout: int = 30) -> str:
        """Run shell command and return output"""
        if self._run_shell_fn:
            return self._run_shell_fn(command, timeout)
        # Fallback implementation
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True, timeout=timeout
            )
            return result.stdout or result.stderr
        except subprocess.TimeoutExpired:
            return f"Command timed out after {timeout}s"
        except Exception as e:
            return f"Error running command: {e}"

    def run_shell_async(self, command: str) -> None:
        """Run shell command in background, don't wait"""
        try:
            subprocess.Popen(command, shell=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass  # Silent failure - notifications aren't critical

    def add_user_message(self, message: str) -> None:
        """Add a message for the AI to see"""
        if self._add_user_message_fn:
            self._add_user_message_fn(message)

    def log(self, message: str) -> None:
        """Plugin logging"""
        print(f"[plugin] {message}")


class PluginSystem:
    """
    Ultra-fast plugin loader

    Features:
    - Only loads if .aicoder/plugins/ directory exists
    - Single file per plugin
    - Duck-typed: just create_plugin(context) function
    - Hook system for events
    - Closure-based state management
    """

    def __init__(self, plugins_dir: str = ".aicoder/plugins"):
        self.plugins_dir = plugins_dir
        self.plugins: List[Any] = []
        self.tools: Dict[str, Dict] = {}
        self.commands: Dict[str, Callable] = {}
        self.hooks: Dict[str, List[Callable]] = {}
        self.cleanup_handlers: List[Callable] = []

        # Context object with callbacks
        self.context = PluginContext()
        self.context._register_tool_fn = self._register_tool
        self.context._register_command_fn = self._register_command
        self.context._register_hook_fn = self._register_hook
        self.context._run_shell_fn = self._run_shell
        self.context._add_user_message_fn = self._add_user_message

        # Callbacks set by main app
        self._add_user_message_fn = None

    def set_message_callback(self, fn: Callable) -> None:
        """Set callback for adding user messages"""
        self._add_user_message_fn = fn
        self.context._add_user_message_fn = fn

    def _add_user_message(self, message: str) -> None:
        """Internal: add user message via callback"""
        if self._add_user_message_fn:
            self._add_user_message_fn(message)

    def _run_shell(self, command: str, timeout: int = 30) -> str:
        """Internal: run shell command"""
        try:
            result = subprocess.run(
                command, shell=True, capture_output=True, text=True, timeout=timeout
            )
            return result.stdout or result.stderr
        except subprocess.TimeoutExpired:
            return f"Command timed out after {timeout}s"
        except Exception as e:
            return f"Error: {e}"

    def _register_tool(
        self,
        name: str,
        fn: Callable,
        description: str,
        parameters: Dict[str, Any],
        auto_approved: bool,
        format_arguments: Optional[Callable] = None,
    ) -> None:
        """Internal: register a tool"""
        self.tools[name] = {
            "fn": fn,
            "description": description,
            "parameters": parameters,
            "auto_approved": auto_approved,
            "formatArguments": format_arguments,
        }

    def _register_command(
        self, name: str, handler: Callable, description: Optional[str]
    ) -> None:
        """Internal: register a command"""
        self.commands[name] = {"fn": handler, "description": description}

    def _register_hook(self, event_name: str, handler: Callable) -> None:
        """Internal: register an event hook"""
        if event_name not in self.hooks:
            self.hooks[event_name] = []
        self.hooks[event_name].append(handler)

    def load_plugins(self) -> None:
        """
        Load plugins from .aicoder/plugins/

        Ultra-fast: returns immediately if directory doesn't exist.
        """
        # Fast exit - no plugins directory
        if not os.path.exists(self.plugins_dir):
            return

        # Get plugin files sorted numerically then alphabetically
        plugin_files = []
        for filename in os.listdir(self.plugins_dir):
            if filename.endswith(".py") and not filename.startswith("_"):
                plugin_files.append(filename)

        # Sort: numbered first (01_, 02_), then alphabetically
        def sort_key(f):
            stem = Path(f).stem
            match = stem.split("_")[0]
            if match.isdigit():
                return (0, int(match))
            return (1, stem)

        plugin_files.sort(key=sort_key)

        # Load each plugin
        for filename in plugin_files:
            self._load_single_plugin(os.path.join(self.plugins_dir, filename))

    def _load_single_plugin(self, plugin_path: str) -> None:
        """Load a single plugin file"""
        try:
            # Fast import using importlib
            spec = importlib.util.spec_from_file_location(
                f"plugin_{Path(plugin_path).stem}", plugin_path
            )
            module = importlib.util.module_from_spec(spec)

            # Execute module
            spec.loader.exec_module(module)

            # Call create_plugin(context) if exists (duck typing)
            if hasattr(module, "create_plugin"):
                result = module.create_plugin(self.context)

                # Handle cleanup if returned
                if result and isinstance(result, dict) and "cleanup" in result:
                    self.cleanup_handlers.append(result["cleanup"])

                print(f"[+] Loaded plugin: {Path(plugin_path).name}")

        except Exception as e:
            print(f"[!] Failed to load plugin {plugin_path}: {e}")

    def get_plugin_tools(self) -> Dict[str, Dict]:
        """Get all tools from plugins"""
        return self.tools.copy()

    def get_plugin_commands(self) -> Dict[str, Dict]:
        """Get all commands from plugins"""
        return self.commands.copy()

    def call_hooks(self, event_name: str, *args, **kwargs) -> Any:
        """Call all hooks for an event"""
        if event_name not in self.hooks:
            return None

        results = []
        for hook in self.hooks[event_name]:
            try:
                result = hook(*args, **kwargs)
                results.append(result)
            except Exception as e:
                print(f"[!] Hook {event_name} failed: {e}")

        return results if results else None

    def cleanup(self) -> None:
        """Cleanup all plugins"""
        for cleanup_fn in self.cleanup_handlers:
            try:
                cleanup_fn()
            except Exception as e:
                print(f"[!] Plugin cleanup failed: {e}")
