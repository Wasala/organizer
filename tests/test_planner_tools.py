import importlib
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


def test_planner_tools(tmp_path, monkeypatch):
    monkeypatch.setattr("agent_utils.agent_vector_db.TextEmbedding", FakeEmbedder)
    cfg = tmp_path / "config.json"
    monkeypatch.setenv("FILE_ORGANIZER_CONFIG", str(cfg))

    # Import tools after patching
    planner_tools = importlib.reload(importlib.import_module(
        "file_organization_planner_agent.agent_tools.tools"
    ))

    db: AgentVectorDB = planner_tools.get_db()
    base = tmp_path / "base"
    base.mkdir()
    db.reset_db(str(base))

    ins1 = db.insert("a.txt")
    ins2 = db.insert("b.txt")
    db.set_file_report("a.txt", "hello world")
    db.set_file_report("b.txt", "hello there")
    (base / "a.txt").write_text("")
    (base / "b.txt").write_text("")

    rep = planner_tools.get_file_report("a.txt")
    assert rep["file_report"] == "hello world"

    notes = planner_tools.append_organization_notes([ins1["id"]], "note1")
    assert ins1["id"] in notes["updated_ids"]

    sim = planner_tools.find_similar_file_reports("a.txt")
    assert any(r["path_rel"] == "a.txt" for r in sim["results"])

    tree = planner_tools.target_folder_tree(str(base))
    assert f"Folder Tree for {base}" in tree
    assert "a.txt" in tree and "b.txt" in tree
