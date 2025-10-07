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
  "embedding_model": "nomic-ai/nomic-embed-text-v1.5",
  "search": { "top_k": 10, "score_round": 4 },
  "sqlite": { "wal": true, "synchronous": "NORMAL", "cache_size_mb": 64, "temp_store_memory": true }
}
"""
from __future__ import annotations

import json
import logging
import os
import re
import threading
from contextlib import nullcontext
from functools import wraps
from pathlib import Path
import time
from datetime import datetime, timezone
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

logger = logging.getLogger(__name__)


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

    @wraps(fn)
    def wrapper(*args, **kwargs):
        self = args[0] if args else None
        lock = getattr(self, "_lock", None)
        ctx = lock if lock is not None else nullcontext()
        with ctx:
            try:
                return fn(*args, **kwargs)
            except Exception as err:  # pylint: disable=broad-except
                return _friendly_error(err)

    return wrapper


CONFIG_FILE_EXCLUDE_KEYS = {"base_dir", "target_dir", "instructions"}


DEFAULT_CONFIG = {
    "db_path": "organizer.sqlite",
    "base_dir": ".",
    "target_dir": "",
    "instructions": "",
    # Use a concrete model string; fastembed expects a string, not None
    "embedding_model": "nomic-ai/nomic-embed-text-v1.5",
    "search": {"top_k": 10, "score_round": 4},
    "log_dir": ".",
    "allowed_file_extentions": [
        ".txt",
        ".md",
        ".rst",
        ".json",
        ".csv",
        ".yaml",
        ".yml",
        ".ini",
        ".toml",
        ".docx",
        ".xlsx",
        ".pptx",
        ".pdf",
        ".html",
        ".xhtml",
        ".htm",
        ".webvtt",
        ".vtt",
        ".png",
        ".jpg",
        ".jpeg",
        ".tiff",
        ".tif",
        ".bmp",
        ".webp",
    ],
    "sqlite": {
        "wal": True,
        "synchronous": "NORMAL",
        "cache_size_mb": 64,
        "temp_store_memory": True,
    },
}

# Placeholder markers used when a file analysis is in progress.
PROCESSING_SENTINELS = ("processing...", "processing..")


def _normalise_extensions(values: T.Iterable[str] | None) -> set[str]:
    """Return a normalised set of file extensions."""

    if not values:
        return set()
    normalised: set[str] = set()
    for value in values:
        if not isinstance(value, str):
            continue
        candidate = value.strip().lower()
        if not candidate:
            continue
        if not candidate.startswith("."):
            candidate = f".{candidate}"
        normalised.add(candidate)
    return normalised


class AgentVectorDB:
    """Semantic vector database for file organization."""

    def __init__(self, config_path: str = "organizer.config.json"):
        self.config_path = config_path
        self.config = self._load_or_create_config(config_path)
        self._allowed_extensions: set[str] = _normalise_extensions(
            self.config.get("allowed_file_extentions", [])
        )
        self._lock = threading.RLock()
        self.conn = self._connect_and_load_vec()

        # --- FastEmbed model (ensure a non-empty string) ---
        model_name = self.config.get("embedding_model") or "nomic-ai/nomic-embed-text-v1.5"
        self.embedder = TextEmbedding(model_name=model_name)

        self._prefix = "passage: "
        # embed() returns a generator; take the first vector to determine dimension
        probe_iter = self.embedder.embed([self._prefix + "probe"])
        probe_vec = next(iter(probe_iter))
        self._dim = int(len(probe_vec))

        self._ensure_schema()
        self._ensure_vector_table_dimensions()
        self._refresh_config_from_db()
        self._refresh_allowed_extensions()
        self._write_config_file()

    @classmethod
    def from_config(cls, config_path: str) -> "AgentVectorDB":
        return cls(config_path=config_path)

    @_safe_json
    def save_config(self, **overrides) -> dict:
        """Persist configuration overrides.

        Any provided keyword arguments are merged into the in-memory configuration,
        saved to the JSON config file and upserted into the ``config`` table within
        the SQLite database. Paths are stored as absolute paths.
        """

        c = self.conn
        for key, value in overrides.items():
            if value is None:
                continue
            if key in {"base_dir", "target_dir"}:
                value = os.path.abspath(str(value))
            self.config[key] = value
            stored = json.dumps(value) if not isinstance(value, str) else value
            c.execute(
                "INSERT OR REPLACE INTO config(key, value) VALUES(?, ?)",
                (key, stored),
            )
        c.commit()
        self._refresh_allowed_extensions()
        self._write_config_file()
        logger.info("Saved config overrides: %s", list(overrides.keys()))
        return {"ok": True, "config_path": self.config_path, "config": self.config}

    @staticmethod
    def _load_or_create_config(path: str) -> dict:
        if not os.path.exists(path):
            to_store = {
                key: value
                for key, value in DEFAULT_CONFIG.items()
                if key not in CONFIG_FILE_EXCLUDE_KEYS
            }
            with open(path, "w", encoding="utf-8") as f:
                json.dump(to_store, f, indent=2)
            logger.info("Created default config at %s", path)
            cfg = json.loads(json.dumps(DEFAULT_CONFIG))
        else:
            with open(path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            logger.info("Loaded config from %s", path)

        def deep_merge(default: dict, user: dict) -> dict:
            out = dict(default)
            for k, v in user.items():
                if isinstance(v, dict) and isinstance(out.get(k), dict):
                    out[k] = deep_merge(out[k], v)
                else:
                    out[k] = v
            return out

        merged = deep_merge(DEFAULT_CONFIG, cfg)
        db_path = merged.get("db_path", DEFAULT_CONFIG["db_path"])
        if db_path and not os.path.isabs(db_path):
            merged["db_path"] = os.path.abspath(os.path.join(os.path.dirname(path), db_path))
        return merged

    def _connect_and_load_vec(self) -> sqlite3.Connection:
        # Allow use across FastAPI worker threads and avoid “created in a different thread”
        db = sqlite3.connect(self.config["db_path"], check_same_thread=False)
        db.row_factory = sqlite3.Row

        # Be kinder under concurrent access
        db.execute("PRAGMA busy_timeout=5000")

        s = self.config.get("sqlite", {})
        if s.get("wal", True):
            try:
                db.execute("PRAGMA journal_mode=WAL")
            except sqlite3.OperationalError as exc:  # pragma: no cover - depends on sqlite build
                logger.warning("WAL mode unavailable (%s); falling back to DELETE", exc)
                db.execute("PRAGMA journal_mode=DELETE")
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
              planner_processed INTEGER NOT NULL DEFAULT 0,
              planned_dest TEXT,
              final_dest TEXT,
              log TEXT,
              selected INTEGER NOT NULL DEFAULT 1,
              created_at TEXT NOT NULL,
              updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS config(
              key TEXT PRIMARY KEY,
              value TEXT NOT NULL
            );
            """
        )
        cols = {r["name"] for r in c.execute("PRAGMA table_info(files)")}
        if "planner_processed" not in cols:
            c.execute(
                "ALTER TABLE files ADD COLUMN planner_processed INTEGER NOT NULL DEFAULT 0"
            )
        if "selected" not in cols:
            c.execute(
                "ALTER TABLE files ADD COLUMN selected INTEGER NOT NULL DEFAULT 1"
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
        for key in ("target_dir", "instructions"):
            val = self.config.get(key)
            if val is not None:
                c.execute(
                    "INSERT OR IGNORE INTO config(key, value) VALUES(?, ?)",
                    (key, val),
                )
        c.commit()

    def _ensure_vector_table_dimensions(self) -> None:
        """Ensure vector tables match the current embedding dimensionality."""

        with self._lock:
            existing_dim = self._get_stored_embedding_dim()
            vec_file_dim = self._get_vec_table_dim("vec_file_report")
            vec_notes_dim = self._get_vec_table_dim("vec_org_notes")

            mismatch = any(
                dim is not None and dim != self._dim
                for dim in (existing_dim, vec_file_dim, vec_notes_dim)
            )

            if mismatch:
                logger.warning(
                    "Embedding dimension changed (stored=%s, file=%s, notes=%s -> current=%s). "
                    "Rebuilding vector tables.",
                    existing_dim,
                    vec_file_dim,
                    vec_notes_dim,
                    self._dim,
                )
                self._rebuild_vector_tables()

            self._set_stored_embedding_dim(self._dim)

    def _get_vec_table_dim(self, table_name: str) -> int | None:
        row = self.conn.execute(
            "SELECT sql FROM sqlite_master WHERE type='table' AND name=?",
            (table_name,),
        ).fetchone()
        if not row or not row["sql"]:
            return None
        match = re.search(r"FLOAT\[(\d+)\]", row["sql"])
        return int(match.group(1)) if match else None

    def _get_stored_embedding_dim(self) -> int | None:
        row = self.conn.execute(
            "SELECT value FROM config WHERE key='embedding_dim'",
        ).fetchone()
        if not row:
            return None
        try:
            return int(row["value"])
        except (TypeError, ValueError):
            return None

    def _set_stored_embedding_dim(self, dim: int) -> None:
        self.conn.execute(
            "INSERT OR REPLACE INTO config(key, value) VALUES('embedding_dim', ?)",
            (str(dim),),
        )
        self.conn.commit()
        self.config["embedding_dim"] = dim

    def _rebuild_vector_tables(self) -> None:
        """Recreate vector tables and repopulate embeddings with the new dimension."""

        c = self.conn
        c.executescript(
            """
            DROP TABLE IF EXISTS vec_file_report;
            DROP TABLE IF EXISTS vec_org_notes;
            """
        )
        c.executescript(
            f"""
            CREATE VIRTUAL TABLE vec_file_report USING vec0(
              file_id INTEGER PRIMARY KEY,
              embedding FLOAT[{self._dim}] distance_metric=cosine,
              +path_rel TEXT
            );
            CREATE VIRTUAL TABLE vec_org_notes USING vec0(
              file_id INTEGER PRIMARY KEY,
              embedding FLOAT[{self._dim}] distance_metric=cosine,
              +path_rel TEXT
            );
            """
        )

        rows = c.execute(
            "SELECT id, path_rel, file_report FROM files WHERE IFNULL(TRIM(file_report),'')<>''",
        ).fetchall()
        for row in rows:
            try:
                emb = self._embed_doc(row["file_report"])
            except Exception:  # pylint: disable=broad-except
                continue
            c.execute(
                "INSERT INTO vec_file_report(file_id, embedding, path_rel) VALUES(?, ?, ?)",
                (int(row["id"]), emb, row["path_rel"]),
            )

        rows = c.execute(
            "SELECT id, path_rel, organization_notes FROM files WHERE IFNULL(TRIM(organization_notes),'')<>''",
        ).fetchall()
        for row in rows:
            try:
                emb = self._embed_doc(row["organization_notes"])
            except Exception:  # pylint: disable=broad-except
                continue
            c.execute(
                "INSERT INTO vec_org_notes(file_id, embedding, path_rel) VALUES(?, ?, ?)",
                (int(row["id"]), emb, row["path_rel"]),
            )

        c.commit()

    @_safe_json
    def reset_db(self, base_dir_abs: str) -> dict:
        logger.info("Resetting database with base directory %s", base_dir_abs)
        base_dir_abs = os.path.abspath(base_dir_abs)
        c = self.conn
        c.executescript(
            """
            DELETE FROM vec_file_report;
            DELETE FROM vec_org_notes;
            DELETE FROM files;
            DELETE FROM config;
            """
        )
        try:
            c.execute("DELETE FROM sqlite_sequence WHERE name='files'")
        except sqlite3.OperationalError:
            logger.debug("sqlite_sequence table missing; skipping autoincrement reset")
        self.config.pop("target_dir", None)
        self.config.pop("instructions", None)
        c.execute(
            "INSERT OR REPLACE INTO config(key, value) VALUES('base_dir', ?)",
            (base_dir_abs,),
        )
        c.commit()
        self.config["base_dir"] = base_dir_abs
        self._set_stored_embedding_dim(self._dim)
        logger.info("Database reset complete; base_dir=%s", self.config["base_dir"])
        return {"ok": True, "message": "database reset", "base_dir": self.config["base_dir"]}

    def _write_config_file(self) -> None:
        """Persist the JSON configuration excluding runtime-only keys."""

        persisted = {
            key: value
            for key, value in self.config.items()
            if key not in CONFIG_FILE_EXCLUDE_KEYS
        }
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(persisted, f, indent=2)

    def _refresh_config_from_db(self) -> None:
        """Load persisted configuration values from SQLite into memory."""

        rows = self.conn.execute("SELECT key, value FROM config").fetchall()
        for row in rows:
            value = row["value"]
            if isinstance(value, (bytes, bytearray)):
                value = value.decode("utf-8")
            try:
                parsed = json.loads(value)
            except (TypeError, json.JSONDecodeError):
                parsed = value
            self.config[row["key"]] = parsed
        self._refresh_allowed_extensions()

    def _refresh_allowed_extensions(self) -> None:
        """Update the cached set of allowed file extensions."""

        values = self.config.get("allowed_file_extentions", [])
        if isinstance(values, str):
            values = [part.strip() for part in values.split(",") if part.strip()]
        self._allowed_extensions = _normalise_extensions(values)

    def get_allowed_extensions(self) -> set[str]:
        """Return a copy of the configured allowed file extensions."""

        return set(self._allowed_extensions)

    def is_allowed_file(self, path_from_base: str) -> bool:
        """Return ``True`` when ``path_from_base`` uses an allowed extension."""

        suffix = Path(path_from_base).suffix.lower()
        if suffix:
            return suffix in self._allowed_extensions
        return False

    @_safe_json
    def get_base_dir(self) -> dict:
        row = self.conn.execute("SELECT value FROM config WHERE key='base_dir'").fetchone()
        if not row:
            raise RuntimeError("Base directory not set. Call reset_db(base_dir_abs).")
        return {"ok": True, "base_dir": row["value"]}

    @_safe_json
    def get_instructions(self) -> dict:
        """Return user folder organization instructions.

        The instructions are stored in the ``config`` table under the
        ``instructions`` key.  If no instructions have been saved, an empty
        string is returned.
        """

        row = self.conn.execute(
            "SELECT value FROM config WHERE key='instructions'"
        ).fetchone()
        return {"ok": True, "instructions": row["value"] if row else ""}

    @_safe_json
    def insert(self, path_from_base: str) -> dict:
        path_rel = _norm_rel(path_from_base)
        if not self.is_allowed_file(path_rel):
            raise ValueError(
                f"unsupported file extension: {Path(path_rel).suffix or 'no extension'}"
            )
        now = _iso_now()
        cur = self.conn.execute(
            "INSERT OR IGNORE INTO files(path_rel, selected, created_at, updated_at) VALUES (?, 1, ?, ?)",
            (path_rel, now, now),
        )
        self.conn.commit()
        existed = cur.rowcount == 0
        row = self.conn.execute("SELECT id FROM files WHERE path_rel=?", (path_rel,)).fetchone()
        if not row:
            raise RuntimeError("Failed to insert row.")
        logger.info("Inserted path %s (existed=%s)", path_rel, existed)
        return {"ok": True, "id": int(row["id"]), "path_rel": path_rel, "existed": existed}

    @_safe_json
    def get_file_id(self, path_from_base: str) -> dict:
        """Return the database identifier for ``path_from_base``.

        Parameters
        ----------
        path_from_base:
            File path relative to the base directory.

        Returns
        -------
        dict
            JSON-friendly result containing ``id`` and ``path_rel``.

        Raises
        ------
        KeyError
            If the path is not present in the database.
        """

        path_rel = _norm_rel(path_from_base)
        row = self.conn.execute("SELECT id FROM files WHERE path_rel=?", (path_rel,)).fetchone()
        if not row:
            raise KeyError(f"path not found: {path_rel}")
        return {"ok": True, "id": int(row["id"]), "path_rel": path_rel}

    @_safe_json
    def set_file_report(self, path_from_base: str, text: str) -> dict:
        if not text or not text.strip():
            raise ValueError("file_report text is empty.")
        path_rel = _norm_rel(path_from_base)
        row = self.conn.execute("SELECT id FROM files WHERE path_rel=?", (path_rel,)).fetchone()
        if not row:
            raise KeyError(f"path not found: {path_rel}")
        file_id = int(row["id"])

        attempts = 0
        while True:
            try:
                self.conn.execute(
                    "UPDATE files SET file_report=?, updated_at=? WHERE id=?",
                    (text, _iso_now(), file_id),
                )
                try:
                    emb = self._embed_doc(text)
                    self.conn.execute(
                        "INSERT OR REPLACE INTO vec_file_report(file_id, embedding, path_rel) VALUES(?,?,?)",
                        (file_id, emb, path_rel),
                    )
                except Exception:  # pylint: disable=broad-except
                    # Even if embedding fails we still want the report persisted.
                    pass
                self.conn.commit()
                break
            except sqlite3.OperationalError as exc:  # pragma: no cover - rare
                if "locked" in str(exc).lower() and attempts < 3:
                    attempts += 1
                    time.sleep(0.1 * attempts)
                    continue
                raise

        logger.info("Saved file report for %s", path_rel)
        return {"ok": True, "id": file_id, "path_rel": path_rel}

    @_safe_json
    def clear_processing_file_reports(self) -> dict:
        """Remove placeholder ``file_report`` entries left mid-analysis.

        If the application stops while a file is being analysed, the
        ``file_report`` column may contain one of the
        :data:`PROCESSING_SENTINELS`.  On the next start we want such
        files to appear as pending rather than perpetually "processing".
        This method clears those markers.

        Returns
        -------
        dict
            JSON-friendly result with the count of cleared rows under the
            ``cleared`` key.
        """

        cur = self.conn.execute(
            "UPDATE files SET file_report='', updated_at=? WHERE file_report IN (?, ?)",
            (_iso_now(), *PROCESSING_SENTINELS),
        )
        self.conn.commit()
        logger.info("Cleared %s processing file reports", cur.rowcount)
        return {"ok": True, "cleared": int(cur.rowcount)}

    @_safe_json
    def append_organization_cluser_notes(
        self, ids: T.Iterable[int], notes_to_append: str
    ) -> dict:
        """Append timestamped organisation notes to the specified files.

        Parameters
        ----------
        ids:
            Iterable of file identifiers to update.
        notes_to_append:
            Note text to append.

        Returns
        -------
        dict
            JSON-friendly result containing ``updated_ids``.
        """

        ids = [int(i) for i in ids]
        if not ids:
            raise ValueError("No ids provided.")
        if not notes_to_append or not notes_to_append.strip():
            raise ValueError("organization_notes to append is empty.")
        cur = self.conn.cursor()
        now = _iso_now()
        updated: list[int] = []
        timestamp = datetime.now(timezone.utc).strftime("%d-%m-%y-%H:%M:%S")
        note_line = f"[{timestamp}]{notes_to_append.strip()}\n"
        for file_id in ids:
            row = cur.execute(
                "SELECT organization_notes, path_rel FROM files WHERE id=?",
                (file_id,),
            ).fetchone()
            if not row:
                continue
            merged = row["organization_notes"] or ""
            if merged and not merged.endswith("\n"):
                merged += "\n"
            merged += note_line
            cur.execute(
                "UPDATE files SET organization_notes=?, updated_at=? WHERE id=?",
                (merged, now, file_id),
            )
            emb = self._embed_doc(merged)
            cur.execute("DELETE FROM vec_org_notes WHERE file_id=?", (file_id,))
            cur.execute(
                "INSERT INTO vec_org_notes(file_id, embedding, path_rel) VALUES(?, ?, ?)",
                (file_id, emb, row["path_rel"]),
            )
            updated.append(file_id)
        self.conn.commit()
        logger.info("Appended organization notes to ids=%s", updated)
        return {"ok": True, "updated_ids": updated}

    @_safe_json
    def append_organization_anchor_notes(
        self, path_rel: str, notes_to_append: str
    ) -> dict:
        """Append timestamped organisation notes for a single file by path.

        Parameters
        ----------
        path_rel:
            File path relative to the base directory.
        notes_to_append:
            Note text to append.

        Returns
        -------
        dict
            JSON-friendly result containing ``updated_ids`` with the single
            updated file id.
        """

        norm = _norm_rel(path_rel)
        row = self.conn.execute(
            "SELECT id FROM files WHERE path_rel=?", (norm,)
        ).fetchone()
        if not row:
            raise KeyError(f"path not found: {norm}")
        return self.append_organization_cluser_notes([int(row["id"])], notes_to_append)

    @_safe_json
    def prepend_organization_note_sentinel(
        self, path_from_base: str, message: str
    ) -> dict:
        """Prepend a processing sentinel to ``organization_notes``.

        Parameters
        ----------
        path_from_base:
            File path relative to the base directory.
        message:
            Sentinel message to insert as the first line.

        Returns
        -------
        dict
            JSON-friendly result containing ``id`` and ``path_rel``.
        """

        if not message or not message.strip():
            raise ValueError("message is empty.")
        path_rel = _norm_rel(path_from_base)
        cur = self.conn.cursor()
        row = cur.execute(
            "SELECT id, organization_notes FROM files WHERE path_rel=?",
            (path_rel,),
        ).fetchone()
        if not row:
            raise KeyError(f"path not found: {path_rel}")
        existing = row["organization_notes"] or ""
        msg = message.strip()
        if msg in PROCESSING_SENTINELS:
            sentinel_block = f"{msg}\n"
        else:
            timestamp = datetime.now(timezone.utc).strftime("%d-%m-%y-%H:%M:%S")
            sentinel_block = f"[{timestamp}]{msg}\n"
        new_notes = sentinel_block + existing
        cur.execute(
            "UPDATE files SET organization_notes=?, updated_at=? WHERE id=?",
            (new_notes, _iso_now(), int(row["id"])),
        )
        emb = self._embed_doc(new_notes) if new_notes else None
        cur.execute("DELETE FROM vec_org_notes WHERE file_id=?", (int(row["id"]),))
        if emb is not None:
            cur.execute(
                "INSERT INTO vec_org_notes(file_id, embedding, path_rel) VALUES(?, ?, ?)",
                (int(row["id"]), emb, path_rel),
            )
        self.conn.commit()
        logger.info("Prepended sentinel to organization notes for %s", path_rel)
        return {"ok": True, "id": int(row["id"]), "path_rel": path_rel}

    @_safe_json
    def remove_organization_note_sentinel(
        self, path_from_base: str, message: str
    ) -> dict:
        """Remove a processing sentinel from ``organization_notes``.

        Parameters
        ----------
        path_from_base:
            File path relative to the base directory.
        message:
            Sentinel message previously inserted.

        Returns
        -------
        dict
            JSON-friendly result containing ``id`` and ``path_rel``.
        """

        path_rel = _norm_rel(path_from_base)
        cur = self.conn.cursor()
        row = cur.execute(
            "SELECT id, organization_notes FROM files WHERE path_rel=?",
            (path_rel,),
        ).fetchone()
        if not row:
            raise KeyError(f"path not found: {path_rel}")
        existing = row["organization_notes"] or ""
        parts = existing.splitlines(keepends=True)
        new_notes = existing
        msg = message.strip()
        if parts and parts[0].strip() == msg:
            new_notes = "".join(parts[1:])
        elif len(parts) >= 2 and parts[1].strip() == msg:
            new_notes = "".join(parts[2:])
        cur.execute(
            "UPDATE files SET organization_notes=?, updated_at=? WHERE id=?",
            (new_notes, _iso_now(), int(row["id"])),
        )
        cur.execute("DELETE FROM vec_org_notes WHERE file_id=?", (int(row["id"]),))
        if new_notes:
            emb = self._embed_doc(new_notes)
            cur.execute(
                "INSERT INTO vec_org_notes(file_id, embedding, path_rel) VALUES(?, ?, ?)",
                (int(row["id"]), emb, path_rel),
            )
        self.conn.commit()
        logger.info("Removed sentinel from organization notes for %s", path_rel)
        return {"ok": True, "id": int(row["id"]), "path_rel": path_rel}

    @_safe_json
    def set_planned_destination(self, path_from_base: str, planned_dest: str) -> dict:
        path_rel = _norm_rel(path_from_base)
        planned_dest = _norm_rel(planned_dest)
        self._update_one("planned_dest", path_rel, planned_dest)
        logger.info("Set planned destination for %s -> %s", path_rel, planned_dest)
        return {"ok": True, "path_rel": path_rel, "planned_dest": planned_dest}

    @_safe_json
    def set_final_destination(self, path_from_base: str, final_dest: str) -> dict:
        path_rel = _norm_rel(path_from_base)
        final_dest = _norm_rel(final_dest)
        self._update_one("final_dest", path_rel, final_dest)
        logger.info("Set final destination for %s -> %s", path_rel, final_dest)
        return {"ok": True, "path_rel": path_rel, "final_dest": final_dest}

    @_safe_json
    def set_selected(self, path_from_base: str, selected: bool) -> dict:
        path_rel = _norm_rel(path_from_base)
        value = 1 if selected else 0
        row = self.conn.execute("SELECT id FROM files WHERE path_rel=?", (path_rel,)).fetchone()
        if not row:
            raise KeyError(f"path not found: {path_rel}")
        self.conn.execute(
            "UPDATE files SET selected=?, updated_at=? WHERE id=?",
            (value, _iso_now(), int(row["id"])),
        )
        self.conn.commit()
        logger.info("Set selected=%s for %s", selected, path_rel)
        return {"ok": True, "path_rel": path_rel, "selected": bool(value)}

    @_safe_json
    def set_selected_by_ids(self, ids: list[int], selected: bool) -> dict:
        if not ids:
            return {"ok": True, "updated": 0, "selected": selected}
        value = 1 if selected else 0
        placeholders = ",".join("?" for _ in ids)
        now = _iso_now()
        cur = self.conn.execute(
            f"UPDATE files SET selected=?, updated_at=? WHERE id IN ({placeholders})",
            (value, now, *ids),
        )
        self.conn.commit()
        logger.info("Updated selected=%s for %s rows", selected, cur.rowcount)
        return {"ok": True, "updated": int(cur.rowcount), "selected": selected}

    @_safe_json
    def set_selected_all(self, selected: bool) -> dict:
        value = 1 if selected else 0
        cur = self.conn.execute(
            "UPDATE files SET selected=?, updated_at=?",
            (value, _iso_now()),
        )
        self.conn.commit()
        logger.info("Updated selected=%s for all rows", selected)
        return {"ok": True, "updated": int(cur.rowcount), "selected": selected}

    def _update_one(self, col: str, path_rel: str, value: T.Any) -> None:
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
            """
            SELECT path_rel FROM files
            WHERE selected=1
              AND (IFNULL(TRIM(file_report),'')='' OR file_report IN (?, ?))
            ORDER BY id ASC LIMIT 1
            """,
            PROCESSING_SENTINELS,
        ).fetchone()
        return {"ok": True, "path_rel": row["path_rel"] if row else None}

    @_safe_json
    def mark_organization_plan_processed(self, path_from_base: str) -> dict:
        """Mark that the planner has processed ``path_from_base``.

        Parameters
        ----------
        path_from_base:
            File path relative to the base directory.

        Returns
        -------
        dict
            JSON-friendly result containing the normalised ``path_rel``.
        """

        path_rel = _norm_rel(path_from_base)
        self._update_one("planner_processed", path_rel, 1)
        logger.info("Marked planner processed for %s", path_rel)
        return {"ok": True, "path_rel": path_rel}

    @_safe_json
    def get_next_path_pending_organization_plan(self) -> dict:
        """Return the next file whose planner step has not run."""

        row = self.conn.execute(
            """
            SELECT path_rel FROM files
            WHERE selected=1
              AND IFNULL(TRIM(file_report),'')<>''
              AND planner_processed=0
            ORDER BY id ASC LIMIT 1
            """
        ).fetchone()
        return {"ok": True, "path_rel": row["path_rel"] if row else None}

    @_safe_json
    def get_next_path_missing_planned_destination(self) -> dict:
        row = self.conn.execute(
            """
            SELECT path_rel FROM files
            WHERE selected=1
              AND IFNULL(TRIM(file_report),'')<>''
              AND planner_processed=1
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
            WHERE selected=1
              AND IFNULL(TRIM(planned_dest),'')<>''
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
    def get_organization_notes(self, path_from_base: str) -> dict:
        path_rel = _norm_rel(path_from_base)
        row = self.conn.execute(
            "SELECT organization_notes FROM files WHERE path_rel=?",
            (path_rel,),
        ).fetchone()
        if not row:
            raise KeyError(f"path not found: {path_rel}")
        return {
            "ok": True,
            "path_rel": path_rel,
            "organization_notes": row["organization_notes"],
        }

    @_safe_json
    def planned_destination_folders_for_proposed(
        self, proposed_folder_path: str
    ) -> dict:
        """Return planned destination folders for a proposed folder path.

        Parameters
        ----------
        proposed_folder_path:
            Folder path as it appears in ``ProposedFolderPath`` within
            cluster notes. Matching is case-insensitive.

        Returns
        -------
        dict
            Result containing a unique list of destination folders under the
            ``folders`` key.
        """

        path_norm = _norm_rel(proposed_folder_path).lower()
        if not path_norm:
            return {"ok": True, "folders": []}

        query = (
            """
            SELECT planned_dest FROM files
            WHERE IFNULL(TRIM(planned_dest),'')<>''
              AND LOWER(organization_notes) LIKE :path_match
              AND LOWER(organization_notes) LIKE '%"kind"%"clusternotes"%'
            """
        )
        rows = self.conn.execute(
            query, {"path_match": f'%"proposedfolderpath"%"{path_norm}"%'}
        ).fetchall()

        target_dir = _norm_rel(self.config.get("target_dir", ""))
        folders: set[str] = set()
        for row in rows:
            dest = row["planned_dest"]
            if not dest:
                continue
            dest_norm = _norm_rel(dest)
            if target_dir and dest_norm.lower().startswith(target_dir.lower()):
                dest_norm = dest_norm[len(target_dir) :].lstrip("/\\")
            folder = os.path.dirname(dest_norm).replace("\\", "/")
            if folder and not folder.startswith("/"):
                folder = "/" + folder
            if folder:
                folders.add(folder)

        return {"ok": True, "folders": sorted(folders)}

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
        # embed() yields a generator of vectors; take the first and return float32 ndarray
        vec_iter = self.embedder.embed([self._prefix + text])
        vec = next(iter(vec_iter))
        return np.asarray(vec, dtype=np.float32)
