"""
Remote Control Plugin - Web-based collaborative chat interface for AI Coder

Features:
- HTTP server with chat UI (port 8000 default)
- Multi-user collaborative mode (anyone with secret can connect)
- User identification (username or IP)
- 3-strike auth security
- Yolo mode (auto-approve all tools)

Environment Variables:
- REMOTE_CONTROL_SECRET: Authentication secret (optional, can also set via command)
- REMOTE_CONTROL_HOST: Host to bind (default: 127.0.0.1)
- REMOTE_CONTROL_PORT: Port to bind (default: 8000)

Commands:
- /remote-control - Start remote control mode
- /remote-control secret <secret> - Set secret for session
"""

import os
import sys
import json
import threading
import signal
import time
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import parse_qs, urlparse
from typing import Dict, Any, Optional, List

from aicoder.core.config import Config
from aicoder.utils.log import LogUtils

# Store original LogUtils.print for monkey patching
_original_log_print = None


# Global state
class RemoteControlState:
    is_active = False
    http_server: Optional[ThreadingHTTPServer] = None
    server_thread: Optional[threading.Thread] = None
    failed_auth_attempts = 0
    secret: Optional[str] = None  # Set via command or env var
    host = "127.0.0.1"
    port = 8000
    is_processing = False
    pending_message: Optional[str] = None
    pending_message_user: Optional[str] = None
    message_history_with_sender: List[Dict] = []
    last_history_index = 0
    stop_requested_by: Optional[str] = None
    auth_tokens: set = set()  # Multiple valid tokens for multi-user support


state = RemoteControlState()

# Reference to app (set when plugin loads)
_app = None
_yolo_mode_was_enabled = False


def get_secret() -> Optional[str]:
    """Get secret from state (command) or env var (command has priority)"""
    if state.secret:
        return state.secret
    return os.environ.get("REMOTE_CONTROL_SECRET")


def get_client_ip(handler) -> str:
    """Get client IP address from request"""
    # Check for X-Forwarded-For header (proxy/load balancer)
    forwarded = handler.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    return handler.client_address[0]


def get_username_from_request(handler) -> str:
    """Get username from request header or fall back to IP"""
    username = handler.headers.get("X-Username")
    if username and username.strip():
        return username.strip()
    return get_client_ip(handler)


# HTML UI Template
HTML_UI = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>AI Coder Remote Control</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        html, body {
            height: 100%;
            overflow: hidden;
        }
        body {
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            background: #f0f2f5;
            display: flex;
            flex-direction: column;
        }
        
        /* Auth Screen */
        #auth-screen {
            display: flex;
            align-items: center;
            justify-content: center;
            height: 100vh;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
        }
        .auth-box {
            background: white;
            padding: 40px;
            border-radius: 12px;
            box-shadow: 0 10px 40px rgba(0,0,0,0.2);
            width: 100%;
            max-width: 400px;
        }
        .auth-box h1 {
            color: #333;
            margin-bottom: 10px;
            font-size: 24px;
        }
        .auth-box p {
            color: #666;
            margin-bottom: 24px;
        }
        .auth-box input {
            width: 100%;
            padding: 12px 16px;
            border: 2px solid #e1e1e1;
            border-radius: 8px;
            font-size: 16px;
            margin-bottom: 16px;
            transition: border-color 0.2s;
        }
        .auth-box input:focus {
            outline: none;
            border-color: #667eea;
        }
        .auth-box button {
            width: 100%;
            padding: 14px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 8px;
            font-size: 16px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s;
        }
        .auth-box button:hover {
            transform: scale(1.02);
        }
        .auth-box .error {
            color: #e74c3c;
            margin-bottom: 16px;
            padding: 12px;
            background: #fdeaea;
            border-radius: 6px;
            display: none;
        }
        
        /* Chat Screen */
        #chat-screen {
            display: none;
            flex-direction: column;
            height: 100%;
            flex: 1;
        }
        .chat-header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 16px 24px;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }
        .chat-header h1 {
            font-size: 18px;
            font-weight: 600;
        }
        .status-indicator {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 14px;
        }
        .status-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: #2ecc71;
            animation: pulse 2s infinite;
        }
        .status-dot.processing {
            background: #f39c12;
        }
        @keyframes pulse {
            0%, 100% { opacity: 1; }
            50% { opacity: 0.5; }
        }
        
        .chat-messages {
            flex: 1;
            overflow-y: auto;
            overflow-x: hidden;
            padding: 20px;
            display: flex;
            flex-direction: column;
            gap: 12px;
            min-width: 0;
        }
        .message {
            max-width: 70%;
            padding: 12px 16px;
            border-radius: 12px;
            line-height: 1.5;
            position: relative;
            word-wrap: break-word;
            overflow-wrap: break-word;
        }
        .message-user {
            align-self: flex-end;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border-bottom-right-radius: 4px;
        }
        .message-ai {
            align-self: flex-start;
            background: white;
            color: #333;
            border-bottom-left-radius: 4px;
            box-shadow: 0 1px 2px rgba(0,0,0,0.1);
        }
        .message-system {
            align-self: center;
            background: #e8e8e8;
            color: #666;
            font-size: 13px;
            padding: 8px 16px;
        }
        .message-sender {
            font-size: 11px;
            opacity: 0.8;
            margin-bottom: 4px;
        }
        .message-content {
            white-space: pre-wrap;
            word-wrap: break-word;
        }
        
        .chat-input-area {
            background: white;
            padding: 16px 24px;
            display: flex;
            gap: 12px;
            border-top: 1px solid #e1e1e1;
            flex-shrink: 0;
            width: 100%;
        }
        .chat-input-area input {
            flex: 1;
            min-width: 0;
            padding: 12px 16px;
            border: 2px solid #e1e1e1;
            border-radius: 24px;
            font-size: 15px;
            transition: border-color 0.2s;
        }
        .chat-input-area input:focus {
            outline: none;
            border-color: #667eea;
        }
        .chat-input-area button {
            padding: 12px 24px;
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            border: none;
            border-radius: 24px;
            font-size: 15px;
            font-weight: 600;
            cursor: pointer;
            transition: transform 0.2s;
        }
        .chat-input-area button:hover {
            transform: scale(1.05);
        }
        .chat-input-area button:disabled {
            opacity: 0.5;
            cursor: not-allowed;
            transform: none;
        }
        .stop-btn {
            background: linear-gradient(135deg, #e74c3c 0%, #c0392b 100%) !important;
            display: none;
        }
        .stop-btn.visible {
            display: inline-block;
        }
        
        /* Scrollbar */
        .chat-messages::-webkit-scrollbar {
            width: 8px;
        }
        .chat-messages::-webkit-scrollbar-track {
            background: #f1f1f1;
        }
        .chat-messages::-webkit-scrollbar-thumb {
            background: #c1c1c1;
            border-radius: 4px;
        }
        .chat-messages::-webkit-scrollbar-thumb:hover {
            background: #a1a1a1;
        }
    </style>
</head>
<body>
    <!-- Auth Screen -->
    <div id="auth-screen">
        <div class="auth-box">
            <h1>AICoder</h1>
            <p>Enter the secret to access the remote control interface</p>
            <div class="error" id="auth-error"></div>
            <input type="password" id="secret-input" placeholder="Secret" />
            <input type="text" id="username-input" placeholder="Your name (optional)" />
            <button onclick="authenticate()">Connect</button>
        </div>
    </div>
    
    <!-- Chat Screen -->
    <div id="chat-screen">
        <div class="chat-header">
            <h1>AICoder</h1>
            <div class="status-indicator">
                <div class="status-dot" id="status-dot"></div>
                <span id="status-text">Ready</span>
            </div>
        </div>
        
        <div class="chat-messages" id="chat-messages"></div>
        
        <div class="chat-input-area">
            <input type="text" id="message-input" placeholder="Type a message..." onkeypress="handleKeyPress(event)" />
            <button onclick="sendMessage()" id="send-btn">Send</button>
            <button onclick="stopProcessing()" class="stop-btn" id="stop-btn">Stop</button>
        </div>
    </div>
    
    <script>
        let authToken = null;
        let lastHistoryIndex = 0;
        let pollInterval = null;
        
        // Load saved username
        const savedUsername = localStorage.getItem('aicoder_remote_username');
        if (savedUsername) {
            document.getElementById('username-input').value = savedUsername;
        }
        
        async function authenticate() {
            const secret = document.getElementById('secret-input').value;
            const username = document.getElementById('username-input').value.trim();
            
            if (!secret) {
                showError('Please enter the secret');
                return;
            }
            
            try {
                const response = await fetch('/auth', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Username': username
                    },
                    body: JSON.stringify({ secret })
                });
                
                const data = await response.json();
                
                if (data.status === 'success') {
                    authToken = data.token;
                    // Save username
                    if (username) {
                        localStorage.setItem('aicoder_remote_username', username);
                    }
                    showChatScreen();
                    startPolling();
                } else {
                    showError(data.message || 'Authentication failed');
                }
            } catch (e) {
                showError('Connection failed: ' + e.message);
            }
        }
        
        function showError(msg) {
            const errorEl = document.getElementById('auth-error');
            errorEl.textContent = msg;
            errorEl.style.display = 'block';
        }
        
        function showChatScreen() {
            document.getElementById('auth-screen').style.display = 'none';
            document.getElementById('chat-screen').style.display = 'flex';
        }
        
        function startPolling() {
            pollInterval = setInterval(async () => {
                await pollHistory();
                await pollStatus();
            }, 3000);
        }
        
        async function pollHistory() {
            try {
                const response = await fetch('/history?index=' + lastHistoryIndex, {
                    headers: { 'X-Auth-Token': authToken }
                });
                const data = await response.json();
                
                if (data.status === 'success' && data.messages && data.messages.length > 0) {
                    for (const msg of data.messages) {
                        addMessage(msg.sender, msg.content, msg.type);
                    }
                    lastHistoryIndex = data.index;
                    scrollToBottom();
                }
            } catch (e) {
                console.error('Poll error:', e);
            }
        }
        
        async function pollStatus() {
            try {
                const response = await fetch('/status', {
                    headers: { 'X-Auth-Token': authToken }
                });
                const data = await response.json();
                
                const statusDot = document.getElementById('status-dot');
                const statusText = document.getElementById('status-text');
                const stopBtn = document.getElementById('stop-btn');
                const sendBtn = document.getElementById('send-btn');
                
                if (data.is_processing) {
                    statusDot.classList.add('processing');
                    statusText.textContent = 'AI is thinking...';
                    stopBtn.classList.add('visible');
                    sendBtn.disabled = true;
                } else {
                    statusDot.classList.remove('processing');
                    statusText.textContent = 'Ready';
                    stopBtn.classList.remove('visible');
                    sendBtn.disabled = false;
                    
                    if (data.stopped_by) {
                        addMessage('system', 'Stopped by ' + data.stopped_by, 'system');
                        // Clear the stopped_by flag
                        await fetch('/status/clear-stop', { method: 'POST', headers: { 'X-Auth-Token': authToken } });
                    }
                }
            } catch (e) {
                console.error('Status error:', e);
            }
        }
        
        function addMessage(sender, content, type) {
            const messagesEl = document.getElementById('chat-messages');
            const msgEl = document.createElement('div');
            msgEl.className = 'message message-' + type;
            
            if (type !== 'system') {
                const senderEl = document.createElement('div');
                senderEl.className = 'message-sender';
                senderEl.textContent = sender;
                msgEl.appendChild(senderEl);
            }
            
            const contentEl = document.createElement('div');
            contentEl.className = 'message-content';
            contentEl.textContent = content;
            msgEl.appendChild(contentEl);
            
            messagesEl.appendChild(msgEl);
        }
        
        function scrollToBottom() {
            const messagesEl = document.getElementById('chat-messages');
            messagesEl.scrollTop = messagesEl.scrollHeight;
        }
        
        async function sendMessage() {
            const input = document.getElementById('message-input');
            const message = input.value.trim();
            
            if (!message) return;
            
            const username = document.getElementById('username-input').value.trim() || getIpAddress();
            
            try {
                const response = await fetch('/message', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'X-Auth-Token': authToken,
                        'X-Username': username
                    },
                    body: JSON.stringify({ message })
                });
                
                const data = await response.json();
                
                if (data.status === 'success') {
                    input.value = '';
                    // Don't add message here - it will come from server polling
                    // This prevents duplication
                } else {
                    alert('Failed to send: ' + (data.message || 'Unknown error'));
                }
            } catch (e) {
                alert('Connection failed: ' + e.message);
            }
        }
        
        async function stopProcessing() {
            const username = document.getElementById('username-input').value.trim() || getIpAddress();
            
            try {
                const response = await fetch('/stop', {
                    method: 'POST',
                    headers: {
                        'X-Auth-Token': authToken,
                        'X-Username': username
                    }
                });
                
                const data = await response.json();
                if (data.status !== 'success') {
                    alert('Failed to stop: ' + (data.message || 'Unknown error'));
                }
            } catch (e) {
                alert('Connection failed: ' + e.message);
            }
        }
        
        function handleKeyPress(event) {
            if (event.key === 'Enter') {
                sendMessage();
            }
        }
        
        function getIpAddress() {
            // Return a placeholder for IP in client-side
            return 'User';
        }
    </script>
</body>
</html>
"""


class RemoteControlHandler(BaseHTTPRequestHandler):
    """HTTP request handler for remote control"""
    
    def log_message(self, format, *args):
        """Suppress default logging"""
        pass
    
    def send_json_response(self, data, status=200):
        """Send JSON response"""
        self.send_response(status)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(json.dumps(data).encode())
    
    def do_OPTIONS(self):
        """Handle CORS preflight"""
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, X-Auth-Token, X-Username')
        self.end_headers()
    
    def do_GET(self):
        """Handle GET requests"""
        parsed = urlparse(self.path)
        path = parsed.path
        query = parse_qs(parsed.query)
        
        if path == '/':
            # Serve HTML UI
            try:
                self.send_response(200)
                self.send_header('Content-Type', 'text/html')
                self.end_headers()
                self.wfile.write(HTML_UI.encode())
            except BrokenPipeError:
                pass  # Client closed connection
        
        elif path == '/status':
            # Get current status
            self.send_json_response({
                'status': 'success',
                'is_processing': state.is_processing,
                'stopped_by': state.stop_requested_by
            })
        
        elif path == '/status/clear-stop':
            # Clear stop flag
            if not validate_auth(self):
                self.send_json_response({'status': 'error', 'message': 'Unauthorized'}, 401)
                return
            state.stop_requested_by = None
            self.send_json_response({'status': 'success'})
        
        elif path == '/history':
            # Get message history since index
            if not validate_auth(self):
                self.send_json_response({'status': 'error', 'message': 'Unauthorized'}, 401)
                return
            
            index = int(query.get('index', ['0'])[0])
            messages = state.message_history_with_sender[index:]
            self.send_json_response({
                'status': 'success',
                'messages': messages,
                'index': len(state.message_history_with_sender)
            })
        
        else:
            self.send_json_response({'status': 'error', 'message': 'Not found'}, 404)
    
    def do_POST(self):
        """Handle POST requests"""
        parsed = urlparse(self.path)
        path = parsed.path
        
        content_length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(content_length).decode() if content_length > 0 else '{}'
        
        try:
            data = json.loads(body) if body else {}
        except json.JSONDecodeError:
            data = {}
        
        if path == '/auth':
            self.handle_auth(data)
        
        elif path == '/message':
            self.handle_message(data)
        
        elif path == '/stop':
            self.handle_stop()
        
        else:
            self.send_json_response({'status': 'error', 'message': 'Not found'}, 404)
    
    def handle_auth(self, data):
        """Handle authentication"""
        global state
        
        secret = data.get('secret', '')
        expected_secret = get_secret()
        
        if not expected_secret:
            self.send_json_response({
                'status': 'error',
                'message': 'Remote control secret not set. Use /remote-control secret <secret> or set REMOTE_CONTROL_SECRET env var'
            }, 400)
            return
        
        if secret != expected_secret:
            state.failed_auth_attempts += 1
            LogUtils.print(f"{Config.colors['yellow']}[Remote] Failed auth attempt {state.failed_auth_attempts}/3 from {get_client_ip(self)}{Config.colors['reset']}")
            
            if state.failed_auth_attempts >= 3:
                LogUtils.print(f"{Config.colors['red']}[Remote] SECURITY: 3 failed auth attempts. Exiting.{Config.colors['reset']}")
                # Schedule exit (can't exit directly from handler thread)
                threading.Thread(target=lambda: os._exit(1)).start()
                self.send_json_response({
                    'status': 'error',
                    'message': 'Too many failed attempts. Exiting.'
                }, 403)
                return
            
            self.send_json_response({
                'status': 'error',
                'message': f'Invalid secret. {3 - state.failed_auth_attempts} attempts remaining.'
            }, 401)
            return
        
        # Success - reset failed attempts and generate unique token
        state.failed_auth_attempts = 0
        new_token = f"token_{os.urandom(16).hex()}"
        state.auth_tokens.add(new_token)
        
        username = get_username_from_request(self)
        LogUtils.print(f"{Config.colors['green']}[Remote] User '{username}' authenticated from {get_client_ip(self)}{Config.colors['reset']}")
        
        self.send_json_response({
            'status': 'success',
            'token': new_token
        })
    
    def handle_message(self, data):
        """Handle incoming message"""
        if not validate_auth(self):
            self.send_json_response({'status': 'error', 'message': 'Unauthorized'}, 401)
            return
        
        message = data.get('message', '').strip()
        if not message:
            self.send_json_response({'status': 'error', 'message': 'Message cannot be empty'}, 400)
            return
        
        username = get_username_from_request(self)
        
        if state.is_processing:
            self.send_json_response({
                'status': 'error',
                'message': 'AI is currently processing. Please wait.'
            }, 409)
            return
        
        # Set pending message
        state.pending_message = message
        state.pending_message_user = username
        
        # Add to history for web UI polling
        add_to_history(username, message, 'user')
        
        LogUtils.print(f"{Config.colors['cyan']}[Remote] Message from '{username}': {message[:50]}...{Config.colors['reset']}")
        
        self.send_json_response({'status': 'success'})
    
    def handle_stop(self):
        """Handle stop request"""
        if not validate_auth(self):
            self.send_json_response({'status': 'error', 'message': 'Unauthorized'}, 401)
            return
        
        username = get_username_from_request(self)
        state.stop_requested_by = username
        
        # Set is_processing to False to stop the AI
        if _app:
            _app.is_processing = False
        
        LogUtils.print(f"{Config.colors['yellow']}[Remote] Stop requested by '{username}'{Config.colors['reset']}")
        
        self.send_json_response({'status': 'success'})


def validate_auth(handler) -> bool:
    """Validate auth token from header"""
    token = handler.headers.get('X-Auth-Token')
    return token in state.auth_tokens


def start_server():
    """Start HTTP server in background thread"""
    global state
    
    state.host = os.environ.get('REMOTE_CONTROL_HOST', '127.0.0.1')
    state.port = int(os.environ.get('REMOTE_CONTROL_PORT', '8000'))
    
    try:
        server = ThreadingHTTPServer((state.host, state.port), RemoteControlHandler)
        server.timeout = 5  # 5 second timeout for requests
        state.http_server = server
        
        server.serve_forever()
    except Exception as e:
        LogUtils.print(f"{Config.colors['red']}[Remote] Server error: {e}{Config.colors['reset']}")
        state.is_active = False


def stop_server():
    """Stop HTTP server"""
    global state, _yolo_mode_was_enabled, _original_log_print
    
    if state.http_server:
        state.http_server.shutdown()
        state.http_server = None
    
    state.is_active = False
    state.auth_tokens.clear()  # Invalidate all tokens
    state.pending_message = None
    state.pending_message_user = None
    
    # Restore original LogUtils.print
    if _original_log_print is not None:
        LogUtils.print = _original_log_print
        _original_log_print = None
    
    # Restore yolo mode if it wasn't enabled before
    if not _yolo_mode_was_enabled:
        Config.set_yolo_mode(False)
        LogUtils.print(f"{Config.colors['yellow']}[Remote] Yolo mode restored to previous state{Config.colors['reset']}")
    
    LogUtils.print(f"{Config.colors['yellow']}[Remote] Remote control stopped{Config.colors['reset']}")


def on_before_user_prompt():
    """Hook: Wait for web message after AI response (blocks until message arrives)"""
    global state
    
    if not state.is_active:
        return
    
    # Check if next_prompt is already set (from previous web message)
    # If set, let it through without blocking
    if _app and _app.has_next_prompt():
        return
    
    # Block and wait for next message from web UI
    LogUtils.print(f"{Config.colors['yellow']}[Remote] Waiting for next message from web UI...{Config.colors['reset']}")
    
    # Set up signal handler for Ctrl+C
    original_handler = signal.getsignal(signal.SIGINT)
    
    def signal_handler(signum, frame):
        raise KeyboardInterrupt()
    
    signal.signal(signal.SIGINT, signal_handler)
    
    try:
        while state.is_active and not state.pending_message:
            time.sleep(1.0)
    except KeyboardInterrupt:
        LogUtils.print(f"\n{Config.colors['yellow']}[Remote] Ctrl+C - returning to terminal input{Config.colors['reset']}")
        state.is_active = False
        state.pending_message = None
        signal.signal(signal.SIGINT, original_handler)
        return
    
    signal.signal(signal.SIGINT, original_handler)
    
    if not state.is_active:
        return
    
    # Got message
    message = state.pending_message
    user = state.pending_message_user or "Web User"
    state.pending_message = None
    state.pending_message_user = None
    
    if _app:
        _app.set_next_prompt(message)
        LogUtils.print(f"{Config.colors['green']}[Remote] ✓ Message from '{user}' - processing{Config.colors['reset']}")


def on_before_ai_processing():
    """Hook: Called before AI starts processing - set processing flag"""
    global state
    
    if state.is_active:
        state.is_processing = True
        if Config.debug():
            LogUtils.print(f"{Config.colors['yellow']}[Remote] Remote control session active{Config.colors['reset']}")


def on_after_assistant_message_added(message: dict):
    """Hook: Track AI responses for web UI polling and reset processing flag"""
    global state
    
    if state.is_active:
        state.is_processing = False  # Reset flag after AI response
        content = message.get('content', '')
        if content:
            add_to_history('AI', content, 'ai')


def add_to_history(sender: str, content: str, msg_type: str):
    """Add message to history with sender info"""
    global state
    state.message_history_with_sender.append({
        'sender': sender,
        'content': content,
        'type': msg_type
    })


def _patch_log_print():
    """Monkey patch LogUtils.printc to capture output for remote control"""
    global _original_log_print
    
    if _original_log_print is not None:
        return  # Already patched
    
    import re
    ANSI_ESCAPE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')
    
    # Patch printc since all log methods route through it
    _original_log_print = LogUtils.printc
    
    def patched_printc(message: str, options=None, color=None, bold=False, debug=False):
        # Call original printc
        _original_log_print(message, options=options, color=color, bold=bold, debug=debug)
        
        # Capture for remote control history (if active and not processing flag messages)
        if state.is_active and message and not message.startswith('[Remote]'):
            # Strip ANSI escape codes for clean web display
            clean_message = ANSI_ESCAPE.sub('', message)
            add_to_history('System', clean_message, 'system')
    
    LogUtils.printc = patched_printc


def sync_message_history():
    """Sync message history from core to our tracked history"""
    global state
    
    if not _app or not _app.message_history:
        return
    
    # Get messages from core history
    messages = _app.message_history.get_messages() if hasattr(_app.message_history, 'get_messages') else []
    
    # Sync new messages
    for msg in messages[state.last_history_index:]:
        role = msg.get('role', 'unknown')
        content = msg.get('content', '')
        
        if role == 'user':
            # Check if this was from web
            if state.pending_message_user and content == state.pending_message:
                add_to_history(state.pending_message_user, content, 'user')
            else:
                add_to_history('Terminal', content, 'user')
        elif role == 'assistant':
            add_to_history('AI', content, 'ai')
        
        state.last_history_index += 1


# Command handler
def cmd_remote_control(args_str: str) -> None:
    """Handle /remote-control command"""
    global state, _app, _yolo_mode_was_enabled
    
    # Parse args
    args = args_str.strip().split() if args_str.strip() else []
    
    if len(args) > 0 and args[0] == 'secret':
        if len(args) < 2:
            LogUtils.print(f"{Config.colors['red']}Usage: /remote-control secret <secret>{Config.colors['reset']}")
            return
        
        state.secret = args[1]
        LogUtils.print(f"{Config.colors['green']}[Remote] Secret set for this session{Config.colors['reset']}")
        return
    
    # Start remote control
    if state.is_active:
        LogUtils.print(f"{Config.colors['yellow']}[Remote] Remote control already running at http://{state.host}:{state.port}{Config.colors['reset']}")
        return
    
    # Check secret is set
    if not get_secret():
        LogUtils.print(f"{Config.colors['red']}[Remote] Secret not set. Use: /remote-control secret <secret>{Config.colors['reset']}")
        return
    
    # Enable yolo mode
    _yolo_mode_was_enabled = Config.yolo_mode()
    Config.set_yolo_mode(True)
    LogUtils.print(f"{Config.colors['yellow']}[Remote] Yolo mode enabled (auto-approve all tools){Config.colors['reset']}")
    
    # Patch LogUtils.print to capture output
    _patch_log_print()
    
    # Reset state
    state.message_history_with_sender = []
    state.last_history_index = 0
    state.failed_auth_attempts = 0
    state.stop_requested_by = None
    state.auth_tokens = set()  # Clear any old tokens
    state.is_active = True  # Set BEFORE starting thread
    
    # Start server thread
    state.server_thread = threading.Thread(target=start_server, daemon=True)
    state.server_thread.start()
    
    # Register cleanup on exit
    import atexit
    atexit.register(stop_server)
    
    LogUtils.print(f"{Config.colors['green']}[Remote] Remote control started at http://{state.host}:{state.port}{Config.colors['reset']}")
    LogUtils.print(f"{Config.colors['green']}[Remote] Open browser and enter secret to send messages{Config.colors['reset']}")
    LogUtils.print(f"{Config.colors['yellow']}[Remote] Waiting for first message from web UI...{Config.colors['reset']}")
    
    # Wait for first message before returning (blocks command execution)
    try:
        while not state.pending_message:
            time.sleep(0.5)
    except KeyboardInterrupt:
        LogUtils.print(f"\n{Config.colors['yellow']}[Remote] Ctrl+C - cancelled{Config.colors['reset']}")
        state.is_active = False
        return
    
    if state.pending_message:
        message = state.pending_message
        user = state.pending_message_user or "Web User"
        state.pending_message = None
        state.pending_message_user = None
        
        if _app:
            _app.set_next_prompt(message)
            LogUtils.print(f"{Config.colors['green']}[Remote] ✓ First message from '{user}' - processing...{Config.colors['reset']}")
            LogUtils.print(f"{Config.colors['cyan']}[Remote] Message: {message[:50]}...{Config.colors['reset']}")


def create_plugin(ctx):
    """Remote control plugin entry point"""
    global _app
    
    _app = ctx.app
    
    # Register command
    ctx.register_command('remote-control', cmd_remote_control, 'Start remote control mode')
    
    # Register hooks
    ctx.register_hook('before_user_prompt', on_before_user_prompt)
    ctx.register_hook('before_ai_processing', on_before_ai_processing)
    ctx.register_hook('after_assistant_message_added', on_after_assistant_message_added)
    
    if Config.debug():
        LogUtils.print("  - /remote-control command")
        LogUtils.print("  - /remote-control secret <secret> subcommand")
        LogUtils.print("  - before_user_prompt hook")
        LogUtils.print("  - before_ai_processing hook")
        LogUtils.print("  - after_assistant_message_added hook")
        LogUtils.print(f"  - HTTP server (configurable via env vars)")
