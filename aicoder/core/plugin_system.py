"""
Ultra-fast plugin system for AI Coder v3

Design principles:
- Startup speed: Load plugins only when .aicoder/plugins/ exists
- Minimalism: Single create_plugin(context) function (duck typing)
- Per-project: Plugins live in .aicoder/plugins/ (not global)
- No dependencies: Pure Python stdlib only
- Closure state: Plugin state in closures, no complex state mgmt
- Direct access: Plugins get ctx.app for direct component access
- Elegant indirections: Only registration methods (register_tool, etc.) are bridged
"""

import os
import sys
import importlib.util
import threading
import subprocess
from typing import Any, Callable, Dict, List, Optional, Set, TYPE_CHECKING
from pathlib import Path

if TYPE_CHECKING:
    from aicoder.core.aicoder import AICoder


class PluginContext:
    """
    Context object passed to plugins - minimal API surface

    Plugins get direct access to the main AICoder app via ctx.app,
    allowing them to interact with all components without bureaucracy.

    Registration methods are provided as elegant abstractions for
    registering tools, commands, and hooks.
    """

    def __init__(self):
        # Direct reference to the main AICoder app (set by PluginSystem)
        self.app: Optional['AICoder'] = None

        # Registration callbacks (elegant indirections)
        self._register_tool_fn: Optional[Callable] = None
        self._register_command_fn: Optional[Callable] = None
        self._register_hook_fn: Optional[Callable] = None

    def register_tool(
        self,
        name: str,
        fn: Callable,
        description: str,
        parameters: Dict[str, Any],
        auto_approved: bool = False,
        format_arguments: Optional[Callable] = None,
    ) -> None:
        """
        Register a tool for AI to use

        This is an elegant abstraction - plugins shouldn't need to know
        the internal details of how tools are registered.
        """
        if self._register_tool_fn:
            self._register_tool_fn(name, fn, description, parameters, auto_approved, format_arguments)

    def register_command(
        self, name: str, handler: Callable, description: Optional[str] = None
    ) -> None:
        """
        Register a user command (e.g., /ruff, /web)

        This is an elegant abstraction - plugins shouldn't need to know
        the internal details of how commands are registered.
        """
        if self._register_command_fn:
            self._register_command_fn(name, handler, description)

    def register_hook(self, event_name: str, handler: Callable) -> None:
        """
        Register an event hook

        This is an elegant abstraction - plugins shouldn't need to know
        the internal details of how hooks are registered.
        """
        if self._register_hook_fn:
            self._register_hook_fn(event_name, handler)


class PluginSystem:
    """
    Ultra-fast plugin loader

    Features:
    - Only loads if .aicoder/plugins/ directory exists
    - Single file per plugin
    - Duck-typed: just create_plugin(context) function
    - Hook system for events
    - Closure-based state management
    - Direct app access: plugins get ctx.app for full component access
    """

    def __init__(self, plugins_dir: str = ".aicoder/plugins"):
        self.plugins_dir = plugins_dir
        self.plugins: List[Any] = []
        self.tools: Dict[str, Dict] = {}
        self.commands: Dict[str, Callable] = {}
        self.hooks: Dict[str, List[Callable]] = {}
        self.cleanup_handlers: List[Callable] = []

        # Context object with registration callbacks
        self.context = PluginContext()
        self.context._register_tool_fn = self._register_tool
        self.context._register_command_fn = self._register_command
        self.context._register_hook_fn = self._register_hook

        # App reference (set by AICoder)
        self._app = None

    def set_app(self, app: 'AICoder') -> None:
        """Set the main AICoder app reference"""
        self._app = app
        self.context.app = app

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
