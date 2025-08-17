from __future__ import annotations
"""Convenience alias for the underlying AgentVectorDB implementation."""

from agent_utils.agent_vector_db import AgentVectorDB


class FileOrganizerDB(AgentVectorDB):
    """Thin wrapper around :class:`AgentVectorDB` for compatibility.

    The original project referred to its database utility as
    ``FileOrganizerDB``.  Later revisions consolidated functionality into
    :class:`~agent_utils.agent_vector_db.AgentVectorDB`.  To minimise
    changes in the rest of the codebase and maintain backwards
    compatibility, this module simply re-exports that class under the
    expected name.
    """

    pass
