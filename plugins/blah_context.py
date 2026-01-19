"""
Blah Context Plugin - AI Coherence Management

Plugin for maintaining AI coherence over long sessions through intelligent
knowledge organization and selective retrieval.

Commands:
- /blah organize - Manual organization
- /blah status - Show current settings  
- /blah set-threshold N - Set token threshold
- /blah reload - Refresh file listing
"""

import os
import sys
import json
import uuid
from datetime import datetime
from pathlib import Path

from aicoder.core.config import Config
from aicoder.utils.log import LogUtils


class BlahContextPlugin:
    """Blah context plugin - all state in closure"""
    
    def __init__(self, ctx):
        self.ctx = ctx
        self.app = ctx.app
        
        # Configuration
        self.blah_dir = None
        self.current_session_dir = None
        self.archives_dir = None
        self.token_threshold = 100000  # Default 100k tokens
        self.enabled = True
        self.before_compaction_hook_enabled = False  # Default disabled
        
        # Session tracking
        self.session_id = None
        self.is_organizing = False
        self.last_user_msg_before_org = None  # Track last user message before organization
        self.organization_reason = ""  # Reason for current organization
        
        # Initialize session directory
        self._initialize_session_directory()
        
    def _initialize_session_directory(self):
        """Initialize session directory and subdirectories"""
        # Base directory from environment or default
        base_dir = os.environ.get('AICODER_BLAH_SESSION_DIR', '.aicoder/blah')
        self.blah_dir = os.path.abspath(base_dir)
        
        # Create base directory
        os.makedirs(self.blah_dir, exist_ok=True)
        
        # Create session directory
        date_str = datetime.now().strftime('%Y-%m-%d')
        uuid_short = str(uuid.uuid4()).replace('-', '')[:8]
        self.session_id = f"{date_str}_{uuid_short}"
        self.current_session_dir = os.path.join(self.blah_dir, self.session_id)
        os.makedirs(self.current_session_dir, exist_ok=True)
        
        # Create blah_files directory (AI creates/reads knowledge files here ONLY)
        self.blah_files_dir = os.path.join(self.current_session_dir, 'blah_files')
        os.makedirs(self.blah_files_dir, exist_ok=True)
        
        # Create archives directory (System-only - JSON and TXT of entire session)
        self.archives_dir = os.path.join(self.current_session_dir, 'archives')
        os.makedirs(self.archives_dir, exist_ok=True)
        
        # Update current_session symlink
        current_link = os.path.join(self.blah_dir, 'current_session')
        try:
            if os.path.lexists(current_link):
                os.unlink(current_link)
            os.symlink(self.session_id, current_link)
        except OSError:
            pass  # Symlink not supported
        
        # Load configuration
        self._load_configuration()
        
    def _load_configuration(self):
        """Load configuration from environment"""
        # Token threshold
        threshold_env = os.environ.get('BLAH_TOKEN_THRESHOLD')
        if threshold_env:
            try:
                self.token_threshold = int(threshold_env)
            except ValueError:
                pass
        
        # Enabled flag
        enabled_env = os.environ.get('BLAH_ENABLED')
        if enabled_env:
            self.enabled = enabled_env.lower() in ('true', '1', 'yes', 'on')
        
        # Before compaction hook enabled flag (default: disabled)
        before_compaction_env = os.environ.get('BLAH_BEFORE_COMPACTION_HOOK')
        if before_compaction_env:
            self.before_compaction_hook_enabled = before_compaction_env.lower() in ('true', '1', 'yes', 'on')
        else:
            self.before_compaction_hook_enabled = False
    
    def _get_next_archive_number(self):
        """Get next archive number for sequential naming"""
        existing_archives = []
        for filename in os.listdir(self.archives_dir):
            if filename.startswith('compacted_') and filename.endswith('.txt'):
                parts = filename.replace('compacted_', '').replace('.txt', '').split('_')
                if parts and parts[0].isdigit():
                    existing_archives.append(int(parts[0]))
        
        return max(existing_archives, default=0) + 1
    
    def _save_archives(self):
        """Save current messages as both text and JSON archives"""
        messages = self.app.message_history.get_messages()
        if not messages:
            return False
        
        archive_num = self._get_next_archive_number()
        
        # Save text format (for AI retrieval)
        text_path = os.path.join(self.archives_dir, f'compacted_{archive_num:03d}.txt')
        try:
            with open(text_path, 'w', encoding='utf-8') as f:
                f.write(self._format_messages_for_archive(messages))
        except Exception as e:
            LogUtils.warn(f"Failed to save text archive: {e}")
            return False
        
        # Save JSON format (for reconstruction)
        json_path = os.path.join(self.archives_dir, f'compacted_{archive_num:03d}.json')
        try:
            with open(json_path, 'w', encoding='utf-8') as f:
                json.dump(messages, f, indent=2, ensure_ascii=False)
        except Exception as e:
            LogUtils.warn(f"Failed to save JSON archive: {e}")
            return False
        
        return True
    
    def _format_messages_for_archive(self, messages):
        """Format messages for text archive (same as compaction format)"""
        total_messages = len(messages)
        result = []
        
        for i, msg in enumerate(messages):
            role = msg.get("role")
            content = msg.get("content", "")
            
            # Skip system messages for archive
            if role == "system":
                continue
            
            # Calculate temporal position
            current_index = i + 1
            position_ratio = current_index / total_messages
            position_percent = position_ratio * 100
            
            # Add temporal priority indicator
            if position_percent >= 80:
                priority = "🔴 VERY RECENT (Last 20%)"
            elif position_percent >= 60:
                priority = "🟡 RECENT (Last 40%)"
            elif position_percent >= 30:
                priority = "🟢 MIDDLE"
            else:
                priority = "🔵 OLD (First 30%)"
            
            prefix = f"[{current_index:03d}/{total_messages}] {priority} "
            
            # Format based on role
            if role == "assistant":
                tool_calls = msg.get("tool_calls", [])
                if tool_calls and len(tool_calls) > 0:
                    tool_info = "\n".join(
                        f"Tool Call: {call.get('function', {}).get('name', 'unknown')}({call.get('function', {}).get('arguments', '{}')})"
                        for call in tool_calls
                    )
                    result.append(f"{prefix} Assistant: {content}\n{tool_info}")
                else:
                    result.append(f"{prefix} Assistant: {content}")
            elif role == "tool":
                tool_call_id = msg.get("tool_call_id", "unknown")
                tool_content = content
                
                # Truncate very long tool results
                if len(tool_content) > 500:
                    tool_content = tool_content[:500] + "... (truncated)"
                
                result.append(f"{prefix} Tool Result (ID: {tool_call_id}): {tool_content}")
            elif role == "user":
                result.append(f"{prefix} User: {content}")
            else:
                result.append(f"{prefix} {role.capitalize() if role else 'Unknown'}: {content}")
            
            result.append("---")
        
        return "\n".join(result)
    
    def _discover_blah_files(self):
        """Discover all blah files in blah_files/ directory"""
        blah_files = {}
        
        if not self.blah_files_dir or not os.path.exists(self.blah_files_dir):
            return blah_files
        
        for filename in os.listdir(self.blah_files_dir):
            if filename.endswith('.md') and not filename.startswith('session_info'):
                file_path = os.path.join(self.blah_files_dir, filename)
                
                try:
                    with open(file_path, 'r', encoding='utf-8') as f:
                        content = f.read()
                    
                    # Parse YAML frontmatter
                    name = self._parse_field(content, 'name') or filename[:-3]
                    description = self._parse_field(content, 'description') or 'No description available'
                    
                    blah_files[name] = {
                        'name': name,
                        'path': file_path,
                        'description': description
                    }
                except Exception:
                    continue
        
        return blah_files
    
    def _parse_field(self, content, field):
        """Parse a field from YAML frontmatter"""
        parts = content.split('---', 2)
        if len(parts) < 3:
            return None
        
        for line in parts[1].strip().split('\n'):
            line = line.strip()
            if line.startswith(f'{field}:'):
                return line.split(':', 1)[1].strip()
        
        return None
    
    def _generate_blah_files_message(self):
        """Generate [BLAH FILES] message"""
        blah_files = self._discover_blah_files()
        
        # Count archives
        archive_count = len([f for f in os.listdir(self.archives_dir) if f.endswith('.txt')]) if os.path.exists(self.archives_dir) else 0
        
        if not blah_files and archive_count == 0:
            return "[BLAH FILES] No organized knowledge files available yet.\nUse /blah organize to create knowledge files from current conversation."
        
        source_info = f"Loading from: {self.blah_files_dir} ({len(blah_files)} files found)"
        
        files_list = []
        for file_name, file_info in sorted(blah_files.items()):
            relative_path = os.path.relpath(file_info['path'], os.getcwd())
            files_list.append(f"- {file_name} ({relative_path}): {file_info['description']}")
        
        archives_info = ""
        if archive_count > 0:
            archives_info = f"\n📁 archives/ - Detailed conversation history (compacted_001-{archive_count:03d})"
        
        return f"""[BLAH FILES] You have access to these organized knowledge files. Load a file by reading its full path when the task requires it.

{source_info}{archives_info}

Available Knowledge Files:

{chr(10).join(files_list)}

To load a file, use: read_file(path/to/file.md)
For detailed search, use: grep archives/compacted_*.txt
"""
    
    def _ensure_blah_files_message(self):
        """Ensure [BLAH FILES] message exists in history"""
        if not self.current_session_dir:
            return
        
        blah_text = self._generate_blah_files_message()
        
        # Find and replace existing [BLAH FILES] message
        for idx, msg in enumerate(self.app.message_history.messages):
            content = msg.get("content", "")
            if msg.get("role") == "user" and content.startswith("[BLAH FILES]"):
                self.app.message_history.messages[idx]["content"] = blah_text
                return
        
        # Only add if not already present elsewhere (avoid duplicates)
        # Check if the blah_text is already in any message
        for msg in self.app.message_history.messages:
            if msg.get("role") == "user" and msg.get("content", "").startswith("[BLAH FILES]"):
                return  # Already exists, don't add duplicate
        
        # Add after system message at index 1
        self.app.message_history.messages.insert(1, {
            "role": "user", 
            "content": blah_text
        })
    
    def _get_current_tokens(self):
        """Get current token count from stats object"""
        return self.app.stats.current_prompt_size or 0
    
    def _check_auto_organize(self):
        """Check if auto-organization should be triggered"""
        if not self.enabled or self.is_organizing:
            return False
        
        current_tokens = self._get_current_tokens()
        return current_tokens >= self.token_threshold
    
    # Tool handlers
    def _blah_tool(self, args):
        """Handle blah tool call from AI"""
        reason = args.get('reason', 'Manual organization request')
        
        # Check if already organizing
        if self.is_organizing:
            return {
                "tool": "blah",
                "friendly": "Blah organization already in progress",
                "detailed": f"Cannot start new organization while one is in progress. Current session: {self.session_id}"
            }
        
        # Start organization process
        organization_result = self._start_organization(reason)
        return {
            "tool": "blah",
            "friendly": organization_result.get("friendly", "Organization completed"),
            "detailed": organization_result.get("detailed", "Organization process completed")
        }
    
    def _start_organization(self, reason=""):
        """Start the organization process"""
        if self.is_organizing:
            return {"success": False, "error": "Already organizing"}

        self.is_organizing = True

        try:
            # Capture last user message BEFORE injecting org prompt
            self.last_user_msg_before_org = None
            for msg in reversed(self.app.message_history.get_messages()):
                if msg.get("role") == "user":
                    # Skip system messages and [BLAH FILES] messages
                    content = msg.get("content", "")
                    if not content.startswith("[BLAH FILES]"):
                        self.last_user_msg_before_org = msg
                        break

            # Save archives first
            if not self._save_archives():
                LogUtils.error("[!] Failed to save archives before organization")
                self.is_organizing = False
                return {"success": False, "error": "Failed to save archives"}

            # Create org prompt with new format
            current_tokens = self._get_current_tokens()
            org_prompt = f"""<system-reminder>
⚠️  CONTEXT ARCHIVAL MODE ACTIVATED  ⚠️

THIS IS NOT A DISCUSSION. THIS IS NOT A TASK TO DELEGATE.
YOUR ONLY FOCUS RIGHT NOW IS TO ARCHIVE THIS CONVERSATION.

───────────────────────────────────────────────────────────────────────
WHAT IS HAPPENING:
───────────────────────────────────────────────────────────────────────
Your current conversation context has grown too large ({current_tokens:,}+ tokens).
To prevent AI coherence loss and enable continued work, we must
archive important patterns and decisions into structured memory files.

───────────────────────────────────────────────────────────────────────
WHAT WILL HAPPEN NEXT:
───────────────────────────────────────────────────────────────────────
1. You create/edit markdown files ONLY in: {self.blah_files_dir}
2. Each file contains extracted knowledge from this conversation
3. When finished, end your LAST message with: <promise>BLAHDONE</promise>
4. After that, your ENTIRE context is WIPED
   - All conversation history is deleted
   - You retain only: last user prompt + list of created memory files
   - Future sessions can load these files to recall what was done

───────────────────────────────────────────────────────────────────────
YOUR TASK:
───────────────────────────────────────────────────────────────────────
Analyze this conversation and extract:

  • WHAT WAS DONE - completed work, decisions made
  • WHAT IS BEING DONE - current state, pending items
  • RECENT CONVERSATION HISTORY - key exchanges from the last few turns that led to current state
  • NEXT STEPS - planned work, known issues
  • LEARNED PATTERNS - reusable solutions, gotchas, decisions
  • IMPORTANT CONTEXT - hard-won understanding, design rationale

Focus especially on the most recent exchanges that define the current task state.

───────────────────────────────────────────────────────────────────────
SPECIAL FILE REQUIRED:
───────────────────────────────────────────────────────────────────────
You MUST create a special file called 'next_session_summary.md' that will serve as orientation for the next session. This file should contain:

  • Clear statement about the context wipe and why it happened
  • Main objective of this session
  • Current status and what we're working on
  • Next steps to continue the work
  • Guidance on where to find more detailed information

Use this template for next_session_summary.md:
---
name: next_session_summary
description: Orientation guide for AI after context wipe - main objectives, current status, and next steps
license: Complete terms in LICENSE.txt
---

# Next Session Summary

Your memory was wiped because the session context reached {current_tokens:,}+ tokens to maintain performance and coherence.

## Main Objective
The primary goal of this session is:
- [State the main objective clearly]

## Current Status
What we are currently working on:
- [Item 1]
- [Item 2] 
- [Item 3]

## Next Steps
Immediate next actions:
- [Step 1]
- [Step 2]
- [Step 3]

## Additional Context
For more detailed information about previous work, decisions, and patterns, refer to the [BLAH FILES] listing above and examine the knowledge files as needed.

───────────────────────────────────────────────────────────────────────
CURRENT FILES IN SESSION DIRECTORY:
───────────────────────────────────────────────────────────────────────
BEFORE creating new files, review the existing files in blah_files/:

{os.linesep.join([f"- {f}" for f in os.listdir(self.blah_files_dir) if f.endswith('.md')]) if os.path.exists(self.blah_files_dir) and os.listdir(self.blah_files_dir) else "- No existing .md files in blah_files/"}

───────────────────────────────────────────────────────────────────────
YOUR WORK DIRECTORY:
───────────────────────────────────────────────────────────────────────
{self.blah_files_dir}

⚠️  CRITICAL: ONLY USE blah_files/ FOR YOUR WORK
   - NEVER list or read ANY other directories (including archives/)
   - The archives/ directory is SYSTEM-ONLY AND INACCESSIBLE TO YOU
   - If you need to reference past context, CREATE NEW knowledge files based on your memory
   - DO NOT ATTEMPT TO ACCESS archives/ - IT WILL FAIL

───────────────────────────────────────────────────────────────────────
FILE FORMAT (follow exactly):
───────────────────────────────────────────────────────────────────────
Each file must use this format:

---
name: <short_identifying_name>
description: <2-3 sentences describing file contents for future AI selection>
license: Complete terms in LICENSE.txt
---

# Name: <name>
# Description: <description>
# Session: {self.session_id}
# Created: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}

## Content Here
[Organized patterns, decisions, code examples, etc.]

───────────────────────────────────────────────────────────────────────
GUIDELINES:
───────────────────────────────────────────────────────────────────────
• Target ~15KB per file (not too small, not too large)
• One file may suffice if content is cohesive
• Create 2-5 files if content spans distinct topics
• Use descriptive names: "auth_system.md" not "stuff.md"
• Write descriptions that help future AI choose relevant files
• Focus on information that's hard to re-discover
• Include recent conversation context that led to current task state
• Most importantly: Create 'next_session_summary.md' as your orientation guide
• PREFER UPDATING EXISTING FILES: Review current files first and update them instead of creating duplicates
• Look at file names and descriptions to determine if existing files can be enhanced rather than creating new ones

───────────────────────────────────────────────────────────────────────
START NOW:
───────────────────────────────────────────────────────────────────────
1. First, examine existing files in {self.blah_files_dir}
2. Decide whether to update existing files or create new ones
3. Use write_file or edit_file to manage your knowledge files
4. Create 'next_session_summary.md' as your first priority
5. End your final response with: <promise>BLAHDONE</promise>
</system-reminder>"""

            # Inject self-acknowledgment messages to ensure AI attention
            self._inject_acknowledgment_messages()

            # Set as next prompt to trigger AI processing
            self.app.set_next_prompt(org_prompt)

            colors = Config.colors
            print(f"{colors['cyan']}[*]{colors['reset']} Blah plugin start")
            return {"success": True, "message": "Organization request queued"}

        except Exception as e:
            LogUtils.error(f"Organization start failed: {e}")
            self.is_organizing = False
            return {"success": False, "error": str(e)}

    def _inject_acknowledgment_messages(self):
        """
        Inject self-acknowledgment messages to ensure AI attention before organization.

        This follows message ordering rules:
        - If last message was user: inject assistant acknowledgment, then user org prompt
        - If last message was NOT user: inject user critical notice, then assistant acknowledgment, then user org prompt
        """
        messages = self.app.message_history.get_messages()

        # Get last message role
        last_role = None
        if messages:
            last_role = messages[-1].get("role")

        # Critical state user message (for non-user context)
        critical_user_msg = "CRITICAL SYSTEM STATE. SESSION CONTEXT IS FULL. FOLLOW THE INSTRUCTIONS BELOW TO ORGANIZE THE SESSION NOW."

        # Assistant acknowledgment message
        assistant_ack_msg = (
            "I AM AWARE THAT THE SYSTEM IS IN A CRITICAL STATE. "
            "I WILL FOLLOW THE INSTRUCTIONS BELOW TO ORGANIZE THE SESSION CONTEXT INTO FILES. "
            "IN ORDER TO KEEP TOKEN USAGE AS LOW AS POSSIBLE, I WILL AVOID UNNECESSARY CONVERSATION AND KEEP FOCUSED ON THE FILES CREATION. "
            "I WILL NOT ASK QUESTIONS DURING THIS PROCESS. I AM AUTONOMOUS."
        )

        if last_role == "user":
            # Last was user - just add assistant acknowledgment
            self.app.message_history.add_assistant_message({"content": assistant_ack_msg})
        else:
            # Last was not user (assistant, tool, etc.) - need user message first
            self.app.message_history.add_user_message(critical_user_msg)
            self.app.message_history.add_assistant_message({"content": assistant_ack_msg})

    def _complete_organization(self):
        """Complete the organization process - clear context and add [BLAH FILES]"""
        if not self.is_organizing:
            return

        try:
            # Clear all messages
            self.app.message_history.clear()

            # Restore system prompt (message_history.clear() handles this)
            # The system prompt is restored automatically by clear() method

            # Restore last user message BEFORE organization
            if self.last_user_msg_before_org:
                self.app.message_history.add_user_message(self.last_user_msg_before_org["content"])
            else:
                # Fallback: try to find last user message (shouldn't happen but defensive)
                print("[!] Warning: No saved last user message before organization")

            # Load next_session_summary.md if it exists and add it as a user message
            next_session_file = os.path.join(self.blah_files_dir, "next_session_summary.md")
            if os.path.exists(next_session_file):
                try:
                    with open(next_session_file, 'r', encoding='utf-8') as f:
                        summary_content = f.read()
                    
                    # Add the summary as a user message to provide context
                    self.app.message_history.add_user_message(f"[CONTEXT RESUMPTION]\n\n{summary_content}")
                except Exception as e:
                    LogUtils.warn(f"Could not read next_session_summary.md: {e}")

            # Ensure [BLAH FILES] message
            self._ensure_blah_files_message()

            colors = Config.colors
            print(f"{colors['green']}[✓]{colors['reset']} Blah plugin finish")
            
            # Continue processing with a resume prompt to help AI understand the new state
            resume_prompt = """[SYSTEM NOTICE: CONTEXT ORGANIZATION COMPLETE]

Your context has been successfully organized and cleaned up to maintain coherence. You now have access to:

1. Your original last user prompt (preserved from before organization)
2. A summary of the session state in next_session_summary.md 
3. Other knowledge files in the [BLAH FILES] listing above

Please continue working on the task based on the preserved context and available knowledge files. If you need to reference specific details from the organized knowledge, use read_file to access the relevant .md files."""
            
            # Set this as the next prompt to continue processing
            self.app.set_next_prompt(resume_prompt)

        except Exception as e:
            LogUtils.error(f"Organization completion failed: {e}")

        finally:
            self.is_organizing = False
            self.last_user_msg_before_org = None  # Clear the saved message
    
    # Command handlers
    def _cmd_organize(self, args_str):
        """Handle /blah organize command - same behavior as auto-organization"""
        if self.is_organizing:
            return "Organization already in progress"

        result = self._start_organization("Manual organization requested")
        return result.get("friendly", result.get("error", "Organization failed"))
    
    def _cmd_status(self, args_str):
        """Handle /blah status command"""
        current_tokens = self._get_current_tokens()
        percentage = (current_tokens / self.token_threshold) * 100 if self.token_threshold > 0 else 0
        
        blah_files = self._discover_blah_files()
        archive_count = len([f for f in os.listdir(self.archives_dir) if f.endswith('.txt')]) if os.path.exists(self.archives_dir) else 0
        
        status = f"""Blah Context Plugin Status:

Session: {self.session_id}
Enabled: {self.enabled}
Token Threshold: {self.token_threshold}
Current Tokens: {current_tokens:,} ({percentage:.1f}%)
Auto-organize: {'Triggered' if percentage >= 100 else 'Ready'}

Knowledge Files: {len(blah_files)} (in blah_files/)
Archives: {archive_count} (in archives/)
Session Directory: {self.current_session_dir}

Directory Structure:
  blah_files/  - AI creates knowledge files here
  archives/    - System stores full session (JSON + TXT)

Commands:
/blah organize - Manual organization
/blah cancel   - Cancel stuck organization
/blah status   - Show current settings and status
/blah set-threshold N - Set token threshold
/blah reload   - Refresh file listing
/blah list     - List all blah files with details
/blah stats    - Show comprehensive statistics and efficiency metrics
"""
        return status.strip()
    
    def _cmd_set_threshold(self, args_str):
        """Handle /blah set-threshold command"""
        try:
            new_threshold = int(args_str.strip())
            if new_threshold < 1000:
                return "Threshold must be at least 1000 tokens"
            
            self.token_threshold = new_threshold
            return f"Token threshold set to {new_threshold:,} tokens"
        except ValueError:
            return "Usage: /blah set-threshold <number>\nExample: /blah set-threshold 40000"
    
    def _cmd_reload(self, args_str):
        """Handle /blah reload command"""
        self._ensure_blah_files_message()
        return f"BLAH FILES listing refreshed\nFound {len(self._discover_blah_files())} knowledge files"
    
    def _cmd_cancel(self, args_str):
        """Handle /blah cancel command - cancel any pending organization"""
        if not self.is_organizing:
            return "No organization in progress to cancel"
        
        self.is_organizing = False
        self.organization_reason = ""
        return "Organization cancelled. You can start a new /blah organize when ready."
    
    def _cmd_list(self, args_str):
        """Handle /blah list command"""
        blah_files = self._discover_blah_files()
        archive_count = len([f for f in os.listdir(self.archives_dir) if f.endswith('.txt')]) if os.path.exists(self.archives_dir) else 0
        
        if not blah_files and archive_count == 0:
            return "No blah files or archives available.\nUse /blah organize to create knowledge files from current conversation."
        
        output = f"""Blah Files for Session: {self.session_id}
Directory: {self.current_session_dir}

"""
        
        if blah_files:
            output += "📝 Knowledge Files:\n"
            for file_name, file_info in sorted(blah_files.items()):
                relative_path = os.path.relpath(file_info['path'], os.getcwd())
                file_size = os.path.getsize(file_info['path']) if os.path.exists(file_info['path']) else 0
                
                output += f"\n  📄 {file_name}\n"
                output += f"     Path: {relative_path}\n"
                output += f"     Size: {file_size:,} bytes\n"
                output += f"     Description: {file_info['description']}\n"
        
        if archive_count > 0:
            output += f"\n📁 Archives:\n"
            output += f"     Total: {archive_count} archived conversations\n"
            output += f"     Directory: archives/\n"
            output += f"     Search with: grep archives/compacted_*.txt\n"
        
        return output.strip()
    
    def _estimate_file_tokens(self, file_path):
        """Estimate tokens for a single file using the same estimator as messages"""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Create a mock message structure like the estimator expects
            mock_message = {
                "role": "user",
                "content": content
            }
            
            # Simple 4 chars per token estimation (good enough for stats)
            return len(content) // 4
        except Exception:
            return 0
    
    def _cmd_stats(self, args_str):
        """Handle /blah stats command with comprehensive statistics"""
        # Get current context info
        current_tokens = self._get_current_tokens()
        
        # Analyze blah files
        blah_files = self._discover_blah_files()
        blah_tokens = 0
        blah_bytes = 0
        file_details = []
        
        for file_name, file_info in blah_files.items():
            if os.path.exists(file_info['path']):
                file_bytes = os.path.getsize(file_info['path'])
                file_tokens = self._estimate_file_tokens(file_info['path'])
                
                blah_bytes += file_bytes
                blah_tokens += file_tokens
                
                file_details.append({
                    'name': file_name,
                    'path': file_info['path'],
                    'bytes': file_bytes,
                    'tokens': file_tokens
                })
        
        # Analyze archives
        archive_bytes = 0
        archive_tokens = 0
        archive_count = 0
        
        if os.path.exists(self.archives_dir):
            for filename in os.listdir(self.archives_dir):
                if filename.endswith('.txt'):
                    archive_path = os.path.join(self.archives_dir, filename)
                    if os.path.exists(archive_path):
                        file_bytes = os.path.getsize(archive_path)
                        file_tokens = self._estimate_file_tokens(archive_path)
                        
                        archive_bytes += file_bytes
                        archive_tokens += file_tokens
                        archive_count += 1
        
        # Calculate totals and efficiency
        total_bytes = blah_bytes + archive_bytes
        total_tokens = blah_tokens + archive_tokens
        
        # Efficiency metrics
        context_reduction = 0
        if total_tokens > 0 and current_tokens > 0:
            context_reduction = ((total_tokens - current_tokens) / total_tokens) * 100
        
        # Format output
        output = f"""📊 Blah Context Statistics
Session: {self.session_id}
Directory: {self.current_session_dir}

🧠 Active Context:
   Current Tokens: {current_tokens:,}
   Threshold: {self.token_threshold:,}
   Usage: {(current_tokens/self.token_threshold)*100:.1f}%

📝 Knowledge Files:
   Files: {len(blah_files)}
   Bytes: {blah_bytes:,}
   Tokens: {blah_tokens:,}
   Average per file: {blah_tokens//len(blah_files) if blah_files else 0:,} tokens

"""
        
        if file_details:
            output += "   File Details:\n"
            for detail in sorted(file_details, key=lambda x: x['tokens'], reverse=True):
                relative_path = os.path.relpath(detail['path'], os.getcwd())
                output += f"     • {detail['name']}: {detail['tokens']:,} tokens ({detail['bytes']:,} bytes)\n"
        
        output += f"""
📁 Archives:
   Conversations: {archive_count}
   Bytes: {archive_bytes:,}
   Tokens: {archive_tokens:,}
   Average per archive: {archive_tokens//archive_count if archive_count else 0:,} tokens

💾 Total Storage:
   Bytes: {total_bytes:,}
   Tokens: {total_tokens:,}

⚡ Efficiency:
   Context Reduction: {context_reduction:.1f}% (how much smaller active context is vs stored knowledge)
   Storage Efficiency: {current_tokens if total_tokens > 0 else 0} active tokens vs {total_tokens} stored tokens
   Total Knowledge Available: {total_tokens:,} tokens for selective loading

🎯 Performance Target:
   Goal: Stay under 100k active tokens while having millions of stored tokens available
   Current: {current_tokens:,} active tokens with {total_tokens:,} stored tokens available
"""
        
        return output.strip()
    
    # Hook handlers
    def _before_compaction(self):
        """Hook called before traditional compaction"""
        # Only interfere with compaction if explicitly enabled via environment variable
        if not self.before_compaction_hook_enabled:
            return True  # Allow traditional compaction
        
        if not self.enabled or self.is_organizing:
            return True  # Allow traditional compaction
        
        # Check if we should organize instead
        if self._check_auto_organize():
            result = self._start_organization(f"Auto-organize triggered at {self._get_current_tokens()} tokens")
            if result.get("success"):
                colors = Config.colors
                print(f"{colors['cyan']}[*]{colors['reset']} Blah plugin start (auto)")
                return False  # Skip traditional compaction
        
        return True  # Allow traditional compaction
    
    def _after_ai_processing(self, has_tool_calls):
        """Hook called after AI processing - check for BLAHDONE signal"""
        # Check threshold after each AI message
        if self._check_auto_organize() and not self.is_organizing:
            result = self._start_organization(f"Auto-organize triggered at {self._get_current_tokens()} tokens")
            if result.get("success"):
                colors = Config.colors
                print(f"{colors['cyan']}[*]{colors['reset']} Blah plugin start (auto)")
        
        if not self.is_organizing:
            return None
        
        # Get last assistant message to check for completion promise
        messages = self.app.message_history.get_messages()
        last_assistant_content = ""
        
        for msg in reversed(messages):
            if msg.get("role") == "assistant":
                content = msg.get("content", "")
                if content:
                    last_assistant_content = content
                    break
        
        if "<promise>BLAHDONE</promise>" in last_assistant_content:
            # Organization complete - clear context and add [BLAH FILES]
            self._complete_organization()
        
        return None
    
    def _before_user_prompt(self):
        """Hook called before each user prompt"""
        # Check auto-organize threshold and trigger if needed
        if self._check_auto_organize():
            result = self._start_organization(f"Auto-organize triggered at {self._get_current_tokens()} tokens")
            if result.get("success"):
                colors = Config.colors
                print(f"{colors['cyan']}[*]{colors['reset']} Blah plugin start (auto)")
        
        # Ensure [BLAH FILES] message exists
        self._ensure_blah_files_message()
    
    def _after_file_write(self, path, content):
        """Hook called after any file is written - refresh [BLAH FILES] if it's a blah file"""
        # Check if the written file is in blah_files/ directory and is a .md file
        if (self.blah_files_dir and 
            path.startswith(self.blah_files_dir) and 
            path.endswith('.md')):
            # Force update the [BLAH FILES] message to include the new/updated file
            self._update_blah_files_message()
    
    def _update_blah_files_message(self):
        """Force update the [BLAH FILES] message in history (replace if exists)"""
        if not self.current_session_dir:
            return
        
        blah_text = self._generate_blah_files_message()
        
        # Find and replace existing [BLAH FILES] message
        for idx, msg in enumerate(self.app.message_history.messages):
            content = msg.get("content", "")
            if msg.get("role") == "user" and content.startswith("[BLAH FILES]"):
                self.app.message_history.messages[idx]["content"] = blah_text
                return
        
        # If no existing message found, add after system message at index 1
        self.app.message_history.messages.insert(1, {
            "role": "user", 
            "content": blah_text
        })
    
    def _before_approval_prompt(self, tool_name: str, arguments: dict) -> bool | None:
        """
        Hook called before approval prompt. Return:
        - True  -> auto-approve
        - False -> auto-deny
        - None  -> ask user
        """
        # Auto-approve file operations within blah_files/ directory
        if tool_name in ['write_file', 'edit_file']:
            # Get the path from arguments
            path = arguments.get('path', '')
            
            # Check if the path is within blah_files/ directory
            if (self.blah_files_dir and 
                path.startswith(self.blah_files_dir)):
                return True  # Auto-approve file operations in blah_files directory
        
        # For all other operations, return None to ask user
        return None
    
    def _after_messages_set(self, messages):
        """
        Hook called after messages are set (e.g., after compaction).
        Clear is_organizing flag if compaction wiped the organization context.
        """
        # If we were organizing but the org prompt is no longer in messages,
        # compaction likely happened and wiped our context
        if self.is_organizing:
            # Check if any message contains our org prompt markers
            org_wiped = True
            for msg in messages:
                content = msg.get("content", "")
                if "CONTEXT ARCHIVAL MODE" in content or "SILENCE ENFORCEMENT" in content:
                    org_wiped = False
                    break
            
            if org_wiped:
                colors = Config.colors
                print(f"{colors['yellow']}[!]{colors['reset']} Blah organization cancelled by compaction")
                self.is_organizing = False
                self.organization_reason = ""
    
    def _cmd_handler(self, args_str):
        """Handle all /blah commands (like skills plugin)"""
        args = args_str.strip().split(maxsplit=1) if args_str.strip() else []
        
        if not args:
            return "Use: /blah organize|status|set-threshold|reload|list|stats|help"
        
        command = args[0]
        command_args = args[1] if len(args) > 1 else ""
        
        if command == "organize":
            return self._cmd_organize(command_args)
        elif command == "cancel":
            return self._cmd_cancel(command_args)
        elif command == "status":
            return self._cmd_status(command_args)
        elif command == "set-threshold":
            return self._cmd_set_threshold(command_args)
        elif command == "reload":
            return self._cmd_reload(command_args)
        elif command == "list":
            return self._cmd_list(command_args)
        elif command == "stats":
            return self._cmd_stats(command_args)
        elif command == "help":
            return """Blah Context Plugin Commands:

/blah organize      - Manual organization of current conversation
/blah cancel         - Cancel any pending organization (use if stuck)
/blah status         - Show current settings and token usage
/blah set-threshold N - Set auto-organization token threshold
/blah reload         - Refresh [BLAH FILES] listing
/blah list           - List all blah files with paths and descriptions
/blah stats          - Show comprehensive statistics and efficiency metrics
/blah help           - Show this help message

Directory Structure:
  blah_files/  - AI creates/updates knowledge files here
  archives/    - System stores full session (JSON + TXT) - DO NOT ACCESS

The plugin maintains AI coherence by organizing conversation knowledge
when context grows beyond token threshold (default: 100,000 tokens).
"""
        else:
            return f"Unknown blah command: {command}. Use /blah help for usage."

    def cleanup(self):
        """Cleanup plugin resources"""
        self.is_organizing = False


def create_plugin(ctx):
    """Create blah context plugin"""
    
    # Create plugin instance
    plugin = BlahContextPlugin(ctx)
    
    # Register tool
    ctx.register_tool(
        name='blah',
        fn=plugin._blah_tool,
        description='Request blah organization process to maintain AI coherence over long sessions',
        parameters={
            'reason': {'type': 'string', 'description': 'Reason why organization is needed'}
        },
        auto_approved=True
    )
    
    # Register single command handler (like skills plugin)
    ctx.register_command("blah", plugin._cmd_handler, description="Blah context management commands")
    
    # Register hooks
    ctx.register_hook('before_compaction', plugin._before_compaction)
    ctx.register_hook('after_ai_processing', plugin._after_ai_processing)
    ctx.register_hook('before_user_prompt', plugin._before_user_prompt)
    ctx.register_hook('after_file_write', plugin._after_file_write)
    ctx.register_hook('before_approval_prompt', plugin._before_approval_prompt)
    ctx.register_hook('after_messages_set', plugin._after_messages_set)
    
    if Config.debug():
        print(f"[+] Blah Context plugin loaded")
        print(f"  - Session: {plugin.session_id}")
        print(f"  - Directory: {plugin.current_session_dir}")
        print(f"  - blah_files/: {plugin.blah_files_dir}")
        print(f"  - archives/: {plugin.archives_dir}")
        print(f"  - Token threshold: {plugin.token_threshold}")
        print(f"  - /blah commands available (organize, cancel, status, set-threshold, reload, list, stats, help)")
        print(f"  - blah tool registered for AI")
    
    return {"cleanup": plugin.cleanup}