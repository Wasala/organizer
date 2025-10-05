"""Tests for config persistence and reset behaviour."""

import importlib
from fastapi.testclient import TestClient  # pylint: disable=import-error


class FakeEmbedder:  # pylint: disable=too-few-public-methods
    """Minimal fake embedder for tests."""

    def __init__(self, model_name: str | None = None) -> None:
        """Ignore the model name."""

        _ = model_name  # unused

    def embed(self, texts):
        """Return zero vectors matching input length."""

        return [[0.0]] * len(list(texts))


def _prepare_agent_db(monkeypatch):
    """Monkeypatch expensive dependencies and return the agent module."""

    monkeypatch.setattr("agent_utils.agent_vector_db.TextEmbedding", FakeEmbedder)

    import agent_utils.agent_vector_db as avdb  # pylint: disable=import-outside-toplevel

    orig_connect = avdb.sqlite3.connect

    def _connect(*args, **kwargs):
        kwargs.setdefault("check_same_thread", False)
        return orig_connect(*args, **kwargs)

    monkeypatch.setattr(avdb.sqlite3, "connect", _connect)
    return avdb


def test_config_persist(tmp_path, monkeypatch):
    """Ensure config values persist in SQLite and reset clears them."""

    avdb = _prepare_agent_db(monkeypatch)

    import foldermate.app as app_module  # pylint: disable=import-outside-toplevel
    importlib.reload(app_module)

    db_path = tmp_path / "config.json"
    new_db = app_module.AgentVectorDB(config_path=str(db_path))
    base = tmp_path / "base"
    base.mkdir()
    new_db.reset_db(str(base))
    monkeypatch.setattr(app_module, "db", new_db)

    client = TestClient(app_module.app)

    dest = tmp_path / "dest"
    dest.mkdir()
    instr = "Keep PDFs in docs"
    resp = client.put(
        "/api/config",
        json={"target_dir": str(dest), "instructions": instr},
    )
    assert resp.status_code == 200
    data = client.get("/api/config").json()
    assert data["config"]["target_dir"] == str(dest)
    assert data["config"]["instructions"] == instr
    row = new_db.conn.execute(
        "SELECT value FROM config WHERE key='instructions'"
    ).fetchone()
    assert row["value"] == instr

    client.post("/api/reset", json={"base_dir": str(base)})
    row = new_db.conn.execute(
        "SELECT value FROM config WHERE key='instructions'"
    ).fetchone()
    assert row is None
    data = client.get("/api/config").json()
    assert "instructions" not in data["config"]


def test_reset_does_not_mutate_config_file(tmp_path, monkeypatch):
    """Resetting the database should leave the JSON config untouched."""

    avdb = _prepare_agent_db(monkeypatch)

    config_path = tmp_path / "config.json"
    db = avdb.AgentVectorDB(config_path=str(config_path))
    before_bytes = config_path.read_bytes()
    before_mtime = config_path.stat().st_mtime_ns

    base = tmp_path / "base"
    base.mkdir()
    db.reset_db(str(base))

    assert config_path.read_bytes() == before_bytes
    assert config_path.stat().st_mtime_ns == before_mtime
