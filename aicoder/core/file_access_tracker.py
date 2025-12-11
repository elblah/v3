"""
File Access Tracker - Enforces read-before-edit safety rule
Class-based implementation matching TypeScript pattern
"""

from typing import Set


class FileAccessTracker:
    """Tracks which files have been read to enforce safety"""
    
    _read_files: Set[str] = set()  # Class variable matching TypeScript
    
    @classmethod
    def record_read(cls, path: str) -> None:
        """Record that a file has been read"""
        cls._read_files.add(path)
    
    @classmethod
    def was_file_read(cls, path: str) -> bool:
        """Check if a file was previously read in this session"""
        return path in cls._read_files