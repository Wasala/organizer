"""Tests for logging configuration resolution."""
from __future__ import annotations

import json
import sys
from pathlib import Path


def _root() -> Path:
    return Path(__file__).resolve().parents[1]


def test_planner_agent_logging_respects_config(tmp_path, monkeypatch):
    """Ensure logging honours the path in ``organizer.config.json``."""
    root = _root()
    config_file = root / "organizer.config.json"
    original = config_file.read_text()
    data = json.loads(original)
    data["log_dir"] = str(tmp_path)
    config_file.write_text(json.dumps(data, indent=2))

    def _clear_agent_utils():
        for name in list(sys.modules):
            if name == "agent_utils" or name.startswith("agent_utils."):
                sys.modules.pop(name, None)

    try:
        planner_dir = root / "file_organization_planner_agent"
        monkeypatch.chdir(planner_dir)
        _clear_agent_utils()
        import agent_utils  # pylint: disable=import-outside-toplevel
        log_files = list(tmp_path.glob("*.log"))
        assert log_files, "Logging did not write to configured directory"
        assert not list(planner_dir.glob("*.log")), "Log file written to agent directory"
    finally:
        config_file.write_text(original)
        _clear_agent_utils()
