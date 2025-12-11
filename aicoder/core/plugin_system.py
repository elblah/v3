"""
Plugin System for AI Coder
Ported exactly from TypeScript version

IMPORTANT: There is only ONE plugin API. If this API changes,
all plugins MUST be updated to match. No legacy support is provided.

Design principles:
- Simple: Minimal abstractions, direct API
- Robust: Graceful error handling, no plugin crashes
- Single API: One way to create plugins, no backward compatibility
"""

import os
import importlib.util
from typing import Dict, List, Any, Optional, Callable
from dataclasses import dataclass
from abc import ABC, abstractmethod

from aicoder.core.config import Config
from aicoder.utils.log import LogUtils
from aicoder.type_defs.tool_types import ToolExecutionArgs, ToolResult
from aicoder.type_defs.system_types import PopupMenuItem


@dataclass
class PluginTool:
    """Simple tool definition for plugins"""

    name: str
    description: str
    parameters: Dict[str, Any]
    execute: Callable[[Any], str]
    auto_approved: bool = False  # Whether tool is auto-approved (default: false)


@dataclass
class HookResult:
    pass


class ToolOutputResult:
    pass


class ConfigValue:
    pass


class NotificationHooks:
    pass


class PluginContext:
    """Plugin context - provides access to app internals"""

    def __init__(self):
        # Config access - direct access to app config
        self.config = Config

        # Commands
        self.register_command = lambda name, handler, description=None: None

        # Messages
        self.add_user_message = lambda message: None
        self.add_system_message = lambda message: None

        # Configuration
        self._config_store: Dict[str, Any] = {}
        self.get_config = lambda key: self._config_store.get(key)
        self.set_config = lambda key, value: self._config_store.__setitem__(key, value)

        # File operations (intercepted)
        self.original_write_file = lambda path, content: None
        self.original_edit_file = lambda path, old_str, new_str: None

        # App reference for advanced use cases
        self.app: Optional[Dict[str, Any]] = None

        # Notification hooks (optional)
        self.register_notify_hooks = lambda hooks: None

        # Popup menu items
        self.register_popup_menu_item = lambda item: None
        self.unregister_popup_menu_item = lambda key: None


class Plugin(ABC):
    """Core plugin interface - simple and minimal"""

    @property
    @abstractmethod
    def name(self) -> str:
        """Plugin name"""
        pass

    @property
    @abstractmethod
    def version(self) -> str:
        """Plugin version"""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """Plugin description"""
        pass

    # Optional lifecycle hooks
    def initialize(self) -> None:
        """Initialize plugin"""
        pass

    def cleanup(self) -> None:
        """Cleanup plugin"""
        pass

    # Optional capabilities
    def get_tools(self) -> List[PluginTool]:
        """Get tools provided by plugin"""
        return []

    def before_tool_call(self, tool_name: str, args: ToolExecutionArgs) -> HookResult:
        """Hook before tool call"""
        pass

    def after_tool_call(self, tool_name: str, result: ToolResult) -> ToolOutputResult:
        """Hook after tool call"""
        pass

    def before_file_write(self, path: str, content: str) -> ToolOutputResult:
        """Hook before file write"""
        pass

    def after_file_write(self, path: str, content: str) -> None:
        """Hook after file write"""
        pass

    # Note: Future hooks can be added here - plugins must implement them if needed


class PluginSystem:
    """Plugin system for loading and managing plugins"""

    def __init__(self):
        self.plugins: Dict[str, Plugin] = {}
        self.tools: Dict[str, PluginTool] = {}
        self.popup_menu_items: Dict[str, PopupMenuItem] = {}
        self.context = self._create_context()

    def load_plugins(self) -> None:
        """
        Load plugins from ~/.config/aicoder-mini/plugins/
        Loads plugins synchronously, one at a time to prevent race conditions

        IMPORTANT: Plugins MUST export a default function: create_plugin(context)
        No other export formats are supported.
        """
        # Set env var so plugins can find us
        os.environ["AICODER_ROOT"] = os.path.dirname(
            os.path.dirname(os.path.dirname(__file__))
        )

        plugins_dir = os.path.join(
            os.path.expanduser("~"), ".config", "aicoder-mini", "plugins"
        )

        try:
            if not os.path.exists(plugins_dir):
                if Config.debug():
                    LogUtils.warn(f"[*] No plugins directory: {plugins_dir}")
                    LogUtils.print(
                        f'[*] Create it to install plugins: mkdir -p "{plugins_dir}"',
                        {"color": Config.colors["cyan"]},
                    )
                return

            entries = os.listdir(plugins_dir)
            loaded_count = 0

            for entry in entries:
                file_path = os.path.join(plugins_dir, entry)
                if os.path.isfile(file_path) and (entry.endswith(".py")):
                    self._load_plugin(file_path)
                    loaded_count += 1

            if Config.debug():
                LogUtils.success(f"[*] Loaded {loaded_count} plugins")
        except Exception as error:
            LogUtils.error(f"[x] Plugin loading failed: {error}")

    def _load_plugin(self, file_path: str) -> None:
        """
        Load a single plugin file

        IMPORTANT: Plugin MUST export default create_plugin(context) function
        No legacy formats are supported.
        """
        try:
            # Load module from file
            spec = importlib.util.spec_from_file_location("plugin", file_path)
            if spec is None or spec.loader is None:
                LogUtils.error(f"[x] Could not load plugin spec: {file_path}")
                return

            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)

            # ONLY support the new API: create_plugin(context) function
            if hasattr(module, "create_plugin") and callable(module.create_plugin):
                plugin = module.create_plugin(self.context)

                if self._is_valid_plugin(plugin):
                    self.plugins[plugin.name] = plugin

                    # Initialize plugin if it has an initialize method
                    try:
                        plugin.initialize()
                    except Exception as error:
                        LogUtils.error(f"[x] Plugin {plugin.name} init failed: {error}")
                        # Remove failed plugin
                        del self.plugins[plugin.name]
                        return

                    # Register tools if plugin provides them
                    try:
                        tools = plugin.get_tools()
                        for tool in tools:
                            self.tools[tool.name] = tool
                    except Exception as error:
                        LogUtils.error(
                            f"[x] Plugin {plugin.name} tools failed: {error}"
                        )

                    LogUtils.success(f"[+] Plugin: {plugin.name} v{plugin.version}")
                else:
                    LogUtils.error(
                        f"[x] Invalid plugin format in {file_path}: Must implement Plugin interface"
                    )
            else:
                LogUtils.error(
                    f"[x] Invalid plugin format in {file_path}: Must export create_plugin(context) function"
                )
        except Exception as error:
            LogUtils.error(f"[x] Failed to load {file_path}: {error}")

    def _is_valid_plugin(self, obj: Any) -> bool:
        """Check if object is a valid plugin"""
        return (
            obj
            and isinstance(obj, Plugin)
            and isinstance(obj.name, str)
            and isinstance(obj.version, str)
            and isinstance(obj.description, str)
        )

    def _create_context(self) -> PluginContext:
        """Create plugin context"""
        return PluginContext()

    def set_context(self, context: Dict[str, Any]) -> None:
        """Update context with real implementations"""
        for key, value in context.items():
            if hasattr(self.context, key):
                setattr(self.context, key, value)

    def get_all_tools(self) -> Dict[str, PluginTool]:
        """Get all tools (internal + plugins)"""
        if Config.debug():
            print(f"[DEBUG] getAllTools() returning {len(self.tools)} tools:")
            print(list(self.tools.keys()))
        return self.tools.copy()

    def execute_tool(self, name: str, args: ToolExecutionArgs) -> str:
        """Execute a tool (internal or plugin)"""
        tool = self.tools.get(name)
        if not tool:
            raise Exception(f"Tool not found: {name}")

        try:
            return tool.execute(args)
        except Exception as error:
            LogUtils.error(f"[x] Tool {name} failed: {error}")
            raise error

    def get_tool_definitions(self) -> List[Dict[str, Any]]:
        """Get tool definitions for all tools (for AI)"""
        definitions = []

        for name, tool in self.tools.items():
            definitions.append(
                {
                    "type": "plugin",
                    "auto_approved": tool.auto_approved,
                    "approval_excludes_arguments": False,
                    "approval_key_exclude_arguments": [],
                    "hide_results": False,
                    "description": tool.description,
                    "parameters": tool.parameters,
                    "execute": None,  # Will be filled by tool manager
                }
            )

        return definitions

    def before_tool_call(
        self, tool_name: str, args: ToolExecutionArgs
    ) -> Optional[bool]:
        """Hook before tool call"""
        for plugin in self.plugins.values():
            try:
                if hasattr(plugin, "before_tool_call"):
                    result = plugin.before_tool_call(tool_name, args)
                    if result is False:
                        return False  # Cancel
            except Exception as error:
                LogUtils.error(
                    f"[x] Plugin {plugin.name} beforeToolCall failed: {error}"
                )
        return None

    def after_tool_call(
        self, tool_name: str, result: ToolResult
    ) -> Optional[ToolResult]:
        """Hook after tool call"""
        modified_result = result

        for plugin in self.plugins.values():
            try:
                if hasattr(plugin, "after_tool_call"):
                    plugin_result = plugin.after_tool_call(tool_name, modified_result)
                    if plugin_result is not None:
                        modified_result = plugin_result
            except Exception as error:
                LogUtils.error(
                    f"[x] Plugin {plugin.name} afterToolCall failed: {error}"
                )

        return modified_result

    def before_file_write(self, path: str, content: str) -> str:
        """Hook before file write"""
        modified_content = content

        for plugin in self.plugins.values():
            try:
                if hasattr(plugin, "before_file_write"):
                    plugin_result = plugin.before_file_write(path, modified_content)
                    if plugin_result is not None:
                        modified_content = plugin_result
            except Exception as error:
                LogUtils.error(
                    f"[x] Plugin {plugin.name} beforeFileWrite failed: {error}"
                )

        return modified_content

    def after_file_write(self, path: str, content: str) -> None:
        """Hook after file write"""
        for plugin in self.plugins.values():
            try:
                if hasattr(plugin, "after_file_write"):
                    plugin.after_file_write(path, content)
            except Exception as error:
                LogUtils.error(
                    f"[x] Plugin {plugin.name} afterFileWrite failed: {error}"
                )

    def register_tool(self, name: str, tool: PluginTool) -> None:
        """Register a tool (for internal tools)"""
        self.tools[name] = tool

    def get_context(self) -> PluginContext:
        """Get plugin context"""
        return self.context

    def register_popup_menu_item(self, item: PopupMenuItem) -> None:
        """Register a popup menu item"""
        self.popup_menu_items[item.key] = item

    def unregister_popup_menu_item(self, key: str) -> None:
        """Unregister a popup menu item"""
        self.popup_menu_items.pop(key, None)

    def update_popup_menu_item(self, item: PopupMenuItem) -> None:
        """Update a popup menu item (useful for dynamic labels like status)"""
        self.popup_menu_items[item.key] = item

    def get_popup_menu_items(self) -> Dict[str, PopupMenuItem]:
        """Get all popup menu items"""
        return self.popup_menu_items.copy()

    def get_plugins(self) -> Dict[str, Plugin]:
        """Get all plugins"""
        return self.plugins.copy()

    def cleanup(self) -> None:
        """Cleanup all plugins synchronously"""
        for plugin in self.plugins.values():
            try:
                if hasattr(plugin, "cleanup"):
                    plugin.cleanup()
            except Exception as error:
                LogUtils.error(f"[x] Plugin {plugin.name} cleanup failed: {error}")

        self.plugins.clear()
        self.tools.clear()
        self.popup_menu_items.clear()


# Global plugin system instance
plugin_system = PluginSystem()
