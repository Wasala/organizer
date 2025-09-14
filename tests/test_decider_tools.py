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


def test_decider_tools(tmp_path, monkeypatch):
    monkeypatch.setattr("agent_utils.agent_vector_db.TextEmbedding", FakeEmbedder)
    cfg = tmp_path / "config.json"
    monkeypatch.setenv("FILE_ORGANIZER_CONFIG", str(cfg))

    decider_tools = importlib.reload(importlib.import_module(
        "file_organization_decider_agent.agent_tools.tools"
    ))

    db: AgentVectorDB = decider_tools.get_db()
    base = tmp_path / "base"
    base.mkdir()
    db.reset_db(str(base))

    ins1 = db.insert("a.txt")
    ins2 = db.insert("b.txt")
    db.set_file_report("a.txt", "hello world")
    (base / "a.txt").write_text("")
    (base / "b.txt").write_text("")

    db.save_config(instructions="Keep PDFs in docs", target_dir=str(base))

    instr = decider_tools.get_folder_instructions()
    assert instr["instructions"] == "Keep PDFs in docs"

    notes = decider_tools.append_organization_cluser_notes([ins1["id"]], "note1")
    assert ins1["id"] in notes["updated_ids"]

    rep = decider_tools.get_file_report("a.txt")
    assert rep["file_report"] == "hello world"

    org = decider_tools.get_organization_notes("a.txt")
    assert "note1" in org["organization_notes"]

    decider_tools.set_planned_destination("a.txt", "dest/a")
    row = db.conn.execute("SELECT planned_dest FROM files WHERE path_rel='a.txt'").fetchone()
    assert row["planned_dest"] == "dest/a"

    tree = decider_tools.target_folder_tree()
    assert "a.txt" in tree["tree"] and "b.txt" in tree["tree"]
    assert "errors" not in tree or not tree["errors"]
