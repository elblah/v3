"""
Cross-platform file operations with sandbox enforcement
Stateless module functions - no classes needed
"""

import ctypes
import errno
import os
import stat
import time
from pathlib import Path
from typing import Optional, Set

# Module-level state
_current_dir = os.getcwd()
_read_files: Set[str] = set()
_plugin_system = None


def set_plugin_system(plugin_system) -> None:
    """Set the plugin system (wired by ToolManager at startup)."""
    global _plugin_system
    _plugin_system = plugin_system


def _whitelisted_dirs() -> list:
    """Dirs whitelisted by plugins via the on_file_sandbox_whitelist hook.

    Each hook returns a dir path or an iterable of paths. Whitelisted dirs
    grant READ-ONLY access; write tools never consult the whitelist.
    """
    if not _plugin_system:
        return []
    try:
        results = _plugin_system.call_hooks("on_file_sandbox_whitelist")
    except Exception:
        return []
    if not results:
        return []
    dirs = []
    for result in results:
        if result is None:
            continue
        entries = [result] if isinstance(result, str) else result
        for entry in entries:
            if isinstance(entry, str) and entry:
                dirs.append(str(Path(os.path.expanduser(entry)).resolve()))
    return dirs


def get_current_dir() -> str:
    """Get current working directory"""
    return _current_dir


def get_relative_path(path: str) -> str:
    """Get relative path from current working directory"""
    try:
        # Use Path to get relative path
        current = Path(_current_dir)
        target = Path(path).resolve()
        
        # If target is within current directory, return relative path
        try:
            return str(target.relative_to(current))
        except ValueError:
            # If not within current directory, return absolute path
            return str(target)
    except Exception:
        # Fallback to original path
        return path


def rotate_debug_log(path: str) -> Optional[str]:
    """Keep previous debug log when KEEP_LAST_RESPONSE_LOG=1.

    Moves the existing file to .aicoder/debug/responses/<stem>-<timestamp><ext>
    before the new log overwrites it. Returns the new path, or None if nothing
    was moved.
    """
    if os.environ.get("KEEP_LAST_RESPONSE_LOG", "").lower() in ("", "0", "false", "no", "off"):
        return None
    if not os.path.exists(path):
        return None
    stem, ext = os.path.splitext(os.path.basename(path))
    archive_dir = os.path.join(os.getcwd(), ".aicoder", "debug", "responses")
    os.makedirs(archive_dir, exist_ok=True)
    new_path = os.path.join(archive_dir, f"{stem}-{time.strftime('%Y%m%d-%H%M%S')}{ext}")
    n = 1
    while os.path.exists(new_path):
        new_path = os.path.join(archive_dir, f"{stem}-{time.strftime('%Y%m%d-%H%M%S')}-{n}{ext}")
        n += 1
    os.rename(path, new_path)
    return new_path


def check_sandbox(path: str, context: str = "file operation", print_message: bool = True,
                  write: bool = False) -> bool:
    """Check if a path is allowed by sandbox rules.

    Symlink-safe: resolves symlinks and parent traversal before the prefix
    check, so a link inside cwd pointing outside is rejected (non-existent
    tail is resolved via its parent, so writes to new files still work).

    Paths outside cwd are allowed if inside a plugin-whitelisted dir
    (on_file_sandbox_whitelist hook) — read-only, so write=True skips it.
    """
    # Import here to avoid circular imports
    try:
        from aicoder.core.config import Config
    except ImportError:
        # Config not available - allow everything
        return True

    if Config.sandbox_disabled():
        return True

    if not path:
        return True

    # Resolve relative paths AND symlinks (os.path.abspath is NOT enough:
    # a symlink in cwd pointing at / passes a lexical prefix check)
    current_dir = os.getcwd()
    resolved_path = str(Path(os.path.join(current_dir, path)).resolve())

    # Check if resolved path is within current directory
    # Must either be exactly current dir or start with current dir + '/'
    if not (
        resolved_path == current_dir
        or resolved_path.startswith(current_dir + "/")
    ):
        if not write and any(
            resolved_path == allowed or resolved_path.startswith(allowed + "/")
            for allowed in _whitelisted_dirs()
        ):
            return True
        if print_message:
            try:
                from aicoder.utils.log import warn
                warn(f'Sandbox: {context} trying to access "{resolved_path}" outside current directory "{current_dir}"')
            except ImportError:
                # Fallback if log utils not available
                import sys
                print(
                    f'[x] Sandbox: {context} trying to access "{path}" (contains parent traversal)',
                    file=sys.stderr
                )
        return False

    return True


def file_exists(path: str) -> bool:
    """Check if file exists (no sandbox)"""
    return os.path.exists(path)


class SandboxRaceError(Exception):
    """Raised when an opened fd's real path escapes the sandbox."""


# openat2 kernel UAPI constants. No glibc wrapper exists, so we call the
# raw syscall via ctypes. __NR_openat2 comes from the unified syscall
# table (asm-generic/unistd.h): 437 on arm64 and every other 64-bit arch.
# RESOLVE_BENEATH is from linux/openat2.h and forbids path resolution
# (including symlink targets) from leaving dirfd's subtree.
_SYS_OPENAT2 = 437
_RESOLVE_BENEATH = 0x08

_libc = ctypes.CDLL(None, use_errno=True)

# None = unprobed. Android's zygote seccomp filter sends SIGSYS ("Bad
# system call", instant death) for syscalls missing from its allowlist,
# instead of the ENOSYS a bare old kernel returns — so openat2 support
# must be probed in a throwaway child, never in-process.
_openat2_state: Optional[bool] = None


def _openat2_supported() -> bool:
    """One-shot forked probe; result cached for process lifetime."""
    global _openat2_state
    if _openat2_state is None:
        try:
            pid = os.fork()
            if pid == 0:
                code = 1
                try:
                    fd = os.open(".", os.O_RDONLY | os.O_DIRECTORY)
                    try:
                        _openat2_beneath(fd, ".", os.O_RDONLY, 0)
                        code = 0
                    finally:
                        os.close(fd)
                except OSError as error:
                    if error.errno in (errno.ENOSYS, errno.EINVAL):
                        # Bare old kernel: errno path, safe to attempt
                        # (call sites fall back on these errnos anyway).
                        code = 0
                finally:
                    os._exit(code)
            _, status = os.waitpid(pid, 0)
            _openat2_state = os.WIFEXITED(status) and os.WEXITSTATUS(status) == 0
        except OSError:
            _openat2_state = False  # fork/wait failed: fail closed
    return _openat2_state


def _openat2_beneath(dirfd: int, rel: str, flags: int, mode: int) -> int:
    """openat2(dirfd, rel, {flags, mode, RESOLVE_BENEATH}, 24).

    Kernel-atomic containment: symlink resolution can never escape dirfd.
    Raises OSError(err=ENOSYS/EINVAL) when openat2 is unsupported so the
    caller can fall back to post-open verification.
    """
    # struct open_how { __u64 flags; __u64 mode; __u64 resolve; }
    how = (ctypes.c_uint64 * 3)(
        ctypes.c_uint64(flags & 0xFFFFFFFFFFFFFFFF),
        ctypes.c_uint64(mode),
        ctypes.c_uint64(_RESOLVE_BENEATH),
    )
    ctypes.set_errno(0)
    res = _libc.syscall(
        ctypes.c_long(_SYS_OPENAT2),
        ctypes.c_int(dirfd),
        rel.encode("utf-8"),
        how,
        ctypes.c_size_t(ctypes.sizeof(how)),
    )
    if res < 0:
        raise OSError(ctypes.get_errno(), os.strerror(ctypes.get_errno()))
    return res


def open_directory_verified(path: str, context: str) -> int:
    """Open a directory fd proven in-bounds (TOCTOU-safe). Caller closes."""
    return _open_verified(path, os.O_RDONLY | os.O_DIRECTORY, context)


def _lexical_rel_under(path: str, write: bool):
    """Pick (root, rel) with path lexically inside root; None if outside all.

    Roots: cwd first, then plugin-whitelisted dirs (read-only, skipped for
    writes). Deliberately NOT symlink-resolved — openat2 enforces that part.
    """
    candidates = [os.getcwd()]
    if not write:
        candidates.extend(_whitelisted_dirs())
    for root in candidates:
        rel = os.path.relpath(os.path.normpath(path), root)
        if rel != ".." and not rel.startswith("../"):
            return root, rel
    return None


def _fd_realpath(fd: int) -> Optional[str]:
    """Real path of an open fd via /proc, tolerating '(deleted)' suffix."""
    try:
        real = os.readlink(f"/proc/self/fd/{fd}")
    except OSError:
        return None
    if real.endswith(" (deleted)"):
        real = real.removesuffix(" (deleted)")
    return real


def _real_path_allowed(real: str, write: bool) -> bool:
    """Containment rule on a fully-resolved path (same set as check_sandbox)."""
    current_dir = os.getcwd()
    if real == current_dir or real.startswith(current_dir + "/"):
        return True
    if not write:
        return any(
            real == allowed or real.startswith(allowed + "/")
            for allowed in _whitelisted_dirs()
        )
    return False


def _walk_parent_verified(root_fd: int, rel: str, context: str) -> int:
    """Pin the parent directory of rel by fd, every hop proven in-bounds.

    Each component opens with O_NOFOLLOW under the previously pinned fd;
    a symlink component is followed once and its resulting directory fd
    is verified before the walk continues, so a swapped link can never
    anchor creation outside the sandbox. Caller owns the returned fd.
    """
    parts = [p for p in rel.split("/") if p and p != "."][:-1]
    cur = os.dup(root_fd)
    prefix = ""
    try:
        for part in parts:
            try:
                nxt = os.open(
                    part,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC,
                    dir_fd=cur,
                )
                prefix = os.path.normpath(os.path.join(prefix, part))
            except OSError as error:
                if error.errno not in (errno.ELOOP, errno.ENOTDIR):
                    raise  # ENOENT/EACCES propagate to caller
                # Some kernels give ENOTDIR rather than ELOOP for
                # O_NOFOLLOW|O_DIRECTORY on a symlink; confirm it really
                # is a symlink before following.
                st = os.stat(part, dir_fd=cur, follow_symlinks=False)
                if not stat.S_ISLNK(st.st_mode):
                    raise  # genuine ENOTDIR (file used as directory)
                # Symlinked directory component: follow it once, then
                # prove where it actually landed before continuing.
                target = os.readlink(part, dir_fd=cur)
                if os.path.isabs(target):
                    prefix = os.path.normpath(target)
                else:
                    prefix = os.path.normpath(os.path.join(prefix, target))
                nxt = os.open(
                    os.path.join(os.getcwd(), prefix)
                    if not os.path.isabs(prefix)
                    else prefix,
                    os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC,
                )
            real = _fd_realpath(nxt)
            if real is None or not _real_path_allowed(real, True):
                os.close(nxt)
                raise SandboxRaceError(
                    f'{context}: "{rel}" escapes sandbox via "{part}"; blocked'
                )
            os.close(cur)
            cur = nxt
        return cur
    except BaseException:
        os.close(cur)
        raise


def _open_verified_proc(root_fd: int, rel: str, path: str, flags: int, context: str):
    """Fallback verification without openat2: prove in-bounds BEFORE any
    filesystem side effect.

    Reads (no side effects) still open-then-verify. Writes open WITHOUT
    O_CREAT/O_TRUNC first and truncate only after verification, so a race
    that swaps an escaping symlink into place leaves nothing behind — no
    created file, no truncated victim. Creation happens only via
    openat() with O_EXCL|O_NOFOLLOW inside an fd-pinned verified parent,
    which pins the inode regardless of later path manipulation.
    """
    if not flags & (os.O_WRONLY | os.O_RDWR):
        fd = os.open(path, flags | os.O_CLOEXEC)
        real = _fd_realpath(fd)
        if real is None or not _real_path_allowed(real, write=False):
            os.close(fd)
            raise SandboxRaceError(
                f'{context}: "{path}" escaped sandbox during open '
                f"(resolved to {real or 'unknown'}); blocked"
            )
        return fd

    base_flags = flags & ~(os.O_CREAT | os.O_TRUNC)
    try:
        fd = os.open(path, base_flags | os.O_CLOEXEC)
    except FileNotFoundError:
        # Target absent: create it inside the fd-pinned verified parent.
        parent = _walk_parent_verified(root_fd, rel, context)
        try:
            name = [p for p in rel.split("/") if p][-1]
            fd = os.open(
                name,
                os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                | os.O_CLOEXEC,
                0o666,
                dir_fd=parent,
            )
        except FileExistsError:
            # Raced into existence between our probes: plain open.
            fd = os.open(path, base_flags | os.O_CLOEXEC)
        finally:
            os.close(parent)
    except OSError:
        # Dangling final symlink (ENOENT after follow), EISDIR, EACCES...
        raise
    real = _fd_realpath(fd)
    if real is None or not _real_path_allowed(real, True):
        os.close(fd)
        raise SandboxRaceError(
            f'{context}: "{path}" escaped sandbox during open '
            f"(resolved to {real or 'unknown'}); blocked"
        )
    if flags & os.O_TRUNC:
        os.ftruncate(fd, 0)  # post-verify: inode already proven in-bounds
    return fd


def _open_verified(path: str, flags: int, context: str):
    """Open path proven in-bounds: openat2(RESOLVE_BENEATH) primary.

    RESOLVE_BENEATH makes containment a kernel guarantee during pathname
    resolution — no TOCTOU window at all. Falls back to open+verify (/proc)
    on kernels without openat2; fails closed when neither method works.
    """
    try:
        from aicoder.core.config import Config
        disabled = Config.sandbox_disabled()
    except ImportError:
        disabled = True
    if disabled:
        return os.open(path, flags)

    write = bool(flags & (os.O_WRONLY | os.O_RDWR))
    picked = _lexical_rel_under(
        path if os.path.isabs(path) else os.path.join(os.getcwd(), path), write
    )
    if picked is None:
        raise SandboxRaceError(
            f'{context}: "{path}" is outside sandbox roots; blocked'
        )
    root, rel = picked

    try:
        root_fd = os.open(root, os.O_RDONLY | os.O_DIRECTORY | os.O_CLOEXEC)
    except OSError as error:
        raise SandboxRaceError(f"{context}: cannot open sandbox root '{root}': {error}") from error

    try:
        try:
            if not _openat2_supported():
                raise OSError(errno.ENOSYS, "openat2 unavailable (seccomp/old kernel)")
            return _openat2_beneath(
                root_fd, rel, flags, 0o666 if flags & os.O_CREAT else 0
            )
        except OSError as error:
            if error.errno in (errno.EXDEV, errno.ENOENT):
                # EXDEV: RESOLVE_BENEATH rejects absolute symlinks outright
                # and relative ones that escape. ENOENT is ambiguous: an
                # escaping component can transiently vanish mid-race and
                # surface as ENOENT instead of EXDEV. Re-check via /proc
                # provenance so escapes are named and honest vanishes stay
                # FileNotFoundError; without /proc this fails closed.
                if os.path.exists("/proc/self/fd"):
                    return _open_verified_proc(
                        root_fd, rel, path, flags, context
                    )
                if error.errno == errno.EXDEV:
                    raise SandboxRaceError(
                        f'{context}: "{path}" escaped sandbox during open '
                        "(RESOLVE_BENEATH rejected symlink/traversal; no "
                        "/proc fallback); blocked"
                    ) from error
                raise  # honest ENOENT, no verifier available
            if error.errno not in (errno.ENOSYS, errno.EINVAL):
                raise  # genuine open error (ENOENT, EACCES, ...)
        # openat2 unavailable on this kernel — verify before side effects.
        return _open_verified_proc(root_fd, rel, path, flags, context)
    finally:
        os.close(root_fd)


def read_file_verified(path: str) -> str:
    """TOCTOU-safe read for AI-facing callers. Same content contract as
    read_file(), but the open itself is proven in-bounds."""
    try:
        fd = _open_verified(path, os.O_RDONLY, "read")
        with os.fdopen(fd, "r", encoding="utf-8", closefd=True) as f:
            content = f.read()
        _read_files.add(path)
        return content
    except SandboxRaceError:
        raise
    except Exception as error:
        raise Exception(f"Error reading file '{path}': {error}") from error


def write_file_verified(path: str, content: str) -> str:
    """TOCTOU-safe write for AI-facing callers. Same contract as
    write_file(), but the create/truncate open is proven in-bounds.

    Missing parent dirs are created only after a verified open proves
    them absent. A race swapping an escaping symlink into place after
    that creation can leave an empty directory outside (accepted), but
    the retried verified open still blocks any content escape.
    """
    flags = os.O_WRONLY | os.O_CREAT | os.O_TRUNC
    try:
        try:
            fd = _open_verified(path, flags, "write")
        except FileNotFoundError:
            dir_path = os.path.dirname(os.path.abspath(path))
            if _lexical_rel_under(dir_path, True) is None:
                raise SandboxRaceError(
                    f'write: "{path}" is outside sandbox roots; blocked'
                ) from None
            os.makedirs(dir_path, exist_ok=True)
            fd = _open_verified(path, flags, "write")
        with os.fdopen(fd, "w", encoding="utf-8", closefd=True) as f:
            f.write(content)
        bytes_count = len(content.encode("utf-8"))
        lines_count = len(content.split("\n"))
        return f"Successfully wrote {bytes_count} bytes ({lines_count} lines) to {path}"
    except SandboxRaceError:
        raise
    except Exception as error:
        raise Exception(f"Error writing file '{path}': {error}") from error


def read_file(path: str) -> str:
    """Read a file (no sandbox) - default behavior for internal use"""
    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()
        _read_files.add(path)
        return content
    except Exception as error:
        raise Exception(f"Error reading file '{path}': {error}") from error


def read_file_with_sandbox(path: str) -> str:
    """Read a file with sandbox check - for AI requests only"""
    # Check sandbox first
    if not check_sandbox(path, "read_file"):
        raise Exception(
            f'read_file: path "{path}" outside current directory not allowed'
        )

    return read_file_verified(path)


def write_file(path: str, content: str) -> str:
    """Write to a file (no sandbox) - default behavior for internal use"""
    try:
        # Create directory if it doesn't exist
        dir_path = os.path.dirname(path)
        if dir_path:  # Only create if there's actually a directory path
            os.makedirs(dir_path, exist_ok=True)

        with open(path, "w", encoding="utf-8") as f:
            f.write(content)

        bytes_count = len(content.encode("utf-8"))
        lines_count = len(content.split("\n"))
        return f"Successfully wrote {bytes_count} bytes ({lines_count} lines) to {path}"
    except Exception as error:
        raise Exception(f"Error writing file '{path}': {error}") from error


def write_file_with_sandbox(path: str, content: str) -> str:
    """Write to a file with sandbox check - for AI requests only"""
    # Check sandbox first
    if not check_sandbox(path, "write_file"):
        raise Exception(
            f'write_file: path "{path}" outside current directory not allowed'
        )

    return write_file_verified(path, content)


def list_directory(path: str) -> list:
    """List directory contents (with sandbox check)"""
    # Resolve path first
    resolved_path = str(Path(path).resolve())

    # Check sandbox
    if not check_sandbox(resolved_path, "list_directory"):
        raise Exception(
            f'list_directory: path "{path}" (resolves to "{resolved_path}") outside current directory not allowed'
        )

    try:
        fd = _open_verified(path or ".", os.O_RDONLY | os.O_DIRECTORY, "list_directory")
        try:
            entries = os.listdir(fd)  # fd-bound: kernel-proven directory
        finally:
            os.close(fd)

        # Filter only files/dirs (no special entries)
        excluded = ["node_modules", ".git", ".vscode", ".idea", "dist", "build"]
        valid_entries = []

        for entry in entries:
            if not entry.startswith(".") and entry not in excluded:
                valid_entries.append(entry)

        return valid_entries
    except Exception as error:
        raise Exception(f"Error listing directory '{resolved_path}': {error}") from error


def get_read_files() -> Set[str]:
    """Get set of files that have been read"""
    return _read_files.copy()
