from fastapi.testclient import TestClient
import importlib


class FakeEmbedder:
    def __init__(self, model_name=None):
        pass

    def embed(self, texts):
        return [[0.0]] * len(texts)


def test_scan_populates_db(tmp_path, monkeypatch):
    monkeypatch.setattr("agent_utils.agent_vector_db.TextEmbedding", FakeEmbedder)

    import agent_utils.agent_vector_db as avdb

    orig_connect = avdb.sqlite3.connect

    def _connect(*args, **kwargs):
        kwargs.setdefault("check_same_thread", False)
        return orig_connect(*args, **kwargs)

    monkeypatch.setattr(avdb.sqlite3, "connect", _connect)

    import foldermate.app as app_module
    importlib.reload(app_module)

    db_path = tmp_path / "config.json"
    new_db = app_module.AgentVectorDB(config_path=str(db_path))
    new_db.reset_db(str(tmp_path / "base"))
    monkeypatch.setattr(app_module, "db", new_db)
    client = TestClient(app_module.app)

    base_dir = tmp_path / "src"
    base_dir.mkdir()
    (base_dir / "a.txt").write_text("a")
    sub = base_dir / "sub"
    sub.mkdir()
    (sub / "b.txt").write_text("b")

    resp = client.post("/api/actions/scan", json={"base_dir": str(base_dir), "recursive": False})
    assert resp.status_code == 200
    data = client.get("/api/files").json()
    paths = [r["path_rel"] for r in data["rows"]]
    assert "a.txt" in paths and "sub/b.txt" not in paths

    resp = client.post("/api/actions/scan", json={"base_dir": str(base_dir), "recursive": True})
    assert resp.status_code == 200
    data = client.get("/api/files").json()
    paths = [r["path_rel"] for r in data["rows"]]
    assert "sub/b.txt" in paths
