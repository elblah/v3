"""
Alt file tools plugin - move / copy / delete / mkdir / stat without a shell.

Registered only when AICODER_ALT_FILETOOLS=1. Meant for restricted
deployments where run_shell_command is unavailable (no exec), so the model
still has a way to reorganize files.

Tools: move_path, copy_path, delete_path, create_directory, path_info.

Safety model:
- Every path passes check_sandbox(..., write=True) first, which also fires
  the on_file_access plugin hook (file_guard veto) and the hard denylist.
- Real operations run through fd-pinned parent directories
  (open_directory_verified -> openat2 RESOLVE_BENEATH where available), so a
  symlink swapped in after the check cannot redirect outside the sandbox.
- Symlinks are never followed: lstat decides the type, unlink removes the
  link itself, copy recreates it, recursion descends only real directories.
- Refuses to move/delete the working directory or any of its ancestors, to
  move/copy a directory into itself, and to overwrite unless explicitly
  asked (overwrite defaults to false).
- Recursive delete pre-scans the tree and refuses above MAX_ENTRIES before
  touching anything (no half-deleted trees).
"""

import errno
import os
import stat
import time
from typing import Any, Dict, Optional, Tuple

from aicoder.utils.bool_utils import env_bool, parse_bool
from aicoder.utils.file_utils import (
    check_sandbox,
    open_directory_verified,
    sandbox_denial_message,
)

ENV_FLAG = "AICODER_ALT_FILETOOLS"

# Recursive operations refuse to run above this many entries.
MAX_ENTRIES = 5000
COPY_CHUNK = 1 << 16
DIR_OPEN_FLAGS = os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW | os.O_CLOEXEC


class Refused(Exception):
    """Operation rejected before any filesystem change was made."""


# ---------------------------------------------------------------- helpers


def _fail(tool: str, message: str) -> Dict[str, str]:
    text = f"{tool}: {message}"
    return {"tool": tool, "friendly": text, "detailed": text}


def _ok(tool: str, text: str) -> Dict[str, str]:
    return {"tool": tool, "friendly": text, "detailed": text}


def _arg(args: Dict[str, Any], key: str) -> str:
    value = args.get(key)
    if isinstance(value, str):
        value = value.strip()
    if not value:
        raise Refused(f"'{key}' is required")
    return str(value)


def _flag(args: Dict[str, Any], key: str, default: bool = False) -> bool:
    """Bool argument, tolerant of 'true'/'yes'/'1' strings."""
    value = args.get(key)
    if value is None:
        return default
    if isinstance(value, str):
        return parse_bool(value.strip(), default)
    return bool(value)


def _abs(path: str) -> str:
    return os.path.abspath(os.path.expanduser(path))


def _resolve(path: str, tool: str, write: bool) -> str:
    """Sandbox-check a path and return its absolute form."""
    abs_path = _abs(path)
    if not check_sandbox(abs_path, tool, print_message=False, write=write):
        raise Refused(f"{abs_path}: {sandbox_denial_message(path)}")
    return abs_path


def _pin_parent(path: str, tool: str, write: bool = True) -> Tuple[int, str, str]:
    """Open the verified parent dir. Returns (fd, name, abs_path).

    Caller owns the fd.
    """
    abs_path = _resolve(path, tool, write)
    parent, name = os.path.split(abs_path)
    if name in ("", ".", "..", os.sep):
        raise Refused(f"invalid target name in '{abs_path}'")
    try:
        fd = open_directory_verified(parent, tool)
    except FileNotFoundError:
        raise Refused(f"parent directory not found: {parent}")
    except NotADirectoryError:
        raise Refused(f"parent path is not a directory: {parent}")
    except OSError as error:
        raise Refused(f"cannot open parent directory '{parent}': {error.strerror}")
    return fd, name, abs_path


def _lstat(fd: int, name: str) -> Optional[os.stat_result]:
    try:
        return os.lstat(name, dir_fd=fd)
    except FileNotFoundError:
        return None


def _exists(fd: int, name: str) -> bool:
    return _lstat(fd, name) is not None


def _kind(st: os.stat_result) -> str:
    mode = st.st_mode
    if stat.S_ISLNK(mode):
        return "symlink"
    if stat.S_ISDIR(mode):
        return "directory"
    if stat.S_ISREG(mode):
        return "file"
    if stat.S_ISFIFO(mode):
        return "fifo"
    if stat.S_ISSOCK(mode):
        return "socket"
    if stat.S_ISCHR(mode) or stat.S_ISBLK(mode):
        return "device"
    return "special file"


def _guard_target(abs_path: str, action: str) -> None:
    """Refuse destroying the session's working directory or an ancestor."""
    cwd = os.getcwd()
    if abs_path == cwd or cwd.startswith(abs_path + os.sep):
        raise Refused(
            f"refusing to {action} '{abs_path}': it is the working directory "
            f"or contains it"
        )


def _human(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if value < 1024 or unit == "TB":
            return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{size} B"


def _scan_tree(parent_fd: int, name: str, abs_path: str) -> Tuple[int, int]:
    """Count (entries, bytes) under name. Never follows symlinks."""
    count, size = 0, 0
    try:
        root = os.open(name, DIR_OPEN_FLAGS, dir_fd=parent_fd)
    except OSError:
        return 0, 0
    stack = [(root, abs_path)]
    try:
        while stack:
            fd, base = stack.pop()
            try:
                entries = list(os.scandir(fd))
                for entry in entries:
                    count += 1
                    if count > MAX_ENTRIES:
                        return count, size
                    if entry.is_dir(follow_symlinks=False):
                        try:
                            child = os.open(
                                entry.name, DIR_OPEN_FLAGS, dir_fd=fd
                            )
                        except OSError:
                            continue
                        stack.append((child, os.path.join(base, entry.name)))
                    elif entry.is_file(follow_symlinks=False):
                        try:
                            size += entry.stat(follow_symlinks=False).st_size
                        except OSError:
                            pass
            except OSError:
                pass
            finally:
                os.close(fd)
    finally:
        for fd, _ in stack:
            os.close(fd)
    return count, size


def _write_all(fd: int, data: bytes) -> None:
    view = memoryview(data)
    while view:
        written = os.write(fd, view)
        if written <= 0:
            raise OSError(errno.EIO, "short write")
        view = view[written:]


def _copy_file(
    src_fd: int, src_name: str, dst_fd: int, dst_name: str, st: os.stat_result
) -> int:
    """Copy one regular file's bytes + mode. Returns bytes copied."""
    src = os.open(src_name, os.O_RDONLY | os.O_NOFOLLOW | os.O_CLOEXEC, dir_fd=src_fd)
    try:
        dst = os.open(
            dst_name,
            os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW | os.O_CLOEXEC,
            st.st_mode & 0o777,
            dir_fd=dst_fd,
        )
        try:
            total = 0
            while True:
                chunk = os.read(src, COPY_CHUNK)
                if not chunk:
                    break
                _write_all(dst, chunk)
                total += len(chunk)
        finally:
            os.close(dst)
    finally:
        os.close(src)
    # Restore the source mode exactly (umask trimmed it at creation).
    try:
        os.chmod(dst_name, st.st_mode & 0o777, dir_fd=dst_fd)
    except OSError:
        pass
    return total


def _copy_entry(
    src_fd: int,
    src_name: str,
    dst_fd: int,
    dst_name: str,
    abs_src: str,
    abs_dst: str,
    overwrite: bool,
    counter: Dict[str, int],
) -> None:
    """Recursively copy one entry. Never follows symlinks."""
    st = _lstat(src_fd, src_name)
    if st is None:
        raise Refused(f"source not found: {abs_src}")
    counter["entries"] += 1
    if counter["entries"] > MAX_ENTRIES:
        raise Refused(
            f"copy exceeds the {MAX_ENTRIES}-entry limit; refusing partial copy"
        )

    if stat.S_ISLNK(st.st_mode):
        target = os.readlink(src_name, dir_fd=src_fd)
        if _exists(dst_fd, dst_name):
            if not overwrite:
                raise Refused(f"destination exists: {abs_dst} (pass overwrite=true)")
            os.unlink(dst_name, dir_fd=dst_fd)
        os.symlink(target, dst_name, dir_fd=dst_fd)
        return

    if stat.S_ISDIR(st.st_mode):
        dst_st = _lstat(dst_fd, dst_name)
        if dst_st is None:
            os.mkdir(dst_name, st.st_mode & 0o777, dir_fd=dst_fd)
        elif not stat.S_ISDIR(dst_st.st_mode):
            if not overwrite:
                raise Refused(f"destination exists: {abs_dst} (pass overwrite=true)")
            os.unlink(dst_name, dir_fd=dst_fd)
            os.mkdir(dst_name, st.st_mode & 0o777, dir_fd=dst_fd)
        src_sub = os.open(src_name, DIR_OPEN_FLAGS, dir_fd=src_fd)
        try:
            dst_sub = os.open(dst_name, DIR_OPEN_FLAGS, dir_fd=dst_fd)
            try:
                for entry in sorted(os.listdir(src_sub)):
                    _copy_entry(
                        src_sub,
                        entry,
                        dst_sub,
                        entry,
                        os.path.join(abs_src, entry),
                        os.path.join(abs_dst, entry),
                        overwrite,
                        counter,
                    )
            finally:
                os.close(dst_sub)
        finally:
            os.close(src_sub)
        try:
            os.chmod(dst_name, st.st_mode & 0o777, dir_fd=dst_fd)
        except OSError:
            pass
        return

    if stat.S_ISREG(st.st_mode):
        dst_st = _lstat(dst_fd, dst_name)
        if dst_st is not None:
            if stat.S_ISDIR(dst_st.st_mode):
                raise Refused(f"destination is a directory: {abs_dst}")
            if not overwrite:
                raise Refused(f"destination exists: {abs_dst} (pass overwrite=true)")
        counter["bytes"] += _copy_file(src_fd, src_name, dst_fd, dst_name, st)
        return

    raise Refused(f"unsupported file type: {abs_src} ({_kind(st)})")


def _remove_tree(parent_fd: int, name: str, abs_path: str) -> Tuple[int, int]:
    """Delete a directory tree through fd-pinned hops. (entries, bytes)."""
    count, size = 0, 0
    fd = os.open(name, DIR_OPEN_FLAGS, dir_fd=parent_fd)
    try:
        for entry in list(os.scandir(fd)):
            count += 1
            child_abs = os.path.join(abs_path, entry.name)
            st = entry.stat(follow_symlinks=False)
            if stat.S_ISDIR(st.st_mode):
                if not check_sandbox(child_abs, "delete_path", print_message=False, write=True):
                    raise Refused(
                        f"{child_abs}: {sandbox_denial_message(child_abs)}"
                    )
                sub_count, sub_size = _remove_tree(fd, entry.name, child_abs)
                count += sub_count
                size += sub_size
            else:
                if stat.S_ISREG(st.st_mode):
                    size += st.st_size
                os.unlink(entry.name, dir_fd=fd)
    finally:
        os.close(fd)
    os.rmdir(name, dir_fd=parent_fd)
    return count, size


# ------------------------------------------------------------------ tools


def move_path(args: Dict[str, Any]) -> Dict[str, str]:
    """Move/rename a file, symlink or directory (same filesystem)."""
    tool = "move_path"
    try:
        source = _arg(args, "source")
        destination = _arg(args, "destination")
        overwrite = _flag(args, "overwrite")

        src_fd, src_name, src_abs = _pin_parent(source, tool)
        try:
            dst_fd, dst_name, dst_abs = _pin_parent(destination, tool)
        except Exception:
            os.close(src_fd)
            raise
        try:
            st = _lstat(src_fd, src_name)
            if st is None:
                raise Refused(f"source not found: {src_abs}")
            _guard_target(src_abs, "move")
            if src_abs == dst_abs:
                raise Refused("source and destination are the same path")
            if stat.S_ISDIR(st.st_mode) and (
                dst_abs == src_abs or dst_abs.startswith(src_abs + os.sep)
            ):
                raise Refused(f"cannot move '{src_abs}' inside itself")

            dst_st = _lstat(dst_fd, dst_name)
            if dst_st is not None:
                if not overwrite:
                    raise Refused(
                        f"destination exists: {dst_abs} (pass overwrite=true)"
                    )
                if stat.S_ISDIR(dst_st.st_mode):
                    raise Refused(f"refusing to overwrite a directory: {dst_abs}")
                os.unlink(dst_name, dir_fd=dst_fd)

            note = ""
            try:
                os.rename(src_name, dst_name, src_dir_fd=src_fd, dst_dir_fd=dst_fd)
            except OSError as error:
                if error.errno != errno.EXDEV:
                    raise
                if stat.S_ISDIR(st.st_mode):
                    raise Refused(
                        "cross-device directory move is not supported; "
                        "use copy_path then delete_path"
                    )
                _copy_file(src_fd, src_name, dst_fd, dst_name, st)
                os.unlink(src_name, dir_fd=src_fd)
                note = " (cross-device: copied then removed source)"

            text = (
                f"Moved {_kind(st)}:\n"
                f"  from: {src_abs}\n"
                f"  to:   {dst_abs}{note}"
            )
            return _ok(tool, text)
        finally:
            os.close(src_fd)
            os.close(dst_fd)
    except Refused as error:
        return _fail(tool, str(error))
    except OSError as error:
        return _fail(tool, _os_error(error))


def copy_path(args: Dict[str, Any]) -> Dict[str, str]:
    """Copy a file, symlink or directory tree."""
    tool = "copy_path"
    try:
        source = _arg(args, "source")
        destination = _arg(args, "destination")
        overwrite = _flag(args, "overwrite")

        src_fd, src_name, src_abs = _pin_parent(source, tool)
        try:
            dst_fd, dst_name, dst_abs = _pin_parent(destination, tool)
        except Exception:
            os.close(src_fd)
            raise
        try:
            st = _lstat(src_fd, src_name)
            if st is None:
                raise Refused(f"source not found: {src_abs}")
            if src_abs == dst_abs:
                raise Refused("source and destination are the same path")
            if stat.S_ISDIR(st.st_mode) and dst_abs.startswith(src_abs + os.sep):
                raise Refused(f"cannot copy '{src_abs}' inside itself")

            dst_st = _lstat(dst_fd, dst_name)
            if dst_st is not None and not overwrite and not stat.S_ISDIR(dst_st.st_mode):
                raise Refused(f"destination exists: {dst_abs} (pass overwrite=true)")

            counter = {"entries": 0, "bytes": 0}
            _copy_entry(
                src_fd, src_name, dst_fd, dst_name, src_abs, dst_abs,
                overwrite, counter,
            )
            text = (
                f"Copied {_kind(st)}:\n"
                f"  from:    {src_abs}\n"
                f"  to:      {dst_abs}\n"
                f"  entries: {counter['entries']}, {_human(counter['bytes'])}"
            )
            return _ok(tool, text)
        finally:
            os.close(src_fd)
            os.close(dst_fd)
    except Refused as error:
        return _fail(tool, str(error))
    except OSError as error:
        return _fail(tool, _os_error(error))


def delete_path(args: Dict[str, Any]) -> Dict[str, str]:
    """Delete a file, symlink, empty dir or (with recursive=true) a tree."""
    tool = "delete_path"
    try:
        path = _arg(args, "path")
        recursive = _flag(args, "recursive")

        fd, name, abs_path = _pin_parent(path, tool)
        try:
            st = _lstat(fd, name)
            if st is None:
                raise Refused(f"path not found: {abs_path}")
            _guard_target(abs_path, "delete")

            if not stat.S_ISDIR(st.st_mode):
                os.unlink(name, dir_fd=fd)
                return _ok(tool, f"Deleted {_kind(st)}: {abs_path}")

            if not recursive:
                try:
                    os.rmdir(name, dir_fd=fd)
                except OSError as error:
                    if error.errno in (errno.ENOTEMPTY, errno.EEXIST):
                        raise Refused(
                            f"directory not empty: {abs_path} "
                            f"(pass recursive=true to delete it)"
                        )
                    raise
                return _ok(tool, f"Deleted empty directory: {abs_path}")

            entries, size = _scan_tree(fd, name, abs_path)
            if entries > MAX_ENTRIES:
                raise Refused(
                    f"refusing to delete {entries} entries from '{abs_path}' "
                    f"(limit {MAX_ENTRIES})"
                )
            _remove_tree(fd, name, abs_path)
            return _ok(
                tool,
                f"Deleted directory: {abs_path} "
                f"({entries} entries, {_human(size)})",
            )
        finally:
            os.close(fd)
    except Refused as error:
        return _fail(tool, str(error))
    except OSError as error:
        return _fail(tool, _os_error(error))


def create_directory(args: Dict[str, Any]) -> Dict[str, str]:
    """mkdir -p (or a single level with parents=false)."""
    tool = "create_directory"
    try:
        path = _arg(args, "path")
        parents = _flag(args, "parents", default=True)
        abs_path = _resolve(path, tool, write=True)

        cwd = os.getcwd()
        if abs_path == cwd:
            return _ok(tool, f"Directory already exists: {abs_path}")

        rel = os.path.relpath(abs_path, cwd)
        components = [c for c in rel.split(os.sep) if c not in ("", ".")]
        if not components:
            return _ok(tool, f"Directory already exists: {abs_path}")

        created = 0

        try:
            fd = open_directory_verified(cwd, tool)
        except OSError as error:
            raise Refused(f"cannot open working directory: {error.strerror}")

        base = cwd
        try:
            for index, comp in enumerate(components):
                last = index == len(components) - 1
                st = _lstat(fd, comp)
                if st is None:
                    if not parents and not last:
                        raise Refused(
                            f"parent directory not found: {os.path.join(base, comp)} "
                            f"(pass parents=true to create it)"
                        )
                    os.mkdir(comp, 0o777, dir_fd=fd)
                    created += 1
                elif not stat.S_ISDIR(st.st_mode):
                    raise Refused(
                        f"path component is not a directory: "
                        f"{os.path.join(base, comp)}"
                    )
                try:
                    next_fd = os.open(comp, DIR_OPEN_FLAGS, dir_fd=fd)
                except OSError as error:
                    raise Refused(f"cannot enter '{comp}': {error.strerror}")
                finally:
                    os.close(fd)
                fd = next_fd
                base = os.path.join(base, comp)
        finally:
            os.close(fd)

        if created:
            return _ok(tool, f"Created directory: {abs_path}")
        return _ok(tool, f"Directory already exists: {abs_path}")
    except Refused as error:
        return _fail(tool, str(error))
    except OSError as error:
        return _fail(tool, _os_error(error))


def path_info(args: Dict[str, Any]) -> Dict[str, str]:
    """Read-only stat of a path (never follows the final symlink)."""
    tool = "path_info"
    try:
        path = _arg(args, "path")
        abs_path = _resolve(path, tool, write=False)
        try:
            st = os.lstat(abs_path)
        except FileNotFoundError:
            raise Refused(f"path not found: {abs_path}")

        kind = _kind(st)
        lines = [abs_path, f"type: {kind}"]
        if stat.S_ISREG(st.st_mode):
            lines.append(f"size: {st.st_size} bytes ({_human(st.st_size)})")
        elif stat.S_ISDIR(st.st_mode):
            try:
                entries = len(os.listdir(abs_path))
                lines.append(f"entries: {entries} (top level)")
            except OSError:
                pass
        elif stat.S_ISLNK(st.st_mode):
            try:
                target = os.readlink(abs_path)
            except OSError:
                target = "?"
            lines.append(f"symlink target: {target}")
            lines.append(
                f"target exists: {'yes' if os.path.exists(abs_path) else 'no'}"
            )
        else:
            lines.append(f"size: {st.st_size} bytes")

        lines.append(f"mode: 0o{stat.S_IMODE(st.st_mode):04o}")
        lines.append(f"uid/gid: {st.st_uid}/{st.st_gid}")
        lines.append(f"links: {st.st_nlink}")
        lines.append(
            "modified: "
            + time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(st.st_mtime))
        )
        return _ok(tool, "\n".join(lines))
    except Refused as error:
        return _fail(tool, str(error))
    except OSError as error:
        return _fail(tool, _os_error(error))


def _os_error(error: OSError) -> str:
    """Readable OSError text (the operation usually lacks the filename)."""
    if error.filename:
        return f"{error.strerror or error} ({error.filename})"
    return error.strerror or str(error)


# --------------------------------------------------------- preview/format


def _preview_move(args: Dict[str, Any]) -> Dict[str, Any]:
    lines = [
        f"From: {args.get('source')}",
        f"To:   {args.get('destination')}",
    ]
    if _flag(args, "overwrite"):
        lines.append("Overwrite destination: yes")
    return {"tool": "move_path", "content": "\n".join(lines), "can_approve": True}


def _preview_copy(args: Dict[str, Any]) -> Dict[str, Any]:
    lines = [
        f"From: {args.get('source')}",
        f"To:   {args.get('destination')}",
    ]
    if _flag(args, "overwrite"):
        lines.append("Overwrite destination: yes")
    return {"tool": "copy_path", "content": "\n".join(lines), "can_approve": True}


def _preview_delete(args: Dict[str, Any]) -> Dict[str, Any]:
    path = args.get("path")
    recursive = _flag(args, "recursive")
    lines = [f"Path: {path}", f"Recursive: {'yes' if recursive else 'no'}"]
    try:
        fd, name, abs_path = _pin_parent(str(path or ""), "delete_path")
        try:
            st = _lstat(fd, name)
            if st is None:
                lines.append("Target: (not found)")
            elif stat.S_ISDIR(st.st_mode):
                if recursive:
                    entries, size = _scan_tree(fd, name, abs_path)
                    lines.append(
                        f"Target: directory, {entries} entries, {_human(size)}"
                    )
                    if entries >= MAX_ENTRIES:
                        lines.append(
                            f"Warning: at/over the {MAX_ENTRIES}-entry limit - "
                            f"the call will be refused"
                        )
                else:
                    lines.append("Target: directory (must be empty)")
            else:
                lines.append(f"Target: {_kind(st)}, {_human(st.st_size)}")
        finally:
            os.close(fd)
    except (Refused, OSError) as error:
        lines.append(f"Note: {error}")
    return {"tool": "delete_path", "content": "\n".join(lines), "can_approve": True}


def _preview_create(args: Dict[str, Any]) -> Dict[str, Any]:
    lines = [
        f"Path: {args.get('path')}",
        f"Parents: {'yes' if _flag(args, 'parents', default=True) else 'no'}",
    ]
    return {
        "tool": "create_directory",
        "content": "\n".join(lines),
        "can_approve": True,
    }


def _preview_info(args: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "tool": "path_info",
        "content": f"Path: {args.get('path')}",
        "can_approve": True,
    }


def _format_args_move(args: Dict[str, Any]) -> str:
    return f"{args.get('source')} -> {args.get('destination')}"


def _format_args_copy(args: Dict[str, Any]) -> str:
    return f"{args.get('source')} -> {args.get('destination')}"


def _format_args_delete(args: Dict[str, Any]) -> str:
    suffix = " (recursive)" if _flag(args, "recursive") else ""
    return f"{args.get('path')}{suffix}"


def _format_args_create(args: Dict[str, Any]) -> str:
    return str(args.get("path"))


def _format_args_info(args: Dict[str, Any]) -> str:
    return str(args.get("path"))


# ------------------------------------------------------------- parameters

_PARAMS_MOVE = {
    "type": "object",
    "properties": {
        "source": {"type": "string", "description": "Path to move"},
        "destination": {
            "type": "string",
            "description": "New path (file name or target directory)",
        },
        "overwrite": {
            "type": "boolean",
            "description": "Replace an existing destination (default: false)",
        },
    },
    "required": ["source", "destination"],
    "additionalProperties": False,
}

_PARAMS_COPY = {
    "type": "object",
    "properties": {
        "source": {"type": "string", "description": "Path to copy"},
        "destination": {
            "type": "string",
            "description": "Target path (directories are copied recursively)",
        },
        "overwrite": {
            "type": "boolean",
            "description": "Replace existing destination files (default: false)",
        },
    },
    "required": ["source", "destination"],
    "additionalProperties": False,
}

_PARAMS_DELETE = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "Path to delete"},
        "recursive": {
            "type": "boolean",
            "description": "Delete a non-empty directory tree (default: false)",
        },
    },
    "required": ["path"],
    "additionalProperties": False,
}

_PARAMS_MKDIR = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "Directory to create"},
        "parents": {
            "type": "boolean",
            "description": "Create missing parent directories (default: true)",
        },
    },
    "required": ["path"],
    "additionalProperties": False,
}

_PARAMS_INFO = {
    "type": "object",
    "properties": {
        "path": {"type": "string", "description": "Path to stat"},
    },
    "required": ["path"],
    "additionalProperties": False,
}

_DESCRIPTIONS = {
    "move_path": (
        "Move or rename a file, symlink or directory. Fails if the "
        "destination exists unless overwrite=true. Refuses to move the "
        "working directory."
    ),
    "copy_path": (
        "Copy a file, symlink or directory tree. Symlinks are copied as "
        "links, directories recursively. Existing files are only replaced "
        "with overwrite=true."
    ),
    "delete_path": (
        "Delete a file, symlink or directory. Non-empty directories need "
        "recursive=true. Refuses to delete the working directory or its "
        "ancestors."
    ),
    "create_directory": (
        "Create a directory (mkdir -p by default, single level with "
        "parents=false). Succeeds silently if it already exists."
    ),
    "path_info": (
        "Read-only stat: type, size, mode, uid/gid, mtime, symlink target. "
        "Never follows the final symlink."
    ),
}


# ---------------------------------------------------------------- plugin


def create_plugin(ctx):
    """Register the alt file tools (only with AICODER_ALT_FILETOOLS=1)."""
    if not env_bool(ENV_FLAG, False):
        return

    tools = [
        ("move_path", move_path, _PARAMS_MOVE, _format_args_move, _preview_move, False),
        ("copy_path", copy_path, _PARAMS_COPY, _format_args_copy, _preview_copy, False),
        ("delete_path", delete_path, _PARAMS_DELETE, _format_args_delete, _preview_delete, False),
        ("create_directory", create_directory, _PARAMS_MKDIR,
         _format_args_create, _preview_create, False),
        ("path_info", path_info, _PARAMS_INFO, _format_args_info, _preview_info, True),
    ]
    for name, fn, params, fmt, preview, auto_approved in tools:
        ctx.register_tool(
            name=name,
            fn=fn,
            description=_DESCRIPTIONS[name],
            parameters=params,
            auto_approved=auto_approved,
            format_arguments=fmt,
            generate_preview=preview,
        )
