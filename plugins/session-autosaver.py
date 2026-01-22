"""
Session Autosaver Plugin - AI Coder v3 session persistence

Automatically loads and saves session to SESSION_FILE in JSONL format.
V3 behavior:
- SESSION_FILE environment variable
- Auto-load on startup
- Auto-append messages (user, assistant, tool)
- Always save system prompt for proper /load functionality
- Support both JSON and JSONL based on file extension
- Respect debug mode configuration
"""

import os
from pathlib import Path

from aicoder.utils.log import LogUtils

def create_plugin(ctx):
    """Create session autosaver plugin"""
    
    session_file = os.environ.get("SESSION_FILE")
    if not session_file:
        return None  # Silent disable if no SESSION_FILE
    
    session_path = Path(session_file)
    is_jsonl = session_path.suffix.lower() == ".jsonl"
    
    if not is_jsonl and session_path.suffix.lower() != ".json":
        LogUtils.error(f"[!] Unsupported session file format: {session_path.suffix}, expected .json or .jsonl")
        return None
    
    from aicoder.core.config import Config
    if Config.debug():
        LogUtils.print(f"[*] Session autosaver enabled: {session_file} ({'JSONL' if is_jsonl else 'JSON'} format)")
    
    def load_existing_session(messages):
        """Load existing session from file"""
        if not session_path.exists():
            return
        
        try:
            if is_jsonl:
                from aicoder.utils.jsonl_utils import read_file as read_jsonl
                existing_messages = read_jsonl(session_file)
            else:
                # JSON format (backward compatibility)
                from aicoder.utils.json_utils import read_file as read_json
                existing_messages = read_json(session_file)
            
            if existing_messages:
                # JSONL/JSON should already contain system prompt from previous saves
                # Just replace current messages with loaded ones
                ctx.app.message_history.set_messages(existing_messages)
                
                from aicoder.core.config import Config
                if Config.debug():
                    LogUtils.print(f"[*] Loaded {len(existing_messages)} messages from {session_file}")
                
                # Re-estimate context after loading
                ctx.app.message_history.estimate_context()
                
        except Exception as e:
            LogUtils.error(f"[!] Failed to load session from {session_file}: {e}")
    
    def save_current_state():
        """Save current complete state to session file (for initialization)"""
        try:
            if is_jsonl:
                from aicoder.utils.jsonl_utils import write_file as write_jsonl
                # For JSONL: Save current complete state
                all_messages = ctx.app.message_history.get_messages()
                write_jsonl(session_file, all_messages)
            else:
                # JSON format - write all messages (backward compatibility)
                from aicoder.utils.json_utils import write_file as write_json
                all_messages = ctx.app.message_history.get_messages()
                write_json(session_file, all_messages)
        except Exception as e:
            LogUtils.error(f"[!] Failed to save current state to {session_file}: {e}")
    
    def save_message_to_session(message):
        """Save a single message to session file (append mode for JSONL)"""
        # Save ALL messages now including system prompt for proper /load support
        
        try:
            if is_jsonl:
                from aicoder.utils.jsonl_utils import write_file as write_jsonl
                
                # For JSONL, we need to append to existing file
                # Read current messages, append new one, write all back
                if session_path.exists():
                    from aicoder.utils.jsonl_utils import read_file as read_jsonl
                    existing_messages = read_jsonl(session_file)
                else:
                    existing_messages = []
                
                existing_messages.append(message)
                write_jsonl(session_file, existing_messages)
            else:
                # JSON format - write all messages (backward compatibility)
                from aicoder.utils.json_utils import write_file as write_json
                all_messages = ctx.app.message_history.get_messages()
                # Save ALL messages now for proper /load support
                write_json(session_file, all_messages)
                
        except Exception as e:
            LogUtils.error(f"[!] Failed to save message to {session_file}: {e}")
    
    def on_session_initialized(messages):
        """Handle session initialization - load existing session"""
        # NOTE: This hook runs early in initialization before plugins are ready
        # We handle session loading differently - see below
        pass
    
    def on_user_message_added(message):
        """Handle user message addition"""
        save_message_to_session(message)
    
    def on_assistant_message_added(message):
        """Handle assistant message addition"""
        save_message_to_session(message)
    
    def on_tool_results_added(message):
        """Handle tool results addition"""
        save_message_to_session(message)
    
    def on_messages_set(messages):
        """Handle messages being set (serious operations like compaction, load, /m)"""
        # This is called for serious operations that replace entire message history
        # For JSONL, we need to recreate the file with current state to stay in sync
        # For JSON, we can use normal logic (always rewrites anyway)
        
        try:
            if is_jsonl:
                from aicoder.utils.jsonl_utils import write_file as write_jsonl
                # For JSONL: Delete and recreate with current complete state
                all_messages = ctx.app.message_history.get_messages()
                # Save ALL messages now including system prompt for proper /load support
                write_jsonl(session_file, all_messages)
                
                from aicoder.core.config import Config
                if Config.debug():
                    LogUtils.debug(f"[*] JSONL file recreated with current state after serious operation ({len(all_messages)} messages)")
            else:
                # For JSON: Use normal save logic (will rewrite everything anyway)
                from aicoder.utils.json_utils import write_file as write_json
                all_messages = ctx.app.message_history.get_messages()
                # Save ALL messages now for proper /load support
                write_json(session_file, all_messages)
                
        except Exception as e:
            LogUtils.error(f"[!] Failed to recreate session file after serious operation: {e}")
    
    # Register hooks
    ctx.register_hook("after_session_initialized", on_session_initialized)
    ctx.register_hook("after_user_message_added", on_user_message_added)
    ctx.register_hook("after_assistant_message_added", on_assistant_message_added)
    ctx.register_hook("after_tool_results_added", on_tool_results_added)
    ctx.register_hook("after_messages_set", on_messages_set)
    
    # Load existing session AFTER all hooks are registered and system is ready
    # This ensures we have access to fully initialized message history
    messages = ctx.app.message_history.get_messages()
    if len(messages) == 1 and messages[0].get("role") == "system":
        if session_path.exists():
            from aicoder.core.config import Config
            if Config.debug():
                LogUtils.debug(f"[*] Loading existing session from {session_file}")
            load_existing_session(messages)
        else:
            from aicoder.core.config import Config
            if Config.debug():
                LogUtils.debug(f"[*] No existing session file at {session_file}, starting fresh")
            # New session: Save current state (includes system prompt) to new JSONL file
            save_current_state()
    elif not session_path.exists():
        # Also save if we have messages but no file (shouldn't happen but handle it)
        save_current_state()
    
    from aicoder.core.config import Config
    if Config.debug():
        LogUtils.debug("[+] Session autosaver plugin loaded successfully")
    
    return {"cleanup": lambda: LogUtils.print("[-] Session autosaver plugin unloaded")}