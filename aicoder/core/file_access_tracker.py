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
    
    @classmethod
    def clear_state(cls) -> None:
        """Clear all read files - useful for testing"""
        cls._read_files.clear()
    
    @classmethod
    def get_all_read_files(cls) -> Set[str]:
        """Get all files that have been read - useful for testing"""
        return cls._read_files.copy()
    
    @classmethod
    def get_read_count(cls) -> int:
        """Get count of read files - useful for testing"""
        return len(cls._read_files)