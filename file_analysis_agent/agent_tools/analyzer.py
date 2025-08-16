"""Core analyzer handling file state and tool operations."""
from __future__ import annotations

import logging
import mimetypes
import os
import random
import re
import time
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from pathlib import Path
from typing import List, Optional

import tiktoken
from pydantic import BaseModel

from .cache import CacheManager, CacheEntry
from .config import CONFIG
from .converter import convert_to_markdown

logger = logging.getLogger(__name__)


class SliceOutput(BaseModel):
    start_line: int
    end_line: int
    text: str


class FindHit(BaseModel):
    line: int
    match: str
    start: int
    end: int
    context: str


class MetadataOutput(BaseModel):
    exists: bool
    path: Optional[str] = None
    size_megabytes: Optional[float] = None
    extension: Optional[str] = None
    mime_type: Optional[str] = None
    created_time: Optional[float] = None
    modified_time: Optional[float] = None
    inode: Optional[int] = None
    device: Optional[int] = None
    cache: Optional[dict] = None


class FileAnalyzer:
    """Stateful analyzer used by tools."""

    def __init__(self) -> None:
        self.cache = CacheManager()
        self.current_file: Optional[Path] = None
        self.current_lines: List[str] = []
        self.cache_entry: Optional[CacheEntry] = None
        self.last_error: Optional[str] = None

    # Utility
    def _truncate(self, text: str) -> str:
        if len(text) <= CONFIG.max_return_chars:
            return text
        return text[: CONFIG.max_return_chars] + "\n...[truncated]"

    # Public API
    def set(self, path: str, force: bool = False) -> dict:
        """Load and cache a file for subsequent operations."""
        file_path = Path(path).expanduser().resolve()
        if not file_path.exists():
            msg = f"File not found: {file_path}"
            self.last_error = msg
            return {"status": "error", "message": msg}

        def _task() -> dict:
            entry = None if force else self.cache.load(file_path)
            if entry:
                markdown = entry.md_path.read_text(encoding="utf-8")
                self.cache_entry = entry
            else:
                markdown = convert_to_markdown(file_path)
                entry = self.cache.save(file_path, markdown)
                self.cache_entry = entry
            self.current_file = file_path
            self.current_lines = markdown.splitlines()
            self.last_error = None
            return {"status": "ok", "message": "file successfully loaded for analysis"}

        with ThreadPoolExecutor(max_workers=1) as ex:
            future = ex.submit(_task)
            try:
                result = future.result(timeout=CONFIG.conversion_timeout)
                return result
            except TimeoutError:
                self.last_error = (
                    "file could not be loaded within configured time"
                )
                return {"status": "error", "message": self.last_error}
            except Exception as exc:  # pragma: no cover - depends on docling
                msg = f"conversion failed: {exc}"
                self.last_error = msg
                logger.exception("Conversion failed")
                return {"status": "error", "message": msg}

    def _ensure_loaded(self) -> Optional[dict]:
        if not self.current_lines:
            return {"status": "error", "message": self.last_error or "no file loaded"}
        return None

    def top(self, start_line: int = 1, num_lines: int = 50) -> dict:
        err = self._ensure_loaded()
        if err:
            return err
        start = max(start_line, 1)
        end = min(start + num_lines - 1, len(self.current_lines))
        text = "\n".join(self.current_lines[start - 1 : end])
        return SliceOutput(start_line=start, end_line=end, text=self._truncate(text)).model_dump()

    def tail(self, num_lines: int = 50) -> dict:
        err = self._ensure_loaded()
        if err:
            return err
        end = len(self.current_lines)
        start = max(end - num_lines + 1, 1)
        text = "\n".join(self.current_lines[start - 1 : end])
        return SliceOutput(start_line=start, end_line=end, text=self._truncate(text)).model_dump()

    def read_full_file(self) -> dict:
        err = self._ensure_loaded()
        if err:
            return err
        text = "\n".join(self.current_lines)
        try:
            enc = tiktoken.get_encoding(CONFIG.encoding_name)
            tokens = enc.encode(text)
        except Exception:
            # Fallback if tiktoken data is unavailable
            tokens = text.split()
        if len(tokens) > CONFIG.token_limit:
            msg = (
                "unable to return full file as it exceeds token limit"
            )
            return {
                "status": "error",
                "message": msg,
                "text": self._truncate(text),
            }
        return {"text": self._truncate(text), "token_count": len(tokens)}

    def find_within_doc(self, regex_string: str, flags: Optional[str] = None, max_hits: int = 50) -> dict:
        err = self._ensure_loaded()
        if err:
            return err
        flag_value = 0
        flag_string = flags if flags is not None else CONFIG.regex_default_flags
        for ch in flag_string:
            flag_value |= getattr(re, ch, 0)
        try:
            pattern = re.compile(regex_string, flag_value)
        except re.error as exc:
            return {"status": "error", "message": f"regex compilation error: {exc}"}

        hits: List[FindHit] = []
        for idx, line in enumerate(self.current_lines, start=1):
            for match in pattern.finditer(line):
                hits.append(
                    FindHit(
                        line=idx,
                        match=match.group(),
                        start=match.start() + 1,
                        end=match.end() + 1,
                        context=line,
                    )
                )
                if len(hits) >= max_hits:
                    break
            if len(hits) >= max_hits:
                break
        return {"hits": [h.model_dump() for h in hits]}

    def get_random_lines(self, start: int = 1, num_lines: int = 20, seed: Optional[int] = None) -> dict:
        err = self._ensure_loaded()
        if err:
            return err
        rng = random.Random(seed)
        total_lines = len(self.current_lines)
        if total_lines <= num_lines:
            start_line = 1
            end_line = total_lines
        else:
            min_start = max(start, 1)
            max_start = max(total_lines - num_lines + 1, min_start)
            start_line = rng.randint(min_start, max_start)
            end_line = min(start_line + num_lines - 1, total_lines)
        text = "\n".join(self.current_lines[start_line - 1 : end_line])
        return SliceOutput(start_line=start_line, end_line=end_line, text=self._truncate(text)).model_dump()

    def get_file_metadata(self) -> dict:
        if not self.current_file:
            return {"status": "error", "message": self.last_error or "no file loaded"}
        p = self.current_file
        exists = p.exists()
        data = MetadataOutput(exists=exists, path=str(p))
        if not exists:
            return data.model_dump()
        stat = p.stat()
        data.size_megabytes = stat.st_size / (1024 * 1024)
        data.extension = p.suffix
        data.mime_type = mimetypes.guess_type(p.name)[0]
        data.created_time = getattr(stat, "st_ctime", None)
        data.modified_time = getattr(stat, "st_mtime", None)
        data.inode = getattr(stat, "st_ino", None)
        data.device = getattr(stat, "st_dev", None)
        if self.cache_entry:
            cache_info = {
                "cache_key": self.cache_entry.key,
                "cache_path": str(self.cache_entry.md_path),
                "metadata_path": str(self.cache_entry.meta_path),
            }
            data.cache = cache_info
        return data.model_dump()

    def delete_cache(self, path: str) -> dict:
        file_path = Path(path).expanduser().resolve()
        removed = self.cache.delete(file_path)
        return {"removed": removed}


# Global analyzer instance
analyzer = FileAnalyzer()
