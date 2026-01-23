"""
Socket Server - Simple Unix domain socket for external control
Inspired by mpv IPC: minimal, straightforward, practical
"""

import os
import sys
import json
import socket
import threading
import fcntl
import select
import subprocess
import secrets
import signal
import base64
from typing import Optional, Dict, Any, List

from aicoder.core.config import Config
from aicoder.utils.log import LogUtils, LogOptions
from aicoder.utils.temp_file_utils import create_temp_file


# Error codes
ERR_NOT_PROCESSING = 1001
ERR_UNKNOWN_CMD = 1002
ERR_MISSING_ARG = 1003
ERR_INVALID_ARG = 1004
ERR_PERMISSION = 1101
ERR_IO_ERROR = 1201
ERR_INTERNAL = 1301

# Limits
MAX_INJECT_TEXT_SIZE = 10 * 1024 * 1024  # 10MB


def response(data=None, error_code=None, error_msg=None):
    """Build consistent JSON response for socket API

    Args:
        data: Response data for success
        error_code: Error code number
        error_msg: Error message

    Returns:
        JSON string
    """
    if error_code:
        return json.dumps({
            "status": "error",
            "code": error_code,
            "message": error_msg
        })
    return json.dumps({
        "status": "success",
        "data": data
    })


class SocketServer:
    """
    Simple Unix socket server for controlling AI Coder
    One client at a time, simple request-response
    """

    def __init__(self, aicoder_instance):
        self.aicoder = aicoder_instance
        self.socket_path: Optional[str] = None
        self.server_socket: Optional[socket.socket] = None
        self.server_thread: Optional[threading.Thread] = None
        self.is_running = False
        self.lock = threading.Lock()

    def start(self) -> None:
        """Start the socket server"""
        if self.is_running:
            return

        # Check for fixed socket path first
        self.socket_path = os.environ.get("AICODER_SOCKET_IPC_FILE")

        if self.socket_path:
            # Use provided path directly (no tmux logic needed)
            tmpdir = os.path.dirname(self.socket_path)
        else:
            # Default behavior: generate path with tmux pane id
            tmpdir = (
                os.environ.get("AICODER_SOCKET_DIR") or
                os.environ.get("TMPDIR") or
                "/tmp"
            )

            # Generate random component for uniqueness (6 chars)
            random_id = os.urandom(3).hex()

            # Simple socket path: <tmpdir>/aicoder-<pid>-<pane_id>-<random>.socket
            pid = os.getpid()
            tmux_pane = os.environ.get("TMUX_PANE", "0")

            # Get just pane name (e.g., "%1" or just → basename)
            if tmux_pane != "0":
                tmux_pane = os.path.basename(tmux_pane)
                # Remove % to get just numeric part (e.g., "%1" → "1")
                tmux_pane = tmux_pane.replace("%", "")

            self.socket_path = f"{tmpdir}/aicoder-{pid}-{tmux_pane}-{random_id}.socket"

        try:
            # Ensure directory exists
            os.makedirs(tmpdir, exist_ok=True)

            # Remove old socket if exists
            if os.path.exists(self.socket_path):
                os.unlink(self.socket_path)

            # Create Unix socket
            self.server_socket = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.server_socket.bind(self.socket_path)
            self.server_socket.listen(1)

            # Owner only permissions
            os.chmod(self.socket_path, 0o600)

            self.is_running = True

            # Start server thread
            self.server_thread = threading.Thread(target=self._server_loop, daemon=True)
            self.server_thread.start()

            # Always print socket path (simple log line)
            LogUtils.print(
                f"[Socket] {self.socket_path}"
            )

        except Exception as e:
            # Print socket path on error for troubleshooting
            LogUtils.error(
                f"{Config.colors['cyan']}[Socket]{Config.colors['reset']} "
                f"Failed to create socket at: {self.socket_path}"
            )
            LogUtils.error(
                f"{Config.colors['red']}[Socket]{Config.colors['reset']} "
                f"Error: {e}"
            )
            self.is_running = False

    def stop(self) -> None:
        """Stop the socket server"""
        self.is_running = False

        if self.server_socket:
            try:
                self.server_socket.close()
            except Exception:
                pass
            self.server_socket = None

        if self.server_thread:
            self.server_thread.join(timeout=1.0)
            self.server_thread = None

        # Clean up socket file
        if self.socket_path and os.path.exists(self.socket_path):
            try:
                os.unlink(self.socket_path)
            except Exception:
                pass

    def _server_loop(self) -> None:
        """Main server loop"""
        while self.is_running:
            try:
                self.server_socket.settimeout(0.5)

                try:
                    client_socket, _ = self.server_socket.accept()
                except socket.timeout:
                    continue



                # Handle client
                self._handle_client(client_socket)

            except Exception as e:
                if self.is_running and Config.debug():
                    LogUtils.warn(f"[Socket] Error: {e}")

    def _handle_client(self, client_socket: socket.socket) -> None:
        """Handle one client connection"""
        try:
            # Read command
            command = self._read_line(client_socket, timeout=3.0)

            if not command:
                self._send_line(client_socket, response(None, error_code=ERR_INTERNAL, error_msg="Empty command"))
                client_socket.close()
                return

            if Config.debug():
                LogUtils.debug(f"[Socket] Cmd: {command}")

            # Execute
            resp = self._execute_command(command)

            # Send response
            self._send_line(client_socket, resp)

        except socket.timeout:
            self._send_line(client_socket, response(None, error_code=ERR_INTERNAL, error_msg="Timeout"))
        except Exception as e:
            self._send_line(client_socket, response(None, error_code=ERR_INTERNAL, error_msg=str(e)))
        finally:
            try:
                client_socket.close()
            except Exception:
                pass

    def _read_line(self, sock: socket.socket, timeout: float) -> Optional[str]:
        """Read one line with timeout"""
        sock.settimeout(timeout)
        data = b""

        try:
            while True:
                chunk = sock.recv(1024)
                if not chunk:
                    break
                data += chunk
                # Check if we have complete line
                if b"\n" in data:
                    line, _, _ = data.partition(b"\n")
                    return line.decode("utf-8").strip()

            return data.decode("utf-8").strip() if data else None

        except socket.timeout:
            return None
        except Exception as e:
            if Config.debug():
                LogUtils.warn(f"[Socket] Read error: {e}")
            return None

    def _send_line(self, sock: socket.socket, line: str) -> None:
        """Send one line"""
        try:
            sock.sendall((line + "\n").encode("utf-8"))
        except Exception as e:
            if Config.debug():
                LogUtils.warn(f"[Socket] Send error: {e}")

    def _execute_command(self, command: str) -> str:
        """Execute a command and return response"""
        command = command.strip()
        if not command:
            return response(None, error_code=ERR_INTERNAL, error_msg="Empty command")

        # Split into parts
        parts = command.split(None, 1)
        cmd = parts[0]
        args = parts[1] if len(parts) > 1 else ""

        # Dispatch
        handlers = {
            "is_processing": self._cmd_is_processing,
            "yolo": self._cmd_yolo,
            "detail": self._cmd_detail,
            "sandbox": self._cmd_sandbox,
            "status": self._cmd_status,
            "stop": self._cmd_stop,
            "messages": self._cmd_messages,
            "inject": self._cmd_inject,
            "inject-text": self._cmd_inject_text,
            "process": self._cmd_process,
            "command": self._cmd_command,
            "save": self._cmd_save,
            "kill": self._cmd_kill,
            "quit": self._cmd_quit,
        }

        handler = handlers.get(cmd)
        if not handler:
            return response(
                None, error_code=ERR_UNKNOWN_CMD, error_msg=f"Unknown command: {cmd}"
            )

        try:
            result = handler(args)
            # If result is already JSON string (old format), parse it
            # If result is dict, it's already a JSON response
            if isinstance(result, str):
                try:
                    parsed = json.loads(result)
                    if "status" in parsed:
                        # Already JSON response format, return as-is
                        return result
                except json.JSONDecodeError:
                    pass
            return result
        except Exception as e:
            error_msg = str(e)
            if Config.debug():
                LogUtils.debug(f"[Socket] EXCEPTION in _cmd_inject: {error_msg}")
            LogUtils.printc(f"[Socket] Inject error: {error_msg}", color="red")
            return response(
                None, error_code=ERR_INTERNAL, error_msg=error_msg
            )

    # ========================================================================
    # Command Handlers
    # ========================================================================

    def _cmd_is_processing(self, args: str) -> str:
        """Check if AI is processing"""
        is_proc = False

        with self.lock:
            if hasattr(self.aicoder, "session_manager"):
                is_proc = self.aicoder.session_manager.is_processing
            elif hasattr(self.aicoder, "is_processing"):
                is_proc = self.aicoder.is_processing

        return response({"processing": is_proc})

    def _cmd_yolo(self, args: str) -> str:
        """Get or set YOLO mode"""
        args = args.strip()

        if not args or args == "status":
            return response({"enabled": Config.yolo_mode()})

        if args == "toggle":
            current = Config.yolo_mode()
            Config.set_yolo_mode(not current)
            new_state = not current
            return response({"enabled": new_state, "message": f"YOLO {'enabled' if new_state else 'disabled'}"})

        if args == "on":
            Config.set_yolo_mode(True)
            return response({"enabled": True, "message": "YOLO enabled"})

        if args == "off":
            Config.set_yolo_mode(False)
            return response({"enabled": False, "message": "YOLO disabled"})

        return response(
            None, error_code=ERR_INVALID_ARG, error_msg="Usage: yolo [on|off|status|toggle]"
        )

    def _cmd_detail(self, args: str) -> str:
        """Get or set detail mode"""
        args = args.strip()

        if not args or args == "status":
            return response({"enabled": Config.detail_mode()})

        if args == "toggle":
            current = Config.detail_mode()
            Config.set_detail_mode(not current)
            new_state = not current
            return response({"enabled": new_state, "message": f"Detail mode {'enabled' if new_state else 'disabled'}"})

        if args == "on":
            Config.set_detail_mode(True)
            return response({"enabled": True, "message": "Detail mode enabled"})

        if args == "off":
            Config.set_detail_mode(False)
            return response({"enabled": False, "message": "Detail mode disabled"})

        return response(
            None, error_code=ERR_INVALID_ARG, error_msg="Usage: detail [on|off|status|toggle]"
        )

    def _cmd_sandbox(self, args: str) -> str:
        """Get or set sandbox"""
        args = args.strip()

        if not args or args == "status":
            enabled = not Config.sandbox_disabled()
            return response({"enabled": enabled})

        if args == "toggle":
            current_disabled = Config.sandbox_disabled()
            new_disabled = not current_disabled
            Config.set_sandbox_disabled(new_disabled)
            return response({"enabled": not new_disabled, "message": f"Sandbox {'enabled' if not new_disabled else 'disabled'}"})

        if args == "on":
            Config.set_sandbox_disabled(False)
            return response({"enabled": True, "message": "Sandbox enabled"})

        if args == "off":
            Config.set_sandbox_disabled(True)
            return response({"enabled": False, "message": "Sandbox disabled"})

        return response(
            None, error_code=ERR_INVALID_ARG, error_msg="Usage: sandbox [on|off|status|toggle]"
        )

    def _cmd_status(self, args: str) -> str:
        """Get full status"""
        messages = self.aicoder.message_history.get_messages()

        is_proc = False
        with self.lock:
            if hasattr(self.aicoder, "session_manager"):
                is_proc = self.aicoder.session_manager.is_processing
            elif hasattr(self.aicoder, "is_processing"):
                is_proc = self.aicoder.is_processing

        return response({
            "processing": is_proc,
            "yolo_enabled": Config.yolo_mode(),
            "detail_enabled": Config.detail_mode(),
            "sandbox_enabled": not Config.sandbox_disabled(),
            "messages": len(messages),
        })

    def _cmd_stop(self, args: str) -> str:
        """Stop current processing"""
        stopped = False

        with self.lock:
            if hasattr(self.aicoder, "session_manager"):
                if self.aicoder.session_manager.is_processing:
                    self.aicoder.session_manager.is_processing = False
                    stopped = True
            elif hasattr(self.aicoder, "is_processing"):
                if self.aicoder.is_processing:
                    self.aicoder.is_processing = False
                    stopped = True

        if stopped:
            return response({"stopped": True, "message": "Processing stopped"})

        return response(
            None, error_code=ERR_NOT_PROCESSING, error_msg="Not currently processing"
        )

    def _cmd_messages(self, args: str) -> str:
        """List or count messages"""
        args = args.strip()

        if args == "count":
            messages = self.aicoder.message_history.get_messages()
            return response({
                "total": len(messages),
                "user": sum(1 for m in messages if m.get("role") == "user"),
                "assistant": sum(1 for m in messages if m.get("role") == "assistant"),
                "system": sum(1 for m in messages if m.get("role") == "system"),
                "tool": sum(1 for m in messages if m.get("role") == "tool"),
            })

        # Return all messages
        messages = self.aicoder.message_history.get_messages()
        return response({
            "messages": messages,
            "count": len(messages)
        })

    def _cmd_inject(self, args: str) -> str:
        """Inject message from $EDITOR - non-blocking, returns immediately"""
        try:
            if not os.environ.get("TMUX"):
                error_msg = "This feature only works inside a tmux environment"
                return response(
                    None, error_code=ERR_IO_ERROR, error_msg=error_msg
                )

            editor = os.environ.get("EDITOR", "nano")
            random_suffix = secrets.token_hex(4)
            temp_file = create_temp_file(f"aicoder-inject-{random_suffix}", ".md")

            with open(temp_file, "w", encoding="utf-8") as f:
                f.write("")

            sync_point = f"inject_done_{random_suffix}"
            window_name = f"inject_{random_suffix}"

            tmux_cmd = f'tmux new-window -n "{window_name}" \'bash -c "{editor} {temp_file}; tmux wait-for -S {sync_point}"\''

            # Execute tmux command to open editor
            subprocess.Popen(tmux_cmd, shell=True)

            # Start background thread to wait for editor and inject
            def wait_and_inject():
                try:
                    subprocess.run(f"tmux wait-for {sync_point}", shell=True, capture_output=True, text=True)

                    with open(temp_file, "r", encoding="utf-8") as f:
                        content = f.read().strip()

                    if content:
                        self.aicoder.message_history.insert_user_message_at_appropriate_position(content)
                        if Config.debug():
                            LogUtils.debug(f"[Socket] Injected: {repr(content[:100])}")
                except Exception as e:
                    if Config.debug():
                        LogUtils.debug(f"[Socket] Background inject error: {e}")
                finally:
                    try:
                        os.remove(temp_file)
                    except:
                        pass

            thread = threading.Thread(target=wait_and_inject, daemon=True)
            thread.start()

            return response({
                "injected": False,
                "message": "Editor opened. Message will be injected when you save and exit."
            })

        except Exception as e:
            error_msg = str(e)
            LogUtils.printc(f"[Socket] Inject error: {error_msg}", color="red")
            return response(
                None, error_code=ERR_INTERNAL, error_msg=error_msg
            )

    def _cmd_inject_text(self, args: str) -> str:
        """Inject base64-encoded text directly into conversation"""
        args = args.strip()

        if not args:
            return response(
                None, error_code=ERR_MISSING_ARG, error_msg="Missing base64 encoded text"
            )

        try:
            # Decode base64
            decoded_bytes = base64.b64decode(args, validate=True)

            # Check size limit
            if len(decoded_bytes) > MAX_INJECT_TEXT_SIZE:
                return response(
                    None, error_code=ERR_INVALID_ARG,
                    error_msg=f"Text too large: {len(decoded_bytes)} bytes (max: {MAX_INJECT_TEXT_SIZE})"
                )

            # Decode as UTF-8
            text = decoded_bytes.decode("utf-8")

            # Insert into message history
            self.aicoder.message_history.insert_user_message_at_appropriate_position(text)

            if Config.debug():
                preview = repr(text[:100]) if len(text) > 100 else repr(text)
                LogUtils.debug(f"[Socket] inject-text: {preview}")

            return response({
                "injected": True,
                "length": len(text)
            })

        except ValueError as e:
            # Invalid base64
            return response(
                None, error_code=ERR_INVALID_ARG, error_msg="Invalid base64 encoding"
            )
        except UnicodeDecodeError as e:
            # Valid base64 but not UTF-8
            return response(
                None, error_code=ERR_INVALID_ARG, error_msg="Invalid UTF-8 encoding"
            )
        except Exception as e:
            error_msg = str(e)
            LogUtils.printc(f"[Socket] inject-text error: {error_msg}", color="red")
            return response(
                None, error_code=ERR_INTERNAL, error_msg=error_msg
            )

    def _cmd_command(self, args: str) -> str:
        """Execute any slash command via socket"""
        args = args.strip()

        if not args:
            return response(
                None, error_code=ERR_MISSING_ARG, error_msg="Missing command"
            )

        if not args.startswith("/"):
            return response(
                None, error_code=ERR_INVALID_ARG, error_msg="Command must start with '/'"
            )

        try:
            # Execute the command using existing command handler
            result = self.aicoder.command_handler.handle_command(args)

            if result.should_quit:
                # Schedule quit but return response first
                import threading
                def delayed_quit():
                    self.aicoder.is_running = False
                threading.Thread(target=delayed_quit, daemon=True).start()

            return response({
                "executed": args,
                "should_quit": result.should_quit,
                "run_api_call": result.run_api_call
            })

        except Exception as e:
            error_msg = str(e)
            LogUtils.printc(f"[Socket] command error: {error_msg}", color="red")
            return response(
                None, error_code=ERR_INTERNAL, error_msg=error_msg
            )

    def _cmd_process(self, args: str) -> str:
        """Trigger AI processing (runs in background thread)"""
        # Check if already processing to prevent concurrent calls
        is_proc = False
        with self.lock:
            if hasattr(self.aicoder, "session_manager"):
                is_proc = self.aicoder.session_manager.is_processing
            elif hasattr(self.aicoder, "is_processing"):
                is_proc = self.aicoder.is_processing

        if is_proc:
            return response(
                None, error_code=ERR_NOT_PROCESSING,
                error_msg="Already processing, please wait"
            )

        # Start processing in background thread (non-blocking)
        def process_in_background():
            try:
                self.aicoder.session_manager.process_with_ai()
            except Exception as e:
                LogUtils.error(f"[Socket] Process error: {e}")

        thread = threading.Thread(target=process_in_background, daemon=True)
        thread.start()

        if Config.debug():
            LogUtils.debug("[Socket] process: started AI processing in background")

        return response({
            "processing": True,
            "message": "Started processing"
        })

    def _cmd_save(self, args: str) -> str:
        """Save session to file"""
        path = args.strip() if args else None

        try:
            if not path:
                # Default path in ./.aicoder/sessions
                import time
                timestamp = time.strftime("%Y-%m-%d_%H-%M-%S")
                save_dir = os.path.join(os.getcwd(), ".aicoder", "sessions")
                os.makedirs(save_dir, exist_ok=True)
                path = os.path.join(save_dir, f"session-{timestamp}.json")

            # Validate path (sandbox check)
            abs_path = os.path.abspath(path)
            home = os.path.expanduser("~")
            if not abs_path.startswith(home) and not abs_path.startswith("/tmp"):
                return response(
                    None, error_code=ERR_PERMISSION, error_msg="Path outside allowed directories"
                )

            # Save
            messages = self.aicoder.message_history.get_messages()
            with open(path, "w") as f:
                json.dump({"messages": messages}, f, indent=2)

            # Print path to screen
            LogUtils.print(f"Session saved to: {path}")

            return response({"saved": True, "path": path})

        except Exception as e:
            return response(
                None, error_code=ERR_IO_ERROR, error_msg=str(e)
            )

    def _cmd_kill(self, args: str) -> str:
        """Kill AI Coder immediately"""
        LogUtils.print("Killing AI Coder...")
        # Kill process for immediate exit
        os.kill(os.getpid(), signal.SIGKILL)
        return response({"killed": True, "message": "Terminating process"})

    def _cmd_quit(self, args: str) -> str:
        """Quit AI Coder gracefully"""
        LogUtils.print("Quitting AI Coder...")
        # Save session and terminate process immediately
        if hasattr(self.aicoder, 'save_session'):
            self.aicoder.save_session()
        # Perform proper shutdown sequence and exit
        self.aicoder.shutdown()
        sys.exit(0)
        # Note: This return is never reached due to sys.exit, but included for completeness
        return response({"quit": True, "message": "Shutting down"})
