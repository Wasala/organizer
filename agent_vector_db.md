# Agent Vector DB

`AgentVectorDB` is a small, self‑contained SQLite database that stores file
metadata alongside vector embeddings.  It is designed for use in automation
agents that need to remember information about files and look up similar
documents later.  Everything lives in a single `.sqlite` file and all public
methods return simple JSON dictionaries, so beginners can experiment without
having to learn SQL.

## Installation

The database relies on a handful of Python packages.  Install the project in
editable mode to pull them in:

```bash
pip install -e .
```

If your Python cannot load SQLite extensions (common on macOS system Python)
install `pysqlite3-binary` as well.  The project already lists it as a
dependency but it can be installed separately if needed:

```bash
pip install pysqlite3-binary
```

## Getting Started

```python
from agent_utils.agent_vector_db import AgentVectorDB

# Create a database using the default configuration file (organizer.config.json)
db = AgentVectorDB()

# Prepare the database and set the base directory for your files
db.reset_db('/absolute/path/to/my/files')

# Insert a file relative to the base directory
db.insert('notes/todo.txt')

# Attach a short report about the file
db.set_file_report('notes/todo.txt', 'text from an OCR or manual summary')

# Add personal organisation notes
db.append_organization_notes([1], 'Remember to move this to /archive')

# Find similar reports using vector search
similar = db.find_similar_file_reports('notes/todo.txt')
print(similar)
```

The first run creates `organizer.config.json` in the current directory.  It
stores the path to the SQLite database, the base directory for files and tuning
parameters for the search engine.  You can edit this JSON file directly or call
`db.save_config()` with keyword overrides.

## Core Methods

| Method | Purpose |
| ------ | ------- |
| `reset_db(base_dir_abs)` | Create a fresh database and remember the absolute base directory. |
| `insert(path_from_base)` | Register a file path relative to the base directory. |
| `set_file_report(path, text)` | Store a block of descriptive text and index it for similarity search. |
| `append_organization_notes(ids, notes)` | Add notes for one or more file ids. |
| `set_planned_destination(path, dest)` / `set_final_destination(path, dest)` | Track where a file should go or ended up. |
| `find_similar_file_reports(path, top_k)` | Return paths with reports similar to the given file. |
| `get_next_path_missing_*()` | Helper methods that return the next file path lacking a particular field. |

All methods use defensive error handling and return dictionaries like
`{"ok": True, ...}` or `{"ok": False, "error": "message"}`.  This makes it
easy to feed results back into larger agent workflows without worrying about
exceptions.

## Design Decisions

* **SQLite everywhere** – Storing data in one local file keeps things portable
  and simple for small projects.
* **`sqlite-vec` for similarity search** – The `sqlite-vec` extension provides
  fast cosine similarity queries directly inside SQLite.
* **`fastembed` for embeddings** – Embeddings are generated with the
  lightweight `fastembed` library, avoiding the need for external services.
* **JSON friendly API** – Returning JSON-style dictionaries keeps the surface
  area easy to understand for novice developers and works well with LLM agents.

## Testing

Run the unit tests to verify that everything is wired up correctly:

```bash
pytest tests/test_agent_vector_db.py
```

The test suite creates a temporary database, inserts sample files and exercises
the main features.

