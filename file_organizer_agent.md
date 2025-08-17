# File Organizer Agent

This package provides a simple PydanticAI agent that helps plan how files should be organized.
It wraps a lightweight SQLite-based vector database from `agent_utils` and exposes a few
useful tools:

- `find_similar_file_reports(path, top_k=10)` – find semantically similar file reports.
- `append_organization_notes(ids, notes)` – append notes for one or more file ids.
- `get_file_report(path)` – fetch the stored file report for a path.
- `target_folder_tree(path)` – produce a textual folder tree for the given path.

The `agent.py` file illustrates how these tools can be connected to a `pydantic_ai.Agent`
for interactive use.
