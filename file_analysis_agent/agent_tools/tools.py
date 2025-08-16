"""PydanticAI-compatible tools wrapping the FileAnalyzer methods."""
from __future__ import annotations

from typing import Optional

from ..agent import analyzer


def set(path: str, force: bool = False) -> dict:
    """Load a file for analysis, converting and caching markdown as needed."""
    return analyzer.set(path, force=force)


def top(start_line: int = 1, num_lines: int = 50) -> dict:
    """Return a slice of lines from the cached markdown starting at ``start_line``."""
    return analyzer.top(start_line=start_line, num_lines=num_lines)


def tail(num_lines: int = 50) -> dict:
    """Return the last ``num_lines`` from the cached markdown."""
    return analyzer.tail(num_lines=num_lines)


def read_full_file() -> dict:
    """Return the full cached markdown subject to token limits."""
    return analyzer.read_full_file()


def find_within_doc(regex_string: str, flags: Optional[str] = None, max_hits: int = 50) -> dict:
    """Find regex matches line by line in the cached markdown."""
    return analyzer.find_within_doc(regex_string, flags=flags, max_hits=max_hits)


def get_random_lines(start: int = 1, num_lines: int = 20, seed: Optional[int] = None) -> dict:
    """Return a random contiguous window of lines from the cached markdown."""
    return analyzer.get_random_lines(start=start, num_lines=num_lines, seed=seed)


def get_file_metadata() -> dict:
    """Return metadata about the current file and cache entry."""
    return analyzer.get_file_metadata()


def delete_cache(path: str) -> dict:
    """Remove cached markdown/metadata for ``path`` if present."""
    return analyzer.delete_cache(path)
