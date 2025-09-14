"""Tools for planning file organization."""
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

def find_similar_file_reports(path: str, top_k=10) -> dict:
    """Find semantically similar file reports for ``path``."""
    return _db.find_similar_file_reports(path, top_k=top_k)

def append_organization_cluser_notes(ids: Iterable[int], notes: str) -> dict:
    """Append organization notes for the given file ``ids``."""
    return _db.append_organization_cluser_notes(ids, notes)


def append_organization_anchor_notes(path: str, notes: str) -> dict:
    """Append organization notes for a single file specified by ``path``."""
    return _db.append_organization_anchor_notes(path, notes)

def get_file_report(path: str) -> dict:
    """Retrieve the stored file report for ``path``."""
    return _db.get_file_report(path)


def get_folder_instructions() -> dict:
    """Retrieve user folder organization instructions."""
    return _db.get_instructions()


def target_folder_tree() -> dict:
    """Return a folder tree for the configured target directory.

    The result dictionary always contains a ``"tree"`` key with the textual
    representation and may include an ``"errors"`` list describing any
    directories that could not be read.

    Raises
    ------
    ValueError
        If the ``target_dir`` configuration option has not been set.
    """

    target_dir = _db.config.get("target_dir")
    if not target_dir:
        raise ValueError("target_dir is not configured")
    return _target_folder_tree(target_dir)



def get_db() -> AgentVectorDB:
    """Return the global database instance (primarily for tests)."""
    return _db


def set_db(db: AgentVectorDB) -> None:
    """Replace the global database instance (primarily for tests)."""
    global _db  # noqa: PLW0603
    _db = db
