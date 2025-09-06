"""Tests for default configuration path resolution."""
from __future__ import annotations

import importlib
from pathlib import Path


class DummyDB:
    """Simple stand-in for :class:`AgentVectorDB` recording the config path."""

    def __init__(self, config_path: str):
        self.config_path = config_path


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_planner_tools_default_config(monkeypatch):
    monkeypatch.delenv("FILE_ORGANIZER_CONFIG", raising=False)
    monkeypatch.setattr("agent_utils.agent_vector_db.AgentVectorDB", DummyDB)
    planner_dir = _root() / "file_organization_planner_agent"
    monkeypatch.chdir(planner_dir)
    tools = importlib.reload(
        importlib.import_module("file_organization_planner_agent.agent_tools.tools")
    )
    db = tools.get_db()
    assert Path(db.config_path) == _root() / "organizer.config.json"


def test_decider_tools_default_config(monkeypatch):
    monkeypatch.delenv("FILE_ORGANIZER_CONFIG", raising=False)
    monkeypatch.setattr("agent_utils.agent_vector_db.AgentVectorDB", DummyDB)
    decider_dir = _root() / "file_organization_decider_agent"
    monkeypatch.chdir(decider_dir)
    tools = importlib.reload(
        importlib.import_module("file_organization_decider_agent.agent_tools.tools")
    )
    db = tools.get_db()
    assert Path(db.config_path) == _root() / "organizer.config.json"
