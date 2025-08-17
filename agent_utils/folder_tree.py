"""Utilities for displaying folder trees."""
from __future__ import annotations

from pathlib import Path


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
