# File Organizer Agent

A PydanticAI-based assistant that helps plan how files should be organized.  The agent
builds on `AgentVectorDB` and provides tool functions for finding similar file reports,
recording organization notes and inspecting folder structures.

## Installation

```bash
pip install -e .
```

## Configuration

The underlying `AgentVectorDB` reads its settings from a JSON file.  By default the
tools look for `organizer.config.json` in the current working directory, but you can
point to another location with the `FILE_ORGANIZER_CONFIG` environment variable.

A minimal configuration looks like:

```json
{
  "db_path": "organizer.sqlite",
  "base_dir": "/absolute/path/to/files",
  "search": {"top_k": 10}
}
```

`reset_db` from `AgentVectorDB` will create the SQLite file and remember `base_dir`.

## Tools

The `file_organization_planner_agent.agent_tools.tools` module exposes a handful of
JSON‑friendly helper functions:

- `find_similar_file_reports(path, top_k=10)` – return file reports whose embeddings
  are close to `path`.
- `append_organization_notes(ids, notes)` – add free‑form notes to one or more file
  ids.
- `get_file_report(path)` – retrieve the stored report for `path`.
- `target_folder_tree()` – return a dictionary with the textual folder tree and
  an optional list of traversal errors.

These functions operate on a global `AgentVectorDB` instance. Most results follow
the pattern `{"ok": True, ...}` or contain an `"error"` field when something goes
wrong. `target_folder_tree` instead provides a `{"tree": ..., "errors": [...]}`
dictionary so that partial traversal issues can be reported.

## Pydantic agent

A ready‑made `pydantic_ai.Agent` wires the tools into a chat interface:

```python
from file_organization_planner_agent.agent import agent

agent.run("Use find_similar_file_reports('notes/todo.txt')")
agent.run("Show the folder tree for '.'")
```

The agent uses the `google-gla:gemini-1.5-flash` model and a system prompt geared
towards organising files.

## Testing

Run the tests for the planner tools with:

```bash
pytest tests/test_planner_tools.py
```

Running the full suite exercises all modules:

```bash
pytest
```

## Design notes

* Built on the lightweight `AgentVectorDB` for local, self-contained storage.
* Uses a single SQLite file and FastEmbed embeddings for semantic search.
* Tools return plain dictionaries so that other agents can easily consume the data.
