from agent_utils.agent_vector_db import AgentVectorDB, PROCESSING_SENTINELS


import json
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
    db.append_organization_anchor_notes("file2.txt", "anchor")

    assert db.get_file_report("file1.txt")["file_report"] == "hello world"

    notes_res = db.append_organization_cluser_notes([ins1["id"]], "note1")
    assert ins1["id"] in notes_res["updated_ids"]
    notes_res = db.append_organization_cluser_notes([ins1["id"]], "note2")
    assert ins1["id"] in notes_res["updated_ids"]
    notes_lines = db.get_organization_notes("file1.txt")["organization_notes"].splitlines()
    assert len(notes_lines) == 2
    assert notes_lines[0].endswith("note1")
    assert notes_lines[1].endswith("note2")

    anchor_lines = db.get_organization_notes("file2.txt")["organization_notes"].splitlines()
    assert any(line.endswith("anchor") for line in anchor_lines)

    db.set_planned_destination("file1.txt", "dest/a")
    db.set_final_destination("file1.txt", "final/a")

    # Insert third file for planned/final tests
    ins3 = db.insert("file3.txt")
    db.set_file_report("file3.txt", "hello world again")
    db.append_organization_cluser_notes([ins3["id"]], "note3")
    db.mark_organization_plan_processed("file1.txt")
    db.mark_organization_plan_processed("file3.txt")

    # next path helpers
    assert db.get_next_path_missing_file_report()["path_rel"] is None
    assert db.get_next_path_pending_organization_plan()["path_rel"] == "file2.txt"
    assert db.get_next_path_missing_planned_destination()["path_rel"] == "file3.txt"
    db.set_planned_destination("file3.txt", "dest/c")
    assert db.get_next_path_missing_final_destination()["path_rel"] == "file3.txt"
    db.mark_organization_plan_processed("file2.txt")
    assert db.get_next_path_pending_organization_plan()["path_rel"] is None

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


def test_prepend_and_remove_sentinel(tmp_path, monkeypatch):
    monkeypatch.setattr("agent_utils.agent_vector_db.TextEmbedding", FakeEmbedder)
    config_path = tmp_path / "sent.cfg"
    db = AgentVectorDB(config_path=str(config_path))
    base_dir = tmp_path / "base"
    base_dir.mkdir()
    db.reset_db(str(base_dir))
    inserted = db.insert("note.txt")
    db.append_organization_cluser_notes([inserted["id"]], "note1")
    db.prepend_organization_note_sentinel("note.txt", PROCESSING_SENTINELS[0])
    notes = db.get_organization_notes("note.txt")["organization_notes"].splitlines()
    assert notes[0] == PROCESSING_SENTINELS[0]
    db.remove_organization_note_sentinel("note.txt", PROCESSING_SENTINELS[0])
    remaining = db.get_organization_notes("note.txt")["organization_notes"].splitlines()
    assert PROCESSING_SENTINELS[0] not in remaining
    assert any("note1" in line for line in remaining)


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


def test_get_file_id(tmp_path, monkeypatch):
    """Ensure file identifiers can be retrieved without modifying rows."""

    monkeypatch.setattr("agent_utils.agent_vector_db.TextEmbedding", FakeEmbedder)
    config_path = tmp_path / "id.cfg"
    db = AgentVectorDB(config_path=str(config_path))
    base_dir = tmp_path / "b"
    base_dir.mkdir()
    db.reset_db(str(base_dir))

    inserted = db.insert("foo.txt")
    res = db.get_file_id("foo.txt")
    assert res["id"] == inserted["id"]


def test_planned_destination_folders_for_proposed(tmp_path, monkeypatch):
    monkeypatch.setattr("agent_utils.agent_vector_db.TextEmbedding", FakeEmbedder)
    config_path = tmp_path / "plan.cfg"
    db = AgentVectorDB(config_path=str(config_path))
    base_dir = tmp_path / "base"
    base_dir.mkdir()
    db.reset_db(str(base_dir))
    db.save_config(target_dir=str(base_dir))

    ins1 = db.insert("a.txt")
    ins2 = db.insert("b.txt")

    cluster_json = json.dumps(
        {"Kind": "ClusterNotes", "ProposedFolderPath": "/Personal/Health/Laya_OutpatientClaims"}
    )
    db.append_organization_cluser_notes([ins1["id"]], cluster_json)
    db.append_organization_cluser_notes([ins2["id"]], cluster_json)
    db.set_planned_destination(
        "a.txt", str(base_dir / "Personal/Health/Laya_OutpatientClaims/a.txt")
    )
    db.set_planned_destination(
        "b.txt", str(base_dir / "Personal/Health/InsuranceClaims/b.txt")
    )

    res = db.planned_destination_folders_for_proposed(
        "/Personal/Health/Laya_OutpatientClaims"
    )
    assert "/Personal/Health/Laya_OutpatientClaims" in res["folders"]
    assert "/Personal/Health/InsuranceClaims" in res["folders"]


def test_selection_filters_work_while_processing(tmp_path, monkeypatch):
    """Selection flags should control which files are processed next."""

    monkeypatch.setattr("agent_utils.agent_vector_db.TextEmbedding", FakeEmbedder)
    config_path = tmp_path / "sel.cfg"
    db = AgentVectorDB(config_path=str(config_path))
    base_dir = tmp_path / "base"
    base_dir.mkdir()
    db.reset_db(str(base_dir))

    db.insert("alpha.txt")
    db.insert("beta.txt")

    assert db.get_next_path_missing_file_report()["path_rel"] == "alpha.txt"
    db.set_selected("alpha.txt", False)
    assert db.get_next_path_missing_file_report()["path_rel"] == "beta.txt"
    db.set_selected("beta.txt", False)
    assert db.get_next_path_missing_file_report()["path_rel"] is None

    db.set_selected("alpha.txt", True)
    db.set_selected("beta.txt", True)
    db.set_file_report("alpha.txt", "report alpha")
    db.set_file_report("beta.txt", "report beta")

    assert db.get_next_path_pending_organization_plan()["path_rel"] == "alpha.txt"
    db.set_selected("alpha.txt", False)
    assert db.get_next_path_pending_organization_plan()["path_rel"] == "beta.txt"
    db.set_selected("beta.txt", False)
    assert db.get_next_path_pending_organization_plan()["path_rel"] is None

    db.set_selected("alpha.txt", True)
    db.set_selected("beta.txt", True)
    db.mark_organization_plan_processed("alpha.txt")
    db.mark_organization_plan_processed("beta.txt")

    assert db.get_next_path_missing_planned_destination()["path_rel"] == "alpha.txt"
    db.set_selected("alpha.txt", False)
    assert db.get_next_path_missing_planned_destination()["path_rel"] == "beta.txt"
    db.set_selected("beta.txt", False)
    assert db.get_next_path_missing_planned_destination()["path_rel"] is None

    db.set_selected("alpha.txt", True)
    db.set_selected("beta.txt", True)
    db.set_planned_destination("alpha.txt", "organized/alpha.txt")
    db.set_planned_destination("beta.txt", "organized/beta.txt")

    assert db.get_next_path_missing_final_destination()["path_rel"] == "alpha.txt"
    db.set_selected("alpha.txt", False)
    assert db.get_next_path_missing_final_destination()["path_rel"] == "beta.txt"
    db.set_selected("beta.txt", False)
    assert db.get_next_path_missing_final_destination()["path_rel"] is None
