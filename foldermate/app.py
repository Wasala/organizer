# FastAPI layer for FolderMate
# pip install fastapi uvicorn pydantic sqlite-vec fastembed numpy

from __future__ import annotations
from typing import List, Optional, Literal, Dict, Any
from datetime import datetime
import threading, time
import os

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field, validator

from agent_utils.agent_vector_db import AgentVectorDB

# ---------- App + CORS ----------
BASE_DIR = os.path.dirname(__file__)
STATIC_DIR = os.path.join(BASE_DIR, "static")

app = FastAPI(title="FolderMate API", version="0.1")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # tighten for prod
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve static UI
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
INDEX_PATH = os.path.join(STATIC_DIR, "index.html")

@app.get("/", include_in_schema=False)
def ui_root():
    return FileResponse(INDEX_PATH)

db = AgentVectorDB("organizer.config.json")

# ---------- Single-action state ----------
class RunState:
    def __init__(self):
        self._lock = threading.Lock()
        self.current_action: Optional[str] = None  # "scan" | "analyze" | ...
        self.started_at: Optional[float] = None
        self.status_text: str = "Idle"
        self.cancel_event = threading.Event()

    def start(self, action: str):
        with self._lock:
            if self.current_action and self.current_action != action:
                raise RuntimeError(f"Another action '{self.current_action}' is running.")
            if not self.current_action:
                self.current_action = action
                self.started_at = time.time()
                self.status_text = {
                    "scan": "Scanning source files…",
                    "analyze": "File analysis in progress…",
                    "plan": "Planning…",
                    "decide": "Final decisions…",
                    "move": "Moving files…",
                }.get(action, "Working…")
                self.cancel_event.clear()

    def stop(self):
        with self._lock:
            self.cancel_event.set()
            self.current_action = None
            self.started_at = None
            self.status_text = "Stopped"

runstate = RunState()

# ---------- Schemas ----------
class ConfigOut(BaseModel):
    ok: bool = True
    config: Dict[str, Any]
    base_dir: str

class ConfigUpdate(BaseModel):
    base_dir: Optional[str] = None
    recursive: Optional[bool] = None
    dont_delete: Optional[bool] = None

class ResetPayload(BaseModel):
    base_dir: str


class ScanPayload(BaseModel):
    base_dir: Optional[str] = None
    recursive: Optional[bool] = None

class FileRow(BaseModel):
    id: int
    path_rel: str
    file_report_preview: Optional[str] = None
    organization_notes_preview: Optional[str] = None
    planned_dest: Optional[str] = None
    organized_path: Optional[str] = Field(None, alias="final_dest")
    created_at: str
    updated_at: str
    has_file_report: bool
    has_organization_notes: bool

class FileRowFull(BaseModel):
    ok: bool = True
    id: int
    path_rel: str
    file_report: Optional[str] = None
    organization_notes: Optional[str] = None
    planned_dest: Optional[str] = None
    organized_path: Optional[str] = Field(None, alias="final_dest")
    created_at: str
    updated_at: str

class FilesListOut(BaseModel):
    ok: bool = True
    page: int
    page_size: int
    total: int
    rows: List[FileRow]

class InsertFilePayload(BaseModel):
    path_rel: str

class PlannedDestUpdate(BaseModel):
    planned_dest: str

class NotesAppend(BaseModel):
    ids: List[int]
    text: str

class FileReportUpdate(BaseModel):
    file_report: str

class StatusOut(BaseModel):
    ok: bool = True
    current_action: Optional[str]
    status_text: str
    started_at: Optional[str] = None

class SimilarOut(BaseModel):
    ok: bool = True
    results: List[Dict[str, Any]]

# ---------- Helpers ----------

def _preview(s: Optional[str], n=140) -> Optional[str]:
    if not s:
        return None
    first_line = s.splitlines()[0]
    return (first_line[: n - 1] + "…") if len(first_line) > n else first_line

def _row_to_file_row(r) -> FileRow:
    return FileRow(
        id=int(r["id"]),
        path_rel=r["path_rel"],
        file_report_preview=_preview(r["file_report"]),
        organization_notes_preview=_preview(r["organization_notes"]),
        planned_dest=r["planned_dest"],
        organized_path=r["final_dest"],
        created_at=r["created_at"],
        updated_at=r["updated_at"],
        has_file_report=bool(r["file_report"]),
        has_organization_notes=bool(r["organization_notes"]),
    )

# ---------- Config ----------
@app.get("/api/config", response_model=ConfigOut)
def get_config():
    base = db.get_base_dir()
    return {"ok": True, "config": db.config, "base_dir": base["base_dir"]}

@app.put("/api/config", response_model=ConfigOut)
def put_config(payload: ConfigUpdate):
    if payload.base_dir:
        db.save_config(base_dir=payload.base_dir)
    # you can also persist recursive/dont_delete if you store them in config
    if payload.recursive is not None:
        db.save_config(recursive=payload.recursive)
    if payload.dont_delete is not None:
        db.save_config(dont_delete=payload.dont_delete)
    base = db.get_base_dir()
    return {"ok": True, "config": db.config, "base_dir": base["base_dir"]}

@app.post("/api/reset", response_model=Dict[str, Any])
def reset(payload: ResetPayload):
    return db.reset_db(payload.base_dir)

# ---------- Status / single action ----------
@app.get("/api/status", response_model=StatusOut)
def status():
    return {
        "ok": True,
        "current_action": runstate.current_action,
        "status_text": runstate.status_text,
        "started_at": datetime.utcfromtimestamp(runstate.started_at).isoformat() if runstate.started_at else None,
    }

@app.post("/api/actions/{action}", response_model=StatusOut)
def start_action(
    action: Literal["scan", "analyze", "plan", "decide", "move"],
    payload: Optional[ScanPayload] = None,
):
    try:
        runstate.start(action)
    except RuntimeError as e:  # pragma: no cover - networking
        raise HTTPException(status_code=409, detail=str(e))

    if action == "scan":
        base_dir = payload.base_dir if payload and payload.base_dir else db.config.get("base_dir")
        recursive = payload.recursive if payload and payload.recursive is not None else db.config.get("recursive", True)
        if not base_dir:
            runstate.stop()
            raise HTTPException(status_code=400, detail="base_dir not set")
        db.save_config(base_dir=base_dir, recursive=recursive)
        base_dir_abs = os.path.abspath(base_dir)
        for root, dirs, files in os.walk(base_dir_abs):
            for fname in files:
                rel = os.path.relpath(os.path.join(root, fname), base_dir_abs)
                db.insert(rel)
            if not recursive:
                break
        runstate.stop()
        runstate.status_text = "Idle"
        return status()

    return status()

@app.post("/api/stop", response_model=StatusOut)
def stop_all():
    runstate.stop()
    return status()

# ---------- Files / table ----------
@app.get("/api/files", response_model=FilesListOut)
def list_files(
    q: Optional[str] = None,
    page: int = 1,
    page_size: int = 50,
    order_by: Literal["path_rel", "created_at", "updated_at"] = "updated_at",
    order_dir: Literal["asc", "desc"] = "desc",
):
    page = max(1, page)
    page_size = max(1, min(200, page_size))
    offset = (page - 1) * page_size

    where = []
    params: Dict[str, Any] = {}
    if q:
        where.append(
            "(LOWER(path_rel) LIKE :q OR LOWER(file_report) LIKE :q OR LOWER(organization_notes) LIKE :q OR LOWER(IFNULL(planned_dest,'')) LIKE :q OR LOWER(IFNULL(final_dest,'')) LIKE :q)"
        )
        params["q"] = f"%{q.lower()}%"

    where_sql = ("WHERE " + " AND ".join(where)) if where else ""
    order_sql = f"ORDER BY {order_by} {order_dir.upper()}"

    total = db.conn.execute(f"SELECT COUNT(*) as c FROM files {where_sql}", params).fetchone()["c"]
    rows = db.conn.execute(
        f"""
        SELECT id, path_rel, file_report, organization_notes, planned_dest, final_dest,
               created_at, updated_at
        FROM files
        {where_sql}
        {order_sql}
        LIMIT :limit OFFSET :offset
        """,
        {**params, "limit": page_size, "offset": offset},
    ).fetchall()

    return {
        "ok": True,
        "page": page,
        "page_size": page_size,
        "total": int(total),
        "rows": [_row_to_file_row(r) for r in rows],
    }

@app.get("/api/files/{file_id}", response_model=FileRowFull)
def get_file(file_id: int):
    r = db.conn.execute("SELECT * FROM files WHERE id=?", (file_id,)).fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    return {
        "ok": True,
        "id": int(r["id"]),
        "path_rel": r["path_rel"],
        "file_report": r["file_report"],
        "organization_notes": r["organization_notes"],
        "planned_dest": r["planned_dest"],
        "organized_path": r["final_dest"],
        "created_at": r["created_at"],
        "updated_at": r["updated_at"],
    }

@app.post("/api/files", response_model=Dict[str, Any])
def insert_file(payload: InsertFilePayload):
    return db.insert(payload.path_rel)

@app.put("/api/files/{file_id}/planned_dest", response_model=Dict[str, Any])
def set_planned_dest(file_id: int, payload: PlannedDestUpdate):
    r = db.conn.execute("SELECT path_rel FROM files WHERE id=?", (file_id,)).fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    # use OOP helper (by path)
    return db.set_planned_destination(r["path_rel"], payload.planned_dest)

@app.get("/api/files/{file_id}/report", response_model=Dict[str, Any])
def get_report(file_id: int):
    r = db.conn.execute("SELECT path_rel FROM files WHERE id=?", (file_id,)).fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    out = db.get_file_report(r["path_rel"])
    return {"ok": True, "file_report": out.get("file_report")}

@app.get("/api/files/{file_id}/notes", response_model=Dict[str, Any])
def get_notes(file_id: int):
    r = db.conn.execute("SELECT organization_notes FROM files WHERE id=?", (file_id,)).fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    return {"ok": True, "organization_notes": r["organization_notes"]}

@app.put("/api/files/{file_id}/file_report", response_model=Dict[str, Any])
def put_file_report(file_id: int, payload: FileReportUpdate):
    r = db.conn.execute("SELECT path_rel FROM files WHERE id=?", (file_id,)).fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    return db.set_file_report(r["path_rel"], payload.file_report)

@app.post("/api/files/notes/append", response_model=Dict[str, Any])
def append_notes(payload: NotesAppend):
    return db.append_organization_notes(payload.ids, payload.text)

# ---------- Similarity ----------
@app.get("/api/files/{file_id}/similar", response_model=SimilarOut)
def similar(file_id: int, top_k: int = 10):
    r = db.conn.execute("SELECT path_rel FROM files WHERE id=?", (file_id,)).fetchone()
    if not r:
        raise HTTPException(status_code=404, detail="Not found")
    return db.find_similar_file_reports(r["path_rel"], top_k=top_k)

# ---------- Run ----------
# uvicorn foldermate.app:app --host 127.0.0.1 --port 8000 --reload
