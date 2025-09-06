"""Utilities for displaying folder trees."""
from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List


def target_folder_tree(path: str) -> Dict[str, Any]:
    """Return a folder tree for ``path`` with a heading.

    The function attempts to traverse ``path`` recursively while collecting any
    errors encountered along the way.  All discovered entries are returned even
    if some directories cannot be read.

    Parameters
    ----------
    path:
        Path for which a folder tree should be created.

    Returns
    -------
    dict
        A dictionary containing the textual folder tree in ``"tree"`` and, if
        any problems occurred, an ``"errors"`` list with human readable
        descriptions of those issues.
    """

    p = Path(path).expanduser()
    lines: List[str] = [f"Folder Tree for {p}:"]
    errors: List[str] = []

    if not p.exists():
        lines.append("[Path does not exist]")
        errors.append(f"Path does not exist: {p}")
        return {"tree": "\n".join(lines), "errors": errors}

    def walk(current: Path, prefix: str = "") -> None:
        try:
            entries = sorted(
                current.iterdir(),
                key=lambda e: (not e.is_dir(), e.name.lower()),
            )
        except Exception as exc:  # pragma: no cover - rare OS errors
            errors.append(f"{current}: {exc}")
            return

        count = len(entries)
        for idx, entry in enumerate(entries):
            connector = "└── " if idx == count - 1 else "├── "
            try:
                is_dir = entry.is_dir()
            except Exception as exc:  # pragma: no cover - rare OS errors
                errors.append(f"{entry}: {exc}")
                continue
            if is_dir:
                lines.append(f"{prefix}{connector}{entry.name}/")
                extension = "    " if idx == count - 1 else "│   "
                walk(entry, prefix + extension)
            else:
                lines.append(f"{prefix}{connector}{entry.name}")

    if p.is_dir():
        walk(p)
    else:
        lines.append(p.name)

    result: Dict[str, Any] = {"tree": "\n".join(lines)}
    if errors:
        result["errors"] = errors
    return result
