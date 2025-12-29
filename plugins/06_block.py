"""
Block Plugin - Unified network and disk restrictions

/block on net disk    - Block network + disk writes
/block on net         - Block network only
/block on disk        - Block disk writes only
/block toggle net     - Toggle network blocking
/block toggle disk    - Toggle disk blocking
/block toggle         - Toggle both
/block off           - Remove all restrictions
"""

import os
import sys
import subprocess
import tempfile
import shutil
import hashlib
from typing import Dict, Any

_network_blocking_enabled = False
_disk_blocking_enabled = False
_block_executable_path = None
_block_executable_hash = None
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

static int install_network_filter(scmp_filter_ctx ctx) {
    // Network syscalls
    if (seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(socket), 0) < 0) return -1;
    if (seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(connect), 0) < 0) return -1;
    if (seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(bind), 0) < 0) return -1;
    if (seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(listen), 0) < 0) return -1;
    if (seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(accept), 0) < 0) return -1;
    if (seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(accept4), 0) < 0) return -1;
    if (seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(sendto), 0) < 0) return -1;
    if (seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(recvfrom), 0) < 0) return -1;
    if (seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(sendmsg), 0) < 0) return -1;
    if (seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(recvmsg), 0) < 0) return -1;
    if (seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(sendmmsg), 0) < 0) return -1;
    if (seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(recvmmsg), 0) < 0) return -1;
    if (seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(socketcall), 0) < 0) return -1;
    return 0;
}

static int install_disk_filter(scmp_filter_ctx ctx) {
    // Block ALL file modification operations
    if (seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(creat), 0) < 0) return -1;
    if (seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(unlink), 0) < 0) return -1;
    if (seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(unlinkat), 0) < 0) return -1;
    if (seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(rename), 0) < 0) return -1;
    if (seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(renameat), 0) < 0) return -1;
    if (seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(renameat2), 0) < 0) return -1;
    if (seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(mkdir), 0) < 0) return -1;
    if (seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(mkdirat), 0) < 0) return -1;
    if (seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(rmdir), 0) < 0) return -1;
    if (seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(chmod), 0) < 0) return -1;
    if (seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(fchmod), 0) < 0) return -1;
    if (seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(fchmodat), 0) < 0) return -1;
    if (seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(chown), 0) < 0) return -1;
    if (seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(fchown), 0) < 0) return -1;
    if (seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(fchownat), 0) < 0) return -1;
    if (seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(lchown), 0) < 0) return -1;
    if (seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(link), 0) < 0) return -1;
    if (seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(linkat), 0) < 0) return -1;
    if (seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(symlink), 0) < 0) return -1;
    if (seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(symlinkat), 0) < 0) return -1;
    if (seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(truncate), 0) < 0) return -1;
    if (seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(ftruncate), 0) < 0) return -1;

    // Block openat with all write flag combinations
    if (seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(openat), 1,
                         SCMP_A2(SCMP_CMP_MASKED_EQ, O_WRONLY, O_WRONLY)) < 0) return -1;
    if (seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(openat), 1,
                         SCMP_A2(SCMP_CMP_MASKED_EQ, O_RDWR, O_RDWR)) < 0) return -1;
    if (seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(openat), 1,
                         SCMP_A2(SCMP_CMP_MASKED_EQ, O_CREAT, O_CREAT)) < 0) return -1;
    if (seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(openat), 1,
                         SCMP_A2(SCMP_CMP_MASKED_EQ, O_WRONLY|O_CREAT|O_TRUNC, O_WRONLY|O_CREAT|O_TRUNC)) < 0) return -1;
    if (seccomp_rule_add(ctx, SCMP_ACT_ERRNO(EACCES), SCMP_SYS(openat), 1,
                         SCMP_A2(SCMP_CMP_MASKED_EQ, O_RDWR|O_CREAT|O_EXCL, O_RDWR|O_CREAT|O_EXCL)) < 0) return -1;

    return 0;
}

int main(int argc, char **argv) {
    if (argc < 2) {
        fprintf(stderr, "Usage: %s --no-net --no-disk -- <command>\\n", argv[0]);
        return 1;
    }

    int block_net = 0, block_disk = 0;
    int cmd_start = 1;

    // Parse arguments
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "--no-net") == 0) {
            block_net = 1;
        } else if (strcmp(argv[i], "--no-disk") == 0) {
            block_disk = 1;
        } else if (strcmp(argv[i], "--") == 0) {
            cmd_start = i + 1;
            break;
        }
    }

    if (cmd_start >= argc) {
        fprintf(stderr, "Error: No command specified after --\\n");
        return 1;
    }

    scmp_filter_ctx ctx = seccomp_init(SCMP_ACT_ALLOW);
    if (!ctx) return -1;

    if (block_net && install_network_filter(ctx) < 0) {
        fprintf(stderr, "Failed to install network filter\\n");
        return -1;
    }

    if (block_disk && install_disk_filter(ctx) < 0) {
        fprintf(stderr, "Failed to install disk filter\\n");
        return -1;
    }

    int rc = seccomp_load(ctx);
    seccomp_release(ctx);
    if (rc != 0) {
        fprintf(stderr, "Failed to load seccomp filter\\n");
        return -1;
    }

    execvp(argv[cmd_start], &argv[cmd_start]);
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

def compute_file_hash(filepath: str) -> str:
    """Compute SHA256 hash of file for integrity checking."""
    with open(filepath, 'rb') as f:
        return hashlib.sha256(f.read()).hexdigest()

def verify_binary_integrity() -> bool:
    """Verify the block binary hasn't been tampered with."""
    if not _block_executable_path or not _block_executable_hash:
        return False
    if not os.path.exists(_block_executable_path):
        return False
    
    current_hash = compute_file_hash(_block_executable_path)
    return current_hash == _block_executable_hash

def compile_block_executable() -> str | None:
    global _block_executable_path, _block_executable_hash, _compilation_in_progress

    # Check if binary exists and verify integrity
    if _block_executable_path and os.path.exists(_block_executable_path):
        if verify_binary_integrity():
            return _block_executable_path
        else:
            print("[!] Block binary tampered with or corrupted, recompiling")

    if _compilation_in_progress:
        return None

    requirements_ok, missing = check_requirements()
    if not requirements_ok:
        print(f"[X] Block plugin unavailable - missing requirements:")
        for req in missing:
            print(f"    - {req}")
        return None

    _compilation_in_progress = True
    
    try:
        with tempfile.TemporaryDirectory() as temp_dir:
            source_file = os.path.join(temp_dir, "block_seccomp.c")
            executable_file = os.path.join(temp_dir, "block")
            
            with open(source_file, "w") as f:
                f.write(SECCOMP_SOURCE)
            
            compile_cmd = ["gcc", "-o", executable_file, source_file, "-lseccomp"]
            
            result = subprocess.run(compile_cmd, capture_output=True, text=True)
            
            if result.returncode != 0:
                print(f"[X] Failed to compile block binary: {result.stderr.strip()}")
                return None
            
            permanent_path = "/tmp/block-aicoder"
            shutil.move(executable_file, permanent_path)
            os.chmod(permanent_path, 0o755)
            
            # Compute and store hash for integrity checking
            _block_executable_hash = compute_file_hash(permanent_path)
            _block_executable_path = permanent_path
            
            print(f"[+] Block binary compiled and verified")
            print(f"[+] SHA256: {_block_executable_hash[:16]}...")
            return permanent_path
            
    except Exception as e:
        print(f"[X] Failed to compile block binary: {e}")
        return None
    finally:
        _compilation_in_progress = False

def create_plugin(ctx):
    def _handle_block(args_str: str) -> None:
        global _network_blocking_enabled, _disk_blocking_enabled
        
        args = args_str.strip().split()

        if not args or args == [""]:
            net_status = "ON" if _network_blocking_enabled else "OFF"
            disk_status = "ON" if _disk_blocking_enabled else "OFF"
            print(f"Block status: Network {net_status}, Disk {disk_status}")
            return

        if args[0] in ("on", "enable", "1"):
            # Enable specified blocks
            net_enabled = "net" in args
            disk_enabled = "disk" in args
            if net_enabled and not _network_blocking_enabled:
                _network_blocking_enabled = True
                print("[+] Network blocking enabled")
            if disk_enabled and not _disk_blocking_enabled:
                _disk_blocking_enabled = True
                print("[+] Disk blocking enabled")
            if not net_enabled and not disk_enabled:
                _network_blocking_enabled = True
                _disk_blocking_enabled = True
                print("[+] Network and disk blocking enabled")
                
        elif args[0] in ("off", "disable", "0"):
            _network_blocking_enabled = False
            _disk_blocking_enabled = False
            print("[-] All blocking disabled")
            
        elif args[0] == "toggle":
            if len(args) == 1:
                # Toggle both
                _network_blocking_enabled = not _network_blocking_enabled
                _disk_blocking_enabled = not _disk_blocking_enabled
                net_status = "enabled" if _network_blocking_enabled else "disabled"
                disk_status = "enabled" if _disk_blocking_enabled else "disabled"
                print(f"[+] Network and disk blocking {net_status}/{disk_status}")
            else:
                # Toggle specific
                if "net" in args:
                    _network_blocking_enabled = not _network_blocking_enabled
                    status = "enabled" if _network_blocking_enabled else "disabled"
                    print(f"[+] Network blocking {status}")
                if "disk" in args:
                    _disk_blocking_enabled = not _disk_blocking_enabled
                    status = "enabled" if _disk_blocking_enabled else "disabled"
                    print(f"[+] Disk blocking {status}")

        elif args[0] in ("help", "-h", "--help"):
            print("Block Plugin Commands:")
            print("  /block              - Show current status")
            print("  /block on net disk  - Enable network and disk blocking")
            print("  /block on net       - Enable network blocking only")
            print("  /block on disk      - Enable disk blocking only")
            print("  /block off          - Disable all blocking")
            print("  /block toggle       - Toggle both network and disk")
            print("  /block toggle net   - Toggle network only")
            print("  /block toggle disk  - Toggle disk only")
        else:
            print(f"Unknown argument: {args[0]}")
            print("Use /block help for usage")

    def patch_run_shell_command():
        tool_def = ctx.app.tool_manager.tools.get("run_shell_command")
        if not tool_def or not tool_def.get("execute"):
            return
        
        original_execute = tool_def["execute"]
        
        def patched_execute(args_obj: Dict[str, Any]) -> Dict[str, Any]:
            global _network_blocking_enabled, _disk_blocking_enabled, _block_executable_path
            
            if _network_blocking_enabled or _disk_blocking_enabled:
                # Verify binary integrity before use
                if not _block_executable_path or not os.path.exists(_block_executable_path) or not verify_binary_integrity():
                    executable = compile_block_executable()
                    if not executable:
                        print("[!] Failed to compile secure block binary - running without protection")
                        return original_execute(args_obj)
                
                command = args_obj.get("command", "")
                if command:
                    # Build flags
                    flags = []
                    if _network_blocking_enabled:
                        flags.append("--no-net")
                    if _disk_blocking_enabled:
                        flags.append("--no-disk")
                    
                    # Use heredoc approach with unique delimiter to handle complex commands safely
                    flag_str = " ".join(flags)
                    import time
                    import random
                    unique_id = f"{int(time.time())}_{random.randint(1000, 9999)}"
                    delimiter = f"__AICODER_HEREDOC_DELIMITER_{unique_id}"
                    
                    if flag_str:
                        wrapped_command = f'''command=$(cat <<'{delimiter}'
{command}
{delimiter}
)
timeout 60s {_block_executable_path} {flag_str} -- bash -c "$command"'''
                    else:
                        wrapped_command = f'''command=$(cat <<'{delimiter}'
{command}
{delimiter}
)
timeout 60s {_block_executable_path} -- bash -c "$command"'''
                    
                    args_obj = args_obj.copy()
                    args_obj["command"] = wrapped_command
            
            return original_execute(args_obj)
        
        tool_def["execute"] = patched_execute
    
    ctx.register_command("/block", _handle_block, "Unified network and disk blocking")
    patch_run_shell_command()
    
    requirements_ok, missing = check_requirements()
    if requirements_ok:
        print("[+] Block plugin loaded (use /block on net disk)")
    else:
        print("[+] Block plugin loaded (missing: {', '.join(missing)})")