"""Tools for deciding file organization."""
from __future__ import annotations

import os
from pathlib import Path
from typing import Iterable

from agent_utils.agent_vector_db import AgentVectorDB
from agent_utils.folder_tree import target_folder_tree as _target_folder_tree

_DEFAULT_CONFIG = Path(__file__).resolve().parents[2] / "organizer.config.json"
_CONFIG_PATH = os.environ.get("FILE_ORGANIZER_CONFIG", str(_DEFAULT_CONFIG))

# Global database instance used by the tools
_db = AgentVectorDB(config_path=_CONFIG_PATH)


def append_organization_notes(ids: Iterable[int], notes: str) -> dict:
    """Append organization notes for the given file ``ids``."""
    return _db.append_organization_notes(ids, notes)


def get_file_report(path: str) -> dict:
    """Retrieve the stored file report for ``path``."""
    return _db.get_file_report(path)


def set_planned_destination(path: str, planned_dest: str) -> dict:
    """Set the planned destination for ``path``."""
    return _db.set_planned_destination(path, planned_dest)


def get_organization_notes(path: str) -> dict:
    """Retrieve the organization notes for ``path``."""
    return _db.get_organization_notes(path)


def get_folder_instructions() -> dict:
    """Retrieve user folder organization instructions."""
    return _db.get_instructions()


def target_folder_tree(path: str) -> str:
    """Return a folder tree for ``path`` with a heading."""
    return _target_folder_tree(path)


def get_db() -> AgentVectorDB:
    """Return the global database instance (primarily for tests)."""
    return _db


def set_db(db: AgentVectorDB) -> None:
    """Replace the global database instance (primarily for tests)."""
    global _db  # pylint: disable=global-statement
    _db = db
