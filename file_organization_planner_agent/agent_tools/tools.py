"""Tools for planning file organization."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from agent_utils.agent_vector_db import AgentVectorDB

_CONFIG_PATH = os.environ.get("FILE_ORGANIZER_CONFIG", "organizer.config.json")

# Global database instance used by the tools
_db = AgentVectorDB(config_path=_CONFIG_PATH)

def find_similar_file_reports(path: str, top_k: int = 10) -> dict:
    """Find semantically similar file reports for ``path``."""
    return _db.find_similar_file_reports(path, top_k=top_k)

def append_organization_notes(ids: Iterable[int], notes: str) -> dict:
    """Append organization notes for the given file ``ids``."""
    return _db.append_organization_notes(ids, notes)

def get_file_report(path: str) -> dict:
    """Retrieve the stored file report for ``path``."""
    return _db.get_file_report(path)

def target_folder_tree(path: str) -> str:
    """Return a folder tree for ``path`` with a heading."""
    p = Path(path).expanduser()
    lines = [f"Folder Tree for {p}:"]
    if not p.exists():
        lines.append("[Path does not exist]")
        return "\n".join(lines)

    def walk(current: Path, prefix: str = "") -> None:
        entries = sorted(current.iterdir(), key=lambda e: (not e.is_dir(), e.name.lower()))
        count = len(entries)
        for idx, entry in enumerate(entries):
            connector = "└── " if idx == count - 1 else "├── "
            if entry.is_dir():
                lines.append(f"{prefix}{connector}{entry.name}/")
                extension = "    " if idx == count - 1 else "│   "
                walk(entry, prefix + extension)
            else:
                lines.append(f"{prefix}{connector}{entry.name}")

    if p.is_dir():
        walk(p)
    else:
        lines.append(p.name)
    return "\n".join(lines)


def get_db() -> AgentVectorDB:
    """Return the global database instance (primarily for tests)."""
    return _db


def set_db(db: AgentVectorDB) -> None:
    """Replace the global database instance (primarily for tests)."""
    global _db  # noqa: PLW0603
    _db = db
