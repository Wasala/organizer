"""
AgentVectorDB: A lightweight semantic SQLite database using sqlite-vec and FastEmbed.

This module provides a single-file local database for organizing file metadata and
searching semantically similar file reports. All public methods return friendly
JSON dictionaries to ease integration with agent-based systems.

Dependencies:
  pip install sqlite-vec fastembed numpy
  # If your Python blocks SQLite extensions (macOS system Python):
  # pip install pysqlite3-binary

Configuration example (save as organizer.config.json):
{
  "db_path": "organizer.sqlite",
  "base_dir": "C:/cat",
  "embedding_model": null,
  "search": { "top_k": 10, "score_round": 4 },
  "sqlite": { "wal": true, "synchronous": "NORMAL", "cache_size_mb": 64, "temp_store_memory": true }
}
"""
from __future__ import annotations

import json
import os
import time
import typing as T

try:  # robust sqlite import
    import sqlite3
    _tmp = sqlite3.connect(":memory:")
    if not hasattr(_tmp, "enable_load_extension"):
        raise ImportError("sqlite3 lacks enable_load_extension; try pysqlite3-binary")
    _tmp.close()
except Exception:  # pragma: no cover
    import pysqlite3 as sqlite3  # type: ignore

import numpy as np
import sqlite_vec
from fastembed import TextEmbedding


def _iso_now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


def _norm_rel(path: str) -> str:
    p = path.replace("\\", "/")
    if p.startswith("./"):
        p = p[2:]
    return os.path.normpath(p).replace("\\", "/")


def _friendly_error(err: Exception) -> dict:
    return {"ok": False, "error": str(err)}


def _safe_json(fn):
    """Decorator: convert exceptions to friendly JSON errors."""
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except Exception as e:  # pylint: disable=broad-except
            return _friendly_error(e)
    return wrapper


DEFAULT_CONFIG = {
    "db_path": "organizer.sqlite",
    "base_dir": ".",
    "embedding_model": None,
    "search": {"top_k": 10, "score_round": 4},
    "sqlite": {
        "wal": True,
        "synchronous": "NORMAL",
        "cache_size_mb": 64,
        "temp_store_memory": True,
    },
}


class AgentVectorDB:
    """Semantic vector database for file organization."""

    def __init__(self, config_path: str = "organizer.config.json"):
        self.config_path = config_path
        self.config = self._load_or_create_config(config_path)
        self.conn = self._connect_and_load_vec()
        self.embedder = TextEmbedding(model_name=self.config.get("embedding_model"))
        self._prefix = "passage: "
        self._dim = int(len(self.embedder.embed([self._prefix + "probe"])[0]))
        self._ensure_schema()

    @classmethod
    def from_config(cls, config_path: str) -> "AgentVectorDB":
        return cls(config_path=config_path)

    @_safe_json
    def save_config(self, **overrides) -> dict:
        self.config.update(overrides)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=2)
        return {"ok": True, "config_path": self.config_path, "config": self.config}

    @staticmethod
    def _load_or_create_config(path: str) -> dict:
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as f:
                json.dump(DEFAULT_CONFIG, f, indent=2)
            return json.loads(json.dumps(DEFAULT_CONFIG))
        with open(path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        def deep_merge(default: dict, user: dict) -> dict:
            out = dict(default)
            for k, v in user.items():
                if isinstance(v, dict) and isinstance(out.get(k), dict):
                    out[k] = deep_merge(out[k], v)
                else:
                    out[k] = v
            return out
        return deep_merge(DEFAULT_CONFIG, cfg)

    def _connect_and_load_vec(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.config["db_path"])
        db.row_factory = sqlite3.Row
        s = self.config.get("sqlite", {})
        if s.get("wal", True):
            db.execute("PRAGMA journal_mode=WAL")
        db.execute(f"PRAGMA synchronous={s.get('synchronous', 'NORMAL')}")
        if s.get("temp_store_memory", True):
            db.execute("PRAGMA temp_store=MEMORY")
        cache_mb = int(s.get("cache_size_mb", 64))
        db.execute(f"PRAGMA cache_size={-cache_mb * 1024}")
        db.execute("PRAGMA foreign_keys=ON")
        db.enable_load_extension(True)
        sqlite_vec.load(db)
        db.enable_load_extension(False)
        return db

    def _ensure_schema(self) -> None:
        c = self.conn
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS files(
              id INTEGER PRIMARY KEY AUTOINCREMENT,
              path_rel TEXT NOT NULL UNIQUE,
              file_report TEXT,
              organization_notes TEXT,
              planned_dest TEXT,
              final_dest TEXT,
              log TEXT,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS config(
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );
            """
        )
        exists_vec_fr = c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='vec_file_report'"
        ).fetchone()
        if not exists_vec_fr:
            c.executescript(
                f"""
                CREATE VIRTUAL TABLE vec_file_report USING vec0(
                  file_id INTEGER PRIMARY KEY,
                  embedding FLOAT[{self._dim}] distance_metric=cosine,
                  +path_rel TEXT
                );
                """
            )
        exists_vec_on = c.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name='vec_org_notes'"
        ).fetchone()
        if not exists_vec_on:
            c.executescript(
                f"""
                CREATE VIRTUAL TABLE vec_org_notes USING vec0(
                  file_id INTEGER PRIMARY KEY,
                  embedding FLOAT[{self._dim}] distance_metric=cosine,
                  +path_rel TEXT
                );
                """
            )
        row = c.execute("SELECT value FROM config WHERE key='base_dir'").fetchone()
        if not row:
            c.execute(
                "INSERT INTO config(key, value) VALUES('base_dir', ?)",
                (os.path.abspath(self.config["base_dir"]),),
            )
        c.commit()

    @_safe_json
    def reset_db(self, base_dir_abs: str) -> dict:
        c = self.conn
        c.executescript(
            """
            PRAGMA foreign_keys=OFF;
            DROP TABLE IF EXISTS files;
            DROP TABLE IF EXISTS config;
            DROP TABLE IF EXISTS vec_file_report;
            DROP TABLE IF EXISTS vec_org_notes;
            PRAGMA foreign_keys=ON;
            """
        )
        self._ensure_schema()
        c.execute(
            "INSERT OR REPLACE INTO config(key, value) VALUES('base_dir', ?)",
            (os.path.abspath(base_dir_abs),),
        )
        c.commit()
        self.config["base_dir"] = os.path.abspath(base_dir_abs)
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=2)
        return {"ok": True, "message": "database reset", "base_dir": self.config["base_dir"]}

    @_safe_json
    def get_base_dir(self) -> dict:
        row = self.conn.execute("SELECT value FROM config WHERE key='base_dir'").fetchone()
        if not row:
            raise RuntimeError("Base directory not set. Call reset_db(base_dir_abs).")
        return {"ok": True, "base_dir": row["value"]}

    @_safe_json
    def insert(self, path_from_base: str) -> dict:
        path_rel = _norm_rel(path_from_base)
        now = _iso_now()
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO files(path_rel, created_at, updated_at) VALUES (?, ?, ?)",
            (path_rel, now, now),
        )
        self.conn.commit()
        existed = cur.rowcount == 0
        row = self.conn.execute("SELECT id FROM files WHERE path_rel=?", (path_rel,)).fetchone()
        if not row:
            raise RuntimeError("Failed to insert row.")
        return {"ok": True, "id": int(row["id"]), "path_rel": path_rel, "existed": existed}

    @_safe_json
    def set_file_report(self, path_from_base: str, text: str) -> dict:
        if not text or not text.strip():
            raise ValueError("file_report text is empty.")
        path_rel = _norm_rel(path_from_base)
        row = self.conn.execute("SELECT id FROM files WHERE path_rel=?", (path_rel,)).fetchone()
        if not row:
            raise KeyError(f"path not found: {path_rel}")
        file_id = int(row["id"])
        self.conn.execute(
            "UPDATE files SET file_report=?, updated_at=? WHERE id=?",
            (text, _iso_now(), file_id),
        )
        emb = self._embed_doc(text)
        self.conn.execute(
            "INSERT OR REPLACE INTO vec_file_report(file_id, embedding, path_rel) VALUES(?,?,?)",
            (file_id, emb, path_rel),
        )
        self.conn.commit()
        return {"ok": True, "id": file_id, "path_rel": path_rel}

    @_safe_json
    def append_organization_notes(self, ids: T.Iterable[int], notes_to_append: str) -> dict:
        ids = [int(i) for i in ids]
        if not ids:
            raise ValueError("No ids provided.")
        if not notes_to_append or not notes_to_append.strip():
            raise ValueError("organization_notes to append is empty.")
        cur = self.conn.cursor()
        now = _iso_now()
        updated = []
        for file_id in ids:
            row = cur.execute("SELECT organization_notes, path_rel FROM files WHERE id=?", (file_id,)).fetchone()
            if not row:
                continue
            merged = (row["organization_notes"] or "")
            if merged and not merged.endswith("\n"):
                merged += "\n"
            merged += notes_to_append
            cur.execute(
                "UPDATE files SET organization_notes=?, updated_at=? WHERE id=?",
                (merged, now, file_id),
            )
            emb = self._embed_doc(merged)
            cur.execute(
                "INSERT OR REPLACE INTO vec_org_notes(file_id, embedding, path_rel) VALUES(?, ?, ?)",
                (file_id, emb, row["path_rel"]),
            )
            updated.append(file_id)
        self.conn.commit()
        return {"ok": True, "updated_ids": updated}

    @_safe_json
    def set_planned_destination(self, path_from_base: str, planned_dest: str) -> dict:
        path_rel = _norm_rel(path_from_base)
        planned_dest = _norm_rel(planned_dest)
        self._update_one("planned_dest", path_rel, planned_dest)
        return {"ok": True, "path_rel": path_rel, "planned_dest": planned_dest}

    @_safe_json
    def set_final_destination(self, path_from_base: str, final_dest: str) -> dict:
        path_rel = _norm_rel(path_from_base)
        final_dest = _norm_rel(final_dest)
        self._update_one("final_dest", path_rel, final_dest)
        return {"ok": True, "path_rel": path_rel, "final_dest": final_dest}

    def _update_one(self, col: str, path_rel: str, value: str) -> None:
        row = self.conn.execute("SELECT id FROM files WHERE path_rel=?", (path_rel,)).fetchone()
        if not row:
            raise KeyError(f"path not found: {path_rel}")
        self.conn.execute(
            f"UPDATE files SET {col}=?, updated_at=? WHERE id=?",
            (value, _iso_now(), int(row["id"])),
        )
        self.conn.commit()

    @_safe_json
    def get_next_path_missing_file_report(self) -> dict:
        row = self.conn.execute(
            "SELECT path_rel FROM files WHERE IFNULL(TRIM(file_report),'')='' ORDER BY id ASC LIMIT 1"
        ).fetchone()
        return {"ok": True, "path_rel": row["path_rel"] if row else None}

    @_safe_json
    def get_next_path_missing_organization_notes(self) -> dict:
        row = self.conn.execute(
            """
            SELECT path_rel FROM files
            WHERE IFNULL(TRIM(file_report),'')<>''
              AND IFNULL(TRIM(organization_notes),'')=''
            ORDER BY id ASC LIMIT 1
            """
        ).fetchone()
        return {"ok": True, "path_rel": row["path_rel"] if row else None}

    @_safe_json
    def get_next_path_missing_planned_destination(self) -> dict:
        row = self.conn.execute(
            """
            SELECT path_rel FROM files
            WHERE IFNULL(TRIM(file_report),'')<>''
              AND IFNULL(TRIM(organization_notes),'')<>''
              AND IFNULL(TRIM(planned_dest),'')=''
            ORDER BY id ASC LIMIT 1
            """
        ).fetchone()
        return {"ok": True, "path_rel": row["path_rel"] if row else None}

    @_safe_json
    def get_next_path_missing_final_destination(self) -> dict:
        row = self.conn.execute(
            """
            SELECT path_rel FROM files
            WHERE IFNULL(TRIM(planned_dest),'')<>''
              AND IFNULL(TRIM(final_dest),'')=''
            ORDER BY id ASC LIMIT 1
            """
        ).fetchone()
        return {"ok": True, "path_rel": row["path_rel"] if row else None}

    @_safe_json
    def get_file_report(self, path_from_base: str) -> dict:
        path_rel = _norm_rel(path_from_base)
        row = self.conn.execute("SELECT file_report FROM files WHERE path_rel=?", (path_rel,)).fetchone()
        if not row:
            raise KeyError(f"path not found: {path_rel}")
        return {"ok": True, "path_rel": path_rel, "file_report": row["file_report"]}

    @_safe_json
    def find_similar_file_reports(self, path_from_base: str, top_k: int | None = None) -> dict:
        path_rel = _norm_rel(path_from_base)
        row = self.conn.execute("SELECT id, file_report FROM files WHERE path_rel=?", (path_rel,)).fetchone()
        if not row:
            raise KeyError(f"path not found: {path_rel}")
        if not row["file_report"]:
            raise ValueError(f"file_report is empty for: {path_rel}")
        q_vec = self._embed_doc(row["file_report"])
        k = int(top_k or self.config.get("search", {}).get("top_k", 10))
        score_round = int(self.config.get("search", {}).get("score_round", 4))
        sql = """
        SELECT f.*, v.distance
        FROM vec_file_report v
        JOIN files f ON f.id = v.file_id
        WHERE v.embedding MATCH :q AND k = :k
        ORDER BY v.distance
        LIMIT :k
        """
        matches = self.conn.execute(sql, {"q": q_vec.astype(np.float32), "k": k}).fetchall()
        results = []
        for m in matches:
            d = float(m["distance"]) if m["distance"] is not None else 2.0
            sim = max(0.0, min(1.0, 1.0 - (d / 2.0)))
            results.append({
                "id": int(m["id"]),
                "path_rel": m["path_rel"],
                "similarity_score": round(sim, score_round),
                "distance": round(d, score_round),
                "file_report": m["file_report"],
                "organization_notes": m["organization_notes"],
                "planned_dest": m["planned_dest"],
                "final_dest": m["final_dest"],
                "created_at": m["created_at"],
                "updated_at": m["updated_at"],
            })
        return {"ok": True, "results": results}

    def _embed_doc(self, text: str) -> np.ndarray:
        vec = self.embedder.embed([self._prefix + text])[0]
        return np.asarray(vec, dtype=np.float32)
