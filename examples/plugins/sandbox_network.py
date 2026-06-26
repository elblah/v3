"""
Network Sandbox Plugin - Block shell commands from accessing network

Uses seccomp to block network syscalls:
- Commands are wrapped with a compiled seccomp binary
- /snet command to enable/disable network blocking
- Safe default: disabled (network access allowed by default)
"""

import os
import sys
import subprocess
import tempfile
import shutil
from typing import Dict, Any

from aicoder.core.config import Config
from aicoder.utils.log import LogUtils

# Plugin state
_network_blocking_enabled = False
_blocknet_executable_path = None
_compilation_in_progress = False
_requirements_checked = False
_missing_requirements = []

# C source code for the network blocker
SECCOMP_SOURCE = '''
/*
 * Minimal Network Blocker using libseccomp
 *
 * Blocks network syscalls on any architecture
 */

#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>
#include <sys/prctl.h>
#include <seccomp.h>

static int install_network_filter(void) {
    scmp_filter_ctx ctx;
    int rc;

    ctx = seccomp_init(SCMP_ACT_ALLOW);
    if (!ctx) {
        perror("seccomp_init failed");
        return -1;
    }

    #define BLOCK_SYSCALL(name) do { \\
        rc = seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(name), 0); \\
        if (rc != 0 && rc != -EDOM) { \\
            fprintf(stderr, "Failed to block %s: %s\\n", #name, strerror(-rc)); \\
            seccomp_release(ctx); \\
            return -1; \\
        } \\
    } while(0)

    BLOCK_SYSCALL(socket);
    BLOCK_SYSCALL(connect);
    BLOCK_SYSCALL(bind);
    BLOCK_SYSCALL(listen);
    BLOCK_SYSCALL(accept);
    BLOCK_SYSCALL(accept4);
    BLOCK_SYSCALL(sendto);
    BLOCK_SYSCALL(recvfrom);
    BLOCK_SYSCALL(sendmsg);
    BLOCK_SYSCALL(recvmsg);
    BLOCK_SYSCALL(sendmmsg);
    BLOCK_SYSCALL(recvmmsg);
    BLOCK_SYSCALL(socketcall);

    #undef BLOCK_SYSCALL

    rc = seccomp_load(ctx);
    if (rc != 0) {
        fprintf(stderr, "Failed to load seccomp filter: %s\\n", strerror(-rc));
        seccomp_release(ctx);
        return -1;
    }

    seccomp_release(ctx);
    return 0;
}

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "Usage: %s <command> [args...]\\n", argv[0]);
        return 1;
    }

    if (install_network_filter() != 0) {
        fprintf(stderr, "Failed to install network filter\\n");
        return 1;
    }

    execvp(argv[1], argv + 1);
    perror("execvp failed");
    return 1;
}
'''


def check_requirements() -> tuple[bool, list[str]]:
    """Check if required dependencies are available."""
    global _requirements_checked, _missing_requirements

    if _requirements_checked:
        return len(_missing_requirements) == 0, _missing_requirements

    _missing_requirements = []
    
    seccomp_paths = [
        "/usr/include/seccomp.h",
        "/usr/local/include/seccomp.h",
        "/usr/include/x86_64-linux-gnu/seccomp.h",
    ]
    
    seccomp_found = any(os.path.exists(path) for path in seccomp_paths)
    if not seccomp_found:
        _missing_requirements.append("libseccomp-dev (install with: apt install libseccomp-dev)")
    
    if not shutil.which("gcc"):
        _missing_requirements.append("gcc (install with: apt install build-essential)")
    
    _requirements_checked = True
    
    return len(_missing_requirements) == 0, _missing_requirements


def compile_blocknet_executable() -> str | None:
    """Compile the seccomp network blocker executable."""
    global _blocknet_executable_path, _compilation_in_progress

    if _blocknet_executable_path and os.path.exists(_blocknet_executable_path):
        return _blocknet_executable_path

    if _compilation_in_progress:
        return None

    requirements_ok, missing = check_requirements()
    if not requirements_ok:
        LogUtils.error(f"[X] Network blocking unavailable - missing requirements:")
        for req in missing:
            LogUtils.print(f"    - {req}")
        return None

    _compilation_in_progress = True
    
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_file = os.path.join(temp_dir, "block_network_seccomp.c")
            executable_file = os.path.join(temp_dir, "block-net")
            
            with open(source_file, "w") as f:
                f.write(SECCOMP_SOURCE)
            
            compile_cmd = [
                "gcc",
                "-o", executable_file,
                source_file,
                "-lseccomp"
            ]
            
            result = subprocess.run(
                compile_cmd,
                capture_output=True,
                text=True
            )
            
            if result.returncode != 0:
                LogUtils.error(f"[X] Failed to compile network blocker:")
                LogUtils.print(f"    stderr: {result.stderr.strip()}")
                return None
            
            permanent_path = "/tmp/block-net-aicoder"
            shutil.move(executable_file, permanent_path)
            os.chmod(permanent_path, 0o755)
            
            _blocknet_executable_path = permanent_path
            LogUtils.success(f"[+] Network blocker compiled successfully: {permanent_path}")
            return permanent_path
            
    except Exception as e:
        LogUtils.error(f"[X] Failed to compile network blocker: {e}")
        return None
    finally:
        _compilation_in_progress = False


def create_plugin(ctx):
    """Network sandbox plugin"""

    def _handle_snet(args_str: str) -> None:
        """Handle /snet command - show status or toggle network blocking."""
        global _network_blocking_enabled

        args = args_str.strip().lower()

        if not args or args == "":
            # Show current status
            status = "enabled" if _network_blocking_enabled else "disabled"
            LogUtils.print(f"Network sandbox: {status}")
            return

        if args in ("on", "enable", "1"):
            _network_blocking_enabled = True
            LogUtils.success("[+] Network sandbox enabled")
            LogUtils.print("    Seccomp binary will be compiled on first shell command")
        elif args in ("off", "disable", "0"):
            _network_blocking_enabled = False
            LogUtils.print("[-] Network sandbox disabled")
        elif args == "toggle":
            _network_blocking_enabled = not _network_blocking_enabled
            if _network_blocking_enabled:
                LogUtils.success("[+] Network sandbox enabled")
                LogUtils.print("    Seccomp binary will be compiled on first shell command")
            else:
                LogUtils.print("[-] Network sandbox disabled")
        elif args in ("help", "-h", "--help"):
            LogUtils.print("Network Sandbox Command:")
            LogUtils.print("  /snet          - Show current status")
            LogUtils.print("  /snet on       - Enable network blocking")
            LogUtils.print("  /snet off      - Disable network blocking")
            LogUtils.print("  /snet toggle   - Toggle between enabled/disabled")
            LogUtils.print("  /snet help     - Show this help")
        else:
            LogUtils.error(f"Unknown argument: {args}")
            LogUtils.print("Use /snet help for usage")

    def patch_run_shell_command():
        """Patch run_shell_command tool to prepend network blocker."""
        tool_def = ctx.app.tool_manager.tools.get("run_shell_command")
        if not tool_def:
            LogUtils.error("[X] Cannot patch run_shell_command - tool not found")
            return
        
        original_execute = tool_def.get("execute")
        if not original_execute:
            LogUtils.error("[X] Cannot patch run_shell_command - no execute method")
            return
        
        def patched_execute(args_obj: Dict[str, Any]) -> Dict[str, Any]:
            """Execute shell command with optional network blocking."""
            global _network_blocking_enabled, _blocknet_executable_path
            
            if _network_blocking_enabled:
                if not _blocknet_executable_path or not os.path.exists(_blocknet_executable_path):
                    executable = compile_blocknet_executable()
                    if not executable:
                        LogUtils.warn("[WARNING] Network sandbox unavailable - running without network blocking")
                        return original_execute(args_obj)
                
                command = args_obj.get("command", "")
                if command:
                    wrapped_command = f'{_blocknet_executable_path} bash -c "{command}"'
                    args_obj = args_obj.copy()
                    args_obj["command"] = wrapped_command
            
            return original_execute(args_obj)
        
        tool_def["execute"] = patched_execute
    
    # Register command
    ctx.register_command("/snet", _handle_snet, "Network sandbox for shell commands")
    
    # Patch the run_shell_command tool
    patch_run_shell_command()
    
    # Check requirements on startup
    requirements_ok, missing = check_requirements()
    if Config.debug():
        if requirements_ok:
            LogUtils.print("[+] Network sandbox plugin loaded (requirements satisfied)")
            LogUtils.print("    Use /snet on to enable network blocking for shell commands")
        else:
            LogUtils.print("[+] Network sandbox plugin loaded (missing requirements):")
            for req in missing:
                LogUtils.print(f"      - {req}")
            LogUtils.print("    Install requirements to use network blocking")
