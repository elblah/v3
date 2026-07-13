"""
Session Autosaver Plugin - AI Coder v3 session persistence

Automatically loads and saves session to SESSION_FILE in JSONL format.
- SESSION_FILE environment variable
- Auto-load on startup
- Auto-append messages (user, assistant, tool)
- Saves only chat messages (no system prompt) — matches /save behavior
- On load, preserves current system prompt — matches /load behavior
- Support both JSON and JSONL based on file extension
- Respect debug mode configuration
"""

import sys
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
        """Load existing session from file, preserving current system prompt"""
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
                # Preserve current system prompt, only load chat messages
                current = ctx.app.message_history.get_messages()
                system_msg = None
                for msg in current:
                    if msg.get("role") == "system":
                        system_msg = msg
                        break
                if system_msg:
                    loaded = [system_msg] + [m for m in existing_messages if m.get("role") != "system"]
                else:
                    loaded = existing_messages
                ctx.app.message_history.set_messages(loaded)
                
                from aicoder.core.config import Config
                if Config.debug():
                    LogUtils.print(f"[*] Loaded {len(existing_messages)} messages from {session_file}")
                
                # Re-estimate context after loading
                ctx.app.message_history.estimate_context()
                
        except Exception as e:
            LogUtils.error(f"[!] Failed to load session from {session_file}: {e}")
    
    def save_current_state():
        """Save current chat messages to session file (for initialization)"""
        try:
            chat_messages = ctx.app.message_history.get_chat_messages()
            if is_jsonl:
                from aicoder.utils.jsonl_utils import write_file as write_jsonl
                write_jsonl(session_file, chat_messages)
            else:
                # JSON format (backward compatibility)
                from aicoder.utils.json_utils import write_file as write_json
                write_json(session_file, chat_messages)
        except Exception as e:
            LogUtils.error(f"[!] Failed to save current state to {session_file}: {e}")
    
    def save_message_to_session(message):
        """Save a single message to session file (append mode for JSONL)"""
        # Save only chat messages — matches /save behavior
        
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
                # JSON format - write all chat messages (backward compatibility)
                from aicoder.utils.json_utils import write_file as write_json
                chat_messages = ctx.app.message_history.get_chat_messages()
                write_json(session_file, chat_messages)
                
        except Exception as e:
            LogUtils.error(f"[!] Failed to save message to {session_file}: {e}")
    
    def _count_messages():
        """Quick count of messages in session file without full load"""
        if not session_path.exists():
            return 0
        try:
            if is_jsonl:
                with open(session_file, 'r') as f:
                    return sum(1 for line in f if line.strip())
            else:
                import json
                with open(session_file, 'r') as f:
                    data = json.load(f)
                return len(data) if isinstance(data, list) else 0
        except Exception:
            return 0

    def on_session_initialized(messages):
        """Handle session initialization - load existing session"""
        if not session_path.exists():
            LogUtils.print(f"[*] No existing session at {session_file}, starting fresh")
            save_current_state()
            return
        
        # On TTY, optionally confirm before loading (opt-in via env var)
        should_confirm = (
            sys.stdin.isatty()
            and os.environ.get("SESSION_FILE_CONFIRM_AUTOLOAD", "").lower() in ("1", "true", "yes")
        )
        if should_confirm:
            msg_count = _count_messages()
            extra = f" ({msg_count} messages)" if msg_count else ""
            c = Config.colors
            answer = input(f"\n  {c['bold']}{c['brightYellow']}Load previous session from {session_file}{extra}? [Y/n]{c['reset']} ").strip().lower()
            print()
            if answer in ("n", "no"):
                LogUtils.print("[*] Skipping session load, starting fresh")
                save_current_state()
                return
        
        try:
            load_existing_session(messages)
            LogUtils.print(f"[*] Loaded session from {session_file}")
        except Exception as e:
            LogUtils.error(f"[!] Failed to load session from {session_file}: {e}")
    
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
            chat_messages = ctx.app.message_history.get_chat_messages()
            if is_jsonl:
                from aicoder.utils.jsonl_utils import write_file as write_jsonl
                write_jsonl(session_file, chat_messages)
                
                from aicoder.core.config import Config
                if Config.debug():
                    LogUtils.debug(f"[*] JSONL file recreated with current state after serious operation ({len(chat_messages)} messages)")
            else:
                # For JSON: Use normal save logic (will rewrite everything anyway)
                from aicoder.utils.json_utils import write_file as write_json
                write_json(session_file, chat_messages)
                
        except Exception as e:
            LogUtils.error(f"[!] Failed to recreate session file after serious operation: {e}")
    
    def on_session_change(action=None):
        """Session reset (/new /load) — delete session file so next start is fresh"""
        try:
            if session_path.exists():
                session_path.unlink()
                if Config.debug():
                    LogUtils.debug(f"[*] Deleted session file {session_file} on session change")
        except Exception as e:
            LogUtils.error(f"[!] Failed to delete session file {session_file}: {e}")
    
    # Register hooks
    ctx.register_hook("after_session_initialized", on_session_initialized)
    ctx.register_hook("after_user_message_added", on_user_message_added)
    ctx.register_hook("after_assistant_message_added", on_assistant_message_added)
    ctx.register_hook("after_tool_results_added", on_tool_results_added)
    ctx.register_hook("after_messages_set", on_messages_set)
    ctx.register_hook("on_session_change", on_session_change)
    
    from aicoder.core.config import Config
    if Config.debug():
        LogUtils.debug("[+] Session autosaver plugin loaded successfully")
    
    return {"cleanup": lambda: LogUtils.print("[-] Session autosaver plugin unloaded")}