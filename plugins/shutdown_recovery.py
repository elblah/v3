"""
Shutdown Recovery Plugin

Saves a timestamped recovery snapshot to .aicoder/session_recovery_<date>.json
on SIGTERM/SIGHUP (Ctrl+Alt+Del, system shutdown, kill).
"""

import os
from datetime import datetime

from aicoder.utils.json_utils import write_file
from aicoder.utils.log import LogUtils


def create_plugin(ctx):
    RECOVERY_DIR = ".aicoder"

    def on_shutdown(signum):
        """Save recovery session on termination signal"""
        try:
            ts = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
            path = os.path.join(RECOVERY_DIR, f"session_recovery_{ts}.json")
            os.makedirs(RECOVERY_DIR, exist_ok=True)
            msgs = ctx.app.message_history.get_messages()
            write_file(path, msgs)
            LogUtils.print(f"\n[!] Recovery session saved: {path}")
        except Exception as e:
            LogUtils.print(f"\n[!] Recovery save failed: {e}")

    ctx.register_hook("on_shutdown", on_shutdown)

    from aicoder.core.config import Config
    if Config.debug():
        LogUtils.debug("[+] Shutdown recovery plugin loaded")
