# FolderMate

FolderMate is a local-first workspace for auditing messy folders and safely reorganizing
their contents. It combines a FastAPI backend, a lightweight semantic SQLite database,
and a suite of domain-specific PydanticAI agents that analyse files, plan folder
structures, and decide final destinations. The included single-page UI lets you scan a
source directory, review suggested moves, and apply changes with confidence.

## What it does

* Scans a source directory (recursively if desired) and records file metadata in a
  SQLite database with semantic embeddings for similarity search.
* Generates Markdown reports for each file via the **File Analysis Agent** so that
  language-model driven workflows can reference consistent summaries.
* Plans folder structures and grouping strategies using the **Organization Planner
  Agent**.
* Chooses final destinations for reviewed files using the **Organization Decider
  Agent**, preserving audit trails and notes.
* Exposes a REST API and static UI for configuring runs, reviewing analyses, selecting
  files to move, and triggering long-running actions such as scanning, planning, and
  moving files.

## Design decisions

* **Semantic store** – File metadata, analysis reports, and organization notes live in a
  single SQLite database extended with [`sqlite-vec`](https://github.com/asg017/sqlite-vec)
  and [`fastembed`](https://github.com/qdrant/fastembed) for fast local vector search. It
  keeps the deployment self-contained and auditable.
* **Config-as-JSON** – All runtime settings are loaded from `organizer.config.json`. This
  makes it easy to script changes, share presets, and bootstrap new environments without
  secrets in code.
* **Composable agents** – Each agent (analysis, planner, decider) exposes its tools via
  [PydanticAI](https://github.com/pydantic/pydantic-ai), enabling synchronous use from the
  API or external automations while keeping logging and usage limits consistent.
* **Explicit long-running state** – The FastAPI layer serialises actions (`scan`,
  `analyze`, `plan`, `decide`, `move`) so that only one runs at a time. This avoids race
  conditions when multiple operations compete for the same files or embeddings.
* **Static front-end** – The UI is served from `foldermate/static`, keeping deployment as
  simple as running `uvicorn` without extra build steps.

## Code organization

```
organizer/
├── agent_utils/                 # Shared utilities (vector DB, logging helpers)
├── file_analysis_agent/         # Markdown conversion tools and agent wrapper
├── file_organization_planner_agent/  # Planner agent plus helper tools
├── file_organization_decider_agent/  # Decider agent plus helper tools
├── foldermate/                  # FastAPI app and static SPA for orchestration
├── tests/                       # Pytest coverage for key flows
├── organizer.config.json        # Default runtime configuration
└── pyproject.toml               # Project metadata and Python dependencies
```

## Installation

FolderMate targets Python 3.12+.

```bash
python -m venv .venv
source .venv/bin/activate  # or .\.venv\Scripts\activate on Windows
pip install -e .
```

Optional extras:

* Document conversion for PDFs, Office formats, etc.: `pip install -e .[docling]`
* FolderMate UI and server stack: `pip install -e .[foldermate]` to add FastAPI,
  Uvicorn, and related web dependencies on top of the core agents.

## Windows quick start

Open **PowerShell** and install the complete FolderMate stack with the built-in Python
launcher:

```powershell
py -m pip install organizer[foldermate]
```

This brings in the FastAPI server, Uvicorn, and supporting packages alongside the agent
dependencies so the UI and automation tools are ready to run.

## Configuration

Runtime behaviour is controlled by `organizer.config.json`. Key sections include:

* **Top-level settings**
  * `db_path` – SQLite database file used by `AgentVectorDB`.
  * `base_dir` / `target_dir` – Source directory to audit and destination root for moves.
  * `instructions` – Free-form guidance for the planner/decider agents.
  * `recursive` – Whether scans traverse subdirectories.
  * `dont_delete` – Guard rail flag; when `true`, move operations avoid destructive
    deletes.
  * `embedding_model` – FastEmbed model identifier for vector search.
  * `search` and `sqlite` – Tunables for similarity search and SQLite pragmas.
  * `api_key` – Upstream LLM key shared with agents (leave blank for mock/testing).
* **Agent sections** (`file_analysis_agent`, `file_organization_planner_agent`,
  `file_organization_decider_agent`) – Model names, token limits, and other overrides
  passed directly to each agent wrapper.

Update the JSON manually or via `AgentVectorDB.save_config()` methods exposed through the
API. The FastAPI `/api/config` endpoints support reading and patching settings at runtime.

## Running FolderMate

1. Ensure `organizer.config.json` points at the folders you want to analyse and contains
   any agent instructions.
2. Start the API and static UI:

   ```bash
   uvicorn foldermate.app:app --reload
   ```

3. Open `http://127.0.0.1:8000/` to access the UI. From there you can:
   * Trigger scans to populate the database.
   * Launch analysis/planning/decision actions.
   * Review file reports, notes, and suggested destinations.
   * Select files and initiate move operations.

Automations can interact directly with the REST endpoints documented in
`foldermate/app.py` (e.g. `/api/actions/scan`, `/api/files/{id}/report`, `/api/stop`).

## Dependencies

Core dependencies (see `pyproject.toml` for exact versions):

* [`pydantic`](https://docs.pydantic.dev/) and [`pydantic-ai`](https://github.com/pydantic/pydantic-ai)
  for strongly-typed agent execution.
* [`tiktoken`](https://github.com/openai/tiktoken) for token-aware truncation.
* [`diskcache`](https://grantjenks.com/docs/diskcache/) for local cache management.
* [`sqlite-vec`](https://github.com/asg017/sqlite-vec), [`fastembed`](https://github.com/qdrant/fastembed),
  and `numpy` for semantic search.
* [`pysqlite3-binary`](https://github.com/coleifer/pysqlite3) to ensure SQLite extension
  support on platforms that need it.
* [`fastapi`](https://fastapi.tiangolo.com/) and [`uvicorn`](https://www.uvicorn.org/)
  for serving the API and UI.

## Testing

Run the automated checks with:

```bash
pytest
```

Linting is encouraged via `pylint`, targeting a score above 9.0 for touched modules.

