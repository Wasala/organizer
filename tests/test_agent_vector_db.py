from agent_utils.agent_vector_db import AgentVectorDB, PROCESSING_SENTINELS


import sqlite3
import threading


class FakeEmbedder:
    def __init__(self, model_name=None):
        pass

    def embed(self, texts):
        vectors = []
        for t in texts:
            l = len(t)
            s = sum(ord(c) for c in t)
            vectors.append([float(l), float(s % 97), float((l * s) % 53)])
        return vectors


class FailingEmbedder:
    """Embedder that fails after the first call to :meth:`embed`."""

    def __init__(self, model_name=None):
        self._calls = 0

    def embed(self, texts):
        self._calls += 1
        if self._calls > 1:
            raise RuntimeError("boom")
        vectors = []
        for t in texts:
            l = len(t)
            s = sum(ord(c) for c in t)
            vectors.append([float(l), float(s % 97), float((l * s) % 53)])
        return vectors


def test_agent_vector_db(tmp_path, monkeypatch):
    monkeypatch.setattr("agent_utils.agent_vector_db.TextEmbedding", FakeEmbedder)
    config_path = tmp_path / "config.json"
    db = AgentVectorDB(config_path=str(config_path))
    base_dir = tmp_path / "base"
    base_dir.mkdir()
    assert db.reset_db(str(base_dir))["ok"]
    assert db.get_base_dir()["base_dir"] == str(base_dir)

    db.save_config(instructions="Keep PDFs in docs")
    assert db.get_instructions()["instructions"] == "Keep PDFs in docs"

    ins1 = db.insert("file1.txt")
    ins2 = db.insert("file2.txt")
    db.set_file_report("file1.txt", "hello world")
    db.set_file_report("file2.txt", "hello there")

    assert db.get_file_report("file1.txt")["file_report"] == "hello world"

    notes_res = db.append_organization_notes([ins1["id"]], "note1")
    assert ins1["id"] in notes_res["updated_ids"]
    assert db.get_organization_notes("file1.txt")["organization_notes"].startswith("note1")

    db.set_planned_destination("file1.txt", "dest/a")
    db.set_final_destination("file1.txt", "final/a")

    # Insert third file for planned/final tests
    ins3 = db.insert("file3.txt")
    db.set_file_report("file3.txt", "hello world again")
    db.append_organization_notes([ins3["id"]], "note3")

    # next path helpers
    assert db.get_next_path_missing_file_report()["path_rel"] is None
    assert db.get_next_path_missing_organization_notes()["path_rel"] == "file2.txt"
    assert db.get_next_path_missing_planned_destination()["path_rel"] == "file3.txt"
    db.set_planned_destination("file3.txt", "dest/c")
    assert db.get_next_path_missing_final_destination()["path_rel"] == "file3.txt"

    # similarity search
    sim = db.find_similar_file_reports("file1.txt", top_k=2)
    assert len(sim["results"]) == 2
    paths = [r["path_rel"] for r in sim["results"]]
    assert "file1.txt" in paths

    # config save
    assert db.save_config(search={"top_k": 5})["ok"]


def test_clear_processing_file_reports(tmp_path, monkeypatch):
    monkeypatch.setattr("agent_utils.agent_vector_db.TextEmbedding", FakeEmbedder)
    config_path = tmp_path / "cfg.json"
    db = AgentVectorDB(config_path=str(config_path))
    base_dir = tmp_path / "b"
    base_dir.mkdir()
    db.reset_db(str(base_dir))
    db.insert("foo.txt")
    db.set_file_report("foo.txt", PROCESSING_SENTINELS[0])
    assert db.get_file_report("foo.txt")["file_report"] == PROCESSING_SENTINELS[0]
    res = db.clear_processing_file_reports()
    assert res["cleared"] == 1
    assert db.get_file_report("foo.txt")["file_report"] == ""
    assert db.get_next_path_missing_file_report()["path_rel"] == "foo.txt"


def test_set_file_report_handles_embedding_failure(tmp_path, monkeypatch):
    monkeypatch.setattr("agent_utils.agent_vector_db.TextEmbedding", FailingEmbedder)
    config_path = tmp_path / "f.cfg"
    db = AgentVectorDB(config_path=str(config_path))
    base_dir = tmp_path / "base"
    base_dir.mkdir()
    db.reset_db(str(base_dir))
    db.insert("foo.txt")

    # Should still persist even though embedding fails
    res = db.set_file_report("foo.txt", "hello")
    assert res["ok"]
    assert db.get_file_report("foo.txt")["file_report"] == "hello"


def test_set_file_report_retries_on_locked(tmp_path, monkeypatch):
    monkeypatch.setattr("agent_utils.agent_vector_db.TextEmbedding", FakeEmbedder)
    config_path = tmp_path / "retry.cfg"
    db = AgentVectorDB(config_path=str(config_path))
    base_dir = tmp_path / "b"
    base_dir.mkdir()
    db.reset_db(str(base_dir))
    db.insert("foo.txt")

    other = sqlite3.connect(db.config["db_path"], check_same_thread=False)
    other.execute("BEGIN EXCLUSIVE")
    threading.Timer(0.2, other.commit).start()

    res = db.set_file_report("foo.txt", "hello")
    assert res["ok"]
    assert db.get_file_report("foo.txt")["file_report"] == "hello"
