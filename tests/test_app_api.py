"""Unit tests for the FolderMate FastAPI application."""

from __future__ import annotations

import importlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient


class FakeEmbedder:  # pragma: no cover - simple stand-in
    """Lightweight embedding stub used by the tests."""

    def __init__(self, model_name: str | None = None):
        self.model_name = model_name

    def embed(self, texts: list[str]) -> list[list[float]]:
        return [[0.0] * 3 for _ in texts]


@dataclass
class AppHarness:
    """Container bundling together a freshly initialised app instance."""

    module: Any
    client: TestClient
    db: Any
    base_dir: Path
    target_dir: Path


@pytest.fixture
def app_harness(tmp_path, monkeypatch) -> AppHarness:
    """Return an :class:`AppHarness` with isolated storage for each test."""

    import agent_utils.agent_vector_db as avdb

    monkeypatch.setattr(avdb, "TextEmbedding", FakeEmbedder)

    original_connect = avdb.sqlite3.connect

    def _connect(*args, **kwargs):
        kwargs.setdefault("check_same_thread", False)
        return original_connect(*args, **kwargs)

    monkeypatch.setattr(avdb.sqlite3, "connect", _connect)

    import foldermate.app as app_module

    importlib.reload(app_module)

    config_path = tmp_path / "config.json"
    new_db = app_module.AgentVectorDB(config_path=str(config_path))

    base_dir = tmp_path / "base"
    base_dir.mkdir()
    new_db.reset_db(str(base_dir))

    target_dir = tmp_path / "target"
    target_dir.mkdir()
    new_db.save_config(target_dir=str(target_dir), dont_delete=False)

    monkeypatch.setattr(app_module, "db", new_db)

    with TestClient(app_module.app) as client:
        yield AppHarness(
            module=app_module,
            client=client,
            db=new_db,
            base_dir=base_dir,
            target_dir=target_dir,
        )


def _get_final_dest(db, path_rel: str) -> str:
    row = db.conn.execute(
        "SELECT final_dest FROM files WHERE path_rel=?",
        (path_rel,),
    ).fetchone()
    return row["final_dest"] if row else ""


def test_config_endpoints_roundtrip(app_harness: AppHarness):
    """``/api/config`` should expose and persist configuration updates."""

    client = app_harness.client
    base_dir = str(app_harness.base_dir)
    target_dir = str(app_harness.target_dir)

    resp = client.get("/api/config")
    data = resp.json()
    assert data["base_dir"] == base_dir
    assert data["target_dir"] == target_dir

    payload = {
        "instructions": "Organise invoices",  # ensure text handling
        "dont_delete": True,
    }
    update = client.put("/api/config", json=payload).json()
    assert update["config"]["instructions"] == "Organise invoices"
    assert update["config"]["dont_delete"] is True


def test_insert_and_list_files(app_harness: AppHarness):
    """Inserted files should appear in the paginated listing."""

    client = app_harness.client

    inserted = client.post("/api/files", json={"path_rel": "docs/report.txt"}).json()
    assert inserted["ok"]

    listing = client.get("/api/files", params={"page_size": 10}).json()
    assert listing["total"] == 1
    assert listing["rows"][0]["path_rel"] == "docs/report.txt"
    assert listing["rows"][0]["selected"] is True


def test_get_file_and_set_planned_destination(app_harness: AppHarness):
    """``/api/files/{id}`` should reflect planned destination updates."""

    client = app_harness.client

    inserted = client.post("/api/files", json={"path_rel": "photos/image.jpg"}).json()
    file_id = inserted["id"]

    update = client.put(
        f"/api/files/{file_id}/planned_dest",
        json={"planned_dest": "Images/Trips/image.jpg"},
    ).json()
    assert update["ok"]

    detail = client.get(f"/api/files/{file_id}").json()
    assert detail["planned_dest"] == "Images/Trips/image.jpg"
    assert detail["selected"] is True


def test_selection_endpoints_and_persistence(app_harness: AppHarness):
    """Checkbox selections should persist and support bulk operations."""

    client = app_harness.client

    first = client.post("/api/files", json={"path_rel": "first.txt"}).json()
    second = client.post("/api/files", json={"path_rel": "second.txt"}).json()

    resp = client.put(
        f"/api/files/{first['id']}/selected",
        json={"selected": False},
    ).json()
    assert resp["selected"] is False

    listing = client.get("/api/files", params={"order_by": "path_rel", "order_dir": "asc"}).json()
    rows = {row["path_rel"]: row for row in listing["rows"]}
    assert rows["first.txt"]["selected"] is False
    assert rows["second.txt"]["selected"] is True

    bulk = client.post(
        "/api/files/selection",
        json={"ids": [second["id"]], "selected": False},
    ).json()
    assert bulk["updated"] == 1

    listing = client.get("/api/files", params={"order_by": "path_rel", "order_dir": "asc"}).json()
    rows = {row["path_rel"]: row for row in listing["rows"]}
    assert rows["first.txt"]["selected"] is False
    assert rows["second.txt"]["selected"] is False

    all_resp = client.post(
        "/api/files/selection/all",
        json={"selected": True},
    ).json()
    assert all_resp["updated"] == listing["total"]

    listing = client.get("/api/files", params={"order_by": "path_rel", "order_dir": "asc"}).json()
    assert all(row["selected"] for row in listing["rows"])


def test_file_report_endpoints(app_harness: AppHarness):
    """Uploading file reports should make them retrievable via the API."""

    client = app_harness.client

    inserted = client.post("/api/files", json={"path_rel": "notes/todo.md"}).json()
    file_id = inserted["id"]

    put_resp = client.put(
        f"/api/files/{file_id}/file_report",
        json={"file_report": "Detailed summary"},
    ).json()
    assert put_resp["ok"]

    report = client.get(f"/api/files/{file_id}/report").json()
    assert report["file_report"] == "Detailed summary"


def test_append_notes_endpoint(app_harness: AppHarness):
    """The bulk notes endpoint should append timestamped notes."""

    client = app_harness.client

    inserted = client.post("/api/files", json={"path_rel": "budget.xlsx"}).json()
    file_id = inserted["id"]

    resp = client.post(
        "/api/files/notes/append",
        json={"ids": [file_id], "text": "Reviewed"},
    ).json()
    assert resp["ok"]

    notes = client.get(f"/api/files/{file_id}/notes").json()["organization_notes"]
    assert "Reviewed" in notes


def test_missing_report_returns_404(app_harness: AppHarness):
    """Requesting a report for a non-existent file should raise 404."""

    resp = app_harness.client.get("/api/files/999/report")
    assert resp.status_code == 404


def test_move_pending_files_moves_and_deletes_source(app_harness: AppHarness):
    """Files should be copied to the target and removed when ``dont_delete`` is ``False``."""

    module = app_harness.module
    db = app_harness.db
    base_dir = app_harness.base_dir
    target_dir = app_harness.target_dir

    source = base_dir / "a.txt"
    source.write_text("alpha", encoding="utf-8")

    db.insert("a.txt")
    db.set_planned_destination("a.txt", "organized/a.txt")

    module._move_pending_files(str(base_dir), str(target_dir), dont_delete=False)

    dest = target_dir / "organized/a.txt"
    assert dest.exists()
    assert not source.exists()
    assert _get_final_dest(db, "a.txt") == str(dest)


def test_move_pending_files_respects_dont_delete(app_harness: AppHarness):
    """When ``dont_delete`` is ``True`` the source file should remain."""

    module = app_harness.module
    db = app_harness.db
    base_dir = app_harness.base_dir
    target_dir = app_harness.target_dir

    source = base_dir / "b.txt"
    source.write_text("bravo", encoding="utf-8")

    db.insert("b.txt")
    db.set_planned_destination("b.txt", "organized/b.txt")

    module._move_pending_files(str(base_dir), str(target_dir), dont_delete=True)

    dest = target_dir / "organized/b.txt"
    assert dest.exists()
    assert source.exists()
    assert _get_final_dest(db, "b.txt") == str(dest)


def test_move_pending_files_rejects_invalid_destination(app_harness: AppHarness):
    """Planner errors should be surfaced through the ``final_dest`` column."""

    module = app_harness.module
    db = app_harness.db
    base_dir = app_harness.base_dir
    target_dir = app_harness.target_dir

    base_file = base_dir / "c.txt"
    base_file.write_text("charlie", encoding="utf-8")

    db.insert("c.txt")
    db.set_planned_destination("c.txt", "[error: missing suggestion]")

    module._move_pending_files(str(base_dir), str(target_dir), dont_delete=False)

    final_dest = _get_final_dest(db, "c.txt")
    assert final_dest == "[error: planned destination invalid]"
    assert base_file.exists()


def test_move_pending_files_handles_missing_source(app_harness: AppHarness):
    """Missing source files should be marked with an explanatory error."""

    module = app_harness.module
    db = app_harness.db
    base_dir = app_harness.base_dir
    target_dir = app_harness.target_dir

    db.insert("d.txt")
    db.set_planned_destination("d.txt", "organized/d.txt")

    module._move_pending_files(str(base_dir), str(target_dir), dont_delete=False)

    final_dest = _get_final_dest(db, "d.txt")
    assert final_dest == "[error: source file not found]"


def test_move_pending_files_prevents_target_escape(app_harness: AppHarness):
    """Relative destinations may not traverse outside the configured target folder."""

    module = app_harness.module
    db = app_harness.db
    base_dir = app_harness.base_dir
    target_dir = app_harness.target_dir

    source = base_dir / "e.txt"
    source.write_text("echo", encoding="utf-8")

    db.insert("e.txt")
    db.set_planned_destination("e.txt", "../escape/e.txt")

    module._move_pending_files(str(base_dir), str(target_dir), dont_delete=False)

    final_dest = _get_final_dest(db, "e.txt")
    assert final_dest == "[error: planned destination escapes target folder]"
    assert source.exists()


def test_move_action_updates_organized_path_fields(app_harness: AppHarness):
    """The API should expose the final organised path after files are moved."""

    module = app_harness.module
    client = app_harness.client
    db = app_harness.db
    base_dir = app_harness.base_dir
    target_dir = app_harness.target_dir

    source = base_dir / "f.txt"
    source.write_text("foxtrot", encoding="utf-8")

    created = client.post("/api/files", json={"path_rel": "f.txt"}).json()
    file_id = created["id"]

    db.set_planned_destination("f.txt", "organized/f.txt")

    module._move_pending_files(str(base_dir), str(target_dir), dont_delete=True)

    destination = target_dir / "organized/f.txt"

    listing = client.get("/api/files", params={"page_size": 10}).json()
    row = next(r for r in listing["rows"] if r["id"] == file_id)
    assert row["organized_path"] == str(destination)

    detail = client.get(f"/api/files/{file_id}").json()
    assert detail["organized_path"] == str(destination)

