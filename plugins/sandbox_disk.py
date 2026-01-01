"""
Disk Sandbox Plugin - Block shell commands from modifying files/directories

/sdisk on/off/toggle - Control disk blocking
"""

import os
import sys
import subprocess
import tempfile
import shutil
from typing import Dict, Any

_disk_blocking_enabled = False
_blockdisk_executable_path = None
_compilation_in_progress = False
_requirements_checked = False
_missing_requirements = []

SECCOMP_SOURCE = '''
#define _GNU_SOURCE
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>
#include <sys/prctl.h>
#include <seccomp.h>
#include <fcntl.h>

static int install_disk_filter(void) {
    scmp_filter_ctx ctx = seccomp_init(SCMP_ACT_ALLOW);
    if (!ctx) return -1;

    // Block ALL file modification operations
    seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(creat), 0);
    seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(unlink), 0);
    seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(unlinkat), 0);
    seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(rename), 0);
    seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(renameat), 0);
    seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(renameat2), 0);
    seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(mkdir), 0);
    seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(mkdirat), 0);
    seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(rmdir), 0);
    seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(chmod), 0);
    seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(fchmod), 0);
    seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(fchmodat), 0);
    seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(chown), 0);
    seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(fchown), 0);
    seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(fchownat), 0);
    seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(lchown), 0);
    seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(link), 0);
    seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(linkat), 0);
    seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(symlink), 0);
    seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(symlinkat), 0);
    seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(truncate), 0);
    seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(ftruncate), 0);

    // Block ALL openat with write-related flags
    seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(openat), 1,
                     SCMP_A2(SCMP_CMP_MASKED_EQ, O_WRONLY, O_WRONLY));
    seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(openat), 1,
                     SCMP_A2(SCMP_CMP_MASKED_EQ, O_RDWR, O_RDWR));
    seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(openat), 1,
                     SCMP_A2(SCMP_CMP_MASKED_EQ, O_CREAT, O_CREAT));
    seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(openat), 1,
                     SCMP_A2(SCMP_CMP_MASKED_EQ, O_RDWR|O_CREAT|O_EXCL, O_RDWR|O_CREAT|O_EXCL));

    int rc = seccomp_load(ctx);
    seccomp_release(ctx);
    return rc;
}

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "Usage: %s <command> [args...]\\n", argv[0]);
        return 1;
    }

    if (install_disk_filter() != 0) {
        fprintf(stderr, "Failed to install disk filter\\n");
        return 1;
    }

    execvp(argv[1], argv + 1);
    return 1;
}
'''

def check_requirements() -> tuple[bool, list[str]]:
    global _requirements_checked, _missing_requirements
    if _requirements_checked:
        return len(_missing_requirements) == 0, _missing_requirements

    _missing_requirements = []
    seccomp_paths = ["/usr/include/seccomp.h", "/usr/local/include/seccomp.h", "/usr/include/x86_64-linux-gnu/seccomp.h"]
    if not any(os.path.exists(path) for path in seccomp_paths):
        _missing_requirements.append("libseccomp-dev (apt install libseccomp-dev)")
    if not shutil.which("gcc"):
        _missing_requirements.append("gcc (apt install build-essential)")
    
    _requirements_checked = True
    return len(_missing_requirements) == 0, _missing_requirements

def compile_blockdisk_executable() -> str | None:
    global _blockdisk_executable_path, _compilation_in_progress

    if _blockdisk_executable_path and os.path.exists(_blockdisk_executable_path):
        return _blockdisk_executable_path

    if _compilation_in_progress:
        return None

    requirements_ok, missing = check_requirements()
    if not requirements_ok:
        print(f"[X] Disk blocking unavailable - missing requirements:")
        for req in missing:
            print(f"    - {req}")
        return None

    _compilation_in_progress = True
    
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_file = os.path.join(temp_dir, "block_disk_seccomp.c")
            executable_file = os.path.join(temp_dir, "block-disk")
            
            with open(source_file, "w") as f:
                f.write(SECCOMP_SOURCE)
            
            compile_cmd = ["gcc", "-o", executable_file, source_file, "-lseccomp"]
            
            result = subprocess.run(compile_cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"[X] Failed to compile disk blocker: {result.stderr.strip()}")
                return None
            
            permanent_path = "/tmp/block-disk-aicoder"
            shutil.move(executable_file, permanent_path)
            os.chmod(permanent_path, 0o755)
            
            _blockdisk_executable_path = permanent_path
            print(f"[+] Disk blocker compiled successfully")
            return permanent_path
            
    except Exception as e:
        print(f"[X] Failed to compile disk blocker: {e}")
        return None
    finally:
        _compilation_in_progress = False

def create_plugin(ctx):
    def _handle_sdisk(args_str: str) -> None:
        global _disk_blocking_enabled
        args = args_str.strip().lower()

        if not args or args == "":
            status = "enabled" if _disk_blocking_enabled else "disabled"
            print(f"Disk sandbox: {status}")
            return

        if args in ("on", "enable", "1"):
            _disk_blocking_enabled = True
            print("[+] Disk sandbox enabled")
        elif args in ("off", "disable", "0"):
            _disk_blocking_enabled = False
            print("[-] Disk sandbox disabled")
        elif args == "toggle":
            _disk_blocking_enabled = not _disk_blocking_enabled
            status = "enabled" if _disk_blocking_enabled else "disabled"
            print(f"[+] Disk sandbox {status}")
        else:
            print("Use: /sdisk on/off/toggle")

    def patch_run_shell_command():
        tool_def = ctx.app.tool_manager.tools.get("run_shell_command")
        if not tool_def or not tool_def.get("execute"):
            return
        
        original_execute = tool_def["execute"]
        
        def patched_execute(args_obj: Dict[str, Any]) -> Dict[str, Any]:
            global _disk_blocking_enabled, _blockdisk_executable_path
            
            if _disk_blocking_enabled:
                if not _blockdisk_executable_path or not os.path.exists(_blockdisk_executable_path):
                    executable = compile_blockdisk_executable()
                    if not executable:
                        return original_execute(args_obj)
                
                command = args_obj.get("command", "")
                if command:
                    wrapped_command = f'{_blockdisk_executable_path} bash -c "{command}"'
                    args_obj = args_obj.copy()
                    args_obj["command"] = wrapped_command
            
            return original_execute(args_obj)
        
        tool_def["execute"] = patched_execute
    
    ctx.register_command("/sdisk", _handle_sdisk, "Disk sandbox for shell commands")
    patch_run_shell_command()
    
    requirements_ok, missing = check_requirements()
    if requirements_ok:
        print("[+] Disk sandbox plugin loaded (use /sdisk on)")
    else:
        print("[+] Disk sandbox plugin loaded (missing: {', '.join(missing)})")