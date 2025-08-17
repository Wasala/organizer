# Agent Vector DB

`agent_utils/agent_vector_db.py` provides `AgentVectorDB`, a lightweight
SQLite-backed semantic database for organizing files. It stores metadata and
vector embeddings for file reports and organization notes using
[`sqlite-vec`](https://github.com/asg017/sqlite-vec) for similarity search and
[`fastembed`](https://github.com/Singularity-AI/fastembed) for embeddings.

## Features
- Single-file SQLite database with vector search.
- All public methods return JSON-style dictionaries, making integration with
  agents straightforward.
- Embedding-powered similarity search over `file_report` text.
- Helper methods for tracking organization notes and destinations.

See the docstrings and unit tests for usage examples.
