import os
from agent_utils.agent_vector_db import AgentVectorDB


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


def test_agent_vector_db(tmp_path, monkeypatch):
    monkeypatch.setattr("agent_utils.agent_vector_db.TextEmbedding", FakeEmbedder)
    config_path = tmp_path / "config.json"
    db = AgentVectorDB(config_path=str(config_path))
    base_dir = tmp_path / "base"
    base_dir.mkdir()
    assert db.reset_db(str(base_dir))["ok"]
    assert db.get_base_dir()["base_dir"] == str(base_dir)

    ins1 = db.insert("file1.txt")
    ins2 = db.insert("file2.txt")
    db.set_file_report("file1.txt", "hello world")
    db.set_file_report("file2.txt", "hello there")

    assert db.get_file_report("file1.txt")["file_report"] == "hello world"

    notes_res = db.append_organization_notes([ins1["id"]], "note1")
    assert ins1["id"] in notes_res["updated_ids"]

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
