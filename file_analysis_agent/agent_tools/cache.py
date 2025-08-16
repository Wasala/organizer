"""Cache management for markdown conversions."""
from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from .config import CONFIG

logger = logging.getLogger(__name__)


@dataclass
class CacheEntry:
    key: str
    md_path: Path
    meta_path: Path
    metadata: dict


class CacheManager:
    """Manages cached markdown files and metadata sidecars."""

    def __init__(self, cache_dir: Optional[Path] = None) -> None:
        self.cache_dir = (cache_dir or CONFIG.cache_dir).expanduser().resolve()
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        self.conversions: int = 0
        self.last_convert_time: Optional[float] = None

    # Cache key computation
    def build_key(self, file_path: Path) -> str:
        """Compute a cache key based on file content and critical metadata."""
        stat = file_path.stat()
        h = hashlib.sha256()
        with open(file_path, 'rb') as f:
            for chunk in iter(lambda: f.read(8192), b''):
                h.update(chunk)
        h.update(str(stat.st_size).encode())
        h.update(str(int(stat.st_mtime)).encode())
        return h.hexdigest()

    def _paths_for_key(self, key: str) -> Tuple[Path, Path]:
        md_path = self.cache_dir / f"{key}.md"
        meta_path = self.cache_dir / f"{key}.json"
        return md_path, meta_path

    def load(self, file_path: Path) -> Optional[CacheEntry]:
        key = self.build_key(file_path)
        md_path, meta_path = self._paths_for_key(key)
        if md_path.exists() and meta_path.exists():
            try:
                metadata = json.loads(meta_path.read_text())
            except json.JSONDecodeError:
                return None
            logger.info("Cache hit for %s", file_path)
            return CacheEntry(key, md_path, meta_path, metadata)
        logger.info("Cache miss for %s", file_path)
        return None

    def save(self, file_path: Path, markdown: str, key: Optional[str] = None) -> CacheEntry:
        key = key or self.build_key(file_path)
        md_path, meta_path = self._paths_for_key(key)

        # Write atomically
        tmp_fd, tmp_path = tempfile.mkstemp(dir=self.cache_dir, suffix='.md')
        with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
            f.write(markdown)
        os.replace(tmp_path, md_path)

        metadata = {
            "original_path": str(file_path),
            "size": file_path.stat().st_size,
            "mtime": file_path.stat().st_mtime,
            "created": os.path.getctime(file_path),
            "cache_key": key,
        }

        tmp_fd, tmp_path = tempfile.mkstemp(dir=self.cache_dir, suffix='.json')
        with os.fdopen(tmp_fd, 'w', encoding='utf-8') as f:
            json.dump(metadata, f)
        os.replace(tmp_path, meta_path)

        self.conversions += 1
        self.last_convert_time = metadata["created"]
        logger.info("Cached markdown for %s", file_path)
        return CacheEntry(key, md_path, meta_path, metadata)

    def delete(self, file_path: Path) -> bool:
        entry = self.load(file_path)
        if not entry:
            return False
        if entry.md_path.exists():
            entry.md_path.unlink()
        if entry.meta_path.exists():
            entry.meta_path.unlink()
        logger.info("Deleted cache for %s", file_path)
        return True

    def cache_size_bytes(self) -> int:
        total = 0
        for md_file in self.cache_dir.glob('*.md'):
            total += md_file.stat().st_size
        for meta_file in self.cache_dir.glob('*.json'):
            total += meta_file.stat().st_size
        return total
